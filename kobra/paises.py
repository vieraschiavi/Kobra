"""
MV Kobra AI · Catálogo de países (Fase 1 LATAM)
================================================
Fase 1 de expansión regional: países hispanohablantes donde el producto
funciona tal cual está (mismo chatbot, mismo copiloto de voz, mismo léxico
de sentimiento en español) — no hace falta traducir nada. Lo único que
cambia por país es moneda/formato de número y feriados para la capa de
cumplimiento (`kobra.cumplimiento`).

Brasil/portugués queda fuera a propósito: el léxico de sentimiento del
copiloto y el corpus del asistente están a mano en español y requieren
traducción + validación con un experto local antes de ofrecerse — ver
docs/KOBRA_2_0.md.

> ⚠️ Los feriados de este módulo son fechas fijas (o derivadas de Pascua)
> públicas y verificables, no asesoría legal. Varios países de la región
> (Colombia, Chile, Perú, entre otros) trasladan ciertos feriados al lunes
> siguiente ("leyes de traslado" / Ley Emiliani en Colombia) — esa regla
> NO está modelada acá. Los topes de horario/frecuencia de contacto
> (`kobra.cumplimiento.PoliticaContacto`) vienen con los valores de Uruguay
> por defecto para todo país: hay que confirmarlos con asesoría legal local
> antes de operar una cartera real fuera de Uruguay.
"""
from __future__ import annotations

from dataclasses import dataclass

NOTA_CUMPLIMIENTO_DEFAULT = (
    "Los horarios y topes de contacto muestran los valores de Uruguay por "
    "defecto. Confirmalos con asesoría legal local antes de operar una "
    "cartera real en este país."
)


@dataclass(frozen=True)
class Pais:
    codigo: str          # ISO 3166-1 alfa-2
    nombre: str
    moneda: str          # ISO 4217
    simbolo: str
    locale: str          # BCP 47, para Intl/toLocaleString
    nota_cumplimiento: str = NOTA_CUMPLIMIENTO_DEFAULT


CATALOGO: dict[str, Pais] = {
    "UY": Pais("UY", "Uruguay", "UYU", "$U", "es-UY",
               "Horarios y feriados validados para Uruguay (política por defecto)."),
    "AR": Pais("AR", "Argentina", "ARS", "$", "es-AR"),
    "MX": Pais("MX", "México", "MXN", "$", "es-MX"),
    "CL": Pais("CL", "Chile", "CLP", "$", "es-CL"),
    "CO": Pais("CO", "Colombia", "COP", "$", "es-CO"),
    "PE": Pais("PE", "Perú", "PEN", "S/", "es-PE"),
}

PAIS_DEFAULT = "UY"


def obtener(codigo: str | None) -> Pais:
    """País del catálogo, o Uruguay si el código no existe/está vacío."""
    return CATALOGO.get((codigo or "").upper(), CATALOGO[PAIS_DEFAULT])


def listar() -> list[dict]:
    """Catálogo completo, serializable, en el orden de despliegue de Fase 1."""
    orden = ["UY", "AR", "MX", "CL", "CO", "PE"]
    return [dict(codigo=p.codigo, nombre=p.nombre, moneda=p.moneda,
                 simbolo=p.simbolo, locale=p.locale,
                 nota_cumplimiento=p.nota_cumplimiento)
            for p in (CATALOGO[c] for c in orden)]
