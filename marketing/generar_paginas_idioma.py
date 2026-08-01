"""
MV Kobra AI · Variantes de idioma con URL propia (landing y demo)
===================================================================
`?lang=en` traduce el CONTENIDO visible —el propio JS de la página lo hace,
client-side, vía el diccionario I18N (landing) o `guiones.js` (demo)—, pero
nunca tocó los `<meta>` del `<head>`: `og:title`, `og:description`,
`twitter:*`, `description`, `canonical`, `og:locale`. Un scraper de redes
sociales (Facebook/LinkedIn/X/WhatsApp) no ejecuta JavaScript, así que
compartir `mvkobranzaia.com/?lang=en` siempre mostraba el preview en
castellano.

Este script genera `/en/` y `/pt/` como URLs PROPIAS —no un parámetro— con
los `<meta>` ya traducidos y apuntando a esa URL. El body y el JS quedan
IDÉNTICOS al archivo maestro (byte a byte, salvo la reescritura de rutas
relativas que necesita la demo — ver abajo): la traducción del contenido la
sigue haciendo el mismo mecanismo de siempre, y ahora además el visitante que
entra por `/en/` arranca directo en inglés (ver `langRuta`/`ruta` en
`landing/index.html` y `dashboard_estatico/guiones.js`).

Por qué la demo necesita reescribir rutas y la landing no
-----------------------------------------------------------
`dashboard_estatico/index.html` usa rutas RELATIVAS a propósito
(`src="chart.umd.min.js"`, no `/demo/chart.umd.min.js`): así el paquete
offline funciona abierto con doble clic (`file://`), donde una ruta absoluta
rompería. Pero una ruta relativa resuelve contra la URL del NAVEGADOR, no
contra el archivo físico — si `/demo/en/index.html` (generado acá) mantuviera
`src="chart.umd.min.js"`, el navegador pediría `/demo/en/chart.umd.min.js`,
que no existe. Por eso, y SOLO en las variantes generadas para la web —nunca
en el maestro, que sigue sirviendo al paquete offline sin tocar—, esas rutas
se reescriben a `/demo/...` (absolutas), apoyándose en el rewrite que
`vercel.json` ya tiene para `/demo/:path*`.

`landing/index.html` ya usa rutas absolutas (`/landing/...`) en todo lo que
carga assets propios, así que sus variantes no necesitan tocar nada de eso.

Uso:
    python -m marketing.generar_paginas_idioma
"""
from __future__ import annotations

import os

from kobra import rutas as krutas

LANDING = os.path.join(krutas.ROOT_REPO, "landing", "index.html")
DEMO = os.path.join(krutas.ROOT_REPO, "dashboard_estatico", "index.html")

# Cada entrada: (patrón exacto del <meta>/<link> en el maestro, valor nuevo
# por idioma). El patrón incluye la etiqueta completa para no pisar por
# accidente un `content="..."` de otra meta con el mismo prefijo.
META_LANDING = {
    "pt": {
        '<title>MV Kobra AI · Cobranzas Inteligentes</title>':
            '<title>MV Kobra AI · Cobranças Inteligentes</title>',
        '<meta name="description" content="Plataforma de cobranzas con IA: predice qué deudores van a pagar, prioriza la cartera por valor esperado de recupero y negocia por voz y WhatsApp, con control de calidad de cada gestión.">':
            '<meta name="description" content="Plataforma de cobranças com IA: prevê quais devedores vão pagar, prioriza a carteira por valor esperado de recuperação e negocia por voz e WhatsApp, com controle de qualidade de cada atendimento.">',
        '<link rel="canonical" href="https://mvkobranzaia.com/">':
            '<link rel="canonical" href="https://mvkobranzaia.com/pt/">',
        '<meta property="og:locale" content="es_UY">':
            '<meta property="og:locale" content="pt_BR">',
        '<meta property="og:url" content="https://mvkobranzaia.com/">':
            '<meta property="og:url" content="https://mvkobranzaia.com/pt/">',
        '<meta property="og:title" content="MV Kobra AI · Cobranzas Inteligentes">':
            '<meta property="og:title" content="MV Kobra AI · Cobranças Inteligentes">',
        '<meta property="og:description" content="Predicción de pago, agente negociador por voz y WhatsApp, y control de calidad de cada gestión. Demo con datos sintéticos.">':
            '<meta property="og:description" content="Previsão de pagamento, agente negociador por voz e WhatsApp, e controle de qualidade de cada atendimento. Demo com dados sintéticos.">',
        '<meta name="twitter:title" content="MV Kobra AI · Cobranzas Inteligentes">':
            '<meta name="twitter:title" content="MV Kobra AI · Cobranças Inteligentes">',
        '<meta name="twitter:description" content="Predicción de pago, agente negociador por voz y WhatsApp, y control de calidad de cada gestión. Demo con datos sintéticos.">':
            '<meta name="twitter:description" content="Previsão de pagamento, agente negociador por voz e WhatsApp, e controle de qualidade de cada atendimento. Demo com dados sintéticos.">',
    },
    "en": {
        '<title>MV Kobra AI · Cobranzas Inteligentes</title>':
            '<title>MV Kobra AI · Smart Collections</title>',
        '<meta name="description" content="Plataforma de cobranzas con IA: predice qué deudores van a pagar, prioriza la cartera por valor esperado de recupero y negocia por voz y WhatsApp, con control de calidad de cada gestión.">':
            '<meta name="description" content="AI-powered collections platform: predicts which debtors will pay, prioritises the portfolio by expected recovery value, and negotiates by voice and WhatsApp, with quality control on every interaction.">',
        '<link rel="canonical" href="https://mvkobranzaia.com/">':
            '<link rel="canonical" href="https://mvkobranzaia.com/en/">',
        '<meta property="og:locale" content="es_UY">':
            '<meta property="og:locale" content="en_US">',
        '<meta property="og:url" content="https://mvkobranzaia.com/">':
            '<meta property="og:url" content="https://mvkobranzaia.com/en/">',
        '<meta property="og:title" content="MV Kobra AI · Cobranzas Inteligentes">':
            '<meta property="og:title" content="MV Kobra AI · Smart Collections">',
        '<meta property="og:description" content="Predicción de pago, agente negociador por voz y WhatsApp, y control de calidad de cada gestión. Demo con datos sintéticos.">':
            '<meta property="og:description" content="Payment prediction, AI voice and WhatsApp negotiation agent, and quality control on every interaction. Demo with synthetic data.">',
        '<meta name="twitter:title" content="MV Kobra AI · Cobranzas Inteligentes">':
            '<meta name="twitter:title" content="MV Kobra AI · Smart Collections">',
        '<meta name="twitter:description" content="Predicción de pago, agente negociador por voz y WhatsApp, y control de calidad de cada gestión. Demo con datos sintéticos.">':
            '<meta name="twitter:description" content="Payment prediction, AI voice and WhatsApp negotiation agent, and quality control on every interaction. Demo with synthetic data.">',
    },
}

META_DEMO = {
    "pt": {
        '<title>MV Kobra AI · Cobranzas Inteligentes</title>':
            '<title>MV Kobra AI · Cobranças Inteligentes</title>',
        '<meta name="description" content="Demo interactiva de MV Kobra AI: cartera priorizada por probabilidad de pago, agente negociador y copiloto de calidad. Datos 100% sintéticos.">':
            '<meta name="description" content="Demo interativa da MV Kobra AI: carteira priorizada por probabilidade de pagamento, agente negociador e copiloto de qualidade. Dados 100% sintéticos.">',
        '<link rel="canonical" href="https://mvkobranzaia.com/demo/">':
            '<link rel="canonical" href="https://mvkobranzaia.com/demo/pt/">',
        '<meta property="og:locale" content="es_UY">':
            '<meta property="og:locale" content="pt_BR">',
        '<meta property="og:url" content="https://mvkobranzaia.com/demo/">':
            '<meta property="og:url" content="https://mvkobranzaia.com/demo/pt/">',
        '<meta property="og:title" content="MV Kobra AI · Demo interactiva">':
            '<meta property="og:title" content="MV Kobra AI · Demo interativa">',
        '<meta property="og:description" content="Cartera priorizada por probabilidad de pago, agente negociador y copiloto de calidad. Datos 100% sintéticos.">':
            '<meta property="og:description" content="Carteira priorizada por probabilidade de pagamento, agente negociador e copiloto de qualidade. Dados 100% sintéticos.">',
        '<meta name="twitter:title" content="MV Kobra AI · Demo interactiva">':
            '<meta name="twitter:title" content="MV Kobra AI · Demo interativa">',
        '<meta name="twitter:description" content="Cartera priorizada por probabilidad de pago, agente negociador y copiloto de calidad. Datos 100% sintéticos.">':
            '<meta name="twitter:description" content="Carteira priorizada por probabilidade de pagamento, agente negociador e copiloto de qualidade. Dados 100% sintéticos.">',
    },
    "en": {
        '<title>MV Kobra AI · Cobranzas Inteligentes</title>':
            '<title>MV Kobra AI · Smart Collections</title>',
        '<meta name="description" content="Demo interactiva de MV Kobra AI: cartera priorizada por probabilidad de pago, agente negociador y copiloto de calidad. Datos 100% sintéticos.">':
            '<meta name="description" content="Interactive MV Kobra AI demo: portfolio prioritised by payment probability, negotiation agent and quality copilot. 100% synthetic data.">',
        '<link rel="canonical" href="https://mvkobranzaia.com/demo/">':
            '<link rel="canonical" href="https://mvkobranzaia.com/demo/en/">',
        '<meta property="og:locale" content="es_UY">':
            '<meta property="og:locale" content="en_US">',
        '<meta property="og:url" content="https://mvkobranzaia.com/demo/">':
            '<meta property="og:url" content="https://mvkobranzaia.com/demo/en/">',
        '<meta property="og:title" content="MV Kobra AI · Demo interactiva">':
            '<meta property="og:title" content="MV Kobra AI · Interactive demo">',
        '<meta property="og:description" content="Cartera priorizada por probabilidad de pago, agente negociador y copiloto de calidad. Datos 100% sintéticos.">':
            '<meta property="og:description" content="Portfolio prioritised by payment probability, negotiation agent and quality copilot. 100% synthetic data.">',
        '<meta name="twitter:title" content="MV Kobra AI · Demo interactiva">':
            '<meta name="twitter:title" content="MV Kobra AI · Interactive demo">',
        '<meta name="twitter:description" content="Cartera priorizada por probabilidad de pago, agente negociador y copiloto de calidad. Datos 100% sintéticos.">':
            '<meta name="twitter:description" content="Portfolio prioritised by payment probability, negotiation agent and quality copilot. 100% synthetic data.">',
    },
}

# Assets locales que la demo referencia con ruta RELATIVA en el maestro (para
# funcionar con doble clic / file://) y que, solo en las variantes web, se
# vuelven absolutas contra /demo/ — ver el docstring del módulo.
_ASSETS_DEMO_RELATIVOS = [
    "mv_icon.png", "ejemplo_500_cuentas.csv", "botid-init.js",
    "chart.umd.min.js", "xlsx.full.min.js", "kobra_data.js", "copiloto.js",
    "scoring.js", "modelo_web.js", "guiones.js", "audio_demo/manifest.js",
]


def _absolutizar_rutas_demo(html: str) -> str:
    for nombre in _ASSETS_DEMO_RELATIVOS:
        html = html.replace(f'"{nombre}"', f'"/demo/{nombre}"')
    html = html.replace("fetch('modelo_web.json')", "fetch('/demo/modelo_web.json')")
    html = html.replace("'audio_demo/'+IDIOMA+'/'+archivo",
                        "'/demo/audio_demo/'+IDIOMA+'/'+archivo")
    return html


def _generar(maestro: str, meta_por_idioma: dict, salida_dir: str,
             absolutizar: bool = False) -> list[str]:
    with open(maestro, encoding="utf-8") as f:
        base = f.read()
    escritas = []
    for lang, reemplazos in meta_por_idioma.items():
        html = base.replace('<html lang="es">', f'<html lang="{lang}">')
        for viejo, nuevo in reemplazos.items():
            if viejo not in html:
                raise SystemExit(
                    f"{maestro}: no encontré el meta a traducir para '{lang}':\n  {viejo}\n"
                    "(¿cambió el <head> del maestro? actualizar META_* en este script)")
            html = html.replace(viejo, nuevo)
        if absolutizar:
            html = _absolutizar_rutas_demo(html)
        destino = os.path.join(salida_dir, lang, "index.html")
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8") as f:
            f.write(html)
        escritas.append(destino)
    return escritas


def generar() -> list[str]:
    escritas = []
    escritas += _generar(LANDING, META_LANDING,
                         os.path.join(krutas.ROOT_REPO, "landing"))
    escritas += _generar(DEMO, META_DEMO,
                         os.path.join(krutas.ROOT_REPO, "dashboard_estatico"),
                         absolutizar=True)
    return escritas


def main():
    escritas = generar()
    for ruta in escritas:
        print(f"[OK] {os.path.relpath(ruta, krutas.ROOT_REPO)}")


if __name__ == "__main__":
    main()
