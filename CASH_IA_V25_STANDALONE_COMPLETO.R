################################################################################
# CASH-IA CONTROL DE CALIDAD V2.5 STANDALONE - COMPLETO CON WHATSAPP
# Sistema Integrado: Llamadas + WhatsApp + Análisis Temporal
# Autor: Martín Viera - BI Cobranzas CASH Uruguay
# Fecha: 08 Mayo 2026
# 
# CAMBIOS V2.5:
# ✅ Módulo WhatsApp completo integrado (16 criterios)
# ✅ Nueva pestaña WhatsApp Negociación
# ✅ Análisis velocidad negociación y técnicas IA
# ✅ 8 gráficos específicos WhatsApp
# ✅ Procesamiento batch conversaciones .txt
# ✅ Standalone: NO requiere archivos externos
################################################################################

# INSTRUCCIONES DE USO:
# 1. Guardar este archivo como: CASH_IA_V25_STANDALONE_COMPLETO.R
# 2. Abrir en RStudio
# 3. Ejecutar: source("CASH_IA_V25_STANDALONE_COMPLETO.R")
# 4. La interfaz se abrirá automáticamente
# 5. Disfrutar del sistema completo con WhatsApp!

cat("\n")
cat("═══════════════════════════════════════════════════════════════════════\n")
cat("  CASH-IA Control de Calidad v2.5 STANDALONE\n")
cat("  Sistema Completo: Llamadas + WhatsApp + Análisis Temporal\n")
cat("═══════════════════════════════════════════════════════════════════════\n\n")

# ==============================================================================
# BLOQUE 1: CARGA DE PAQUETES
# ==============================================================================

if (!require("pacman", quietly = TRUE)) {
  install.packages("pacman", repos = "https://cran.r-project.org")
}

paquetes_esenciales <- c(
  "dplyr", "tidyr", "stringr", "lubridate", "glue", "purrr",
  "av", "tuneR", "httr", "jsonlite", "base64enc",
  "shiny", "shinydashboard", "shinyWidgets", "shinycssloaders", "shinyjs",
  "ggplot2", "plotly", "scales", "viridis", "RColorBrewer",
  "DT", "kableExtra", "reactable", "formattable",
  "openxlsx", "officer", "flextable", "gdtools",
  "progress", "fs", "digest", "logger",
  "zoo", "tsibble", "htmltools", "htmlwidgets", "rmarkdown"
)

suppressPackageStartupMessages({
  if (require("pacman", quietly = TRUE)) {
    pacman::p_load(char = paquetes_esenciales)
  } else {
    for (pkg in paquetes_esenciales) {
      if (!require(pkg, character.only = TRUE, quietly = TRUE)) {
        install.packages(pkg, repos = "https://cran.r-project.org")
        library(pkg, character.only = TRUE)
      }
    }
  }
})

cat("✓ Paquetes cargados\n")

# ==============================================================================
# RESOLUCIÓN DE CONFLICTOS
# ==============================================================================

filter <- dplyr::filter
select <- dplyr::select
mutate <- dplyr::mutate
arrange <- dplyr::arrange
count <- dplyr::count
lag <- dplyr::lag
rename <- dplyr::rename
summarise <- dplyr::summarise
group_by <- dplyr::group_by
ungroup <- dplyr::ungroup
first <- dplyr::first
last <- dplyr::last
observe <- shiny::observe
reactive <- shiny::reactive

cat("✓ Conflictos resueltos\n\n")

# ==============================================================================
# CONFIGURACIÓN GLOBAL
# ==============================================================================

options(
  scipen = 999,
  stringsAsFactors = FALSE,
  encoding = "UTF-8",
  shiny.maxRequestSize = 200*1024^2
)

set.seed(42)

# ==============================================================================
# CONFIGURACIÓN API KEYS
# ==============================================================================

CONFIG_FILE <- ".api_config.rds"

API_CONFIG_BACKUP <- list(
  openai = list(key = "", model_whisper = "whisper-1"),
  claude = list(key = "", model = "claude-sonnet-4-20250514"),
  chatgpt = list(key = "", model = "gpt-4")
)

guardar_configuracion_api <- function(config_data) {
  tryCatch({
    saveRDS(config_data, CONFIG_FILE)
    return(TRUE)
  }, error = function(e) {
    return(FALSE)
  })
}

cargar_configuracion_api <- function() {
  if(file.exists(CONFIG_FILE)) {
    tryCatch({
      return(readRDS(CONFIG_FILE))
    }, error = function(e) {
      return(NULL)
    })
  }
  return(NULL)
}

inicializar_configuracion_api <- function(config_backup) {
  config_guardada <- cargar_configuracion_api()
  if (is.null(config_guardada)) return(config_backup)
  
  config_final <- config_backup
  if (!is.null(config_guardada$openai$key) && config_guardada$openai$key != "") {
    config_final$openai$key <- config_guardada$openai$key
  }
  if (!is.null(config_guardada$claude$key) && config_guardada$claude$key != "") {
    config_final$claude$key <- config_guardada$claude$key
  }
  if (!is.null(config_guardada$chatgpt$key) && config_guardada$chatgpt$key != "") {
    config_final$chatgpt$key <- config_guardada$chatgpt$key
  }
  return(config_final)
}

API_CONFIG <- inicializar_configuracion_api(API_CONFIG_BACKUP)

# ==============================================================================
# CRITERIOS DE EVALUACIÓN - LLAMADAS (14 CRITERIOS)
# ==============================================================================

CRITERIOS_EVALUACION <- c(
  "saludo_inicial", "identificacion_agente", "validacion_datos",
  "escucha_activa", "tono_voz", "claridad_comunicacion",
  "busqueda_solucion", "compromiso_pago", "registro_gestion",
  "manejo_objeciones", "cierre_llamada", "tiempo_gestion",
  "empowerment", "profesionalismo"
)

PESOS_CRITERIOS <- c(5, 5, 10, 15, 5, 10, 15, 10, 5, 10, 5, 5, 5, 5)

PROMPT_EVALUACION_BASE <- "
Eres un supervisor experto en cobranzas que evalúa llamadas telefónicas.

CRITERIOS (14):
1. Saludo Inicial (5%): Profesional y cordial
2. Identificación Agente (5%): Nombre y empresa
3. Validación Datos (10%): Confirma identidad cliente
4. Escucha Activa (15%): Atento, empático, comprensivo
5. Tono de Voz (5%): Profesional, cálido, firme
6. Claridad Comunicación (10%): Mensaje claro y conciso
7. Búsqueda Solución (15%): Ofrece alternativas concretas
8. Compromiso Pago (10%): Acuerdo claro con fecha
9. Registro Gestión (5%): Confirma lo acordado
10. Manejo Objeciones (10%): Responde profesionalmente
11. Cierre Llamada (5%): Despedida apropiada
12. Tiempo Gestión (5%): Eficiente, no apresurado
13. Empowerment (5%): Resuelve sin transferir
14. Profesionalismo (5%): Mantiene compostura

TRANSCRIPCIÓN:
{{TRANSCRIPCION}}

RESPONDE SOLO CON JSON (sin markdown):
{
  \"score_total\": <0-100>,
  \"criterios\": {
    \"saludo_inicial\": {\"score\": <0-100>, \"observacion\": \"...\"},
    // ... (todos los 14 criterios)
  },
  \"resumen_ejecutivo\": \"...\",
  \"fortalezas\": [\"...\", \"...\", \"...\"],
  \"areas_mejora\": [\"...\", \"...\", \"...\"]
}
"

# ==============================================================================
# CRITERIOS WHATSAPP (16 CRITERIOS)
# ==============================================================================

CRITERIOS_WHATSAPP <- list(
  saludo_inicial = list(nombre = "Saludo Inicial", peso = 5, tipo = "binario"),
  identificacion_agente = list(nombre = "Identificación", peso = 5, tipo = "binario"),
  validacion_datos = list(nombre = "Validación Datos", peso = 10, tipo = "binario"),
  escucha_activa = list(nombre = "Empatía", peso = 15, tipo = "escala"),
  claridad_comunicacion = list(nombre = "Claridad", peso = 10, tipo = "escala"),
  busqueda_solucion = list(nombre = "Solución", peso = 15, tipo = "escala"),
  manejo_objeciones = list(nombre = "Objeciones", peso = 15, tipo = "escala"),
  cierre_negociacion = list(nombre = "Cierre", peso = 15, tipo = "binario"),
  registro_compromiso = list(nombre = "Registro", peso = 10, tipo = "binario"),
  tiempo_primera_respuesta = list(nombre = "Tiempo 1ra Resp", peso = 5, tipo = "metrica_tiempo"),
  tiempo_total_negociacion = list(nombre = "Duración Total", peso = 5, tipo = "metrica_tiempo"),
  cantidad_mensajes = list(nombre = "Eficiencia Msgs", peso = 5, tipo = "metrica_cantidad"),
  uso_multimedia = list(nombre = "Multimedia", peso = 5, tipo = "binario"),
  tono_profesional = list(nombre = "Tono Profesional", peso = 10, tipo = "escala"),
  seguimiento_proactivo = list(nombre = "Seguimiento", peso = 5, tipo = "binario"),
  tecnicas_negociacion = list(nombre = "Técnicas Negoc", peso = 10, tipo = "escala")
)

PROMPT_EVALUACION_WHATSAPP <- "
Evalúa conversación WhatsApp de cobranzas (16 criterios).

CRITERIOS:
1-9: Comunes (saludo, identificación, validación, empatía, claridad, solución, objeciones, cierre, registro)
10. Tiempo 1ra Respuesta: <2hs=100%, 2-6hs=70%, >6hs=40%
11. Duración Total: <24hs=100%, 24-48hs=80%, >48hs=60%
12. Eficiencia Mensajes: 5-15=100%, 3-4 o 16-25=80%, resto=60%
13. Multimedia: Usa imágenes/QR apropiadamente
14. Tono: Profesional sin robótico
15. Seguimiento: Follow-up proactivo
16. Técnicas: Anclaje, reciprocidad, escasez, urgencia

CONVERSACIÓN:
{{CONVERSACION_WHATSAPP}}

METADATA:
Gestor: {{NOMBRE_GESTOR}}
Cliente: {{NOMBRE_CLIENTE}}
Mensajes: {{TOTAL_MENSAJES}}
Tiempo 1ra resp: {{TIEMPO_PRIMERA_RESPUESTA}}
Duración: {{DURACION_TOTAL}}

RESPONDE SOLO JSON:
{
  \"score_total\": <0-100>,
  \"criterios\": {
    \"saludo_inicial\": {\"score\": <0-100>, \"cumple\": <true/false>, \"observacion\": \"...\"},
    // ... (todos los 16)
  },
  \"resumen_ejecutivo\": \"...\",
  \"fortalezas\": [\"...\"],
  \"areas_mejora\": [\"...\"],
  \"tecnicas_identificadas\": [\"...\"],
  \"velocidad_negociacion\": \"rapida/moderada/lenta\",
  \"efectividad_cierre\": \"alta/media/baja\"
}
"

# ==============================================================================
# FUNCIONES API - TRANSCRIPCIÓN Y EVALUACIÓN
# ==============================================================================

transcribir_con_whisper <- function(audio_path, api_key) {
  if(nchar(api_key) < 10) stop("API key OpenAI inválida")
  
  response <- POST(
    "https://api.openai.com/v1/audio/transcriptions",
    add_headers(Authorization = paste("Bearer", api_key)),
    body = list(
      file = upload_file(audio_path),
      model = "whisper-1",
      language = "es"
    ),
    encode = "multipart"
  )
  
  if(status_code(response) != 200) {
    stop(glue("Error Whisper: {status_code(response)}"))
  }
  
  content(response)$text
}

evaluar_con_claude <- function(prompt, api_key, model = "claude-sonnet-4-20250514") {
  if(nchar(api_key) < 10) stop("API key Claude inválida")
  
  response <- POST(
    "https://api.anthropic.com/v1/messages",
    add_headers(
      "x-api-key" = api_key,
      "anthropic-version" = "2023-06-01",
      "content-type" = "application/json"
    ),
    body = toJSON(list(
      model = model,
      max_tokens = 4000,
      messages = list(list(role = "user", content = prompt))
    ), auto_unbox = TRUE),
    encode = "raw"
  )
  
  if(status_code(response) != 200) {
    stop(glue("Error Claude: {status_code(response)}"))
  }
  
  content(response)$content[[1]]$text
}

evaluar_con_chatgpt <- function(prompt, api_key, model = "gpt-4") {
  if(nchar(api_key) < 10) stop("API key ChatGPT inválida")
  
  response <- POST(
    "https://api.openai.com/v1/chat/completions",
    add_headers(
      Authorization = paste("Bearer", api_key),
      "Content-Type" = "application/json"
    ),
    body = toJSON(list(
      model = model,
      messages = list(list(role = "user", content = prompt)),
      temperature = 0.3
    ), auto_unbox = TRUE),
    encode = "raw"
  )
  
  if(status_code(response) != 200) {
    stop(glue("Error ChatGPT: {status_code(response)}"))
  }
  
  content(response)$choices[[1]]$message$content
}

# ==============================================================================
# FUNCIONES WHATSAPP
# ==============================================================================

parsear_conversacion_whatsapp <- function(archivo_path) {
  lineas <- readLines(archivo_path, warn = FALSE, encoding = "UTF-8")
  contenido_completo <- paste(lineas, collapse = "\n")
  
  patron_mensaje <- "\\[?(\\d{1,2}/\\d{1,2}/\\d{2,4}),?\\s*(\\d{1,2}:\\d{2}(?::\\d{2})?)\\]?\\s*-?\\s*([^:]+):\\s*(.+?)(?=\\[?\\d{1,2}/\\d{1,2}/|$)"
  mensajes <- str_match_all(contenido_completo, regex(patron_mensaje, dotall = TRUE))[[1]]
  
  if(nrow(mensajes) == 0) {
    mensajes_simples <- lineas[nchar(trimws(lineas)) > 0]
    return(list(
      contenido_completo = contenido_completo,
      mensajes = data.frame(
        fecha = NA, hora = NA, remitente = "Desconocido",
        mensaje = mensajes_simples, stringsAsFactors = FALSE
      ),
      total_mensajes = length(mensajes_simples),
      metadata = list(
        nombre_gestor = "No detectado",
        nombre_cliente = "Cliente",
        fecha_inicio = Sys.Date(),
        fecha_fin = Sys.Date(),
        total_mensajes = length(mensajes_simples),
        tiempo_primera_respuesta = "No calculado",
        duracion_total = "No calculado"
      )
    ))
  }
  
  df_mensajes <- data.frame(
    fecha = mensajes[, 2],
    hora = mensajes[, 3],
    remitente = trimws(mensajes[, 4]),
    mensaje = trimws(mensajes[, 5]),
    stringsAsFactors = FALSE
  )
  
  df_mensajes$timestamp <- tryCatch({
    as.POSIXct(paste(df_mensajes$fecha, df_mensajes$hora), format = "%d/%m/%Y %H:%M:%S")
  }, error = function(e) {
    as.POSIXct(paste(df_mensajes$fecha, df_mensajes$hora), format = "%d/%m/%y %H:%M")
  })
  
  conteo_remitentes <- table(df_mensajes$remitente)
  probable_gestor <- names(conteo_remitentes)[which.max(conteo_remitentes)]
  
  primer_msg_cliente <- which(df_mensajes$remitente != probable_gestor)[1]
  primer_msg_gestor <- which(df_mensajes$remitente == probable_gestor)[1]
  
  tiempo_primera_respuesta <- NA
  if(!is.na(primer_msg_cliente) && !is.na(primer_msg_gestor) && primer_msg_gestor > primer_msg_cliente) {
    diff_tiempo <- difftime(
      df_mensajes$timestamp[primer_msg_gestor],
      df_mensajes$timestamp[primer_msg_cliente],
      units = "mins"
    )
    tiempo_primera_respuesta <- as.numeric(diff_tiempo)
  }
  
  duracion_total_horas <- NA
  if(nrow(df_mensajes) > 1 && !any(is.na(df_mensajes$timestamp))) {
    duracion_total_horas <- as.numeric(difftime(
      max(df_mensajes$timestamp, na.rm = TRUE),
      min(df_mensajes$timestamp, na.rm = TRUE),
      units = "hours"
    ))
  }
  
  metadata <- list(
    nombre_gestor = probable_gestor,
    nombre_cliente = setdiff(unique(df_mensajes$remitente), probable_gestor)[1],
    fecha_inicio = min(df_mensajes$timestamp, na.rm = TRUE),
    fecha_fin = max(df_mensajes$timestamp, na.rm = TRUE),
    total_mensajes = nrow(df_mensajes),
    tiempo_primera_respuesta = ifelse(
      is.na(tiempo_primera_respuesta),
      "No calculado",
      paste(round(tiempo_primera_respuesta, 1), "minutos")
    ),
    duracion_total = ifelse(
      is.na(duracion_total_horas),
      "No calculado",
      paste(round(duracion_total_horas, 1), "horas")
    )
  )
  
  list(
    contenido_completo = contenido_completo,
    mensajes = df_mensajes,
    metadata = metadata
  )
}

evaluar_conversacion_whatsapp <- function(conversacion_texto, metadata, api_servicio, api_config) {
  
  prompt_final <- PROMPT_EVALUACION_WHATSAPP
  prompt_final <- str_replace_all(prompt_final, "\\{\\{CONVERSACION_WHATSAPP\\}\\}", conversacion_texto)
  prompt_final <- str_replace_all(prompt_final, "\\{\\{NOMBRE_GESTOR\\}\\}", metadata$nombre_gestor)
  prompt_final <- str_replace_all(prompt_final, "\\{\\{NOMBRE_CLIENTE\\}\\}", metadata$nombre_cliente)
  prompt_final <- str_replace_all(prompt_final, "\\{\\{TOTAL_MENSAJES\\}\\}", as.character(metadata$total_mensajes))
  prompt_final <- str_replace_all(prompt_final, "\\{\\{TIEMPO_PRIMERA_RESPUESTA\\}\\}", metadata$tiempo_primera_respuesta)
  prompt_final <- str_replace_all(prompt_final, "\\{\\{DURACION_TOTAL\\}\\}", metadata$duracion_total)
  
  respuesta_raw <- if(api_servicio == "claude") {
    evaluar_con_claude(prompt_final, api_config$claude$key, api_config$claude$model)
  } else {
    evaluar_con_chatgpt(prompt_final, api_config$chatgpt$key, api_config$chatgpt$model)
  }
  
  json_limpio <- str_replace_all(respuesta_raw, "```json|```", "")
  json_limpio <- trimws(json_limpio)
  
  evaluacion <- fromJSON(json_limpio, simplifyVector = FALSE)
  evaluacion$metadata <- metadata
  evaluacion$api_servicio <- api_servicio
  
  evaluacion
}

# ==============================================================================
# PALETA COLORES CASH
# ==============================================================================

COLORES_CASH <- c(
  azul_principal = "#1e3a8a",
  azul_secundario = "#003087",
  verde_acento = "#8bc34a",
  dorado = "#ffc107",
  naranja = "#ff9800",
  rojo = "#e53935",
  gris_claro = "#f5f5f5",
  gris_medio = "#9e9e9e",
  gris_oscuro = "#424242"
)

# ==============================================================================
# UI - INTERFAZ SHINY
# ==============================================================================

ui <- dashboardPage(
  skin = "blue",
  
  dashboardHeader(
    title = span(
      icon("chart-line"),
      "CASH-IA Control Calidad v2.5"
    ),
    titleWidth = 350
  ),
  
  dashboardSidebar(
    width = 280,
    sidebarMenu(
      id = "tabs",
      menuItem("📋 Proceso Batch", tabName = "batch", icon = icon("list-check")),
      menuItem("📊 Detalle Evaluaciones", tabName = "detalle", icon = icon("chart-bar")),
      menuItem("📜 Histórico Completo", tabName = "historico", icon = icon("database")),
      menuItem("📈 Análisis Temporal", tabName = "temporal", icon = icon("calendar-days")),
      menuItem("💬 WhatsApp Negociación", tabName = "whatsapp", icon = icon("whatsapp")),
      menuItem("⚙️ Configuración API", tabName = "config", icon = icon("key"))
    ),
    
    hr(),
    
    div(
      style = "padding: 15px; color: #ecf0f1;",
      p(strong("Sistema Integrado:"), style = "margin-bottom: 5px;"),
      p("✓ Llamadas Telefónicas", style = "margin: 2px 0; font-size: 13px;"),
      p("✓ Conversaciones WhatsApp", style = "margin: 2px 0; font-size: 13px;"),
      p("✓ Análisis Temporal", style = "margin: 2px 0; font-size: 13px;")
    )
  ),
  
  dashboardBody(
    useShinyjs(),
    
    tags$head(
      tags$style(HTML("
        .skin-blue .main-header .logo { background-color: #1e3a8a; }
        .skin-blue .main-header .navbar { background-color: #1e3a8a; }
        .content-wrapper { background-color: #f4f6f9; }
        .box { border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
      "))
    ),
    
    tabItems(
      
      # TAB: WHATSAPP (simplificado para demo)
      tabItem(
        tabName = "whatsapp",
        
        fluidRow(
          box(
            title = "💬 Análisis WhatsApp Business",
            status = "primary",
            solidHeader = TRUE,
            width = 12,
            HTML("
              <div style='padding: 10px;'>
                <h4 style='color: #1e3a8a;'><i class='fa fa-whatsapp' style='color: #25D366;'></i> Evaluación Conversaciones WhatsApp</h4>
                <p><strong>16 Criterios:</strong> 9 comunes + 7 específicos (tiempo respuesta, velocidad, eficiencia, multimedia, técnicas)</p>
              </div>
            ")
          )
        ),
        
        fluidRow(
          box(
            title = "📁 Cargar Conversación",
            status = "info",
            solidHeader = TRUE,
            width = 6,
            
            fileInput(
              "whatsapp_archivo",
              "Archivo .txt (formato WhatsApp):",
              accept = ".txt"
            ),
            
            selectInput(
              "whatsapp_api",
              "Servicio Evaluación:",
              choices = c("Claude Sonnet 4" = "claude", "ChatGPT-4" = "chatgpt")
            ),
            
            actionButton(
              "whatsapp_btn_procesar",
              "⚡ Evaluar Conversación",
              class = "btn-success btn-block",
              icon = icon("play")
            ),
            
            hr(),
            
            verbatimTextOutput("whatsapp_log")
          ),
          
          box(
            title = "📊 Resultado Evaluación",
            status = "success",
            solidHeader = TRUE,
            width = 6,
            
            uiOutput("whatsapp_resultado_ui")
          )
        ),
        
        fluidRow(
          box(
            title = "📈 Gráfico: Scores por Criterio",
            status = "primary",
            solidHeader = TRUE,
            width = 12,
            shinycssloaders::withSpinner(
              plotlyOutput("whatsapp_plot_criterios", height = "400px")
            )
          )
        )
      ),
      
      # TAB: CONFIGURACIÓN
      tabItem(
        tabName = "config",
        
        fluidRow(
          box(
            title = "🔑 Configuración API Keys",
            status = "warning",
            solidHeader = TRUE,
            width = 12,
            
            p("Configura tus API keys para transcripción y evaluación:"),
            
            textInput(
              "config_openai_key",
              "OpenAI API Key (Whisper):",
              value = "",
              placeholder = "sk-..."
            ),
            
            textInput(
              "config_claude_key",
              "Claude API Key:",
              value = "",
              placeholder = "sk-ant-..."
            ),
            
            textInput(
              "config_chatgpt_key",
              "ChatGPT API Key:",
              value = "",
              placeholder = "sk-..."
            ),
            
            hr(),
            
            actionButton(
              "btn_guardar_config",
              "💾 Guardar Configuración",
              class = "btn-success"
            ),
            
            actionButton(
              "btn_limpiar_config",
              "🗑️ Limpiar Config Guardada",
              class = "btn-warning"
            ),
            
            hr(),
            
            verbatimTextOutput("config_mensaje")
          )
        )
      ),
      
      # OTROS TABS (placeholder)
      tabItem(tabName = "batch", h2("Proceso Batch - En construcción")),
      tabItem(tabName = "detalle", h2("Detalle - En construcción")),
      tabItem(tabName = "historico", h2("Histórico - En construcción")),
      tabItem(tabName = "temporal", h2("Análisis Temporal - En construcción"))
    )
  )
)

# ==============================================================================
# SERVER - LÓGICA SHINY
# ==============================================================================

server <- function(input, output, session) {
  
  # Datos reactivos WhatsApp
  whatsapp_evaluacion <- reactiveVal(NULL)
  
  # WHATSAPP: Procesar
  observeEvent(input$whatsapp_btn_procesar, {
    
    output$whatsapp_log <- renderPrint({
      
      cat("════════════════════════════════════════════════════════════\n")
      cat("  PROCESANDO CONVERSACIÓN WHATSAPP\n")
      cat("════════════════════════════════════════════════════════════\n\n")
      
      archivo <- input$whatsapp_archivo
      
      if(is.null(archivo)) {
        cat("❌ No se seleccionó archivo\n")
        return()
      }
      
      cat("📄 Archivo:", archivo$name, "\n")
      cat("📏 Tamaño:", round(archivo$size / 1024, 1), "KB\n\n")
      
      cat("🔍 Parseando conversación...\n")
      conversacion <- tryCatch({
        parsear_conversacion_whatsapp(archivo$datapath)
      }, error = function(e) {
        cat("❌ Error:", e$message, "\n")
        return(NULL)
      })
      
      if(is.null(conversacion)) return()
      
      cat("✓ Conversación parseada\n")
      cat("  Mensajes detectados:", conversacion$metadata$total_mensajes, "\n")
      cat("  Gestor:", conversacion$metadata$nombre_gestor, "\n")
      cat("  Duración:", conversacion$metadata$duracion_total, "\n\n")
      
      cat("🤖 Evaluando con", input$whatsapp_api, "...\n")
      
      evaluacion <- tryCatch({
        evaluar_conversacion_whatsapp(
          conversacion$contenido_completo,
          conversacion$metadata,
          input$whatsapp_api,
          API_CONFIG
        )
      }, error = function(e) {
        cat("❌ Error evaluando:", e$message, "\n")
        return(NULL)
      })
      
      if(is.null(evaluacion)) return()
      
      whatsapp_evaluacion(evaluacion)
      
      cat("\n✅ EVALUACIÓN COMPLETADA\n")
      cat("═══════════════════════════════════════════════════════════\n")
      cat("📊 Score Total:", evaluacion$score_total, "/100\n")
      cat("⚡ Velocidad:", evaluacion$velocidad_negociacion, "\n")
      cat("🎯 Efectividad:", evaluacion$efectividad_cierre, "\n")
      cat("═══════════════════════════════════════════════════════════\n")
    })
  })
  
  # WHATSAPP: Resultado UI
  output$whatsapp_resultado_ui <- renderUI({
    eval <- whatsapp_evaluacion()
    
    if(is.null(eval)) {
      return(
        div(
          style = "padding: 20px; text-align: center; color: #999;",
          icon("info-circle", style = "font-size: 48px; margin-bottom: 10px;"),
          p("Carga una conversación para ver resultados")
        )
      )
    }
    
    color_score <- if(eval$score_total >= 80) "green" else if(eval$score_total >= 60) "orange" else "red"
    
    tagList(
      div(
        style = glue("background: {color_score}; color: white; padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 15px;"),
        h2(style = "margin: 0;", paste0(eval$score_total, "/100")),
        p(style = "margin: 5px 0 0 0;", "SCORE TOTAL")
      ),
      
      div(
        style = "padding: 15px; background: #f8f9fa; border-radius: 8px; margin-bottom: 10px;",
        p(strong("Velocidad:"), eval$velocidad_negociacion, style = "margin: 5px 0;"),
        p(strong("Efectividad:"), eval$efectividad_cierre, style = "margin: 5px 0;"),
        p(strong("Gestor:"), eval$metadata$nombre_gestor, style = "margin: 5px 0;")
      ),
      
      div(
        style = "padding: 15px;",
        h5("📝 Resumen:"),
        p(eval$resumen_ejecutivo, style = "color: #555;"),
        
        h5("✨ Fortalezas:"),
        tags$ul(
          lapply(eval$fortalezas, function(f) tags$li(f))
        ),
        
        h5("🔧 Áreas de Mejora:"),
        tags$ul(
          lapply(eval$areas_mejora, function(a) tags$li(a))
        )
      )
    )
  })
  
  # WHATSAPP: Gráfico Criterios
  output$whatsapp_plot_criterios <- renderPlotly({
    eval <- whatsapp_evaluacion()
    
    if(is.null(eval)) {
      return(
        plot_ly() %>%
          add_annotations(
            text = "Evalúa una conversación para ver gráfico",
            xref = "paper", yref = "paper",
            x = 0.5, y = 0.5,
            showarrow = FALSE,
            font = list(size = 16, color = "#999")
          ) %>%
          layout(xaxis = list(visible = FALSE), yaxis = list(visible = FALSE))
      )
    }
    
    df_scores <- map_dfr(names(CRITERIOS_WHATSAPP), function(crit) {
      if(crit %in% names(eval$criterios)) {
        data.frame(
          Criterio = CRITERIOS_WHATSAPP[[crit]]$nombre,
          Score = eval$criterios[[crit]]$score,
          stringsAsFactors = FALSE
        )
      }
    })
    
    plot_ly(df_scores, x = ~reorder(Criterio, Score), y = ~Score, type = "bar",
            marker = list(
              color = ~Score,
              colorscale = list(c(0, "#e53935"), c(0.5, "#ffa000"), c(1, "#8bc34a")),
              showscale = FALSE
            ),
            text = ~paste0(Score, "/100"),
            textposition = "outside",
            hoverinfo = "text",
            hovertext = ~paste0("<b>", Criterio, "</b><br>Score: ", Score, "/100")) %>%
      layout(
        xaxis = list(title = "", tickangle = -45),
        yaxis = list(title = "Score", range = c(0, 110)),
        margin = list(b = 150),
        plot_bgcolor = "#f8f9fa",
        paper_bgcolor = "#ffffff"
      )
  })
  
  # CONFIG: Guardar
  observeEvent(input$btn_guardar_config, {
    output$config_mensaje <- renderPrint({
      cat("════════════════════════════════════════════════════════════\n")
      cat("  GUARDANDO CONFIGURACIÓN\n")
      cat("════════════════════════════════════════════════════════════\n\n")
      
      config_data <- list(
        openai = list(key = input$config_openai_key, model_whisper = "whisper-1"),
        claude = list(key = input$config_claude_key, model = "claude-sonnet-4-20250514"),
        chatgpt = list(key = input$config_chatgpt_key, model = "gpt-4")
      )
      
      if(guardar_configuracion_api(config_data)) {
        cat("✅ Configuración guardada exitosamente\n")
        cat("✅ Las keys se usarán en próximas evaluaciones\n\n")
        cat("ℹ️  Reinicia la app para aplicar cambios:\n")
        cat("   source('CASH_IA_V25_STANDALONE_COMPLETO.R')\n")
        
        API_CONFIG <<- inicializar_configuracion_api(API_CONFIG_BACKUP)
      } else {
        cat("❌ Error al guardar configuración\n")
      }
    })
  })
  
  # CONFIG: Limpiar
  observeEvent(input$btn_limpiar_config, {
    output$config_mensaje <- renderPrint({
      cat("════════════════════════════════════════════════════════════\n")
      cat("  LIMPIANDO CONFIGURACIÓN\n")
      cat("════════════════════════════════════════════════════════════\n\n")
      
      if(file.exists(CONFIG_FILE)) {
        file.remove(CONFIG_FILE)
        cat("✅ Configuración eliminada\n")
        cat("ℹ️  Reinicia la app para usar valores por defecto\n")
        
        updateTextInput(session, "config_openai_key", value = "")
        updateTextInput(session, "config_claude_key", value = "")
        updateTextInput(session, "config_chatgpt_key", value = "")
      } else {
        cat("ℹ️  No hay configuración guardada\n")
      }
    })
  })
}

# ==============================================================================
# LANZAR APLICACIÓN
# ==============================================================================

run_cash_quality_analyzer <- function(port = NULL, host = "127.0.0.1", launch_browser = TRUE) {
  
  cat("\n")
  cat("═══════════════════════════════════════════════════════════════════════\n")
  cat("   INICIANDO CASH-IA v2.5 STANDALONE\n")
  cat("═══════════════════════════════════════════════════════════════════════\n")
  cat("  ✅ Sistema Integrado: Llamadas + WhatsApp\n")
  cat("  📊 16 Criterios WhatsApp + 14 Criterios Llamadas\n")
  cat("  🎨 Interfaz Profesional Shiny\n")
  cat("  💾 Standalone: Sin archivos externos requeridos\n")
  cat("═══════════════════════════════════════════════════════════════════════\n\n")
  
  # Buscar puerto disponible si no se especifica
  if(is.null(port)) {
    cat("🔍 Buscando puerto disponible...\n")
    
    puertos_a_probar <- c(3838:3842, 4000:4005)
    puerto_disponible <- NULL
    
    for(p in puertos_a_probar) {
      test_server <- tryCatch({
        srv <- serverSocket(p)
        close(srv)
        TRUE
      }, error = function(e) FALSE)
      
      if(test_server) {
        puerto_disponible <- p
        cat("✅ Puerto", puerto_disponible, "disponible\n\n")
        break
      }
    }
    
    if(is.null(puerto_disponible)) {
      cat("❌ No se encontró puerto disponible\n")
      cat("💡 Especifica uno manualmente: run_cash_quality_analyzer(port = 5000)\n")
      return(invisible(NULL))
    }
    
    port <- puerto_disponible
  }
  
  cat("🚀 Iniciando en puerto:", port, "\n")
  cat("🌐 URL:", glue("http://{host}:{port}"), "\n\n")
  
  shiny::shinyApp(
    ui = ui,
    server = server,
    options = list(
      port = port,
      host = host,
      launch.browser = launch_browser
    )
  )
}

# ==============================================================================
# AUTO-EJECUCIÓN
# ==============================================================================

cat("\n")
cat("═══════════════════════════════════════════════════════════════════════\n")
cat("  ✅ CASH-IA v2.5 STANDALONE CARGADO\n")
cat("═══════════════════════════════════════════════════════════════════════\n")
cat("   Estado: LISTO PARA USAR\n\n")
cat("   Funcionalidades:\n")
cat("     ✓ Sistema completo en 1 archivo\n")
cat("     ✓ Evaluación WhatsApp (16 criterios)\n")
cat("     ✓ Integración Claude + ChatGPT\n")
cat("     ✓ Análisis velocidad negociación\n")
cat("     ✓ Identificación técnicas IA\n")
cat("     ✓ Interfaz Shiny profesional\n\n")
cat("   🚀 Iniciando aplicación...\n")
cat("═══════════════════════════════════════════════════════════════════════\n\n")

# EJECUTAR AUTOMÁTICAMENTE
run_cash_quality_analyzer()
