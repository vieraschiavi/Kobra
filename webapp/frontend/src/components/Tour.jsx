import React, { useState } from "react";

const PASOS = [
  { titulo: "👋 Bienvenido a MV Kobra AI",
    texto: "Tu cobranza priorizada por IA: el modelo ProbPago calcula la probabilidad de pago de cada deudor y el Agente Negociador elige estrategia y canal. Este tour te ubica en 4 pasos." },
  { titulo: "📋 Cartera priorizada",
    texto: "La lista ya viene ordenada por valor esperado de recupero. Filtrá por segmento/tramo/propensión y hacé clic en cualquier fila para ver el briefing completo del deudor, con guion sugerido." },
  { titulo: "📅 Agenda y gestores",
    texto: "En Agenda están las promesas vencidas que conviene retomar hoy. En Gestores, el ranking de tu equipo por calidad y conversión — con datos reales cuando registres gestiones." },
  { titulo: "🤖 Asistente IA",
    texto: "Cualquier duda sobre el programa, preguntala en el Asistente: responde con la documentación real del producto, en español. Y en Configuración cargás tus claves una sola vez." },
];

export default function Tour() {
  const [paso, setPaso] = useState(
    localStorage.getItem("kobra_tour_visto") ? -1 : 0);
  if (paso < 0) return null;

  const cerrar = () => { localStorage.setItem("kobra_tour_visto", "1"); setPaso(-1); };
  const p = PASOS[paso];

  return (
    <div className="tour-backdrop">
      <div className="card tour-card">
        <h2>{p.titulo}</h2>
        <p>{p.texto}</p>
        <div className="tour-dots">
          {PASOS.map((_, i) => <i key={i} className={i === paso ? "on" : ""} />)}
        </div>
        <div className="tour-actions">
          <button className="btn ghost" onClick={cerrar}>Saltar</button>
          {paso < PASOS.length - 1
            ? <button className="btn" onClick={() => setPaso(paso + 1)}>Siguiente →</button>
            : <button className="btn" onClick={cerrar}>¡Empezar!</button>}
        </div>
      </div>
    </div>
  );
}
