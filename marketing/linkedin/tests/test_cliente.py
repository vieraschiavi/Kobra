"""Tests del cliente contra el LinkedIn falso de tests/servidor_falso.py."""
from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from linkedin.auth import Token, cargar_token, guardar_token  # noqa: E402
from linkedin.cliente import Cliente, ErrorAPI  # noqa: E402
from servidor_falso import LinkedInFalso  # noqa: E402


def _token() -> Token:
    futuro = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    return Token(access_token="TOKEN-DE-PRUEBA", expira_en=futuro, sub="ABC123", nombre="Prueba")


class TestPublicar(unittest.TestCase):
    def test_manda_las_cabeceras_que_la_api_exige(self):
        with LinkedInFalso() as s:
            Cliente(_token(), base=s.base, version="202608").publicar("hola")
            cab = s.recibidos[0]["cabeceras"]
        # Sin LinkedIn-Version la API contesta 426; sin X-Restli-Protocol-Version
        # parsea el cuerpo con el protocolo viejo. Las dos son obligatorias.
        self.assertEqual(cab["linkedin-version"], "202608")
        self.assertEqual(cab["x-restli-protocol-version"], "2.0.0")
        self.assertEqual(cab["authorization"], "Bearer TOKEN-DE-PRUEBA")

    def test_el_autor_es_el_urn_del_token(self):
        with LinkedInFalso() as s:
            Cliente(_token(), base=s.base).publicar("hola")
            cuerpo = s.recibidos[0]["cuerpo"]
        self.assertEqual(cuerpo["author"], "urn:li:person:ABC123")
        self.assertEqual(cuerpo["commentary"], "hola")
        self.assertEqual(cuerpo["lifecycleState"], "PUBLISHED")
        self.assertEqual(s.recibidos[0]["ruta"], "/rest/posts")

    def test_el_urn_sale_de_la_cabecera_y_no_del_cuerpo(self):
        # /rest/posts devuelve 201 con el cuerpo VACÍO. Un cliente que busque el
        # id en el JSON se queda sin URN y después no puede comentar el post.
        with LinkedInFalso() as s:
            r = Cliente(_token(), base=s.base).publicar("hola")
        self.assertEqual(r.urn, "urn:li:share:7123456789")
        self.assertIn("urn:li:share:7123456789", r.url)

    def test_rechaza_el_texto_largo_sin_llamar_a_la_api(self):
        with LinkedInFalso() as s:
            with self.assertRaises(ValueError):
                Cliente(_token(), base=s.base).publicar("x" * 3001)
            self.assertEqual(s.recibidos, [], "no tiene que salir ningún request")

    def test_rechaza_el_texto_vacio(self):
        with LinkedInFalso() as s:
            with self.assertRaises(ValueError):
                Cliente(_token(), base=s.base).publicar("   \n  ")
            self.assertEqual(s.recibidos, [])

    def test_rechaza_una_visibilidad_inventada(self):
        with LinkedInFalso() as s:
            with self.assertRaises(ValueError):
                Cliente(_token(), base=s.base).publicar("hola", visibilidad="AMIGOS")
            self.assertEqual(s.recibidos, [])

    def test_el_error_de_la_api_trae_el_codigo_y_el_cuerpo(self):
        def falla(_ruta):
            return 422, {"message": "commentary is required"}, {}

        with LinkedInFalso(responder=falla) as s:
            with self.assertRaises(ErrorAPI) as ctx:
                Cliente(_token(), base=s.base).publicar("hola")
        self.assertEqual(ctx.exception.codigo, 422)
        self.assertIn("commentary is required", ctx.exception.cuerpo)

    def test_si_no_viene_el_urn_no_finge_exito(self):
        # 201 sin x-restli-id: el post capaz se creó, pero no tenemos con qué
        # comentarlo. Devolver un URN vacío hace fallar al comentario después,
        # con un 404 que no explica nada.
        with LinkedInFalso(responder=lambda _r: (201, {}, {})) as s:
            with self.assertRaises(ErrorAPI):
                Cliente(_token(), base=s.base).publicar("hola")


class TestComentar(unittest.TestCase):
    def test_el_urn_va_percent_encoded_en_la_ruta(self):
        urn = "urn:li:share:7123456789"
        with LinkedInFalso() as s:
            Cliente(_token(), base=s.base).comentar(urn, "el link: ejemplo.com")
            ruta = s.recibidos[0]["ruta"]
        # Con los ':' sin escapar la ruta se parsea mal y LinkedIn tira 404.
        self.assertNotIn(":", ruta.split("/rest/socialActions/")[1].split("/")[0])
        self.assertEqual(urllib.parse.unquote(ruta), f"/rest/socialActions/{urn}/comments")

    def test_el_cuerpo_lleva_actor_objeto_y_mensaje(self):
        urn = "urn:li:share:7123456789"
        with LinkedInFalso() as s:
            Cliente(_token(), base=s.base).comentar(urn, "hola")
            cuerpo = s.recibidos[0]["cuerpo"]
        self.assertEqual(cuerpo["actor"], "urn:li:person:ABC123")
        self.assertEqual(cuerpo["object"], urn)
        self.assertEqual(cuerpo["message"]["text"], "hola")

    def test_rechaza_el_comentario_largo(self):
        with LinkedInFalso() as s:
            with self.assertRaises(ValueError):
                Cliente(_token(), base=s.base).comentar("urn:li:share:1", "x" * 1251)
            self.assertEqual(s.recibidos, [])


class TestToken(unittest.TestCase):
    def test_el_token_se_guarda_solo_legible_por_el_dueno(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "sub" / "token.json"
            guardar_token(_token(), ruta)
            modo = stat.S_IMODE(os.stat(ruta).st_mode)
        self.assertEqual(modo, 0o600, f"permisos {oct(modo)}: el token queda legible por otros")

    def test_ida_y_vuelta(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "token.json"
            guardar_token(_token(), ruta)
            self.assertEqual(cargar_token(ruta).sub, "ABC123")

    def test_un_token_corrupto_se_trata_como_ausente(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "token.json"
            ruta.write_text("{no es json", encoding="utf-8")
            self.assertIsNone(cargar_token(ruta))

    def test_un_token_vencido_se_declara_vencido(self):
        pasado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.assertTrue(Token("t", pasado, "X").vencido)

    def test_se_considera_vencido_antes_de_la_hora_exacta(self):
        # Un token que vence en 2 minutos no sirve: puede expirar a mitad del
        # request y devolver un 401 que parece un problema de permisos.
        casi = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
        self.assertTrue(Token("t", casi, "X").vencido)


if __name__ == "__main__":
    unittest.main(verbosity=2)
