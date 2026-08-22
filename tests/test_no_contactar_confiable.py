# © 2026 Martín Viera. Todos los derechos reservados.

"""La lista de No Contactar tiene que aguantar de verdad.

Es el archivo más caro de perder del producto entero. No por lo que vale el
dato: por lo que pasa cuando falta. Un deudor pide por teléfono que no lo
llamen más, el bot le dice «queda registrado», y a la semana lo vuelven a
llamar. Eso no es un bug de software, es el reclamo que llega con la grabación
adjunta.

Tenía dos defectos que apuntaban los dos para el mismo lado — llamar de más:

1. **Se guardaba en la carpeta del programa.** `ROOT/data/no_contactar.csv`,
   al lado del código. Corriendo desde el repo da igual; instalado en Windows,
   `ROOT` es Program Files, de solo lectura para un usuario sin privilegios de
   administrador. En la máquina de un cliente real, registrar el opt-out
   tiraba `PermissionError: [WinError 5]` en el medio de la llamada. Era el
   ÚLTIMO módulo que escribía ahí: todo el resto ya usaba `kobra/rutas.py`,
   que se escribió justamente para esto.

2. **Se fallaba abierto.** `except Exception: return False` — y `False` en
   `esta_en_no_contactar` significa "no está en la lista", o sea "llamalo". Un
   archivo corrupto, bloqueado por otro proceso o con los permisos cambiados
   se convertía, en silencio y a escala, en llamarle a todos los que habían
   pedido que no los llamaran más.
"""
import os

import pytest

from kobra import cumplimiento as kcump
from kobra import gestor_ia
from kobra import rutas as krutas


# ---------------------------------------------------------------------------
# 1) Dónde vive el archivo
# ---------------------------------------------------------------------------
def test_la_lista_sigue_a_la_carpeta_de_datos_y_no_al_codigo(tmp_path, monkeypatch):
    """Instalado, `ROOT` es la carpeta de instalación (Program Files) y no se
    puede escribir; `DIR_DATOS` es la carpeta escribible del usuario, que es
    para lo que existe `kobra/rutas.py`.

    Se comprueba MOVIENDO la carpeta de datos, no comparando strings: en el
    repo las dos rutas coinciden, así que un `startswith` pasaría igual con el
    defecto puesto y no probaría nada.
    """
    import importlib
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "otro disco"))
    importlib.reload(krutas)
    recargado = importlib.reload(kcump)
    try:
        assert recargado.NO_CONTACTAR_CSV.startswith(str(tmp_path / "otro disco")), (
            "la lista de No Contactar quedó colgada de la carpeta del código: "
            "instalada en Program Files, el opt-out no se puede registrar")
    finally:
        monkeypatch.undo()
        importlib.reload(krutas)
        importlib.reload(kcump)


def test_ningun_modulo_de_kobra_escribe_en_la_carpeta_del_programa():
    """La propiedad general, para que no vuelva a pasar en otro archivo.

    Se mira solo lo que se ESCRIBE. Leer de `ROOT` está bien —los datos de
    demo vienen bundleados ahí— y `backups/` ya tiene su propia variable de
    entorno para redirigirlo.
    """
    import ast
    import pathlib
    culpables = []
    for archivo in pathlib.Path("kobra").glob("*.py"):
        if archivo.name in ("rutas.py", "backup.py", "pipeline.py"):
            continue
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            # `X_CSV = os.path.join(ROOT, "data", ...)` — una ruta de datos
            # colgada del código, que es la firma exacta del defecto.
            if not (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Call)):
                continue
            destino = getattr(nodo.targets[0], "id", "")
            if not destino.endswith(("_CSV", "_JSON", "_DIR", "_FILE")):
                continue
            args = getattr(nodo.value, "args", [])
            if args and getattr(args[0], "id", "") == "ROOT":
                culpables.append(f"{archivo.name}:{nodo.lineno} {destino}")
    assert not culpables, (
        "estos archivos se escribirían en la carpeta de instalación, que es de "
        f"solo lectura cuando el programa está instalado: {culpables}")


# ---------------------------------------------------------------------------
# 2) Falla cerrado
# ---------------------------------------------------------------------------
@pytest.fixture()
def lista(tmp_path):
    return str(tmp_path / "no_contactar.csv")


def test_una_lista_corrupta_no_significa_llamar_a_todos(lista, tmp_path):
    """El corazón del asunto. Antes esto devolvía False —"no está en la
    lista"— y la campaña salía a marcar."""
    with open(lista, "w", encoding="utf-8") as f:
        f.write("id_deudor,canal,motivo,fecha\n")
        f.write('KB-1,todos,"comilla sin cerrar,2026-01-01\n')
        f.write("esto,no,es,un,csv,con,las,columnas,que,van\n")
    with pytest.raises(kcump.ListaNoContactarIlegible):
        kcump.esta_en_no_contactar("KB-1", "Llamada", lista)


def test_una_lista_sin_las_columnas_esperadas_tampoco(lista):
    with open(lista, "w", encoding="utf-8") as f:
        f.write("otra_cosa,y_otra\n1,2\n")
    with pytest.raises(kcump.ListaNoContactarIlegible):
        kcump.esta_en_no_contactar("KB-1", "Llamada", lista)


def test_la_campania_se_frena_entera_con_un_motivo_legible(lista):
    """No propaga la excepción: bloquea con código propio. Una campaña que
    devuelve cero contactables con el motivo a la vista se diagnostica; una que
    revienta a mitad deja media base marcada y nadie sabe cuál."""
    with open(lista, "w", encoding="utf-8") as f:
        f.write("no,son,las,columnas\n1,2,3,4\n")
    d = kcump.puede_contactar("KB-1", canal="Llamada", archivo_dnc=lista)
    assert not d.permitido
    assert d.codigo == "LISTA_ILEGIBLE"
    assert "No Contactar" in d.motivo

    r = kcump.filtrar_contactables(["KB-1", "KB-2", "KB-3"], archivo_dnc=lista)
    assert r["contactables"] == [], "salió a marcar con la lista ilegible"
    assert len(r["bloqueados"]) == 3


def test_que_el_archivo_no_exista_sigue_siendo_contactable(lista):
    """Fallar cerrado no puede significar bloquear todo el día uno: si nadie
    pidió opt-out todavía, no hay lista y eso es normal."""
    assert not os.path.exists(lista)
    assert kcump.esta_en_no_contactar("KB-1", "Llamada", lista) is False
    assert kcump.puede_contactar(
        "KB-1", canal="Llamada", archivo_dnc=lista,
        ahora=__import__("datetime").datetime(2026, 3, 3, 11, 0)).permitido


def test_una_lista_vacia_recien_creada_tampoco_frena(lista):
    open(lista, "w", encoding="utf-8").close()
    assert kcump.esta_en_no_contactar("KB-1", "Llamada", lista) is False


def test_el_camino_normal_sigue_funcionando(lista):
    kcump.registrar_no_contactar("KB-77", canal="todos",
                                 motivo="lo pidió por teléfono", archivo=lista)
    assert kcump.esta_en_no_contactar("KB-77", "Llamada", lista)
    assert not kcump.esta_en_no_contactar("KB-78", "Llamada", lista)
    d = kcump.puede_contactar("KB-77", canal="Llamada", archivo_dnc=lista)
    assert not d.permitido and d.codigo == "OPT_OUT"


# ---------------------------------------------------------------------------
# 3) Si igual no se puede escribir, el pedido no se pierde
# ---------------------------------------------------------------------------
def test_si_el_archivo_no_se_puede_escribir_el_opt_out_queda_en_auditoria(monkeypatch):
    """Disco lleno, permisos, el archivo abierto por otro proceso. El pedido
    del deudor no se puede perder por eso — queda en el log de auditoría, que
    es encadenado y vive en otra carpeta."""
    anotado = []
    monkeypatch.setattr(gestor_ia.kauditoria, "registrar",
                        lambda accion, detalle=None, **kw: anotado.append((accion, detalle)))

    def revienta(**kw):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(gestor_ia.cumplimiento, "registrar_no_contactar", revienta)

    ses = gestor_ia.SesionGestorIA(id_deudor="KB-OPTOUT", usar_claude=False)
    ses.responder(None)
    r = ses.responder("no me llamen más, sáquenme de la lista por favor")

    # La llamada NO se corta con un error: cortarle el teléfono en la cara a
    # alguien que acaba de pedir esto es la peor forma de terminar.
    assert r["fin"] is True
    assert r["estado"] == "no_contactar"
    assert "no desea ser contactado" in r["texto"].lower()
    assert ses.campos_erp.get("opt_out") is True
    assert ses.campos_erp.get("opt_out_pendiente") is True

    acciones = [a for a, _ in anotado]
    assert "opt_out_no_persistido" in acciones, (
        "el deudor pidió no ser contactado y no quedó registro en ningún lado")
    detalle = dict(anotado[acciones.index("opt_out_no_persistido")][1])
    assert detalle["id_deudor"] == "KB-OPTOUT"
    assert "a mano" in detalle["accion_requerida"]


def test_el_opt_out_normal_no_marca_pendiente(tmp_path):
    """El flag de "cargalo a mano" solo aparece cuando de verdad falló."""
    ses = gestor_ia.SesionGestorIA(
        id_deudor="KB-OK-OPTOUT", usar_claude=False,
        dnc_archivo=str(tmp_path / "dnc.csv"))
    ses.responder(None)
    ses.responder("no me llamen más por favor")
    assert ses.campos_erp.get("opt_out") is True
    assert "opt_out_pendiente" not in ses.campos_erp
    assert kcump.esta_en_no_contactar("KB-OK-OPTOUT", "Llamada",
                                      str(tmp_path / "dnc.csv"))
