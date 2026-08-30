"""Tests del parser de posts y del comportamiento seguro de la CLI."""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import linkedin_publicar  # noqa: E402
from linkedin import posts  # noqa: E402


def _escribir(texto: str) -> Path:
    d = tempfile.mkdtemp()
    ruta = Path(d) / "post.txt"
    ruta.write_text(texto, encoding="utf-8")
    return ruta


class TestParser(unittest.TestCase):
    def test_separa_cuerpo_de_comentario_y_lee_metadatos(self):
        p = posts.leer(_escribir(
            "# idioma: es\n"
            "# visibilidad: CONNECTIONS\n"
            "Primera línea.\n\nSegunda línea.\n"
            "--- comentario ---\n"
            "El link: mvkobranzaia.com\n"
        ))
        self.assertEqual(p.idioma, "es")
        self.assertEqual(p.visibilidad, "CONNECTIONS")
        self.assertEqual(p.cuerpo, "Primera línea.\n\nSegunda línea.")
        self.assertEqual(p.comentario, "El link: mvkobranzaia.com")

    def test_los_metadatos_no_se_publican(self):
        p = posts.leer(_escribir("# idioma: en\nHola.\n"))
        self.assertNotIn("idioma", p.cuerpo)
        self.assertEqual(p.cuerpo, "Hola.")

    def test_un_numeral_en_el_medio_del_post_es_texto_normal(self):
        # Un hashtag arranca con '#' y es parte del post. Sólo la cabecera, y
        # sólo con forma "# clave: valor", cuenta como metadato.
        p = posts.leer(_escribir("Hola.\n#cobranzas #ml\n"))
        self.assertIn("#cobranzas", p.cuerpo)

    def test_el_comentario_es_opcional(self):
        p = posts.leer(_escribir("Sólo el post.\n"))
        self.assertFalse(p.tiene_comentario)

    def test_dos_separadores_es_un_error(self):
        with self.assertRaises(posts.ErrorFormato):
            posts.leer(_escribir("A\n--- comentario ---\nB\n--- comentario ---\nC\n"))

    def test_cuerpo_vacio_es_un_error(self):
        with self.assertRaises(posts.ErrorFormato):
            posts.leer(_escribir("# idioma: es\n\n--- comentario ---\nsólo comentario\n"))

    def test_archivo_inexistente_es_un_error_claro(self):
        with self.assertRaises(posts.ErrorFormato):
            posts.leer(Path("/no/existe/post.txt"))


class TestCLI(unittest.TestCase):
    def setUp(self):
        os.environ["LINKEDIN_CLIENT_ID"] = "id-de-prueba"
        os.environ["LINKEDIN_CLIENT_SECRET"] = "secreto-de-prueba"
        # Sin esto la CLI leería un .env del directorio de trabajo.
        os.environ["LINKEDIN_DOTENV"] = "/dev/null"

    def _correr(self, argv):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
            codigo = linkedin_publicar.main(argv)
        return codigo, salida.getvalue()

    def test_sin_publicar_no_toca_la_red(self):
        # Si la vista previa intentara autenticar o publicar, con credenciales
        # falsas tendría que fallar. Que salga 0 es la prueba de que no lo hizo.
        ruta = _escribir("Un post cualquiera.\n--- comentario ---\nmvkobranzaia.com\n")
        codigo, texto = self._correr([str(ruta)])
        self.assertEqual(codigo, 0)
        self.assertIn("No se publicó nada", texto)
        self.assertIn("Un post cualquiera.", texto)

    def test_un_link_en_el_cuerpo_frena_la_publicacion(self):
        ruta = _escribir("Mirá esto https://mvkobranzaia.com y contame.\n")
        codigo, texto = self._correr([str(ruta), "--publicar"])
        self.assertEqual(codigo, 1)
        self.assertIn("link en el CUERPO", texto)

    def test_un_post_demasiado_largo_no_llega_a_pedir_confirmacion(self):
        ruta = _escribir("x" * 3001 + "\n")
        codigo, texto = self._correr([str(ruta), "--publicar"])
        self.assertEqual(codigo, 1)
        self.assertIn("máximo", texto)

    def test_sin_credenciales_avisa_donde_ponerlas(self):
        for k in ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"):
            os.environ.pop(k, None)
        ruta = _escribir("Hola.\n")
        codigo, texto = self._correr([str(ruta)])
        self.assertEqual(codigo, 2)
        self.assertIn("linkedin.com/developers/apps", texto)

    def test_un_archivo_roto_devuelve_error_y_no_stacktrace(self):
        ruta = _escribir("A\n--- comentario ---\nB\n--- comentario ---\nC\n")
        codigo, texto = self._correr([str(ruta)])
        self.assertEqual(codigo, 2)
        self.assertIn("separador", texto)


class TestPostsDelRepo(unittest.TestCase):
    """Los posts que vienen en posts/ tienen que ser publicables tal cual."""

    def test_todos_los_posts_del_repo_pasan_la_validacion(self):
        archivos = sorted((RAIZ / "posts").glob("*.txt"))
        self.assertTrue(archivos, "no hay posts en posts/")
        for ruta in archivos:
            with self.subTest(post=ruta.name):
                p = posts.leer(ruta)
                self.assertEqual(linkedin_publicar._validar(p), [])
                self.assertTrue(p.idioma, "falta '# idioma:' en la cabecera")


if __name__ == "__main__":
    unittest.main(verbosity=2)
