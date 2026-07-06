"""
Kobra · Autenticación y roles del dashboard (Streamlit)
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
"""
from __future__ import annotations

import hashlib
import os
import secrets

from kobra import auditoria as kauditoria
from kobra import config as kconfig

ROLES = ("admin", "gestor")
_ITERACIONES = 200_000
_SESSION_KEY = "kobra_auth_rol"


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERACIONES).hex()


def establecer_password(rol: str, password: str) -> None:
    """Genera un salt nuevo y guarda hash+salt para el rol dado."""
    assert rol in ROLES, f"rol inválido: {rol}"
    salt = secrets.token_bytes(16)
    kconfig.guardar_extra(f"AUTH_{rol.upper()}_SALT", salt.hex())
    kconfig.guardar_extra(f"AUTH_{rol.upper()}_HASH", _hash(password, salt))


def tiene_password(rol: str) -> bool:
    return bool(kconfig.leer_extra(f"AUTH_{rol.upper()}_HASH"))


def verificar_password(rol: str, password: str) -> bool:
    salt_hex = kconfig.leer_extra(f"AUTH_{rol.upper()}_SALT")
    hash_guardado = kconfig.leer_extra(f"AUTH_{rol.upper()}_HASH")
    if not salt_hex or not hash_guardado:
        return False
    return secrets.compare_digest(_hash(password, bytes.fromhex(salt_hex)), hash_guardado)


def login(password: str) -> str | None:
    """Prueba la contraseña contra admin y gestor; devuelve el rol o None."""
    for rol in ROLES:
        if tiene_password(rol) and verificar_password(rol, password):
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


def render_gate() -> str | None:
    """
    Renderiza el flujo de login/setup en Streamlit. Devuelve el rol activo si
    ya se puede mostrar el dashboard, o None si hay que detener la ejecución
    (el caller debe hacer `st.stop()` cuando esto devuelve None).
    """
    import streamlit as st

    if not requiere_login():
        return "admin"

    rol = sesion_activa()
    if rol:
        return rol

    if not configurado():
        st.title("🔒 Configurar acceso a Kobra IA")
        st.info("Primer uso: definí una contraseña de administrador antes de entrar. "
                 "Se guarda cifrada (nunca en texto plano) — ver detalle en la pestaña "
                 "Configuración una vez adentro.")
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

    st.title("🔒 Kobra IA · Iniciar sesión")
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
