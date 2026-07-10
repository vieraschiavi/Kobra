"""
MV Kobra AI · Catálogo de países (LATAM)
=========================================
**Fase 1** (Uruguay, Argentina, México, Chile, Colombia, Perú): países
hispanohablantes donde el producto funciona tal cual está — mismo chatbot,
mismo copiloto de voz, mismo léxico de sentimiento en español. Lo único que
cambia por país es moneda/formato de número y feriados para la capa de
cumplimiento (`kobra.cumplimiento`).

**Fase 2** (Brasil): único país no hispanohablante del catálogo. A
diferencia de la Fase 1, acá SÍ cambia el idioma del producto:
  - `kobra.copiloto` tiene un léxico de sentimiento/técnicas de negociación
    en portugués brasileño (`idioma="pt"`), traducido y adaptado al contexto
    de cobranza — pero es traducción propia, no validada aún por un
    profesional de cobranza nativo de Brasil. Tratarlo como una primera
    versión, no como texto listo para producción sin revisión.
  - `kobra.ayuda` puede responder en portugués (modo IA siempre; modo docs
    solo para el contenido ya traducido, ver `docs/README_pt.md`).
  - La transcripción de audio (Whisper) usa `idioma="pt"` en vez de forzar
    español.
  - `nota_cumplimiento` de Brasil menciona la LGPD además del aviso general
    — ver `docs/GUIA_REGISTRO_LEGAL_BRASIL.md` (informativo, no asesoría
    legal).

> ⚠️ Los feriados de este módulo son fechas fijas (o derivadas de Pascua)
> públicas y verificables, no asesoría legal. Varios países de la región
> (Colombia, Chile, Perú, Brasil, entre otros) trasladan ciertos feriados
> al lunes siguiente ("leyes de traslado" / Ley Emiliani en Colombia) — esa
> regla NO está modelada acá. Los topes de horario/frecuencia de contacto
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

NOTA_CUMPLIMIENTO_BR = (
    NOTA_CUMPLIMIENTO_DEFAULT + " En Brasil sumá la LGPD (protección de "
    "datos) al análisis — ver docs/GUIA_REGISTRO_LEGAL_BRASIL.md."
)


@dataclass(frozen=True)
class Pais:
    codigo: str          # ISO 3166-1 alfa-2
    nombre: str
    moneda: str          # ISO 4217
    simbolo: str
    locale: str          # BCP 47, para Intl/toLocaleString
    idioma: str = "es"   # "es" | "pt" — idioma del producto para este país
    nota_cumplimiento: str = NOTA_CUMPLIMIENTO_DEFAULT


CATALOGO: dict[str, Pais] = {
    "UY": Pais("UY", "Uruguay", "UYU", "$U", "es-UY", "es",
               "Horarios y feriados validados para Uruguay (política por defecto)."),
    "AR": Pais("AR", "Argentina", "ARS", "$", "es-AR"),
    "MX": Pais("MX", "México", "MXN", "$", "es-MX"),
    "CL": Pais("CL", "Chile", "CLP", "$", "es-CL"),
    "CO": Pais("CO", "Colombia", "COP", "$", "es-CO"),
    "PE": Pais("PE", "Perú", "PEN", "S/", "es-PE"),
    "BR": Pais("BR", "Brasil", "BRL", "R$", "pt-BR", "pt", NOTA_CUMPLIMIENTO_BR),
}

PAIS_DEFAULT = "UY"


def obtener(codigo: str | None) -> Pais:
    """País del catálogo, o Uruguay si el código no existe/está vacío."""
    return CATALOGO.get((codigo or "").upper(), CATALOGO[PAIS_DEFAULT])


def listar() -> list[dict]:
    """Catálogo completo, serializable, en el orden de despliegue (Fase 1 + Fase 2)."""
    orden = ["UY", "AR", "MX", "CL", "CO", "PE", "BR"]
    return [dict(codigo=p.codigo, nombre=p.nombre, moneda=p.moneda,
                 simbolo=p.simbolo, locale=p.locale, idioma=p.idioma,
                 nota_cumplimiento=p.nota_cumplimiento)
            for p in (CATALOGO[c] for c in orden)]
