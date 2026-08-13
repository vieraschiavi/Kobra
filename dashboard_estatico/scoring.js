// © 2026 Martín Viera. Todos los derechos reservados.
/* MV Kobra AI · Scoring de ProbPago en el navegador
 * ==================================================
 * Le permite a un visitante subir su propio CSV y ver el scoring, SIN mandar
 * el archivo a ningún lado: se parsea y se scorea acá, en su navegador. Para
 * un gerente de cobranzas eso no es un detalle técnico — es la diferencia
 * entre probarlo y no probarlo.
 *
 * El modelo sale de `modelo_web.json`, que exporta `kobra.exportar_modelo_web`
 * desde el `.joblib` entrenado. NO es un modelo "parecido para la demo": es la
 * misma aritmética de scikit-learn, verificada contra `predict_proba` sobre
 * 3.000 filas reales con una diferencia máxima de 1,2e-13.
 *
 *     z     = intercept + Σ coef·x        (x escalado y one-hot)
 *     p_cal = interpolación lineal en los nodos de la isotónica, SOBRE z
 *     p     = promedio de los 3 pliegues
 *
 * Cuidado con el segundo paso: la isotónica de CalibratedClassifierCV se
 * ajusta sobre la salida de decision_function (z crudo), no sobre la sigmoide.
 * Meter un 1/(1+e^-z) antes de interpolar da números plausibles y equivocados
 * —se midió: 0,525 de diferencia máxima—.
 */
(function (global) {
  "use strict";

  // --- CSV -----------------------------------------------------------------
  // Parser propio y no una librería: el demo tiene que abrir con `file://` y
  // sin red. Soporta comillas, comas dentro de comillas y CRLF, que es lo que
  // sale de un export de Excel.
  function parsearCSV(texto) {
    texto = texto.replace(/^﻿/, "");           // BOM de Excel
    var sep = detectarSeparador(texto);
    var filas = [], campo = "", fila = [], enComillas = false;
    for (var i = 0; i < texto.length; i++) {
      var c = texto[i];
      if (enComillas) {
        if (c === '"') {
          if (texto[i + 1] === '"') { campo += '"'; i++; }
          else enComillas = false;
        } else campo += c;
      } else if (c === '"') enComillas = true;
      else if (c === sep) { fila.push(campo); campo = ""; }
      else if (c === "\n") { fila.push(campo); filas.push(fila); fila = []; campo = ""; }
      else if (c !== "\r") campo += c;
    }
    if (campo !== "" || fila.length) { fila.push(campo); filas.push(fila); }
    if (!filas.length) return { columnas: [], filas: [] };
    var columnas = filas[0].map(function (h) { return h.trim(); });
    var datos = [];
    for (var f = 1; f < filas.length; f++) {
      if (filas[f].length === 1 && filas[f][0].trim() === "") continue;   // línea vacía
      var o = {};
      for (var k = 0; k < columnas.length; k++) o[columnas[k]] = (filas[f][k] || "").trim();
      datos.push(o);
    }
    return { columnas: columnas, filas: datos };
  }

  // Excel en configuración regional española exporta con punto y coma. Sin
  // esto, el archivo entra como una sola columna y el demo dice "te faltan
  // todas las columnas", que es un mensaje inútil.
  function detectarSeparador(texto) {
    var primera = texto.slice(0, texto.indexOf("\n") + 1 || texto.length);
    var conteo = { ",": 0, ";": 0, "\t": 0 };
    var enComillas = false;
    for (var i = 0; i < primera.length; i++) {
      var c = primera[i];
      if (c === '"') enComillas = !enComillas;
      else if (!enComillas && conteo[c] !== undefined) conteo[c]++;
    }
    var mejor = ",", max = -1;
    for (var s in conteo) if (conteo[s] > max) { max = conteo[s]; mejor = s; }
    return mejor;
  }

  // --- Modelo --------------------------------------------------------------
  function vector(fila, pre) {
    var bloques = { num: [], cat: [] }, i, c;
    for (i = 0; i < pre.numericas.length; i++) {
      c = pre.numericas[i];
      var v = parseFloat(String(fila[c] === undefined ? "" : fila[c]).replace(",", "."));
      if (!isFinite(v)) v = pre.escala.media[i];      // faltante = la media (queda en 0 al escalar)
      var d = pre.escala.desvio[i] || 1;
      bloques.num.push((v - pre.escala.media[i]) / d);
    }
    for (i = 0; i < pre.categoricas.length; i++) {
      c = pre.categoricas[i];
      var valor = String(fila[c] === undefined ? "" : fila[c]);
      var opciones = pre.categorias[c];
      for (var k = 0; k < opciones.length; k++) bloques.cat.push(valor === opciones[k] ? 1 : 0);
    }
    // El orden de los bloques es el de `transformers_` de scikit-learn: los
    // coeficientes están alineados a ÉL, no al orden en que uno los escribiría.
    var salida = [];
    for (i = 0; i < pre.orden_transformers.length; i++) {
      var b = bloques[pre.orden_transformers[i]];
      if (b) salida = salida.concat(b);
    }
    return salida;
  }

  function interpolar(iso, z) {
    var x = iso.x, y = iso.y;
    if (z <= x[0]) return y[0];
    if (z >= x[x.length - 1]) return y[y.length - 1];
    var lo = 0, hi = x.length - 1, mid;
    while (hi - lo > 1) { mid = (lo + hi) >> 1; if (x[mid] <= z) lo = mid; else hi = mid; }
    if (x[hi] === x[lo]) return y[lo];
    return y[lo] + (z - x[lo]) / (x[hi] - x[lo]) * (y[hi] - y[lo]);
  }

  function scorearFila(bundle, fila) {
    var total = 0;
    for (var p = 0; p < bundle.pliegues.length; p++) {
      var pl = bundle.pliegues[p];
      var v = vector(fila, pl.pre);
      var z = pl.intercept;
      for (var i = 0; i < v.length; i++) z += pl.coef[i] * v[i];
      total += interpolar(pl.calibrador, z);        // sobre z, NO sobre la sigmoide
    }
    return total / bundle.pliegues.length;
  }

  function scorear(bundle, filas) {
    var out = [];
    for (var i = 0; i < filas.length; i++) out.push(scorearFila(bundle, filas[i]));
    return out;
  }

  // --- Qué le falta al archivo del visitante -------------------------------
  function revisarColumnas(bundle, columnas) {
    var pedidas = bundle.pre.numericas.concat(bundle.pre.categoricas);
    var tiene = {};
    columnas.forEach(function (c) { tiene[c.toLowerCase()] = c; });
    var faltan = pedidas.filter(function (c) { return !tiene[c.toLowerCase()]; });
    // Mapa de la columna del archivo (con su capitalización) a la que espera
    // el modelo: así "Monto_Deuda" o "MONTO_DEUDA" funcionan igual.
    var mapa = {};
    pedidas.forEach(function (c) { if (tiene[c.toLowerCase()]) mapa[c] = tiene[c.toLowerCase()]; });
    return { faltan: faltan, mapa: mapa, pedidas: pedidas };
  }

  function normalizar(filas, mapa) {
    return filas.map(function (f) {
      var o = {};
      for (var destino in mapa) o[destino] = f[mapa[destino]];
      return o;
    });
  }

  global.KobraScoring = {
    parsearCSV: parsearCSV,
    detectarSeparador: detectarSeparador,
    scorear: scorear,
    scorearFila: scorearFila,
    revisarColumnas: revisarColumnas,
    normalizar: normalizar
  };
})(typeof window !== "undefined" ? window : globalThis);
