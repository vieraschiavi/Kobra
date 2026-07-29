"""
MV Kobra AI · Licencia que muestra el instalador de Windows
============================================================
El asistente de instalación no mostraba ninguna licencia. Para un programa que
se cobra, la pantalla de términos no es decorativa: es donde el cliente acepta
el EULA, y su ausencia es de las cosas que más rápido delatan que un instalador
no es de un producto comercial.

electron-builder toma `build/license_<idioma>.txt` según el idioma que el
cliente elija en el asistente, así que se escribe uno por idioma soportado.

El texto castellano es el mismo EULA que ya viajaba en el paquete de producción
(`build_release.LICENCIA_PROD`): una sola fuente, para que el instalador y el
ZIP no puedan decir cosas distintas. Las traducciones acompañan.

Como el original, son un **borrador comercial**: hay que pasarlas por asesoría
legal antes de vender con ellas.

Uso:
    python3 packaging/licencias_instalador.py
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "electron", "build")

IDIOMAS = ("es", "pt", "en")


def _es() -> str:
    """El EULA castellano sale de build_release, que ya lo tenía."""
    import importlib.util
    ruta = os.path.join(ROOT, "packaging", "build_release.py")
    spec = importlib.util.spec_from_file_location("_br_lic", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.LICENCIA_PROD


def _version() -> str:
    import importlib.util
    ruta = os.path.join(ROOT, "packaging", "build_release.py")
    spec = importlib.util.spec_from_file_location("_br_ver", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.VERSION


def _pt(version: str) -> str:
    return f"""MV KOBRA AI · CONTRATO DE LICENÇA DE USO (EULA) · v{version}
========================================================

1. OBJETO. O titular da MV Kobra AI concede ao cliente uma licença de uso, não
   exclusiva e intransferível, do software MV Kobra AI (Plataforma de Cobrança
   Inteligente) para uso interno, conforme a proposta comercial acordada.
2. PROPRIEDADE. O software, seu código, design e documentação são propriedade
   do titular. Esta licença não transfere titularidade alguma.
3. DADOS. O cliente é responsável pelos dados que carregar (incl. a LGPD,
   Lei 13.709/2018, no Brasil). O pacote é distribuído com dados sintéticos,
   sem informação pessoal real.
4. ALCANCE HONESTO. As métricas da demonstração são ilustrativas da
   metodologia. O desempenho real (modelo e impacto) é medido durante o
   piloto/implantação com dados do cliente.
5. RESTRIÇÕES. Proibida a redistribuição, sublicenciamento, engenharia
   reversa e remoção de avisos de titularidade.
6. GARANTIA E RESPONSABILIDADE. Salvo acordo escrito, o software é entregue
   "COMO ESTÁ"; a responsabilidade total fica limitada ao valor pago pela
   licença nos últimos 12 meses.
7. LEI APLICÁVEL. República Oriental do Uruguai.

(Minuta comercial: revisar e completar com assessoria jurídica antes de assinar.)
"""


def _en(version: str) -> str:
    return f"""MV KOBRA AI · SOFTWARE LICENCE AGREEMENT (EULA) · v{version}
========================================================

1. GRANT. The owner of MV Kobra AI grants the customer a non-exclusive,
   non-transferable licence to use the MV Kobra AI software (Smart Collections
   Platform) for internal purposes, as set out in the agreed commercial offer.
2. OWNERSHIP. The software, its code, design and documentation belong to the
   owner. This licence transfers no ownership.
3. DATA. The customer is responsible for the data it loads, including
   compliance with applicable data-protection law (Uruguay: Act 18.331;
   Brazil: LGPD). The package ships with synthetic data and no real personal
   information.
4. HONEST SCOPE. The demo metrics illustrate the methodology. Real performance
   (model and business impact) is measured during the pilot or rollout with
   the customer's own data.
5. RESTRICTIONS. Redistribution, sublicensing, reverse engineering and removal
   of ownership notices are prohibited.
6. WARRANTY AND LIABILITY. Unless otherwise agreed in writing, the software is
   provided "AS IS"; total liability is limited to the licence fees paid over
   the previous 12 months.
7. GOVERNING LAW. Oriental Republic of Uruguay.

(Commercial draft: have it reviewed and completed by legal counsel before
signing.)
"""


def textos() -> dict[str, str]:
    v = _version()
    return {"es": _es(), "pt": _pt(v), "en": _en(v)}


def generar(destino: str | None = None) -> dict[str, str]:
    """Escribe `license_<idioma>.txt` en `electron/build/`.

    En CRLF y con BOM: el visor de licencia de NSIS es un control RichEdit de
    Windows; con saltos de línea de Unix muestra todo el texto en un solo
    renglón y sin BOM se come los acentos."""
    destino = destino or BUILD
    os.makedirs(destino, exist_ok=True)
    salida = {}
    for idioma, texto in textos().items():
        ruta = os.path.join(destino, f"license_{idioma}.txt")
        with open(ruta, "w", encoding="utf-8-sig", newline="\r\n") as f:
            f.write(texto)
        salida[idioma] = ruta
    return salida


if __name__ == "__main__":
    for idioma, ruta in generar().items():
        print(f"[OK] {idioma}  {os.path.getsize(ruta):>5d} B  "
              f"{os.path.relpath(ruta, ROOT)}")
