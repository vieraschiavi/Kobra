"""
MV Kobra AI · Gestor IA (agente autónomo de negociación)
=====================================================
El "gestor virtual": conduce la negociación completa con el deudor — por
**voz** (voicebot) o por **WhatsApp** (chatbot) — igual que un gestor humano:

    saluda → valida identidad → propone (según ProbPago/estrategia) →
    maneja objeciones con concesiones escalonadas dentro del tope →
    cierra → completa los campos ERP → registra la gestión

La gestión registrada aparece en la pestaña "Gestores & Evolución" con
gestor_id "IA…", así el desempeño del Gestor IA se mide contra los humanos.

Dependencias externas (por diseño, mínimas):
  - Núcleo 100% offline: la lógica de negociación, sentimiento e intenciones
    corre local (mismos motores del Copiloto).
  - **Claude (Anthropic) es la única IA externa**, opcional: si hay
    ANTHROPIC_API_KEY redacta las respuestas con lenguaje más natural;
    sin key, usa las plantillas del negociador (funciona igual).
  - Voz (TTS/STT) y canal (telefonía/WhatsApp) son adaptadores enchufables
    a la infraestructura del cliente (ver realtime/voicebot.py).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from kobra import copiloto, cumplimiento, registro


# ---------------------------------------------------------------------------
# Detección de intención del cliente (offline, reutiliza el léxico del copiloto)
# ---------------------------------------------------------------------------
NEGATIVA_DURA = r"\b(no (voy|pienso|quiero) pagar|no me interesa|dej[ae]me? de (llamar|molestar)|no insista|abogado|denuncia)\b"
PEDIDO_HUMANO = r"\b(hablar con (una? )?(persona|humano|gestor)|operador|supervisor)\b"
ACEPTA = r"\b(acepto|dale|de acuerdo|me sirve|est[aá] bien|perfecto|ok(ey)?|s[ií],? (dale|acepto|me sirve)|hag[aá]moslo|coordinemos)\b"
PIDE_CUOTAS = r"\b(cuotas?|en partes|financiar|fraccionar|dividir)\b"
PIDE_MENOS = r"\b(descuento|rebaja|quita|menos|muy (caro|alto)|mucha plata|es mucho)\b"


def interpretar(texto: str) -> dict:
    """Intención + emociones del mensaje del cliente (100% local)."""
    s = copiloto.analizar_sentimiento(texto)
    t = texto.lower()
    return {
        "sentimiento": s.score,
        "emociones": s.emociones,
        "acepta": bool(re.search(ACEPTA, t)) or "intencion_pago" in s.emociones,
        "negativa_dura": bool(re.search(NEGATIVA_DURA, t)),
        "pide_humano": bool(re.search(PEDIDO_HUMANO, t)),
        "pide_cuotas": bool(re.search(PIDE_CUOTAS, t)),
        "pide_menos": bool(re.search(PIDE_MENOS, t)),
        "pide_no_contactar": cumplimiento.es_pedido_no_contactar(texto),
        "dificultad": "dificultad_economica" in s.emociones,
        "enojo": bool({"enojo", "frustracion"} & set(s.emociones)),
    }


# ---------------------------------------------------------------------------
# Redacción: Claude si hay key (única IA externa), plantillas si no
# ---------------------------------------------------------------------------
def _redactar_con_claude(instruccion: str, contexto: str) -> str | None:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if len(key) < 10:
        return None
    try:
        import requests
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-5", "max_tokens": 220,
                  "system": ("Sos un gestor de cobranzas uruguayo, cordial, empático y "
                             "profesional. Respondé en 1-3 frases naturales, sin emojis, "
                             "listas ni markdown. Nunca prometas nada fuera de la oferta "
                             "indicada ni superes el descuento máximo autorizado."),
                  "messages": [{"role": "user",
                                "content": f"{contexto}\n\nTAREA: {instruccion}"}]},
            timeout=30)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Sesión de negociación del Gestor IA
# ---------------------------------------------------------------------------
@dataclass
class SesionGestorIA:
    id_deudor: str
    canal: str = "Llamada"            # "Llamada" (voicebot) | "WhatsApp" (chatbot)
    gestor_id: str = "IA01"
    usar_claude: bool = True
    estado: str = "saludo"
    oferta_nivel: int = 0             # escalera de concesiones
    historial: list = field(default_factory=list)   # [(quien, texto)]
    campos_erp: dict = field(default_factory=dict)
    brief: dict | None = None
    dnc_archivo: str | None = None    # lista "No contactar" (default: la del módulo)

    def __post_init__(self):
        # Si ya viene un brief (p. ej. de una cartera manual), se respeta;
        # si no, se busca en la cartera scoreada; si tampoco, defaults neutros.
        if self.brief is None:
            self.brief = registro.brief(self.id_deudor) or {
                "monto_deuda": 0, "probpago": 0.5, "estrategia": "Plan de cuotas",
                "descuento_recomendado": 0.1, "plan_cuotas": 3,
                "segmento_propension": "Media",
            }

    # --- escalera de ofertas (nunca supera el tope del negociador) ----------
    def _oferta(self) -> dict:
        monto = float(self.brief["monto_deuda"])
        tope = float(self.brief["descuento_recomendado"])
        cuotas_max = max(int(self.brief["plan_cuotas"]), 1)
        niveles = [
            {"desc": round(tope / 2, 2), "cuotas": 1},        # contado, desc parcial
            {"desc": tope, "cuotas": 1},                      # contado, desc máximo
            {"desc": round(tope / 2, 2), "cuotas": cuotas_max},  # plan de cuotas
            {"desc": tope, "cuotas": cuotas_max},             # última oferta
        ]
        n = niveles[min(self.oferta_nivel, len(niveles) - 1)]
        total = monto * (1 - n["desc"])
        return {**n, "monto": monto, "total": round(total, 0),
                "valor_cuota": round(total / n["cuotas"], 0)}

    def _texto_oferta(self, o: dict) -> str:
        if o["cuotas"] == 1:
            return (f"pagando hoy {o['total']:,.0f} pesos cancela el total de "
                    f"{o['monto']:,.0f} pesos (un {o['desc']:.0%} de beneficio)")
        return (f"regularizar en {o['cuotas']} cuotas de {o['valor_cuota']:,.0f} pesos"
                + (f" con {o['desc']:.0%} de beneficio" if o["desc"] > 0 else ""))

    # --- turno del gestor IA -------------------------------------------------
    def responder(self, mensaje_cliente: str | None = None) -> dict:
        """
        Procesa el mensaje del cliente (None = arranque de la conversación) y
        devuelve {texto, estado, fin, campos_erp}.
        """
        if mensaje_cliente:
            self.historial.append(("cliente", mensaje_cliente))
            intencion = interpretar(mensaje_cliente)
        else:
            intencion = {}

        texto, fin = self._decidir(intencion)
        self.historial.append(("gestor", texto))
        if fin:
            self._completar_erp()
        return {"texto": texto, "estado": self.estado, "fin": fin,
                "campos_erp": self.campos_erp if fin else None}

    def _decidir(self, i: dict) -> tuple:
        o = self._oferta()
        ref = self.id_deudor

        if self.estado == "saludo":
            self.estado = "validacion"
            base = (f"Hola, buenos días. Le hablo del área de cobranzas por la "
                    f"cuenta {ref}. ¿Hablo con el titular?")
            return self._pulir(base, "Saludá y pedí confirmar que es el titular."), False

        if i.get("pide_humano"):
            self.estado = "derivado"
            self.campos_erp["resultado"] = "Derivado a humano"
            return self._pulir(
                "Con gusto, ya lo derivo con un gestor. Le van a llamar a la brevedad. "
                "Gracias por su tiempo.",
                "El cliente pidió hablar con una persona: despedite y confirmá la derivación."), True

        if i.get("pide_no_contactar"):
            self.estado = "no_contactar"
            self.campos_erp["resultado"] = "No contactar"
            self._registrar_opt_out("el deudor pidió no ser contactado")
            return self._pulir(
                "Entendido, respeto su decisión. Registro que no desea ser contactado y "
                "damos de baja las comunicaciones. Disculpe la molestia. Que tenga buen día.",
                "El cliente pidió que no lo contacten más: confirmá el registro del opt-out "
                "y despedite con respeto."), True

        if i.get("negativa_dura"):
            self.estado = "sin_acuerdo"
            return self._pulir(
                "Entiendo su posición y no voy a insistir. Le dejo el canal abierto por si "
                "cambia de opinión; la propuesta queda registrada. Que tenga buen día.",
                "Negativa firme del cliente: cerrá con respeto y dejá la puerta abierta."), True

        if self.estado == "validacion":
            self.estado = "negociacion"
            base = (f"Gracias. Le comento: registra un saldo pendiente de {o['monto']:,.0f} pesos. "
                    f"Hoy puedo ofrecerle {self._texto_oferta(o)}. ¿Le sirve?")
            if i.get("enojo"):
                base = ("Entiendo su molestia y le pido disculpas por la insistencia. "
                        "Justamente lo llamo para resolverlo de la mejor manera: " + base)
            return self._pulir(base, f"Presentá el saldo y la oferta: {self._texto_oferta(o)}."), False

        if self.estado == "negociacion":
            if i.get("acepta"):
                self.estado = "cierre"
                self.campos_erp["resultado"] = "Promesa"
                self.campos_erp["oferta_aceptada"] = o
                canal_pago = "el link de pago" if self.canal == "WhatsApp" else "un SMS con el link de pago"
                return self._pulir(
                    f"Excelente decisión. Le envío ahora {canal_pago} y el comprobante del "
                    f"acuerdo: {self._texto_oferta(o)}. ¡Muchas gracias!",
                    "El cliente aceptó: confirmá el acuerdo, el envío del link y agradecé."), True
            # objeción → escalar una concesión si queda margen
            if any(i.get(k) for k in ("pide_menos", "pide_cuotas", "dificultad")) and self.oferta_nivel < 3:
                self.oferta_nivel += 1
                o = self._oferta()
                pre = ("Comprendo su situación. " if i.get("dificultad") else
                       "Entiendo, busquemos algo mejor. ")
                return self._pulir(
                    pre + f"Puedo mejorarla: {self._texto_oferta(o)}. ¿Lo cerramos?",
                    f"El cliente objetó; ofrecé la mejora: {self._texto_oferta(o)}."), False
            if self.oferta_nivel >= 3:
                self.estado = "sin_acuerdo"
                return self._pulir(
                    "Le hice mi mejor propuesta y queda registrada a su nombre. Si lo "
                    "reconsidera, puede retomarla cuando quiera. Gracias por su tiempo.",
                    "No hubo acuerdo tras la última oferta: cerrá cordialmente."), True
            # respuesta ambigua → repreguntar
            return self._pulir(
                f"¿Le queda cómoda la propuesta de {self._texto_oferta(o)}? "
                "Puedo ajustarla si lo necesita.",
                "Respuesta ambigua: repreguntá por la oferta vigente."), False

        # estado terminal alcanzado
        return "Gracias por su tiempo. ¡Buen día!", True

    def _registrar_opt_out(self, motivo: str):
        """Anota al deudor en la lista de No Contactar (cumplimiento normativo)."""
        self.campos_erp["opt_out"] = True
        kwargs = dict(id_deudor=self.id_deudor, canal="todos", motivo=motivo)
        if self.dnc_archivo:
            kwargs["archivo"] = self.dnc_archivo
        cumplimiento.registrar_no_contactar(**kwargs)

    def _pulir(self, plantilla: str, instruccion: str) -> str:
        """Con Claude redacta natural; sin key usa la plantilla local."""
        if not self.usar_claude:
            return plantilla
        contexto = (
            f"Deudor {self.id_deudor} · saldo {self.brief['monto_deuda']:,.0f} pesos · "
            f"estrategia: {self.brief['estrategia']} · "
            f"descuento máximo autorizado: {self.brief['descuento_recomendado']:.0%}.\n"
            "Últimos mensajes:\n" +
            "\n".join(f"{q}: {t}" for q, t in self.historial[-4:]))
        return _redactar_con_claude(instruccion, contexto) or plantilla

    # --- campos ERP + registro ------------------------------------------------
    def _completar_erp(self):
        conv = "\n".join(
            f"{'Gestor' if q == 'gestor' else 'Cliente'}: {t}" for q, t in self.historial)
        analisis = copiloto.analizar_conversacion(
            conv, canal="llamada" if self.canal == "Llamada" else "whatsapp",
            probpago=float(self.brief["probpago"]),
            estrategia=self.brief["estrategia"], nombre_gestor="Gestor")
        resultado = self.campos_erp.get("resultado", "Sin acuerdo")
        o = self.campos_erp.get("oferta_aceptada")
        self.campos_erp.update({
            "id_deudor": self.id_deudor,
            "gestor_id": self.gestor_id,
            "canal": self.canal,
            "resultado": resultado,
            "monto_acordado": (o["total"] if o else 0.0),
            "cuotas": (o["cuotas"] if o else 0),
            "descuento_aplicado": (o["desc"] if o else 0.0),
            "fecha_promesa": ((datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
                              if resultado == "Promesa" else None),
            "calidad_gestion": analisis["calidad"]["score_total"],
            "clima_cliente": analisis["copiloto"]["clima_emocional"],
            "emociones": analisis["copiloto"]["emociones_cliente"],
            "tecnicas": [k for k, v in analisis["tecnicas"].items() if v],
            "turnos": len(self.historial),
        })

    # Mapa del resultado interno → tipificación estándar de cobranza
    _TIPIFICACION = {
        "Promesa": "Arreglo de pago",
        "Derivado a humano": "Informado",
        "No contactar": "No contactado",
        "Sin acuerdo": "Sin acuerdo",
    }

    def registrar(self, archivo: str | None = None) -> dict:
        """Persiste la gestión en el ERP/base (aparece en el dashboard y en la
        sábana exportable), con la tipificación y datos completos."""
        e = self.campos_erp
        interno = e.get("resultado", "Sin acuerdo")
        resultado = self._TIPIFICACION.get(interno, "Sin acuerdo")
        o = e.get("oferta_aceptada")
        notas = f"Gestor IA · {self.canal} · {e.get('turnos', 0)} turnos · resultado: {interno}."
        kwargs = dict(
            id_deudor=self.id_deudor, gestor_id=self.gestor_id, canal=self.canal,
            tipo_gestor="IA",
            calidad=e.get("calidad_gestion"), clima=e.get("clima_cliente"),
            emociones=e.get("emociones"), tecnicas=e.get("tecnicas"),
            resultado=resultado,
            fecha_compromiso=e.get("fecha_promesa"),
            monto_acordado=(o["total"] if o else None),
            cuotas=(o["cuotas"] if o else None),
            descuento=(o["desc"] if o else None),
            notas=notas,
            recupero=(e.get("monto_acordado") or None))
        if archivo:
            kwargs["archivo"] = archivo
        return registro.registrar_gestion(**kwargs)
