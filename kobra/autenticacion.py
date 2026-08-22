# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Autenticación y roles del dashboard (Streamlit)
========================================================
El dashboard corre local (`streamlit run app/app.py`, `localhost:8501`), pero
puede terminar accesible en una red compartida o en un servidor — y muestra
datos financieros de deudores. Este módulo agrega:

  - **Login obligatorio** la primera vez que se usa el dashboard (setup de
    contraseña de administrador), y en cada sesión nueva de Streamlit después.
  - **Dos roles**: `admin` (todo, incluida la pestaña Configuración/API keys)
    y `gestor` (operación diaria, sin acceso a Configuración).

Las contraseñas nunca se guardan en texto plano: se persisten como
`hash + salt` (PBKDF2-HMAC-SHA256, 200.000 iteraciones) usando el mismo
backend seguro de `kobra/config.py` (keyring del SO > archivo cifrado >
texto plano como último recurso).

Para desarrollo/CI (correr el dashboard sin login interactivo), se puede
saltear explícitamente con la variable de entorno `KOBRA_DASHBOARD_SIN_LOGIN=1`
— pensado para pipelines/tests, no para uso normal.

**SSO corporativo (OIDC)**: si se configura un proveedor de identidad en la
pestaña Configuración (Azure AD/Entra ID, Okta, Google Workspace, etc.), se
suma un botón "Iniciar sesión con SSO" — ver `kobra/sso_oidc.py`. No
reemplaza el login local (sigue disponible como alternativa/respaldo);
convive con él.
"""
from __future__ import annotations

import hashlib
import os
import secrets

from kobra import auditoria as kauditoria
from kobra import config as kconfig
from kobra import sso_oidc

ROLES = ("admin", "gestor")
_ITERACIONES = 200_000
_SESSION_KEY = "kobra_auth_rol"


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERACIONES).hex()


# Empresa por defecto: la instalación de un solo cliente (escritorio) y la
# copia del dueño. Sus credenciales usan las claves SIN prefijo, que son las
# que ya existen en toda instalación hecha hasta hoy.
EMPRESA_DEFAULT = "principal"


def _clave(rol: str, empresa: str, campo: str) -> str:
    """Nombre de la clave de configuración donde vive la credencial.

    La contraseña se guardaba SOLO por rol (`AUTH_ADMIN_HASH`), compartida por
    todas las empresas del despliegue. Como el login además tomaba el nombre de
    empresa del cuerpo del pedido, cualquier cliente entraba a los datos de
    otro mandando el nombre del vecino con su propia contraseña. Verificado:
    con la clave del cliente A y `empresa: "clienteB"` se leía la cartera de B.

    Ahora la credencial es de la empresa. `principal` conserva las claves sin
    prefijo para no dejar afuera a ninguna instalación existente.
    """
    assert rol in ROLES, f"rol inválido: {rol}"
    emp = (empresa or EMPRESA_DEFAULT).strip().lower()
    if emp == EMPRESA_DEFAULT:
        return f"AUTH_{rol.upper()}_{campo}"
    # El nombre de empresa entra en el nombre de una clave de configuración:
    # se normaliza para que no pueda inventar otra clave ni pisar la de otro.
    seguro = "".join(c if c.isalnum() else "_" for c in emp)[:40].upper()
    return f"AUTH_T_{seguro}_{rol.upper()}_{campo}"


def establecer_password(rol: str, password: str,
                        empresa: str = EMPRESA_DEFAULT) -> None:
    """Genera un salt nuevo y guarda hash+salt para ese rol EN esa empresa."""
    salt = secrets.token_bytes(16)
    kconfig.guardar_extra(_clave(rol, empresa, "SALT"), salt.hex())
    kconfig.guardar_extra(_clave(rol, empresa, "HASH"), _hash(password, salt))


def tiene_password(rol: str, empresa: str = EMPRESA_DEFAULT) -> bool:
    return bool(kconfig.leer_extra(_clave(rol, empresa, "HASH")))


def verificar_password(rol: str, password: str,
                       empresa: str = EMPRESA_DEFAULT) -> bool:
    """¿Es esa la contraseña de ese rol EN esa empresa?

    La empresa no es decorativa: es la mitad de la identidad. Sin ella, la
    contraseña de un cliente abre la puerta de cualquier otro.
    """
    salt_hex = kconfig.leer_extra(_clave(rol, empresa, "SALT"))
    hash_guardado = kconfig.leer_extra(_clave(rol, empresa, "HASH"))
    if not salt_hex or not hash_guardado:
        return False
    return secrets.compare_digest(_hash(password, bytes.fromhex(salt_hex)), hash_guardado)


def login(password: str, empresa: str = EMPRESA_DEFAULT) -> str | None:
    """Prueba la contraseña contra admin y gestor; devuelve el rol o None."""
    for rol in ROLES:
        if tiene_password(rol, empresa) and verificar_password(rol, password, empresa):
            return rol
    return None


def configurado() -> bool:
    """¿Ya se configuró al menos la contraseña de admin (setup inicial hecho)?"""
    return tiene_password("admin")


def sesion_activa() -> str | None:
    """Rol logueado en esta sesión de Streamlit, si lo hay."""
    import streamlit as st
    return st.session_state.get(_SESSION_KEY)


def cerrar_sesion() -> None:
    import streamlit as st
    rol = st.session_state.get(_SESSION_KEY)
    st.session_state.pop(_SESSION_KEY, None)
    kauditoria.registrar("logout", {}, rol=rol or "desconocido")


def requiere_login() -> bool:
    """False solo si se saltea explícitamente para dev/CI."""
    return os.environ.get("KOBRA_DASHBOARD_SIN_LOGIN", "").strip() != "1"


def _procesar_callback_sso(st) -> bool:
    """Si volvimos de la redirección del proveedor (?code=...&state=...),
    procesa el login SSO. Devuelve True si consumió el callback (haya
    funcionado o no) — el caller debe limpiar los query params y parar."""
    qp = st.query_params
    if "code" not in qp or "state" not in qp:
        return False
    try:
        resultado = sso_oidc.procesar_callback(qp["code"], qp["state"], st.session_state)
        st.session_state[_SESSION_KEY] = resultado["rol"]
        kauditoria.registrar("login_sso_ok", {"email": resultado["email"]},
                             usuario=resultado["email"], rol=resultado["rol"])
    except sso_oidc.CallbackError as e:
        st.session_state["kobra_sso_error"] = str(e)
        kauditoria.registrar("login_sso_fallido", {"error": str(e)}, rol="desconocido")
    st.query_params.clear()
    st.rerun()
    return True  # no se alcanza (st.rerun corta acá), queda por claridad


def _boton_sso(st) -> None:
    if not sso_oidc.configurado():
        return
    url = sso_oidc.url_autorizacion(st.session_state)
    if url:
        st.link_button("🏢 Iniciar sesión con SSO corporativo", url,
                       type="primary", use_container_width=True)
    error = st.session_state.pop("kobra_sso_error", None)
    if error:
        st.error(f"SSO: {error}")


def render_gate() -> str | None:
    """
    Renderiza el flujo de login/setup en Streamlit. Devuelve el rol activo si
    ya se puede mostrar el dashboard, o None si hay que detener la ejecución
    (el caller debe hacer `st.stop()` cuando esto devuelve None).
    """
    import streamlit as st

    if not requiere_login():
        return "admin"

    # Edición del dueño: entra directo, sin contraseña. La app de escritorio
    # ya se comportaba así (`/api/licencia/owner-login`), pero el dashboard
    # seguía pidiendo crear una clave — o sea, la MISMA copia owner abierta
    # por una vía u otra hacía cosas distintas. El sello `edicion.json` es lo
    # que la marca como owner; ver kobra/edicion.py.
    try:
        from kobra import edicion as kedicion
        if kedicion.vigencia().get("owner"):
            return "admin"
    except Exception:
        pass

    rol = sesion_activa()
    if rol:
        return rol

    if _procesar_callback_sso(st):
        return None

    hay_sso = sso_oidc.configurado()

    if not configurado() and not hay_sso:
        st.title("🔒 Configurar acceso a MV Kobra AI")
        st.info("Primer uso: definí una contraseña de administrador antes de entrar. "
                 "Se guarda cifrada (nunca en texto plano) — ver detalle en la pestaña "
                 "Configuración una vez adentro. (Si tu empresa usa SSO corporativo, "
                 "configuralo primero en esa misma pestaña y salteá este paso.)")
        with st.form("form_setup_auth"):
            p1 = st.text_input("Contraseña de administrador", type="password")
            p2 = st.text_input("Repetila", type="password")
            ok = st.form_submit_button("Crear y entrar", type="primary")
        if ok:
            if len(p1) < 6:
                st.error("Mínimo 6 caracteres.")
            elif p1 != p2:
                st.error("Las contraseñas no coinciden.")
            else:
                establecer_password("admin", p1)
                st.session_state[_SESSION_KEY] = "admin"
                kauditoria.registrar("auth_setup_inicial", {"rol": "admin"},
                                     rol="admin")
                st.rerun()
        return None

    st.title("🔒 MV Kobra AI · Iniciar sesión")
    if hay_sso:
        _boton_sso(st)
        if configurado():
            st.markdown("— o con contraseña local —")
    if configurado():
        with st.form("form_login"):
            password = st.text_input("Contraseña", type="password")
            ok = st.form_submit_button("Entrar", type="primary")
        if ok:
            rol = login(password)
            if rol:
                st.session_state[_SESSION_KEY] = rol
                kauditoria.registrar("login_ok", {}, rol=rol)
                st.rerun()
            else:
                kauditoria.registrar("login_fallido", {}, rol="desconocido")
                st.error("Contraseña incorrecta.")
    return None
