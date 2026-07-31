"""
MV Kobra AI · Cumplimiento normativo (contact governance)
======================================================
Capa de gobierno que decide **cuándo** y **cómo** se puede contactar a un
deudor, para que la cobranza —humana o del Gestor IA— opere dentro de la ley
y las buenas prácticas:

  - **Horario permitido**: evita contactos fuera de la franja legal, en días
    no hábiles o feriados.
  - **Tope de frecuencia** por deudor (anti-hostigamiento): máximo de contactos
    por día y por semana.
  - **Lista "No contactar" / opt-out**: si el deudor pidió no ser contactado
    (o hubo negativa dura), queda registrado y no se lo vuelve a llamar.
  - **Canales permitidos** por política.

Viene configurado para **Uruguay** por defecto (feriados nacionales, franja
09–20 L–S) pero es 100 % parametrizable por empresa/país. Es exactamente la
capa que un banco / financiera / cooperativa exige antes de dejar que un bot
llame a su cartera.

> ⚠️ Es una **herramienta de apoyo al cumplimiento, no asesoría legal**. Cada
> empresa fija su política según su marco regulatorio, contratos y el criterio
> de su asesoría jurídica. MV Kobra AI provee el mecanismo para hacerla cumplir.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NO_CONTACTAR_CSV = os.path.join(ROOT, "data", "no_contactar.csv")
DNC_COLS = ["id_deudor", "canal", "motivo", "fecha"]


# ---------------------------------------------------------------------------
# Feriados de Uruguay (fijos + movibles derivados de Pascua)
# ---------------------------------------------------------------------------
_FERIADOS_FIJOS = {
    (1, 1): "Año Nuevo",
    (1, 6): "Día de los Niños (Reyes)",
    (5, 1): "Día de los Trabajadores",
    (5, 18): "Batalla de Las Piedras",
    (6, 19): "Natalicio de Artigas",
    (7, 18): "Jura de la Constitución",
    (8, 25): "Declaratoria de la Independencia",
    (10, 12): "Día de la Diversidad Cultural",
    (11, 2): "Día de los Difuntos",
    (12, 25): "Navidad / Día de la Familia",
}


def _pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo de Meeus/Jones/Butcher, gregoriano)."""
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    # `l` es el nombre de la variable en el algoritmo de Gauss publicado
    # (a, b, c, d, e, g, h, i, k, l, m). Renombrarla haria mas dificil
    # cotejar esta funcion contra la formula de referencia, que es la unica
    # forma razonable de auditar un calculo de Pascua.
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(anio, mes, dia + 1)


def feriados_uruguay(anio: int) -> dict[date, str]:
    """Feriados nacionales de Uruguay para el año dado (fijos + Semana de
    Turismo). Los feriados movibles se derivan de Pascua."""
    fer = {date(anio, m, d): nombre for (m, d), nombre in _FERIADOS_FIJOS.items()}
    pascua = _pascua(anio)
    # Carnaval (lunes y martes previos al Miércoles de Ceniza = Pascua-48/-47)
    fer[pascua - timedelta(days=48)] = "Carnaval (lunes)"
    fer[pascua - timedelta(days=47)] = "Carnaval (martes)"
    # Semana de Turismo: Jueves y Viernes Santo (Pascua-3 / Pascua-2)
    fer[pascua - timedelta(days=3)] = "Jueves de Turismo"
    fer[pascua - timedelta(days=2)] = "Viernes de Turismo"
    return fer


# ---------------------------------------------------------------------------
# Feriados nacionales — Fase 1 LATAM (fechas fijas y derivadas de Pascua)
# ---------------------------------------------------------------------------
# Solo fechas fijas + Semana Santa. Varios países trasladan ciertos feriados
# al lunes siguiente (p. ej. la Ley Emiliani en Colombia) — esa regla NO está
# modelada acá; ver el disclaimer en kobra/paises.py.
_FERIADOS_FIJOS_POR_PAIS = {
    "AR": {
        (1, 1): "Año Nuevo", (3, 24): "Día de la Memoria",
        (4, 2): "Día del Veterano y de los Caídos en Malvinas",
        (5, 1): "Día del Trabajador", (5, 25): "Día de la Revolución de Mayo",
        (6, 20): "Día de la Bandera", (7, 9): "Día de la Independencia",
        (10, 12): "Día del Respeto a la Diversidad Cultural",
        (11, 20): "Día de la Soberanía Nacional",
        (12, 8): "Inmaculada Concepción", (12, 25): "Navidad",
    },
    "MX": {
        (1, 1): "Año Nuevo", (5, 1): "Día del Trabajo",
        (9, 16): "Día de la Independencia", (11, 20): "Revolución Mexicana",
        (12, 25): "Navidad",
    },
    "CL": {
        (1, 1): "Año Nuevo", (5, 1): "Día del Trabajo",
        (5, 21): "Día de las Glorias Navales", (6, 29): "San Pedro y San Pablo",
        (7, 16): "Virgen del Carmen", (8, 15): "Asunción de la Virgen",
        (9, 18): "Independencia Nacional", (9, 19): "Glorias del Ejército",
        (10, 12): "Encuentro de Dos Mundos",
        (10, 31): "Día de las Iglesias Evangélicas y Protestantes",
        (11, 1): "Día de Todos los Santos", (12, 8): "Inmaculada Concepción",
        (12, 25): "Navidad",
    },
    "CO": {
        (1, 1): "Año Nuevo", (5, 1): "Día del Trabajo",
        (6, 29): "San Pedro y San Pablo", (7, 20): "Día de la Independencia",
        (8, 7): "Batalla de Boyacá", (8, 15): "Asunción de la Virgen",
        (10, 12): "Día de la Raza", (11, 1): "Todos los Santos",
        (11, 11): "Independencia de Cartagena",
        (12, 8): "Inmaculada Concepción", (12, 25): "Navidad",
    },
    "PE": {
        (1, 1): "Año Nuevo", (5, 1): "Día del Trabajo",
        (6, 29): "San Pedro y San Pablo", (7, 28): "Independencia",
        (7, 29): "Fiestas Patrias", (8, 30): "Santa Rosa de Lima",
        (10, 8): "Combate de Angamos", (11, 1): "Todos los Santos",
        (12, 8): "Inmaculada Concepción", (12, 25): "Navidad",
    },
    # Brasil (Fase 2) — feriados nacionais fixos (não inclui pontos
    # facultativos nem feriados estaduais/municipais, p. ex. Corpus Christi).
    "BR": {
        (1, 1): "Confraternização Universal", (4, 21): "Tiradentes",
        (5, 1): "Dia do Trabalho", (9, 7): "Independência do Brasil",
        (10, 12): "Nossa Senhora Aparecida", (11, 2): "Finados",
        (11, 15): "Proclamação da República",
        (11, 20): "Dia Nacional de Zumbi e da Consciência Negra",
        (12, 25): "Natal",
    },
}


def feriados_por_pais(pais: str, anio: int) -> dict[date, str]:
    """Feriados nacionales para el país dado (ISO alfa-2). Uruguay usa el
    calendario completo de `feriados_uruguay`; el resto de la Fase 1 LATAM
    usa fechas fijas + Semana Santa derivada de Pascua (ver disclaimer)."""
    if (pais or "UY").upper() == "UY":
        return feriados_uruguay(anio)
    fijos = _FERIADOS_FIJOS_POR_PAIS.get(pais.upper())
    if fijos is None:
        return feriados_uruguay(anio)
    fer = {date(anio, m, d): nombre for (m, d), nombre in fijos.items()}
    pascua = _pascua(anio)
    if pais.upper() == "BR":
        fer[pascua - timedelta(days=3)] = "Quinta-feira Santa"
        fer[pascua - timedelta(days=2)] = "Sexta-feira Santa"
    else:
        fer[pascua - timedelta(days=3)] = "Jueves Santo"
        fer[pascua - timedelta(days=2)] = "Viernes Santo"
    return fer


# ---------------------------------------------------------------------------
# Política de contacto
# ---------------------------------------------------------------------------
@dataclass
class PoliticaContacto:
    hora_inicio: int = 9            # primera hora permitida (incluida)
    hora_fin: int = 20             # primera hora NO permitida (20:00 en adelante bloqueado)
    dias_habiles: tuple = (0, 1, 2, 3, 4, 5)   # 0=lunes … 5=sábado (domingo excluido)
    permitir_feriados: bool = False
    pais: str = "UY"
    max_por_dia: int = 1
    max_por_semana: int = 3
    canales: tuple = ("Llamada", "WhatsApp", "SMS", "Email")

    def en_horario(self, ahora: datetime) -> bool:
        return self.hora_inicio <= ahora.hour < self.hora_fin


@dataclass
class Decision:
    permitido: bool
    codigo: str        # OK | FUERA_HORARIO | DIA_NO_HABIL | FERIADO | OPT_OUT | TOPE_DIARIO | TOPE_SEMANAL | CANAL_NO_PERMITIDO
    motivo: str
    detalle: dict = field(default_factory=dict)

    def __bool__(self):
        return self.permitido


# ---------------------------------------------------------------------------
# Lista "No contactar" / opt-out
# ---------------------------------------------------------------------------
PEDIDO_NO_CONTACTAR = re.compile(
    r"\b(no me (llam|contact|molest|escrib)\w*|no (vuelvan? a|quiero que) (llam|contact|molest)\w*|"
    r"dej[ae]n? de (llamar|molestar|contactar)|sac[ae]nme de (la lista|sus registros)|"
    r"no insist\w+|borren mis datos|no quiero (que me llamen|ser contactad\w+))\b",
    re.IGNORECASE)


def es_pedido_no_contactar(texto: str) -> bool:
    """Detecta si el cliente pidió explícitamente no ser contactado."""
    return bool(PEDIDO_NO_CONTACTAR.search(texto or ""))


def registrar_no_contactar(id_deudor: str, canal: str = "todos",
                           motivo: str = "", fecha: str | None = None,
                           archivo: str = NO_CONTACTAR_CSV) -> dict:
    """Agrega (o refuerza) al deudor en la lista de no contactar."""
    fila = {"id_deudor": id_deudor, "canal": canal,
            "motivo": motivo or "solicitud del deudor",
            "fecha": fecha or datetime.now().strftime("%Y-%m-%d")}
    os.makedirs(os.path.dirname(archivo), exist_ok=True)
    nueva = pd.DataFrame([fila], columns=DNC_COLS)
    nueva.to_csv(archivo, mode="a", index=False, header=not os.path.exists(archivo))
    return fila


def esta_en_no_contactar(id_deudor: str, canal: str = "todos",
                         archivo: str = NO_CONTACTAR_CSV) -> bool:
    """True si el deudor está en la lista para ese canal (o para 'todos')."""
    if not os.path.exists(archivo):
        return False
    try:
        df = pd.read_csv(archivo, dtype=str)
    except Exception:
        return False
    if df.empty:
        return False
    m = df["id_deudor"].astype(str) == str(id_deudor)
    if not m.any():
        return False
    canales = set(df.loc[m, "canal"].astype(str))
    return "todos" in canales or canal in canales


# ---------------------------------------------------------------------------
# Decisión de contacto
# ---------------------------------------------------------------------------
def _contactos_en_ventana(contactos_previos, desde: datetime) -> int:
    return sum(1 for c in (contactos_previos or []) if c >= desde)


def puede_contactar(id_deudor: str, canal: str = "Llamada",
                    ahora: datetime | None = None,
                    contactos_previos: list | None = None,
                    politica: PoliticaContacto | None = None,
                    archivo_dnc: str = NO_CONTACTAR_CSV) -> Decision:
    """
    Decide si en este momento se puede contactar al deudor por este canal.

    - `ahora`: momento del contacto (default: ahora).
    - `contactos_previos`: lista de datetimes de contactos anteriores al mismo
      deudor (para aplicar los topes de frecuencia). Vacío = sin contactos.
    - `politica`: `PoliticaContacto` (default: Uruguay 09–20 L–S).
    """
    pol = politica or PoliticaContacto()
    ahora = ahora or datetime.now()

    if canal not in pol.canales:
        return Decision(False, "CANAL_NO_PERMITIDO",
                        f"El canal {canal} no está habilitado por la política.")

    if esta_en_no_contactar(id_deudor, canal, archivo_dnc):
        return Decision(False, "OPT_OUT",
                        "El deudor está en la lista de No Contactar (opt-out).")

    fecha = ahora.date()
    if not pol.permitir_feriados:
        fer = feriados_por_pais(pol.pais, fecha.year)
        if fecha in fer:
            return Decision(False, "FERIADO",
                            f"Feriado en {pol.pais}: {fer[fecha]}.",
                            {"feriado": fer[fecha]})

    if ahora.weekday() not in pol.dias_habiles:
        return Decision(False, "DIA_NO_HABIL",
                        "Día no hábil para contacto según la política (p. ej. domingo).")

    if not pol.en_horario(ahora):
        return Decision(False, "FUERA_HORARIO",
                        f"Fuera de la franja permitida "
                        f"({pol.hora_inicio:02d}:00–{pol.hora_fin:02d}:00).",
                        {"hora": ahora.hour})

    hoy_desde = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    n_dia = _contactos_en_ventana(contactos_previos, hoy_desde)
    if n_dia >= pol.max_por_dia:
        return Decision(False, "TOPE_DIARIO",
                        f"Se alcanzó el tope de {pol.max_por_dia} contacto(s) por día.",
                        {"contactos_hoy": n_dia})

    semana_desde = ahora - timedelta(days=7)
    n_sem = _contactos_en_ventana(contactos_previos, semana_desde)
    if n_sem >= pol.max_por_semana:
        return Decision(False, "TOPE_SEMANAL",
                        f"Se alcanzó el tope de {pol.max_por_semana} contactos "
                        f"en 7 días (anti-hostigamiento).",
                        {"contactos_semana": n_sem})

    return Decision(True, "OK", "Contacto permitido por la política vigente.")


def filtrar_contactables(id_deudores, canal: str = "Llamada",
                         ahora: datetime | None = None,
                         politica: PoliticaContacto | None = None,
                         archivo_dnc: str = NO_CONTACTAR_CSV) -> dict:
    """
    Divide una lista de deudores en contactables / bloqueados según la política.
    Útil para depurar una base de marcación antes de lanzar una campaña.
    """
    permitidos, bloqueados = [], []
    for idd in id_deudores:
        d = puede_contactar(idd, canal=canal, ahora=ahora,
                            politica=politica, archivo_dnc=archivo_dnc)
        (permitidos if d.permitido else bloqueados).append(
            idd if d.permitido else {"id_deudor": idd, "codigo": d.codigo,
                                     "motivo": d.motivo})
    return {"contactables": permitidos, "bloqueados": bloqueados,
            "total": len(list(id_deudores)) if hasattr(id_deudores, "__len__") else
            len(permitidos) + len(bloqueados)}
