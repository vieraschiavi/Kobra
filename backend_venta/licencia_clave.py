# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Clave pública con la que la app verifica una licencia comprada
=============================================================================
El bug que esto arregla: **un cliente pagaba y no podía entrar.**

Las licencias se firmaban con HS256, o sea con un secreto COMPARTIDO entre el
servidor de ventas y la copia instalada. El servidor tiene el suyo en una
variable de entorno de Vercel; la copia instalada lo busca en
`KOBRA_LICENSE_SECRET`, después en su configuración, y si no encuentra
ninguno **se genera uno al azar y lo guarda**.

El instalador de clientes se arma sin `edicion.json` (a propósito: es la demo
de 3 días), así que nunca recibía el secreto del servidor. Resultado: cada
máquina inventaba el suyo, y la licencia comprada fallaba con
`Signature verification failed`. El mensaje que veía el cliente era
"Licencia inválida — revisá que la copiaste completa", echándole la culpa a él
por un token perfectamente válido.

Por qué asimétrica y no repartir el secreto
--------------------------------------------
La solución obvia —meter `KOBRA_LICENSE_SECRET` en el build— funciona y es
peor: con HS256, la clave que verifica es la MISMA que firma. Un secreto
compartido dentro de un .exe que se descarga público se extrae con un editor
hexadecimal, y quien lo saque se emite las licencias que quiera. El negocio
entero es la licencia.

Con RS256 se separan: la privada firma y vive solo en el servidor de ventas;
la pública verifica y es esto de acá. **Publicarla no habilita nada** — es
para lo que existe. Y como no hay ningún secreto que inyectar, el instalador
deja de necesitar tratamiento especial: la clave viaja como código.

Va en un módulo Python y no en un `.pem` suelto porque así entra sola al
bundle de PyInstaller. Un archivo de datos hay que declararlo en el `.spec`, y
olvidarse de eso deja al programa sin poder validar nada — exactamente el
mismo tipo de falla silenciosa que vino a arreglar.

Para rotar el par: `python -m backend_venta.licencia_clave --nuevo-par`.
Imprime la privada (va a Vercel, en `KOBRA_LICENSE_PRIVATE_KEY`) y la pública
para pegar acá abajo.
"""
from __future__ import annotations

# Clave pública de firma de licencias. NO es secreta: solo permite verificar.
PUBLICA = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAq4Dh+dFXzUjGEeuU733J
r4ugVKMQbHTKhZcCA+Zy+DKLkITU5eL2aZIwTOVD+WpqtqIgNYLballDlOGS0WxV
9bjhLHIwFOYdLBmgPgRIImsJVWmFsEmt/5/X3TGfHKkdOaQh4IXQN4RnPWSn3gJp
2Lq7Z7xk50gMoiHYuulU6f5fPp+1UByC/iv23unuPbtLWe/vihCy8InDpBvii1M9
SxSeycLnMxB45IH1HPb++8KTmzuJz/DS2nk0txomyy6Lyj3sEPIzPpc9EINp+cUj
cc0/P8ODZ+fG5FK++AnhSowCALLGrXLd7WD8XRLy9XjvSV3egSWjTM5ieOJeQhTO
tQIDAQAB
-----END PUBLIC KEY-----
"""

ALGORITMO = "RS256"


def _nuevo_par() -> None:
    """Genera un par nuevo. La privada NO se guarda en ningún archivo del
    repositorio: se imprime una vez para pegarla en el servidor de ventas."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    privada = k.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode()
    publica = k.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    print("PRIVADA — va a Vercel en KOBRA_LICENSE_PRIVATE_KEY.")
    print("Nunca al repositorio. Rotarla invalida las licencias ya emitidas.\n")
    print(privada)
    print("PUBLICA — reemplazá con esto la constante PUBLICA de este archivo:\n")
    print(publica)


if __name__ == "__main__":
    import sys
    if "--nuevo-par" in sys.argv:
        _nuevo_par()
    else:
        print(__doc__)
