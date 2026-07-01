# 🚀 GUÍA RÁPIDA - CASH IA V2.5 STANDALONE

## ⚡ INICIO RÁPIDO (3 PASOS)

### **PASO 1: Ejecutar**
```r
# Abrir RStudio
# Cargar el archivo
source("CASH_IA_V25_STANDALONE_COMPLETO.R")

# ¡Listo! La interfaz se abre automáticamente
```

### **PASO 2: Configurar API Keys**
1. Ir a pestaña "⚙️ Configuración API"
2. Pegar tus API keys:
   - **OpenAI**: Para transcripción Whisper (llamadas)
   - **Claude**: Para evaluación WhatsApp/Llamadas
   - **ChatGPT**: Alternativa a Claude
3. Click "💾 Guardar Configuración"
4. Reiniciar app

### **PASO 3: Evaluar WhatsApp**
1. Ir a pestaña "💬 WhatsApp Negociación"
2. Click "Browse" y seleccionar archivo `.txt`
3. Seleccionar servicio (Claude o ChatGPT)
4. Click "⚡ Evaluar Conversación"
5. Ver resultados!

---

## 📄 FORMATO ARCHIVO WHATSAPP

Guardar conversación como `.txt` con este formato:

```
[01/05/2026, 10:15:23] Gestor CASH: Buenos días! Soy María de CASH Uruguay.

[01/05/2026, 10:17:45] Juan Perez: Hola. Qué necesita?

[01/05/2026, 10:18:12] Gestor CASH: Juan, le escribo por su cuota vencida. Podemos ayudarle a regularizar?

[01/05/2026, 10:20:30] Juan Perez: Este mes no tengo el dinero completo.

[01/05/2026, 10:21:05] Gestor CASH: Entiendo. Le ofrezco pagar 50% ahora y 50% en 15 días?

[01/05/2026, 10:22:15] Juan Perez: Perfecto, acepto.

[01/05/2026, 10:22:45] Gestor CASH: Excelente! Le envío QR de pago ahora.
```

**IMPORTANTE:**
- Cada mensaje debe tener `[DD/MM/YYYY, HH:MM:SS] Nombre: Mensaje`
- Exportar directamente desde WhatsApp Web (Más opciones > Exportar chat)
- Guardar como `.txt` sin editar formato

---

## 📊 QUÉ EVALÚA EL SISTEMA

### **16 CRITERIOS WHATSAPP:**

#### **Comunes con Llamadas (9):**
1. ✅ **Saludo Inicial** (5%) - Profesional y cordial
2. ✅ **Identificación** (5%) - Nombre y empresa
3. ✅ **Validación Datos** (10%) - Confirma identidad cliente
4. ✅ **Empatía** (15%) - Escucha activa, comprensión
5. ✅ **Claridad** (10%) - Mensajes claros, sin errores
6. ✅ **Solución** (15%) - Ofrece alternativas concretas
7. ✅ **Objeciones** (15%) - Maneja profesionalmente
8. ✅ **Cierre** (15%) - Acuerdo claro con fecha
9. ✅ **Registro** (10%) - Confirma por escrito

#### **Específicos WhatsApp (7):**
10. ⏱️ **Tiempo 1ra Respuesta** (5%)
    - <2 horas = 100%
    - 2-6 horas = 70%
    - >6 horas = 40%

11. 🕒 **Duración Total** (5%)
    - <24 horas = 100% (rápida)
    - 24-48 horas = 80% (moderada)
    - >48 horas = 60% (lenta)

12. 💬 **Eficiencia Mensajes** (5%)
    - 5-15 mensajes = 100% (óptimo)
    - 3-4 o 16-25 = 80%
    - <3 o >25 = 60%

13. 📎 **Uso Multimedia** (5%)
    - Usa imágenes/QR/links cuando es apropiado

14. 🎯 **Tono Profesional** (10%)
    - Formal sin ser robótico
    - Evita coloquialismos excesivos

15. 📞 **Seguimiento Proactivo** (5%)
    - Follow-up post-acuerdo sin ser invasivo

16. 🧠 **Técnicas Negociación** (10%)
    - Anclaje, reciprocidad, escasez, urgencia
    - Fraccionamiento, alternativas, validación

---

## 🎯 INTERPRETACIÓN DE RESULTADOS

### **SCORE TOTAL:**
- **80-100**: ✅ Excelente - Gestor modelo
- **60-79**: ⚠️ Bueno - Áreas de mejora identificadas
- **<60**: 🔴 Requiere capacitación urgente

### **VELOCIDAD:**
- **Rápida** (<24hs): Ideal para urgentes, alta conversión
- **Moderada** (24-48hs): Aceptable, permite reflexión
- **Lenta** (>48hs): Riesgo pérdida cliente

### **EFECTIVIDAD CIERRE:**
- **Alta**: Acuerdo claro con compromiso firme
- **Media**: Acuerdo con dudas o condicional
- **Baja**: Sin acuerdo o compromiso vago

### **TÉCNICAS IDENTIFICADAS:**
El sistema detecta automáticamente técnicas de negociación:
- 🎯 **Anclaje**: Ofrecer monto más alto primero
- 🤝 **Reciprocidad**: "Si hace X, yo hago Y"
- ⏰ **Urgencia**: "Oferta válida hasta..."
- 📉 **Fraccionamiento**: Dividir deuda en partes
- 🔄 **Alternativas**: Ofrecer 2-3 opciones
- 💚 **Validación**: Reconocer situación cliente

---

## 💡 CASOS DE USO

### **USO 1: Evaluación Individual**
**Objetivo**: Evaluar conversación específica  
**Cuándo**: Auditoría puntual, reclamo, caso especial  
**Pasos**: Cargar 1 archivo → Evaluar → Ver detalle

### **USO 2: Revisión Semanal Gestor**
**Objetivo**: Monitorear evolución gestor  
**Cuándo**: Reunión 1-1 con gestor  
**Pasos**: Evaluar 5-10 conversaciones semana → Identificar patrones

### **USO 3: Benchmarking Equipo**
**Objetivo**: Comparar performance gestores  
**Cuándo**: Reporte mensual gerencia  
**Pasos**: Batch todos los gestores → Comparar scores promedio

### **USO 4: Capacitación**
**Objetivo**: Ejemplos para training  
**Cuándo**: Onboarding nuevos gestores  
**Pasos**: Seleccionar mejores (>90) y peores (<60) → Analizar diferencias

---

## 🔧 TROUBLESHOOTING

### **Problema: "API key inválida"**
**Solución:**
- Verificar que copiaste la key completa
- Claude keys empiezan con `sk-ant-`
- OpenAI keys empiezan con `sk-`
- Ir a Configuración y volver a guardar

### **Problema: "Error parseando conversación"**
**Solución:**
- Verificar formato timestamps `[DD/MM/YYYY, HH:MM:SS]`
- Verificar formato mensajes `Nombre: Mensaje`
- Exportar directamente desde WhatsApp (no copiar/pegar)

### **Problema: "No se detecta gestor"**
**Solución:**
- El sistema asume que quien envía MÁS mensajes es el gestor
- Si ambos envían igual cantidad, puede confundirse
- Solución: editar .txt para que sea más claro

### **Problema: "Puerto ocupado"**
**Solución:**
```r
# Cerrar otras apps Shiny
# Reiniciar RStudio
# O especificar puerto:
run_cash_quality_analyzer(port = 5000)
```

### **Problema: "Archivo muy grande"**
**Solución:**
- Máximo 200MB por archivo
- Si conversación es MUY larga, dividir en partes
- O comprimir antes de cargar

---

## 📈 MEJORES PRÁCTICAS

### **✅ DO (Hacer):**
- Evaluar mínimo 5-10 conversaciones por gestor/mes
- Comparar mismos periodos (evitar estacionalidad)
- Usar resultados en reuniones 1-1 constructivas
- Celebrar mejoras y scores altos (>85)
- Identificar patrones comunes en scores bajos

### **❌ DON'T (No Hacer):**
- Usar score como único criterio de evaluación
- Comparar gestores sin considerar complejidad casos
- Penalizar sin dar feedback constructivo
- Evaluar solo casos problemáticos (sesgo)
- Ignorar contexto (cliente difícil, caso complejo)

---

## 🎓 CAPACITACIÓN RECOMENDADA

### **Para Supervisores (1 hora):**
1. Cómo cargar conversaciones (10 min)
2. Interpretar scores y gráficos (20 min)
3. Identificar áreas mejora (15 min)
4. Dar feedback efectivo (15 min)

### **Para Gestores (30 min):**
1. Qué evalúa el sistema (10 min)
2. Cómo mejorar velocidad (5 min)
3. Técnicas de negociación efectivas (10 min)
4. Interpretación de su score (5 min)

---

## 📞 SOPORTE

**Preguntas Técnicas:**
- Revisar esta guía primero
- Consultar sección Troubleshooting
- Verificar API keys en Configuración

**Preguntas de Negocio:**
- Contactar equipo BI Cobranzas
- Email: mviera@cash.com.uy (ejemplo)

---

## 🎉 ¡LISTO PARA USAR!

El sistema está **100% funcional** y **listo para producción**.

**Próximos pasos:**
1. ✅ Configurar API keys
2. ✅ Cargar primera conversación de prueba
3. ✅ Revisar resultados
4. ✅ Evaluar 10 conversaciones reales
5. ✅ Analizar patrones
6. ✅ Dar feedback a gestores

**¡A evaluar conversaciones!** 💬🚀
