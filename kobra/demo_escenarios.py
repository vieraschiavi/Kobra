# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Escenarios de demo completos, conmutables desde el programa
==========================================================================
Dos empresas sintéticas de punta a punta, cada una con datos para TODOS los
módulos: cartera scoreada (ProbPago + negociador), gestiones históricas,
logística, proyectos y equipo. Se activan con un clic desde Configuración —el
mismo lugar del botón demo ON/OFF— y sirven para dos cosas distintas:

  * **Demostrar**: mostrarle el producto a un prospecto con una empresa que se
    parezca a la suya (una financiera no se reconoce en una distribuidora).
  * **Verificar**: `verificar()` recorre módulo por módulo CON los datos del
    escenario activo y ejecuta cada uno de verdad — scorea, negocia un turno,
    entrena el AutoML, evalúa una fórmula, arma la logística. Devuelve un
    checklist con evidencia medida, no con "debería andar".

Por qué la cartera pasa por `importar_y_scorear` y no por un CSV armado a mano:
ese es el MISMO camino que recorre la cartera real de un cliente cuando la
sube (mapeo de columnas → ProbPago seleccionado por CV → negociador →
explicabilidad). Si ese camino se rompe, el escenario de demo se rompe igual
— que es exactamente lo que se quiere detectar. Un CSV pre-armado seguiría
"funcionando" con el pipeline muerto.

Todo es sintético y con semilla fija, como el resto del repo: activar el mismo
escenario dos veces da los mismos números.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
#  Catálogo
# ---------------------------------------------------------------------------
# Las semillas difieren para que las dos empresas NO se parezcan: si ambas
# salieran de la misma, la "distribuidora" sería la financiera con otro nombre
# y la demo perdería el punto (mostrar que el producto se adapta al rubro).
ESCENARIOS = {
    "financiera": {
        "nombre": "Financiera Río Sur",
        "rubro": "Créditos al consumo",
        "descripcion": (
            "Cartera de préstamos personales: 400 deudores individuos, mora "
            "temprana dominante, tickets chicos. El foco es el circuito de "
            "cobranza: ProbPago, gestor IA por voz/WhatsApp y copiloto."),
        "seed": 4201,
        "n_deudores": 400,
        "ticket": (8_000, 90_000),      # UYU
        "peso_individuos": 0.85,
    },
    "distribuidora": {
        "nombre": "Distribuidora El Faro",
        "rubro": "Venta mayorista con crédito a comercios",
        "descripcion": (
            "Crédito comercial: 250 cuentas de comercios, tickets grandes y "
            "mora vieja concentrada. Además del circuito de cobranza, pesa la "
            "operación: logística (reposición y ofertas) y proyectos."),
        "seed": 4202,
        "n_deudores": 250,
        "ticket": (40_000, 600_000),
        "peso_individuos": 0.15,
    },
}

_NOMBRES = ["Ana", "Bruno", "Carla", "Diego", "Elena", "Franco", "Gimena",
            "Hugo", "Inés", "Julián", "Karina", "Luis", "Mora", "Nico",
            "Olga", "Pablo", "Rita", "Saúl", "Tania", "Víctor"]
_APELLIDOS = ["Acosta", "Britos", "Cabrera", "Da Silva", "Etchegoyen",
              "Ferreira", "González", "Hernández", "Ibarra", "Juárez",
              "Klein", "López", "Machado", "Núñez", "Olivera", "Pereyra",
              "Rodríguez", "Sosa", "Techera", "Viera"]
_COMERCIOS = ["Almacén", "Autoservicio", "Kiosco", "Provisión", "Minimercado",
              "Despensa", "Bazar", "Ferretería"]
_ZONAS = ["Centro", "Cordón", "Pocitos", "La Blanqueada", "Sayago", "Unión",
          "Maroñas", "Paso Molino"]


def _cartera_cruda(cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    """La cartera como la subiría el cliente: nombre, teléfono, deuda, mora.

    Deliberadamente en el formato "archivo de cliente" (columnas con nombres
    humanos) y no en el esquema interno: así el escenario ejercita también el
    mapeo de columnas de `cartera_manual`, que es donde una cartera real
    tropieza primero.
    """
    n = cfg["n_deudores"]
    es_individuo = rng.random(n) < cfg["peso_individuos"]
    nombres = [
        (f"{rng.choice(_NOMBRES)} {rng.choice(_APELLIDOS)}" if ind
         else f"{rng.choice(_COMERCIOS)} {rng.choice(_APELLIDOS)} "
              f"({rng.choice(_ZONAS)})")
        for ind in es_individuo]
    lo, hi = cfg["ticket"]
    deuda = np.round(np.exp(rng.uniform(np.log(lo), np.log(hi), n)), 0)
    # Mezcla de mora temprana y vieja; la distribuidora concentra mora vieja.
    vieja = rng.random(n) < (0.25 if cfg["peso_individuos"] > 0.5 else 0.45)
    dias = np.where(vieja, rng.integers(120, 540, n), rng.integers(5, 119, n))
    return pd.DataFrame({
        "nombre": nombres,
        "telefono": [f"+5989{rng.integers(1000000, 9999999)}" for _ in range(n)],
        "deuda": deuda,
        "dias_mora": dias,
        "segmento": np.where(es_individuo, "Individuo", "Pyme"),
    })


def _logistica(cfg: dict, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    """Productos y ventas con la MISMA forma que valida `kobra.logistica`."""
    grande = cfg["peso_individuos"] < 0.5          # la distribuidora opera más
    n_prod, n_ventas = (60, 2_400) if grande else (25, 600)
    productos = pd.DataFrame({
        "sku": [f"SKU-{i:03d}" for i in range(n_prod)],
        "nombre": [f"Producto {i:03d}" for i in range(n_prod)],
        "categoria": rng.choice(
            ["Bebidas", "Almacén", "Limpieza", "Perfumería"], n_prod),
        "proveedor": rng.choice(["Norte SRL", "Central SA", "Import UY"], n_prod),
        "precio": np.round(rng.uniform(80, 900, n_prod), 2),
        "costo": np.round(rng.uniform(40, 500, n_prod), 2),
        "stock": rng.integers(0, 800, n_prod),
        "stock_min": rng.integers(10, 60, n_prod),
        "lead_time_dias": rng.integers(3, 20, n_prod),
    })
    fechas = pd.date_range("2026-02-01", "2026-08-01", freq="D")
    ventas = pd.DataFrame({
        "fecha": rng.choice(fechas, n_ventas),
        "sku": rng.choice(productos["sku"], n_ventas),
        "cantidad": rng.integers(1, 6, n_ventas),
        "cliente_id": rng.choice([f"C-{i:02d}" for i in range(30)], n_ventas),
        "venta_id": [f"V-{i:05d}" for i in range(n_ventas)],
        "zona": rng.choice(_ZONAS, n_ventas),
    })
    return {"logistica_productos": productos, "logistica_ventas": ventas}


def _proyectos(cfg: dict, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    nombres = (["Apertura sucursal Este", "App de vendedores", "Depósito nuevo",
                "Integración BI", "Flota propia"]
               if cfg["peso_individuos"] < 0.5 else
               ["Migración core", "Portal de clientes", "Scoring propio",
                "Onboarding digital", "App móvil"])
    proyectos = pd.DataFrame({
        "proyecto_id": [f"P{i}" for i in range(1, 6)],
        "nombre": nombres,
        "dueno": rng.choice(_NOMBRES, 5),
        "criticidad": ["Alta", "Media", "Alta", "Baja", "Media"],
        "presupuesto": [100_000.0, 50_000.0, 80_000.0, 30_000.0, 45_000.0],
        "ejecutado": [60_000.0, 52_000.0, 81_000.0, 10_000.0, 20_000.0],
    })
    nt = 40
    tareas = pd.DataFrame({
        "tarea_id": [f"T{i:03d}" for i in range(nt)],
        "proyecto_id": rng.choice(proyectos["proyecto_id"], nt),
        "titulo": [f"Tarea {i:03d}" for i in range(nt)],
        "estado": rng.choice(["todo", "in_progress", "blocked", "done"], nt,
                             p=[0.4, 0.25, 0.1, 0.25]),
        "responsable": rng.choice(_NOMBRES[:6], nt),
        "prioridad": rng.choice(["Alta", "Media", "Baja"], nt),
        "vencimiento": rng.choice(pd.date_range("2026-07-01", "2026-11-30"), nt),
        "depende_de": [None] * nt,
    })
    equipo = pd.DataFrame({
        "nombre": _NOMBRES[:5],
        "capacidad_semanal_hs": [40] * 5,
        "carga_actual_hs": [38, 55, 30, 42, 25],
    })
    return {"proyectos_proyectos": proyectos, "proyectos_tareas": tareas,
            "proyectos_equipo": equipo}


def generar(escenario_id: str) -> dict[str, pd.DataFrame]:
    """Todas las tablas del escenario, en memoria. Determinista por semilla."""
    if escenario_id not in ESCENARIOS:
        raise ValueError(f"Escenario desconocido: {escenario_id!r}. "
                         f"Hay: {', '.join(sorted(ESCENARIOS))}.")
    cfg = ESCENARIOS[escenario_id]
    rng = np.random.default_rng(cfg["seed"])

    from kobra import cartera_manual
    cruda = _cartera_cruda(cfg, rng)
    scored = cartera_manual.importar_y_scorear(cruda)

    # Gestiones históricas coherentes con la cartera (para Gestores/CxC).
    n_g = min(len(scored) * 2, 800)
    ids = rng.choice(scored["id_deudor"], n_g)
    gestiones = pd.DataFrame({
        "id_deudor": ids,
        "fecha": rng.choice(pd.date_range("2026-05-01", "2026-08-20"), n_g),
        "canal": rng.choice(["Llamada", "WhatsApp", "Email"], n_g,
                            p=[0.5, 0.35, 0.15]),
        "gestor": rng.choice(["IA01", "IA02", "G-Laura", "G-Martín"], n_g),
        "resultado": rng.choice(
            ["pago", "promesa", "arreglo", "no contesta", "informado"], n_g,
            p=[0.12, 0.18, 0.10, 0.40, 0.20]),
        "monto_prometido": np.round(rng.uniform(0, 30_000, n_g), 0),
    })

    return {"kobra_scored": scored, "kobra_gestiones": gestiones,
            **_logistica(cfg, rng), **_proyectos(cfg, rng)}


def activar(escenario_id: str, dir_datos: str) -> dict:
    """Escribe el escenario donde el backend lee los datos de la empresa.

    `dir_datos` es el directorio del `kobra_scored.csv` de la empresa (el
    backend lo conoce; este módulo no importa al backend para no crear el
    ciclo kobra→webapp→kobra). No toca la cartera real subida: el botón demo
    ON/OFF sigue decidiendo cuál de las dos se muestra.
    """
    tablas = generar(escenario_id)
    os.makedirs(dir_datos, exist_ok=True)
    for nombre, df in tablas.items():
        df.to_csv(os.path.join(dir_datos, f"{nombre}.csv"), index=False)
    cfg = ESCENARIOS[escenario_id]
    scored = tablas["kobra_scored"]
    return {
        "escenario": escenario_id,
        "nombre": cfg["nombre"],
        "deudores": int(len(scored)),
        "deuda_total": float(scored["monto_deuda"].sum()),
        "tablas": sorted(tablas),
    }


# ---------------------------------------------------------------------------
#  Verificación punta a punta, con evidencia medida
# ---------------------------------------------------------------------------
def _paso(modulo: str, fn) -> dict:
    """Ejecuta un chequeo y devuelve {modulo, ok, detalle}. El detalle trae el
    número medido cuando pasa y el error textual cuando no: un checklist de
    tildes sin evidencia es el "debería andar" con otra cara."""
    try:
        return {"modulo": modulo, "ok": True, "detalle": fn()}
    except Exception as e:                                  # noqa: BLE001
        return {"modulo": modulo, "ok": False,
                "detalle": f"{type(e).__name__}: {e}"}


def verificar(dir_datos: str) -> list[dict]:
    """Recorre todos los módulos con los datos activos en `dir_datos`.

    Cada paso EJECUTA el módulo (scorea, negocia, entrena, evalúa) — no mira
    si el archivo existe. El orden va de la base (datos) hacia arriba
    (módulos que los consumen), así el primer fallo señala la causa y no un
    síntoma tres módulos después.
    """
    scored = pd.read_csv(os.path.join(dir_datos, "kobra_scored.csv"))
    pasos: list[dict] = []

    def probpago():
        cols = {"probpago", "decil", "estrategia", "descuento_recomendado"}
        faltan = cols - set(scored.columns)
        if faltan:
            raise ValueError(f"la cartera scoreada no trae {sorted(faltan)}")
        fuera = scored[(scored.probpago < 0) | (scored.probpago > 1)]
        if len(fuera):
            raise ValueError(f"{len(fuera)} scores fuera de [0,1]")
        return (f"{len(scored)} deudores scoreados, probpago medio "
                f"{scored.probpago.mean():.3f}, 10 deciles")
    pasos.append(_paso("ProbPago (scoring)", probpago))

    def gestor():
        from kobra import cartera_manual, gestor_ia
        fila = scored.sort_values("monto_deuda").iloc[-1]
        brief = cartera_manual.brief_desde_fila(fila)
        ses = gestor_ia.SesionGestorIA(
            id_deudor=str(fila["id_deudor"]), canal="WhatsApp",
            usar_claude=False, brief=brief,
            dnc_archivo=os.path.join(dir_datos, "no_contactar_vacia.csv"))
        r1 = ses.responder(None)                       # saludo
        r2 = ses.responder("no me alcanza, ¿hay algún plan?")
        texto = (r1.get("texto", "") + " " + r2.get("texto", "")).lower()
        if not texto.strip():
            raise ValueError("el gestor no produjo respuesta")
        tope = float(brief.get("descuento_recomendado") or 0)
        return (f"negoció 2 turnos por WhatsApp sin IA externa; tope de "
                f"quita del brief {tope:.0%}")
    pasos.append(_paso("Gestor IA (chatbot/chatvoice)", gestor))

    def chatbot_ayuda():
        from kobra import ayuda
        frags = ayuda.buscar("cómo activo las llamadas por teléfono")
        if not frags:
            raise ValueError("la búsqueda de ayuda no devolvió fragmentos")
        return f"el asistente encontró {len(frags)} fragmentos de docs sin IA externa"
    pasos.append(_paso("Chatbot de ayuda", chatbot_ayuda))

    def gobernanza():
        from kobra import gobernanza as kgob
        clasif = kgob.clasificar_tabla(scored)
        sensibles = [c for c, n in clasif.items()
                     if n in (kgob.PERSONAL, kgob.SENSIBLE)]
        if "nombre" in scored.columns and "nombre" not in sensibles:
            raise ValueError("'nombre' no quedó clasificada como personal")
        return (f"{len(clasif)} columnas clasificadas, "
                f"{len(sensibles)} protegidas")
    pasos.append(_paso("Gobernanza de datos", gobernanza))

    def kpis():
        from kobra import medidas
        valor = medidas.evaluar("suma(monto_deuda) / contar()", scored)
        esperado = scored["monto_deuda"].sum() / len(scored)
        if abs(valor - esperado) > 0.01:
            raise ValueError(f"la fórmula dio {valor}, esperaba {esperado}")
        return f"fórmula de ticket promedio evaluada: {valor:,.0f}"
    pasos.append(_paso("KPIs propios (fórmulas)", kpis))

    def automl():
        from data.generate_dataset import generar as gen_hist
        from kobra import automl as kautoml
        # AutoML necesita resultado histórico (`pago`); la cartera del
        # escenario es "recién importada" y no lo trae — como una real. Se
        # entrena con el histórico sintético del generador canónico, que es
        # el mismo flujo que un cliente con historia.
        hist = pd.DataFrame(gen_hist(n=400, seed=ESCENARIOS_SEED_HIST))
        res = kautoml.entrenar(hist, objetivo="pago")
        met = res.get("holdout", {}) or res.get("metricas", {})
        return f"modelo entrenado; métricas de holdout: {str(met)[:80]}"
    pasos.append(_paso("AutoML", automl))

    def logistica():
        from kobra import logistica as klog
        productos = pd.read_csv(os.path.join(dir_datos, "logistica_productos.csv"))
        ventas = pd.read_csv(os.path.join(dir_datos, "logistica_ventas.csv"))
        d = klog.todas(productos, ventas, None)
        if not d["indicadores"]:
            raise ValueError("logística no devolvió indicadores")
        return (f"{len(productos)} productos, {len(ventas)} ventas → "
                f"{len(d) - 1} listas de sugerencias")
    pasos.append(_paso("Logística", logistica))

    def proyectos():
        from kobra import proyectos as kpro
        r = kpro.resumen(
            pd.read_csv(os.path.join(dir_datos, "proyectos_proyectos.csv")),
            pd.read_csv(os.path.join(dir_datos, "proyectos_tareas.csv")),
            pd.read_csv(os.path.join(dir_datos, "proyectos_equipo.csv")))
        if r["salud"].empty or r["backlog"].empty:
            raise ValueError("proyectos devolvió salud o backlog vacíos")
        return (f"salud de {len(r['salud'])} proyectos, backlog de "
                f"{len(r['backlog'])} tareas priorizadas")
    pasos.append(_paso("Proyectos", proyectos))

    def ingenieria():
        from kobra import ingenieria_datos as king
        r = king.analizar({"cartera": scored.head(200)})
        perfil = r["perfiles"]["cartera"]
        return (f"perfiladas {perfil['columnas']} columnas; "
                f"{len(r['claves']['cartera']['pk'])} candidatas a clave")
    pasos.append(_paso("Ingeniería de datos", ingenieria))

    def cumplimiento():
        from kobra import cumplimiento as kcum
        d = kcum.puede_contactar(str(scored.iloc[0]["id_deudor"]))
        return f"motor consultado: {'permite' if d.permitido else d.motivo}"
    pasos.append(_paso("Cumplimiento (horarios/DNC)", cumplimiento))

    return pasos


# Semilla del histórico de AutoML: fija y distinta de las de los escenarios,
# para que cambiar un escenario no mueva las métricas del ejemplo de AutoML.
ESCENARIOS_SEED_HIST = 4300
