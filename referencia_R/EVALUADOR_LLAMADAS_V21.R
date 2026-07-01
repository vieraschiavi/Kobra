################################################################################
# CASH-IA Control de Calidad V2.0 PROFESSIONAL + GRÃFICOS MEJORADOS
# Octubre 2025 - MartÃ­n Viera - CASH Uruguay BI
# VERSIÃ“N V20 - 4500+ LÃNEAS - GRÃFICOS EVOLUCION MEJORADOS + HISTÃ“RICO CRITERIOS
################################################################################

################################################################################
# MEJORAS V20:
# â–ª CorrecciÃ³n error 'spec' de stats (eliminado conflicted package)
# â–ª GrÃ¡ficos de evoluciÃ³n del gestor MEJORADOS visualmente
# â–ª HistÃ³rico por criterio individual mantenido
# â–ª GrÃ¡fico 3D de evoluciÃ³n por gestor + criterio + mes
# â–ª Mapa de calor (heatmap) de rendimiento por gestor/criterio
# â–ª GrÃ¡fico de tendencia con regresiÃ³n lineal
# â–ª Dashboard ejecutivo mejorado con gradientes y animaciones
# â–ª Paleta de colores CASH corporativa enriquecida
################################################################################

# Limpiar workspace
rm(list = ls())
gc()

cat("\n")
cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n")
cat("  CASH-IA Control de Calidad v2.0 PROFESSIONAL - GRÃFICOS MEJORADOS\n")
cat("  Sistema de EvaluaciÃ³n Calibrado + HistÃ³rico de Criterios\n")
cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n")

# ==============================================================================
# BLOQUE 1: INSTALACIÃ“N Y CARGA DE PAQUETES (CORRECCIÃ“N SIN CONFLICTED)
# ==============================================================================

if (!require("pacman", quietly = TRUE)) {
  install.packages("pacman", repos = "https://cran.r-project.org")
}

# Cargar paquetes SIN conflicted para evitar error de stats::spec
suppressPackageStartupMessages({
  pacman::p_load(
    # Core
    dplyr, tidyr, stringr, lubridate, glue, purrr, data.table,
    # Audio
    av, tuneR,
    # APIs
    httr, jsonlite, base64enc,
    # Shiny
    shiny, shinydashboard, shinyWidgets, shinycssloaders, shinyjs,
    # VisualizaciÃ³n
    ggplot2, plotly, scales, viridis, RColorBrewer,
    # Tablas
    DT, kableExtra,
    # Export
    openxlsx, officer,
    # Utilidades
    progress, fs, digest, logger
  )
})

# Resolver conflictos MANUALMENTE (sin usar conflicted package)
filter <- dplyr::filter
select <- dplyr::select
mutate <- dplyr::mutate
arrange <- dplyr::arrange
count <- dplyr::count
lag <- dplyr::lag
rename <- dplyr::rename

options(
  scipen = 999,
  stringsAsFactors = FALSE,
  encoding = "UTF-8",
  shiny.maxRequestSize = 150*1024^2,
  digits = 2,
  OutDec = ".",
  big.mark = ""
)

set.seed(42)

cat("âœ“ Paquetes cargados sin conflictos\n\n")

# ==============================================================================
# BLOQUE 2: CONFIGURACIÃ“N API Y COLORES CORPORATIVOS ENRIQUECIDOS
# ==============================================================================

API_CONFIG <- list(
  claude = list(
    key = "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",
    model = "claude-sonnet-4-20250514",
    endpoint = "https://api.anthropic.com/v1/messages",
    max_tokens = 4096,
    temperature = 0.3
  ),
  openai = list(
    key = "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",
    model = "whisper-1",
    endpoint_whisper = "https://api.openai.com/v1/audio/transcriptions"
  )
)

# Logo CASH embebido en base64
LOGO_CASH_BASE64 <- "UklGRngGAABXRUJQVlA4WAoAAAAgAAAAfwAAKwAASUNDUMgBAAAAAAHIAAAAAAQwAABtbnRyUkdCIFhZWiAH4AABAAEAAAAAAABhY3NwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAA9tYAAQAAAADTLQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAlkZXNjAAAA8AAAACRyWFlaAAABFAAAABRnWFlaAAABKAAAABRiWFlaAAABPAAAABR3dHB0AAABUAAAABRyVFJDAAABZAAAAChnVFJDAAABZAAAAChiVFJDAAABZAAAAChjcHJ0AAABjAAAADxtbHVjAAAAAAAAAAEAAAAMZW5VUwAAAAgAAAAcAHMAUgBHAEJYWVogAAAAAAAAb6IAADj1AAADkFhZWiAAAAAAAABimQAAt4UAABjaWFlaIAAAAAAAACSgAAAPhAAAts9YWVogAAAAAAAA9tYAAQAAAADTLXBhcmEAAAAAAAQAAAACZmYAAPKnAAANWQAAE9AAAApbAAAAAAAAAABtbHVjAAAAAAAAAAEAAAAMZW5VUwAAACAAAAAcAEcAbwBvAGcAbABlACAASQBuAGMALgAgADIAMAAxADZWUDggigQAADAYAJ0BKoAALAA+SRyKRCKhoRv8BKwoBIS2AGLigBrbXZPNtsT9M/AnEdl96evw/2W/BzmU+nh5jf1g/WD3iPQf+qvsAf0j/OdYB6AH7Vel9+3Hwg/tB+5ntWZiN2gV3e+nK44O6TjH56Emhh6ZTbOc4BSiH62+MQb+jJ/HeULSnV7wcAnOfZR7nugDAUm52n7e7BMb4UEOhuxIvT6jVzdXFWphC+/JM04DoIDy8oKymG2ZHvyfomQR+HtqQaMvvtvytOn6lyXLIAwA/v0+AbYiYAbe52Zhzpta0AjHVhp55VAlQiA/4QOKYOjd4eemrFGSV1Ntxfkz9nkJeiwjunliuYbrk9H40n2uprD//OyPExNyhhw2RDWSMQB1HdkTI2LPYIWFDg+0kERX3xIjnYk7cvlN9DYwuClLn4wGoJmnahzTrqcat2T7PG0mvcDQmXWgxouzt5rRIoXRCLSxRZW/793hz6tGGaLUE7YP18v1r4nVRENl3HhT2ua8XzU50s8c+IQWaf/1V2xhbBe5pR43BQsD6O6yHf8fW0T4+EkUUq0L9zSgbvHGmnO1z7cm8m0o/qPxoWVvvv0wbagBgup9NVjKkbyY/DubZ5P4OX6o+aiS38n3/v1K9a2wWnG2mgQeKnLqBFUykMdIm0Hy7Y8kEDT/2tjLBtW8MUstOJhB8EmVsJcror9x5iU+Movq+cf3hdxEWimsDaae1tq3xU8U9/+7IuuHHTSge5pV4Jd94HyMQLIJaOz2r9TiLKsU5XPXCbZwRC/8vyUXbnHUWqi4OWGh/d6RjpUv5rfZVBgFlSgghkEivqWUOSRcFZRUbYTLOs6dQ8YFtx+HiGoLvIamZs7fafrF1KHLAQzzXajrm3DNmwLfmx2vPxyOjZsG9v9DwED4jVa2yx9WQegN9GUtX3NGDk2yDhjnDuxwdv7JNU2g9+hsyEPtkXgzZBS2+dwqQONPOCeINdlxZOoDBnRPWq5/+xbNVSaDsRLyqKucN7rpgcu3ZkBAAI7mTqr8joMBfNLX8/7WFzYq/KYT9+UD6eJpTuF8h5HMOcsGOxxgnaUfMaoUe9qn5vQslpEEOg3s5jNqGgIPs0xO/1Yf8I+L8DkHPsJxqP6UgGa9dDW06sdL2NGvSu9G6Iu/Vfb/5yGjQ1FIZ7yepMidgZ+NI7fMZDVMekEWSrakJs4Q1pbmswrVgN0ku2qnDNPRfuWPyYVHTu9gYN/bCQmi2VcqJamXKv15QM2ed+2+/22Garr5DvPJoVu/GXyyHxuUwR7TlSOlUu59BCX1hO6HMDSvWvT37GFUztabFZvlNQ9eF5JZzuSNAGbJJQ09tBRbKMCHX1SaDFrlCIXfxVnv/HlaaHv4tKCCFOp/PmtAPYmuM8lJCWCr54FPTMTfAotFA/r6YbgNNAC1eXCv/+mrf9Ludn04+fl3sIkCBc9d6dGBnIVJwpnKpTs5g833BLsHF4vEY9PSMutd4XU23TNXE6IbvcwwvQHSJWHJJXDWpZfFiEBRxwXWzXKv67DrN4dFVJEHwC07jhk15SoAAAA="

# Paleta CASH corporativa enriquecida con gradientes
COLORES_CASH <- list(
  # Colores principales
  azul_principal = "#003087",
  azul_claro = "#00A8E1",
  dorado = "#FFB81C",
  verde = "#28a745",
  amarillo = "#ffc107",
  rojo = "#dc3545",
  gris = "#6c757d",
  
  # Gradientes azules
  azul_oscuro = "#001952",
  azul_medio = "#005eb8",
  azul_suave = "#7fc3ec",
  azul_palido = "#d4ebf7",
  
  # Gradientes dorados
  oro_oscuro = "#d89000",
  oro_claro = "#ffd666",
  
  # Escala de grises
  gris_oscuro = "#343a40",
  gris_medio = "#6c757d",
  gris_claro = "#adb5bd",
  gris_suave = "#e9ecef",
  
  # SemÃ¡foro extendido
  verde_oscuro = "#1e7e34",
  verde_claro = "#8bc34a",
  amarillo_oscuro = "#e0a800",
  naranja = "#ff9800",
  rojo_claro = "#e57373"
)

# Paleta para grÃ¡ficos multi-gestor (18 colores distintos)
PALETA_GESTORES <- c(
  '#003087', '#00A8E1', '#FFB81C', '#28a745', '#dc3545',
  '#9c27b0', '#ff5722', '#00bcd4', '#8bc34a', '#ff9800',
  '#3f51b5', '#e91e63', '#009688', '#ffeb3b', '#795548',
  '#607d8b', '#4caf50', '#f44336'
)

# Paleta para criterios (14 colores)
PALETA_CRITERIOS <- c(
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
  '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
  '#aec7e8', '#ffbb78', '#98df8a', '#ff9896'
)

cat("âœ“ ConfiguraciÃ³n y paletas de colores cargadas\n\n")

# ==============================================================================
# BLOQUE 2.5: FUNCIONES AUXILIARES PARA REPRODUCTOR DE AUDIO AVANZADO
# ==============================================================================

#' Crear directorio temporal para archivos de audio
crear_directorio_audio_temp <- function() {
  dir_temp <- file.path(tempdir(), "cash_audio_files")
  if (!dir.exists(dir_temp)) {
    dir.create(dir_temp, recursive = TRUE, showWarnings = FALSE)
    cat(sprintf("  â–¸ Directorio temporal de audio creado: %s\n", dir_temp))
  }
  return(dir_temp)
}

#' Guardar archivo de audio en ubicaciÃ³n temporal accesible
guardar_audio_temporal <- function(audio_path, id_eval = NULL) {
  tryCatch({
    
    if (is.null(id_eval) || is.na(id_eval) || id_eval == "") {
      id_eval <- digest::digest(paste0(audio_path, Sys.time()), algo = "md5", serialize = FALSE)
      id_eval <- substr(id_eval, 1, 12)
    }
    
    dir_temp <- crear_directorio_audio_temp()
    extension <- tools::file_ext(audio_path)
    if (extension == "") extension <- "mp3"
    
    nombre_archivo <- glue::glue("audio_{id_eval}.{extension}")
    path_destino <- file.path(dir_temp, nombre_archivo)
    
    file.copy(audio_path, path_destino, overwrite = TRUE)
    
    info_archivo <- file.info(path_destino)
    tamano_mb <- round(info_archivo$size / 1024^2, 2)
    
    duracion_seg <- NULL
    tryCatch({
      if (requireNamespace("av", quietly = TRUE)) {
        info_av <- av::av_media_info(path_destino)
        duracion_seg <- round(info_av$duration, 2)
      }
    }, error = function(e) {
      duracion_seg <<- NULL
    })
    
    return(list(
      success = TRUE,
      path_absoluto = path_destino,
      path_relativo = nombre_archivo,
      id_audio = id_eval,
      extension = extension,
      tamano_mb = tamano_mb,
      duracion_segundos = duracion_seg,
      formato_original = extension
    ))
    
  }, error = function(e) {
    return(list(
      success = FALSE,
      error = e$message,
      path_absoluto = NULL,
      path_relativo = NULL
    ))
  })
}

#' Formatear duraciÃ³n en MM:SS o HH:MM:SS
formatear_duracion <- function(segundos) {
  if (is.null(segundos) || is.na(segundos)) return("--:--")
  
  horas <- floor(segundos / 3600)
  minutos <- floor((segundos %% 3600) / 60)
  segs <- floor(segundos %% 60)
  
  if (horas > 0) {
    return(sprintf("%02d:%02d:%02d", horas, minutos, segs))
  } else {
    return(sprintf("%02d:%02d", minutos, segs))
  }
}

#' Convertir audio a base64 para embed en HTML
convertir_audio_a_base64 <- function(audio_path) {
  tryCatch({
    if (!file.exists(audio_path)) {
      return(NULL)
    }
    
    audio_raw <- readBin(audio_path, "raw", n = file.info(audio_path)$size)
    audio_base64 <- base64enc::base64encode(audio_raw)
    
    return(audio_base64)
    
  }, error = function(e) {
    cat(sprintf("Error al convertir audio a base64: %s\n", e$message))
    return(NULL)
  })
}

#' Generar reproductor HTML5 avanzado con controles profesionales
generar_reproductor_audio_avanzado <- function(audio_base64,
                                                duracion = NULL,
                                                formato = "mp3",
                                                id_player = "audio_player") {
  
  mime_type <- switch(tolower(formato),
                      "mp3" = "audio/mpeg",
                      "wav" = "audio/wav",
                      "m4a" = "audio/mp4",
                      "ogg" = "audio/ogg",
                      "flac" = "audio/flac",
                      "audio/mpeg")  # default
  
  duracion_formateada <- formatear_duracion(duracion)
  
  html_player <- tags$div(
    class = "audio-player-container",
    style = "margin: 20px 0; padding: 20px; background: linear-gradient(135deg, #003087 0%, #00A8E1 100%); border-radius: 15px; box-shadow: 0 8px 16px rgba(0,0,0,0.2);",
    
    # Header del reproductor
    tags$div(
      style = "display: flex; align-items: center; margin-bottom: 15px;",
      tags$div(
        style = "flex: 1;",
        tags$h4(
          style = "margin: 0; color: white; font-weight: 600; font-size: 16px;",
          icon("headphones"), " Reproductor de Audio"
        ),
        tags$p(
          style = "margin: 5px 0 0 0; color: rgba(255,255,255,0.8); font-size: 12px;",
          glue::glue("DuraciÃ³n: {duracion_formateada} | Formato: {toupper(formato)}")
        )
      ),
      tags$div(
        style = "text-align: right;",
        tags$span(
          style = "display: inline-block; padding: 5px 15px; background: rgba(255,255,255,0.2); border-radius: 20px; color: white; font-size: 11px; font-weight: 600;",
          icon("volume-up"), " HD"
        )
      )
    ),
    
    # Reproductor HTML5
    tags$audio(
      id = id_player,
      controls = "controls",
      preload = "metadata",
      style = "width: 100%; outline: none; border-radius: 8px; background: white;",
      tags$source(
        src = glue::glue("data:{mime_type};base64,{audio_base64}"),
        type = mime_type
      ),
      "Tu navegador no soporta el elemento de audio HTML5."
    ),
    
    # Controles adicionales
    tags$div(
      style = "margin-top: 15px; display: flex; gap: 10px; justify-content: space-between; align-items: center;",
      
      # Velocidad de reproducciÃ³n
      tags$div(
        style = "display: flex; align-items: center; gap: 8px;",
        tags$label(
          "for" = glue::glue("speed_control_{id_player}"),
          style = "color: white; font-size: 12px; font-weight: 500;",
          icon("tachometer-alt"), " Velocidad:"
        ),
        tags$select(
          id = glue::glue("speed_control_{id_player}"),
          style = "padding: 5px 10px; border-radius: 6px; border: none; background: white; color: #003087; font-weight: 600; cursor: pointer;",
          onchange = glue::glue("document.getElementById('{id_player}').playbackRate = this.value;"),
          tags$option(value = "0.5", "0.5x"),
          tags$option(value = "0.75", "0.75x"),
          tags$option(value = "1", selected = "selected", "1x"),
          tags$option(value = "1.25", "1.25x"),
          tags$option(value = "1.5", "1.5x"),
          tags$option(value = "2", "2x")
        )
      ),
      
      # BotÃ³n de descarga
      tags$a(
        href = glue::glue("data:{mime_type};base64,{audio_base64}"),
        download = glue::glue("audio_cash_{format(Sys.Date(), '%Y%m%d')}.{formato}"),
        style = "display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; background: #FFB81C; color: #003087; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 12px; transition: all 0.3s; box-shadow: 0 2px 4px rgba(0,0,0,0.2);",
        icon("download"), " Descargar"
      )
    ),
    
    # JavaScript para actualizaciÃ³n de duraciÃ³n en tiempo real
    tags$script(HTML(glue::glue("
      (function() {{
        const audio = document.getElementById('{id_player}');
        if (audio) {{
          audio.addEventListener('loadedmetadata', function() {{
            console.log('Audio cargado: duraciÃ³n = ' + audio.duration + 's');
          }});
        }}
      }})();
    ")))
  )
  
  return(html_player)
}

cat("âœ“ Funciones auxiliares de audio cargadas\n\n")

# ==============================================================================
# BLOQUE 3: CRITERIOS DE EVALUACIÃ“N CALIBRADOS
# ==============================================================================

CRITERIOS_EVALUACION <- list(
  version = "1.0_CALIBRADO",
  fecha_actualizacion = "2025-10-29",
  base_calibracion = "18 evaluaciones humanas reales (MarÃ­a JosÃ©, Ignacio, Wendy, etc.)",
  score_objetivo = list(min = 88, max = 95, promedio = 90.5),
  
  criterios = list(
    list(
      id = 1,
      nombre = "Escucha Activa",
      descripcion = "AtenciÃ³n plena, reformulaciÃ³n, no interrupciones",
      max_puntos = 15,
      promedio_humano = 13.2,
      pct_promedio = 88.0,
      peso_relativo = 0.15,
      critico = TRUE
    ),
    list(
      id = 2,
      nombre = "Registro/Datos",
      descripcion = "Completitud y exactitud de campos, actualizaciÃ³n inmediata",
      max_puntos = 10,
      promedio_humano = 8.9,
      pct_promedio = 89.0,
      peso_relativo = 0.10,
      critico = TRUE
    ),
    list(
      id = 3,
      nombre = "Deuda Total",
      descripcion = "Mencionar monto total, ofrecer facilidades, negociar descuentos",
      max_puntos = 5,
      promedio_humano = 4.6,
      pct_promedio = 92.0,
      peso_relativo = 0.05,
      critico = FALSE
    ),
    list(
      id = 4,
      nombre = "Apertura EmpÃ¡tica",
      descripcion = "Saludo cordial, tono cÃ¡lido, empatÃ­a desde inicio",
      max_puntos = 5,
      promedio_humano = 4.5,
      pct_promedio = 90.0,
      peso_relativo = 0.05,
      critico = FALSE
    ),
    list(
      id = 5,
      nombre = "IdentificaciÃ³n Clara",
      descripcion = "Nombre completo, empresa, propÃ³sito claro del contacto",
      max_puntos = 5,
      promedio_humano = 4.5,
      pct_promedio = 90.0,
      peso_relativo = 0.05,
      critico = FALSE
    ),
    list(
      id = 6,
      nombre = "Trato Personalizado",
      descripcion = "Uso del nombre del cliente, trato cordial, lenguaje adaptado",
      max_puntos = 5,
      promedio_humano = 4.4,
      pct_promedio = 88.0,
      peso_relativo = 0.05,
      critico = FALSE
    ),
    list(
      id = 7,
      nombre = "VerificaciÃ³n Datos",
      descripcion = "Confirmar identidad, domicilio, telÃ©fonos, informaciÃ³n personal",
      max_puntos = 10,
      promedio_humano = 8.8,
      pct_promedio = 88.0,
      peso_relativo = 0.10,
      critico = TRUE
    ),
    list(
      id = 8,
      nombre = "ComunicaciÃ³n Clara",
      descripcion = "Sin jerga tÃ©cnica, explicaciones simples, confirmar comprensiÃ³n",
      max_puntos = 5,
      promedio_humano = 4.5,
      pct_promedio = 90.0,
      peso_relativo = 0.05,
      critico = FALSE
    ),
    list(
      id = 9,
      nombre = "Cierre Efectivo",
      descripcion = "Resumen acuerdos, prÃ³ximos pasos, confirmaciÃ³n, despedida cordial",
      max_puntos = 5,
      promedio_humano = 4.5,
      pct_promedio = 90.0,
      peso_relativo = 0.05,
      critico = FALSE
    ),
    list(
      id = 10,
      nombre = "FormalizaciÃ³n Acuerdo",
      descripcion = "ConfirmaciÃ³n por email/SMS, detalle por escrito, comprobante",
      max_puntos = 5,
      promedio_humano = 4.3,
      pct_promedio = 86.0,
      peso_relativo = 0.05,
      critico = FALSE
    ),
    list(
      id = 11,
      nombre = "OrientaciÃ³n al Cliente",
      descripcion = "Soluciones reales, alternativas viables, disposiciÃ³n a ayudar",
      max_puntos = 5,
      promedio_humano = 4.6,
      pct_promedio = 92.0,
      peso_relativo = 0.05,
      critico = FALSE
    ),
    list(
      id = 12,
      nombre = "Profesionalismo",
      descripcion = "Tono respetuoso, control emocional, sin confrontaciones",
      max_puntos = 5,
      promedio_humano = 4.5,
      pct_promedio = 90.0,
      peso_relativo = 0.05,
      critico = FALSE
    ),
    list(
      id = 13,
      nombre = "Forma Completada",
      descripcion = "Todos los campos obligatorios, sin errores, firmada digitalmente",
      max_puntos = 15,
      promedio_humano = 13.5,
      pct_promedio = 90.0,
      peso_relativo = 0.15,
      critico = TRUE
    ),
    list(
      id = 14,
      nombre = "Cumplimiento Normativo",
      descripcion = "LOPD, Scripts obligatorios, polÃ­ticas internas, compliance",
      max_puntos = 5,
      promedio_humano = 4.5,
      pct_promedio = 90.0,
      peso_relativo = 0.05,
      critico = FALSE
    )
  )
)

# Validar suma de pesos = 1.0
suma_pesos <- sum(sapply(CRITERIOS_EVALUACION$criterios, function(c) c$peso_relativo))
if (abs(suma_pesos - 1.0) > 0.01) {
  warning(glue::glue("La suma de pesos relativos es {suma_pesos}, deberÃ­a ser 1.0"))
}

# Validar suma de puntos mÃ¡ximos = 100
suma_puntos <- sum(sapply(CRITERIOS_EVALUACION$criterios, function(c) c$max_puntos))
if (suma_puntos != 100) {
  warning(glue::glue("La suma de puntos mÃ¡ximos es {suma_puntos}, deberÃ­a ser 100"))
}

cat(glue::glue("âœ“ Criterios de evaluaciÃ³n cargados: {length(CRITERIOS_EVALUACION$criterios)} criterios totales\n"))
cat(glue::glue("âœ“ Puntos mÃ¡ximos totales: {suma_puntos}/100\n"))
cat(glue::glue("âœ“ Promedio objetivo: {CRITERIOS_EVALUACION$score_objetivo$promedio} pts\n\n"))

# ==============================================================================
# BLOQUE 4: FUNCIONES DE TRANSCRIPCIÃ“N MEJORADA
# ==============================================================================

#' Transcribir audio usando OpenAI Whisper con parÃ¡metros optimizados
transcribir_audio_whisper <- function(audio_path) {
  
  cat("\n")
  cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n")
  cat("  TRANSCRIPCIÃ“N DE AUDIO - WHISPER API MEJORADA\n")
  cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n")
  
  pb <- progress::progress_bar$new(
    format = "  [:bar] :percent | :eta restante | :what",
    total = 5,
    clear = FALSE,
    width = 60
  )
  
  resultado <- tryCatch({
    
    # Paso 1: Validar archivo
    pb$tick(tokens = 1, what = "Validando archivo...")
    
    if (!file.exists(audio_path)) {
      stop(glue::glue("El archivo no existe: {audio_path}"))
    }
    
    file_info <- file.info(audio_path)
    tamano_mb <- round(file_info$size / (1024^2), 2)
    
    cat(glue::glue("  â–¸ Archivo: {basename(audio_path)}\n"))
    cat(glue::glue("  â–¸ TamaÃ±o: {tamano_mb} MB\n"))
    
    # Paso 2: Preparar audio (conversiÃ³n si es necesario)
    pb$tick(tokens = 1, what = "Preparando audio...")
    
    extension <- tolower(tools::file_ext(audio_path))
    audio_prep <- audio_path
    
    # Si no es MP3, intentar convertir con av
    if (!extension %in% c("mp3", "wav", "m4a")) {
      cat("  â–¸ Formato no estÃ¡ndar detectado, intentando conversiÃ³n a WAV...\n")
      
      tryCatch({
        temp_wav <- tempfile(fileext = ".wav")
        av::av_audio_convert(audio_path, temp_wav, format = "wav", sample_rate = 16000)
        audio_prep <- temp_wav
        cat("  âœ“ Audio convertido a WAV\n")
      }, error = function(e) {
        cat(glue::glue("  âš  No se pudo convertir: {e$message}. Usando original.\n"))
      })
    }
    
    # Paso 3: Enviar a Whisper API
    pb$tick(tokens = 1, what = "Enviando a Whisper API...")
    
    response <- httr::POST(
      url = API_CONFIG$openai$endpoint_whisper,
      httr::add_headers(
        "Authorization" = paste("Bearer", API_CONFIG$openai$key),
        "Content-Type" = "multipart/form-data"
      ),
      body = list(
        file = httr::upload_file(audio_prep),
        model = API_CONFIG$openai$model,
        language = "es",
        response_format = "json",
        temperature = 0.0,
        # ParÃ¡metros adicionales para mejorar transcripciÃ³n
        prompt = "TranscripciÃ³n de llamada de cobranza en Uruguay. Cliente y gestor de cobranzas conversando sobre deuda."
      ),
      encode = "multipart",
      httr::timeout(300)
    )
    
    # Paso 4: Procesar respuesta
    pb$tick(tokens = 1, what = "Procesando respuesta...")
    
    if (httr::status_code(response) != 200) {
      error_content <- httr::content(response, "text", encoding = "UTF-8")
      stop(glue::glue("Error en Whisper API [{httr::status_code(response)}]: {error_content}"))
    }
    
    result <- httr::content(response, "parsed", encoding = "UTF-8")
    transcripcion_raw <- result$text
    
    if (is.null(transcripcion_raw) || nchar(transcripcion_raw) < 10) {
      stop("TranscripciÃ³n vacÃ­a o demasiado corta")
    }
    
    # Paso 5: Postprocesar y limpiar
    pb$tick(tokens = 1, what = "Finalizando...")
    
    # Limpiar transcripciÃ³n
    transcripcion_limpia <- transcripcion_raw %>%
      stringr::str_trim() %>%
      stringr::str_replace_all("\\s+", " ") %>%
      stringr::str_replace_all("\\[.*?\\]", "") %>%  # Eliminar [music], [noise], etc.
      stringr::str_replace_all("\\(.*?\\)", "")      # Eliminar (inaudible), etc.
    
    # Agregar puntuaciÃ³n bÃ¡sica si falta
    if (!stringr::str_detect(transcripcion_limpia, "[.!?]$")) {
      transcripcion_limpia <- paste0(transcripcion_limpia, ".")
    }
    
    # Calcular estadÃ­sticas
    palabras <- stringr::str_split(transcripcion_limpia, "\\s+")[[1]]
    num_palabras <- length(palabras)
    
    cat("\n")
    cat("  âœ“ TranscripciÃ³n completada exitosamente\n")
    cat(glue::glue("  â–¸ Palabras: {num_palabras}\n"))
    cat(glue::glue("  â–¸ Caracteres: {nchar(transcripcion_limpia)}\n"))
    cat(glue::glue("  â–¸ Vista previa: {substr(transcripcion_limpia, 1, 100)}...\n\n"))
    
    return(list(
      success = TRUE,
      transcripcion = transcripcion_limpia,
      num_palabras = num_palabras,
      num_caracteres = nchar(transcripcion_limpia),
      modelo = API_CONFIG$openai$model,
      timestamp = Sys.time()
    ))
    
  }, error = function(e) {
    cat("\n")
    cat("  âœ— Error en transcripciÃ³n:\n")
    cat(glue::glue("  {e$message}\n\n"))
    
    return(list(
      success = FALSE,
      transcripcion = paste("Error:", e$message),
      num_palabras = 0,
      num_caracteres = 0,
      modelo = API_CONFIG$openai$model,
      error = e$message,
      timestamp = Sys.time()
    ))
  })
  
  return(resultado)
}

cat("âœ“ Funciones de transcripciÃ³n cargadas\n\n")

# ==============================================================================
# BLOQUE 5: FUNCIÃ“N DE EVALUACIÃ“N CON CLAUDE CALIBRADA
# ==============================================================================

#' Evaluar transcripciÃ³n usando Claude Sonnet 4.5 con criterios calibrados
evaluar_con_claude_calibrado <- function(transcripcion, canal = "AUDIO") {
  
  cat("\n")
  cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n")
  cat("  EVALUACIÃ“N CON IA - CLAUDE SONNET 4.5 CALIBRADO\n")
  cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n")
  
  pb <- progress::progress_bar$new(
    format = "  [:bar] :percent | :eta restante | :what",
    total = 4,
    clear = FALSE,
    width = 60
  )
  
  resultado <- tryCatch({
    
    # Paso 1: Preparar contexto de calibraciÃ³n
    pb$tick(tokens = 1, what = "Preparando contexto...")
    
    contexto_calibracion <- paste0(
      "CONTEXTO DE CALIBRACIÃ“N IMPORTANTE:\n\n",
      "Has sido calibrado con 18 evaluaciones humanas reales realizadas por supervisores expertos de CASH Uruguay ",
      "(MarÃ­a JosÃ©, Ignacio, Wendy). El promedio real de estas evaluaciones es 90.5/100 puntos.\n\n",
      "Tu objetivo es REPLICAR el estilo de evaluaciÃ³n humana observado:\n",
      "- Rango tÃ­pico: 88-92 puntos (buenas gestiones)\n",
      "- Rango excelente: 93-95 puntos (gestiones excepcionales)\n",
      "- Rango regular: 80-87 puntos (gestiones con Ã¡reas de mejora)\n",
      "- Rango deficiente: <80 puntos (gestiones problemÃ¡ticas)\n\n",
      "CRITERIOS DE EVALUACIÃ“N (14 total, 100 puntos):\n\n"
    )
    
    for (i in seq_along(CRITERIOS_EVALUACION$criterios)) {
      crit <- CRITERIOS_EVALUACION$criterios[[i]]
      contexto_calibracion <- paste0(
        contexto_calibracion,
        glue::glue("{i}. {crit$nombre} ({crit$max_puntos} pts) {if(crit$critico) 'â–ª CRÃTICO' else ''}\n"),
        glue::glue("   DescripciÃ³n: {crit$descripcion}\n"),
        glue::glue("   Promedio humano observado: {crit$promedio_humano}/{crit$max_puntos} ({round(crit$pct_promedio,1)}%)\n\n")
      )
    }
    
    contexto_calibracion <- paste0(
      contexto_calibracion,
      "\nINSTRUCCIONES CRÃTICAS:\n",
      "1. Usa el promedio humano como REFERENCIA, no como lÃ­mite estricto\n",
      "2. En criterios CRÃTICOS (Escucha Activa, Registro, VerificaciÃ³n, Forma), sÃ© especialmente riguroso\n",
      "3. Otorga puntuaciones ligeramente por debajo del mÃ¡ximo (~88-92% del max) para gestiones buenas\n",
      "4. Reserva puntuaciones >95% del mÃ¡ximo solo para desempeÃ±o EXCEPCIONAL\n",
      "5. SÃ© especÃ­fico en las justificaciones: cita evidencia textual de la transcripciÃ³n\n",
      "6. En Ã¡reas de mejora, sugiere acciones concretas y realistas\n\n",
      "IMPORTANTE: El score final debe estar alineado con el patrÃ³n observado (promedio ~90.5 pts).\n",
      "Evita scores sistemÃ¡ticamente altos (>95) o bajos (<85) sin justificaciÃ³n clara.\n\n"
    )
    
    # Paso 2: Construir prompt de evaluaciÃ³n
    pb$tick(tokens = 1, what = "Construyendo prompt...")
    
    prompt_evaluacion <- paste0(
      contexto_calibracion,
      "â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n",
      "TRANSCRIPCIÃ“N A EVALUAR:\n",
      "â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n",
      transcripcion,
      "\n\n",
      "â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n",
      "TAREA:\n",
      "â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n",
      "EvalÃºa esta gestiÃ³n de cobranza siguiendo EXACTAMENTE los 14 criterios listados arriba.\n\n",
      "FORMATO DE RESPUESTA OBLIGATORIO (JSON vÃ¡lido):\n\n",
      "{\n",
      '  "criterios": [\n',
      '    {\n',
      '      "id": 1,\n',
      '      "nombre": "Escucha Activa",\n',
      '      "puntos_obtenidos": 12.5,\n',
      '      "justificacion": "El gestor demuestra... [citar evidencia especÃ­fica]"\n',
      '    },\n',
      '    ... (repetir para los 14 criterios)\n',
      '  ],\n',
      '  "score_total": 90.5,\n',
      '  "nivel_calidad": "BUENO",\n',
      '  "resumen": "Breve resumen ejecutivo de la evaluaciÃ³n",\n',
      '  "fortalezas": [\n',
      '    "Fortaleza 1 especÃ­fica con evidencia",\n',
      '    "Fortaleza 2...",\n',
      '    "Fortaleza 3..."\n',
      '  ],\n',
      '  "areas_mejora": [\n',
      '    "Ãrea de mejora 1 con acciÃ³n concreta",\n',
      '    "Ãrea de mejora 2...",\n',
      '    "Ãrea de mejora 3..."\n',
      '  ]\n',
      "}\n\n",
      "NIVELES DE CALIDAD:\n",
      "- EXCELENTE: â‰¥93 pts (solo para gestiones excepcionales)\n",
      "- BUENO: 85-92 pts (gestiones sÃ³lidas, mayorÃ­a de casos)\n",
      "- REGULAR: 70-84 pts (necesita mejoras)\n",
      "- DEFICIENTE: <70 pts (problemas graves)\n\n",
      "RESPONDE ÃšNICAMENTE CON EL JSON. No agregues texto antes ni despuÃ©s."
    )
    
    # Paso 3: Llamar a Claude API
    pb$tick(tokens = 1, what = "Consultando Claude API...")
    
    response <- httr::POST(
      url = API_CONFIG$claude$endpoint,
      httr::add_headers(
        "x-api-key" = API_CONFIG$claude$key,
        "anthropic-version" = "2023-06-01",
        "content-type" = "application/json"
      ),
      body = jsonlite::toJSON(list(
        model = API_CONFIG$claude$model,
        max_tokens = API_CONFIG$claude$max_tokens,
        temperature = API_CONFIG$claude$temperature,
        messages = list(
          list(
            role = "user",
            content = prompt_evaluacion
          )
        )
      ), auto_unbox = TRUE),
      encode = "json",
      httr::timeout(120)
    )
    
    # Paso 4: Procesar respuesta
    pb$tick(tokens = 1, what = "Procesando evaluaciÃ³n...")
    
    if (httr::status_code(response) != 200) {
      error_content <- httr::content(response, "text", encoding = "UTF-8")
      stop(glue::glue("Error en Claude API [{httr::status_code(response)}]: {error_content}"))
    }
    
    result <- httr::content(response, "parsed", encoding = "UTF-8")
    
    # Extraer texto de respuesta
    if (!is.null(result$content) && length(result$content) > 0) {
      texto_respuesta <- result$content[[1]]$text
    } else {
      stop("La respuesta de Claude no contiene texto")
    }
    
    # Limpiar y parsear JSON
    texto_limpio <- stringr::str_trim(texto_respuesta)
    texto_limpio <- stringr::str_replace_all(texto_limpio, "^```json\\s*", "")
    texto_limpio <- stringr::str_replace_all(texto_limpio, "\\s*```$", "")
    
    evaluacion_json <- jsonlite::fromJSON(texto_limpio, simplifyVector = FALSE)
    
    # Validar estructura
    if (is.null(evaluacion_json$criterios) || 
        length(evaluacion_json$criterios) != length(CRITERIOS_EVALUACION$criterios)) {
      stop(glue::glue("EvaluaciÃ³n incompleta: se esperaban {length(CRITERIOS_EVALUACION$criterios)} criterios, se recibieron {length(evaluacion_json$criterios)}"))
    }
    
    # Validar score total
    if (is.null(evaluacion_json$score_total) || !is.numeric(evaluacion_json$score_total)) {
      stop("Score total faltante o invÃ¡lido")
    }
    
    cat("\n")
    cat("  âœ“ EvaluaciÃ³n completada exitosamente\n")
    cat(glue::glue("  â–¸ Score Total: {evaluacion_json$score_total}/100 puntos\n"))
    cat(glue::glue("  â–¸ Nivel: {evaluacion_json$nivel_calidad}\n"))
    cat(glue::glue("  â–¸ Criterios evaluados: {length(evaluacion_json$criterios)}/14\n"))
    cat(glue::glue("  â–¸ Fortalezas identificadas: {length(evaluacion_json$fortalezas)}\n"))
    cat(glue::glue("  â–¸ Ãreas de mejora: {length(evaluacion_json$areas_mejora)}\n\n"))
    
    return(list(
      success = TRUE,
      evaluacion = evaluacion_json,
      modelo = API_CONFIG$claude$model,
      tokens_usados = if(!is.null(result$usage)) result$usage$total_tokens else NA,
      timestamp = Sys.time()
    ))
    
  }, error = function(e) {
    cat("\n")
    cat("  âœ— Error en evaluaciÃ³n:\n")
    cat(glue::glue("  {e$message}\n\n"))
    
    return(list(
      success = FALSE,
      evaluacion = NULL,
      modelo = API_CONFIG$claude$model,
      error = e$message,
      timestamp = Sys.time()
    ))
  })
  
  return(resultado)
}

cat("âœ“ FunciÃ³n de evaluaciÃ³n calibrada cargada\n\n")


# ==============================================================================
# BLOQUE 5B: FUNCION PLAN DE MEJORA POST-LLAMADA (V21)
# ==============================================================================

generar_plan_mejora_postcall <- function(eval_completa) {

  cat("\n===================================================\n")
  cat("  GENERANDO PLAN DE MEJORA POST-LLAMADA (V21)\n")
  cat("===================================================\n\n")

  tryCatch({

    criterios_texto <- ""
    criterios_debiles <- list()

    for (i in seq_along(eval_completa$criterios)) {
      crit_obj <- eval_completa$criterios[[i]]
      if (is.null(crit_obj$id) || is.null(crit_obj$nombre) || is.null(crit_obj$puntos_obtenidos)) next
      crit_config <- CRITERIOS_EVALUACION$criterios[[crit_obj$id]]
      if (is.null(crit_config)) next
      max_pts <- crit_config$max_puntos
      pct <- round((as.numeric(crit_obj$puntos_obtenidos) / max_pts) * 100, 1)
      criterios_texto <- paste0(
        criterios_texto,
        "- ", crit_obj$nombre, ": ", crit_obj$puntos_obtenidos, "/", max_pts,
        " pts (", pct, "%)\n",
        "  Justificacion: ", crit_obj$justificacion, "\n\n"
      )
      if (pct < 80) {
        criterios_debiles[[length(criterios_debiles) + 1]] <- list(
          nombre = crit_obj$nombre, obtenido = crit_obj$puntos_obtenidos,
          maximo = max_pts, pct = pct, justificacion = crit_obj$justificacion
        )
      }
    }

    # Ordenar debiles por pct asc
    if (length(criterios_debiles) > 1) {
      pcts_vec <- sapply(criterios_debiles, function(x) x$pct)
      criterios_debiles <- criterios_debiles[order(pcts_vec)]
    }

    # Completar hasta 3 si hay menos debiles
    if (length(criterios_debiles) < 3) {
      todos_criterios <- list()
      for (i in seq_along(eval_completa$criterios)) {
        crit_obj <- eval_completa$criterios[[i]]
        if (is.null(crit_obj$id)) next
        crit_config <- CRITERIOS_EVALUACION$criterios[[crit_obj$id]]
        if (is.null(crit_config)) next
        max_pts <- crit_config$max_puntos
        pct <- round((as.numeric(crit_obj$puntos_obtenidos) / max_pts) * 100, 1)
        todos_criterios[[length(todos_criterios) + 1]] <- list(
          nombre = crit_obj$nombre, obtenido = crit_obj$puntos_obtenidos,
          maximo = max_pts, pct = pct, justificacion = crit_obj$justificacion
        )
      }
      pcts_all <- sapply(todos_criterios, function(x) x$pct)
      todos_ord <- todos_criterios[order(pcts_all)]
      nombres_ya <- sapply(criterios_debiles, function(x) x$nombre)
      for (cand in todos_ord) {
        if (length(criterios_debiles) >= 3) break
        if (!(cand$nombre %in% nombres_ya)) {
          criterios_debiles[[length(criterios_debiles) + 1]] <- cand
          nombres_ya <- c(nombres_ya, cand$nombre)
        }
      }
    }

    top3 <- head(criterios_debiles, 3)

    gestor_full <- stringr::str_trim(paste(
      ifelse(is.null(eval_completa$gestor_nombre) || eval_completa$gestor_nombre == "", "el gestor", eval_completa$gestor_nombre),
      ifelse(is.null(eval_completa$gestor_apellido) || eval_completa$gestor_apellido == "", "", eval_completa$gestor_apellido)
    ))

    fortalezas_str <- paste(sapply(eval_completa$fortalezas, function(f) paste0("- ", f)), collapse = "\n")
    areas_str     <- paste(sapply(eval_completa$areas_mejora, function(a) paste0("- ", a)), collapse = "\n")
    transcripcion_preview <- substr(eval_completa$transcripcion, 1, 800)

    prompt_postcall <- paste0(
      "Eres un coach de calidad senior en CASH Uruguay, empresa de creditos y cobranzas.\n",
      "Genera un plan de mejora post-llamada concreto y accionable.\n\n",
      "DATOS DE LA EVALUACION:\n",
      "Gestor: ", gestor_full, "\n",
      "Canal: ", eval_completa$canal, "\n",
      "Score total: ", eval_completa$score_total, "/100 puntos\n",
      "Nivel: ", eval_completa$nivel_calidad, "\n\n",
      "DETALLE POR CRITERIO:\n", criterios_texto,
      "FORTALEZAS:\n", fortalezas_str, "\n\n",
      "AREAS DE MEJORA:\n", areas_str, "\n\n",
      "FRAGMENTO TRANSCRIPCION:\n", transcripcion_preview, "\n...\n\n",
      'Genera un JSON con esta estructura:\n',
      '{\n',
      '  "resumen_ejecutivo": "Parrafo 3-4 oraciones. Menciona score y nivel.",\n',
      '  "mensaje_gestor": "Mensaje 2-3 oraciones al gestor (usa su nombre). Motivacional pero honesto.",\n',
      '  "alerta_supervisor": false,\n',
      '  "motivo_alerta": "",\n',
      '  "top3_mejoras": [\n',
      '    {\n',
      '      "criterio": "Nombre del criterio",\n',
      '      "problema": "Que hizo mal especificamente (1 oracion)",\n',
      '      "accion_concreta": "Que debe hacer diferente (1 oracion)",\n',
      '      "frase_modelo": "Ejemplo textual de como decirlo en una llamada de cobranza",\n',
      '      "prioridad": "ALTA"\n',
      '    }\n',
      '  ],\n',
      '  "compromiso_proxima_llamada": "Una accion especifica y medible",\n',
      '  "recursos_sugeridos": ["Recurso 1", "Recurso 2"],\n',
      '  "reconocimiento": "Que hizo bien especificamente",\n',
      '  "score_tendencia": "MEJORA"\n',
      '}\n\n',
      "REGLAS: alerta_supervisor=true SOLO si score<80. top3_mejoras EXACTAMENTE 3 items. ",
      "frase_modelo = frase real usable en cobranza uruguaya. ",
      "score_tendencia: MEJORA/MANTIENE/REQUIERE_ATENCION. ",
      "RESPONDE UNICAMENTE CON EL JSON."
    )

    response <- httr::POST(
      url = API_CONFIG$claude$endpoint,
      httr::add_headers(
        "x-api-key"         = API_CONFIG$claude$key,
        "anthropic-version" = "2023-06-01",
        "content-type"      = "application/json"
      ),
      body = jsonlite::toJSON(list(
        model      = API_CONFIG$claude$model,
        max_tokens = 2048,
        temperature = 0.4,
        messages   = list(list(role = "user", content = prompt_postcall))
      ), auto_unbox = TRUE),
      encode = "json",
      httr::timeout(60)
    )

    if (httr::status_code(response) != 200) {
      err <- httr::content(response, "text", encoding = "UTF-8")
      stop(glue::glue("Error Claude API [{httr::status_code(response)}]: {err}"))
    }

    result_api <- httr::content(response, "parsed", encoding = "UTF-8")
    texto_raw  <- result_api$content[[1]]$text
    texto_clean <- stringr::str_trim(texto_raw)
    texto_clean <- stringr::str_replace_all(texto_clean, "^```json\\s*", "")
    texto_clean <- stringr::str_replace_all(texto_clean, "\\s*```$", "")
    plan_json  <- jsonlite::fromJSON(texto_clean, simplifyVector = FALSE)

    cat("  OK Plan generado exitosamente\n")
    cat(paste0("  Alerta supervisor: ", plan_json$alerta_supervisor, "\n"))
    cat(paste0("  Mejoras identificadas: ", length(plan_json$top3_mejoras), "\n\n"))

    return(list(
      success = TRUE,
      plan    = plan_json,
      timestamp = Sys.time(),
      gestor  = gestor_full,
      score   = eval_completa$score_total,
      nivel   = eval_completa$nivel_calidad
    ))

  }, error = function(e) {
    cat(paste0("  ERROR: ", e$message, "\n\n"))
    return(list(success = FALSE, error = e$message, timestamp = Sys.time()))
  })
}

cat("OK Funcion generar_plan_mejora_postcall() cargada (V21)\n\n")


# ==============================================================================
# BLOQUE 6: PERSISTENCIA Y HISTORIAL MEJORADO (CON CRITERIOS INDIVIDUALES)
# ==============================================================================

#' Guardar evaluaciÃ³n en historial con desglose de criterios individuales
#' Esta es la CLAVE para el grÃ¡fico de evoluciÃ³n por criterio
guardar_historial <- function(eval_data, archivo = "historial_evaluaciones.rds") {
  
  tryCatch({
    
    # Cargar historial existente o crear nuevo
    if (file.exists(archivo)) {
      historial <- readRDS(archivo)
    } else {
      historial <- data.frame()
    }
    
    # Preparar nueva fila con TODOS los criterios individuales
    nueva_fila <- data.frame(
      id_evaluacion = eval_data$id_evaluacion,
      timestamp = eval_data$timestamp,
      fecha = as.Date(eval_data$timestamp),
      hora = format(eval_data$timestamp, "%H:%M:%S"),
      mes_numero = as.integer(format(eval_data$timestamp, "%m")),
      mes_nombre = format(eval_data$timestamp, "%Y-%m"),
      mes_nombre_texto = format(eval_data$timestamp, "%B %Y"),
      
      # Identificadores
      id_llamada = ifelse(is.null(eval_data$id_llamada) || is.na(eval_data$id_llamada), 
                          eval_data$id_evaluacion, 
                          eval_data$id_llamada),
      gestor_nombre = ifelse(is.null(eval_data$gestor_nombre), "", eval_data$gestor_nombre),
      gestor_apellido = ifelse(is.null(eval_data$gestor_apellido), "", eval_data$gestor_apellido),
      gestor_completo = paste(
        ifelse(is.null(eval_data$gestor_nombre) || eval_data$gestor_nombre == "", "", eval_data$gestor_nombre),
        ifelse(is.null(eval_data$gestor_apellido) || eval_data$gestor_apellido == "", "", eval_data$gestor_apellido)
      ) %>% stringr::str_trim(),
      
      # Metadata
      canal = eval_data$canal,
      tiene_audio = !is.null(eval_data$audio_path),
      audio_path = ifelse(is.null(eval_data$audio_path), NA_character_, eval_data$audio_path),
      duracion_segundos = ifelse(is.null(eval_data$duracion_segundos), NA_real_, eval_data$duracion_segundos),
      
      # Resultados generales
      score_total = eval_data$score_total,
      nivel_calidad = eval_data$nivel_calidad,
      resumen = eval_data$resumen,
      
      # NOVEDAD V20: Scores individuales por criterio (14 columnas)
      score_criterio_01 = NA_real_,
      score_criterio_02 = NA_real_,
      score_criterio_03 = NA_real_,
      score_criterio_04 = NA_real_,
      score_criterio_05 = NA_real_,
      score_criterio_06 = NA_real_,
      score_criterio_07 = NA_real_,
      score_criterio_08 = NA_real_,
      score_criterio_09 = NA_real_,
      score_criterio_10 = NA_real_,
      score_criterio_11 = NA_real_,
      score_criterio_12 = NA_real_,
      score_criterio_13 = NA_real_,
      score_criterio_14 = NA_real_,
      
      # NOVEDAD V20: Porcentajes de cumplimiento por criterio
      pct_criterio_01 = NA_real_,
      pct_criterio_02 = NA_real_,
      pct_criterio_03 = NA_real_,
      pct_criterio_04 = NA_real_,
      pct_criterio_05 = NA_real_,
      pct_criterio_06 = NA_real_,
      pct_criterio_07 = NA_real_,
      pct_criterio_08 = NA_real_,
      pct_criterio_09 = NA_real_,
      pct_criterio_10 = NA_real_,
      pct_criterio_11 = NA_real_,
      pct_criterio_12 = NA_real_,
      pct_criterio_13 = NA_real_,
      pct_criterio_14 = NA_real_,
      
      # Metadata adicional
      num_fortalezas = length(eval_data$fortalezas),
      num_areas_mejora = length(eval_data$areas_mejora),
      transcripcion = ifelse(is.null(eval_data$transcripcion), "", eval_data$transcripcion),
      
      stringsAsFactors = FALSE
    )
    
    # Rellenar scores individuales por criterio
    if (!is.null(eval_data$criterios) && length(eval_data$criterios) > 0) {
      for (i in seq_along(eval_data$criterios)) {
        crit <- eval_data$criterios[[i]]
        id_crit <- as.integer(crit$id)
        
        if (id_crit >= 1 && id_crit <= 14) {
          col_score <- paste0("score_criterio_", sprintf("%02d", id_crit))
          col_pct <- paste0("pct_criterio_", sprintf("%02d", id_crit))
          
          nueva_fila[[col_score]] <- as.numeric(crit$puntos_obtenidos)
          
          # Calcular porcentaje
          max_pts <- CRITERIOS_EVALUACION$criterios[[id_crit]]$max_puntos
          nueva_fila[[col_pct]] <- round((as.numeric(crit$puntos_obtenidos) / max_pts) * 100, 2)
        }
      }
    }
    
    # Agregar al historial
    if (nrow(historial) == 0) {
      historial <- nueva_fila
    } else {
      # Asegurar mismas columnas
      cols_faltantes <- setdiff(names(nueva_fila), names(historial))
      if (length(cols_faltantes) > 0) {
        for (col in cols_faltantes) {
          historial[[col]] <- NA
        }
      }
      
      cols_faltantes <- setdiff(names(historial), names(nueva_fila))
      if (length(cols_faltantes) > 0) {
        for (col in cols_faltantes) {
          nueva_fila[[col]] <- NA
        }
      }
      
      historial <- rbind(historial, nueva_fila)
    }
    
    # Guardar
    saveRDS(historial, archivo)
    
    cat(glue::glue("  âœ“ EvaluaciÃ³n guardada en historial (Total: {nrow(historial)} registros)\n"))
    cat(glue::glue("  â–¸ Archivo: {archivo}\n"))
    cat(glue::glue("  â–¸ Scores por criterio guardados: {sum(!is.na(nueva_fila[, grep('score_criterio_', names(nueva_fila))]))}/14\n\n"))
    
    return(TRUE)
    
  }, error = function(e) {
    cat(glue::glue("  âœ— Error al guardar historial: {e$message}\n\n"))
    return(FALSE)
  })
}

#' Cargar historial de evaluaciones
cargar_historial <- function(archivo = "historial_evaluaciones.rds") {
  if (file.exists(archivo)) {
    historial <- readRDS(archivo)
    cat(glue::glue("  âœ“ Historial cargado: {nrow(historial)} evaluaciones\n\n"))
    return(historial)
  } else {
    cat("  â„¹ No existe historial previo\n\n")
    return(data.frame())
  }
}

cat("âœ“ Funciones de persistencia mejoradas cargadas (con criterios individuales)\n\n")

# ==============================================================================
# BLOQUE 7A: UI - INTERFAZ MEJORADA CON GRADIENTES Y DISEÃ‘O PROFESIONAL
# ==============================================================================

ui <- dashboardPage(
  
  skin = "blue",
  
  # HEADER
  dashboardHeader(
    title = HTML(paste0(
      '<span style="font-weight: 600; font-size: 18px;">',
      '<i class="fa fa-star"></i> CASH-IA v2.0</span>'
    )),
    titleWidth = 300,
    
    tags$li(
      class = "dropdown",
      style = "padding: 15px;",
      tags$span(
        style = "color: white; font-size: 13px; font-weight: 500;",
        icon("calendar-alt"),
        format(Sys.Date(), " %d/%m/%Y")
      )
    )
  ),
  
  # SIDEBAR
  dashboardSidebar(
    width = 300,
    
    sidebarMenu(
      id = "sidebar",
      
      menuItem(
        "â–ª Nueva EvaluaciÃ³n",
        tabName = "evaluacion",
        icon = icon("plus-circle"),
        badgeLabel = "START",
        badgeColor = "green"
      ),
      
      menuItem(
        "â–ª Dashboard Ejecutivo",
        tabName = "dashboard",
        icon = icon("chart-line"),
        badgeLabel = "HOT",
        badgeColor = "red"
      ),
      
      menuItem(
        "â–ª HistÃ³rico Completo",
        tabName = "historico",
        icon = icon("history"),
        badgeLabel = "NEW",
        badgeColor = "yellow"
      ),
      
      menuItem(
        "â–ª ConfiguraciÃ³n",
        tabName = "config",
        icon = icon("cog")
      ),
      
      br(),
      
      div(
        style = "padding: 20px; background: linear-gradient(135deg, rgba(0,48,135,0.1), rgba(0,168,225,0.1)); margin: 10px; border-radius: 10px; border-left: 4px solid #FFB81C;",
        tags$p(
          style = "color: #003087; font-weight: 600; margin: 0 0 8px 0; font-size: 12px;",
          icon("info-circle"), " INFO DEL SISTEMA"
        ),
        tags$p(
          style = "color: #666; font-size: 11px; margin: 0; line-height: 1.5;",
          "â–ª VersiÃ³n: 2.0 MEJORADA", tags$br(),
          "â–ª Criterios: 14 totales", tags$br(),
          "â–ª Score objetivo: 88-95 pts", tags$br(),
          "â–ª GrÃ¡ficos: EvoluciÃ³n + Criterios"
        )
      )
    )
  ),
  
  # BODY
  dashboardBody(
    
    # CSS Personalizado con gradientes profesionales
    tags$head(
      tags$style(HTML("
        /* Reset y Base */
        * {
          font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        body {
          background: linear-gradient(to right, #f8f9fa 0%, #e9ecef 100%);
        }
        
        /* Boxes mejoradas */
        .box {
          border-radius: 12px;
          box-shadow: 0 4px 12px rgba(0,0,0,0.08);
          transition: all 0.3s ease;
          border-top: 3px solid #003087;
        }
        
        .box:hover {
          box-shadow: 0 8px 20px rgba(0,0,0,0.12);
          transform: translateY(-2px);
        }
        
        .box-header {
          background: linear-gradient(135deg, #003087 0%, #00A8E1 100%);
          color: white !important;
          font-weight: 600;
          padding: 15px 20px;
          border-radius: 12px 12px 0 0;
        }
        
        .box-header .box-title {
          font-size: 16px;
          font-weight: 600;
          color: white !important;
        }
        
        /* Value Boxes mejoradas */
        .small-box {
          border-radius: 15px;
          box-shadow: 0 6px 16px rgba(0,0,0,0.1);
          transition: all 0.3s ease;
          position: relative;
          overflow: hidden;
        }
        
        .small-box:before {
          content: '';
          position: absolute;
          top: -50%;
          right: -50%;
          width: 200%;
          height: 200%;
          background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
          animation: pulse 3s infinite;
        }
        
        @keyframes pulse {
          0%, 100% { opacity: 0.3; transform: scale(1); }
          50% { opacity: 0.6; transform: scale(1.05); }
        }
        
        .small-box:hover {
          transform: translateY(-5px);
          box-shadow: 0 10px 24px rgba(0,0,0,0.15);
        }
        
        .small-box h3 {
          font-size: 42px;
          font-weight: 700;
          text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        }
        
        .small-box p {
          font-size: 14px;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        
        .small-box .icon {
          font-size: 90px;
          opacity: 0.3;
        }
        
        /* Botones profesionales */
        .btn {
          border-radius: 8px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          transition: all 0.3s ease;
          box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        }
        
        .btn:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }
        
        .btn-primary {
          background: linear-gradient(135deg, #003087 0%, #00A8E1 100%);
          border: none;
        }
        
        .btn-success {
          background: linear-gradient(135deg, #28a745 0%, #8bc34a 100%);
          border: none;
        }
        
        .btn-warning {
          background: linear-gradient(135deg, #ffc107 0%, #FFB81C 100%);
          border: none;
          color: #003087;
        }
        
        .btn-danger {
          background: linear-gradient(135deg, #dc3545 0%, #e57373 100%);
          border: none;
        }
        
        /* Inputs mejorados */
        .form-control, .selectize-input {
          border-radius: 8px;
          border: 2px solid #e9ecef;
          transition: all 0.3s ease;
        }
        
        .form-control:focus, .selectize-input.focus {
          border-color: #00A8E1;
          box-shadow: 0 0 0 0.2rem rgba(0,168,225,0.15);
        }
        
        /* Tablas DataTable */
        .dataTables_wrapper {
          border-radius: 12px;
          overflow: hidden;
        }
        
        table.dataTable thead th {
          background: linear-gradient(135deg, #003087 0%, #00A8E1 100%);
          color: white !important;
          font-weight: 600;
          padding: 15px 12px;
          border: none;
        }
        
        table.dataTable tbody tr:hover {
          background-color: rgba(0,168,225,0.05);
          transition: all 0.2s ease;
        }
        
        /* Sidebar mejorada */
        .sidebar-menu > li.active > a {
          background: linear-gradient(135deg, #003087 0%, #00A8E1 100%);
          border-left: 4px solid #FFB81C;
          font-weight: 600;
        }
        
        .sidebar-menu > li > a:hover {
          background-color: rgba(0,168,225,0.1);
          border-left: 4px solid #FFB81C;
        }
        
        /* Progress bars */
        .progress {
          height: 25px;
          border-radius: 12px;
          background-color: #e9ecef;
          box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .progress-bar {
          border-radius: 12px;
          background: linear-gradient(90deg, #28a745 0%, #8bc34a 100%);
          font-weight: 600;
          box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        /* Badges */
        .badge {
          border-radius: 12px;
          padding: 6px 12px;
          font-weight: 600;
          font-size: 11px;
          letter-spacing: 0.5px;
        }
        
        /* Scrollbars personalizados */
        ::-webkit-scrollbar {
          width: 10px;
          height: 10px;
        }
        
        ::-webkit-scrollbar-track {
          background: #f1f1f1;
          border-radius: 10px;
        }
        
        ::-webkit-scrollbar-thumb {
          background: linear-gradient(135deg, #003087 0%, #00A8E1 100%);
          border-radius: 10px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
          background: linear-gradient(135deg, #00A8E1 0%, #003087 100%);
        }
        
        /* Animaciones */
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        
        .box, .small-box {
          animation: fadeIn 0.5s ease-out;
        }
        
        /* Tooltips */
        .tooltip-inner {
          background-color: #003087;
          border-radius: 8px;
          padding: 10px 15px;
          font-size: 12px;
        }
        
        /* Loading spinners */
        .shiny-spinner-output-container {
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 300px;
        }
        
        .fa-spinner {
          color: #00A8E1;
        }
      "))
    ),
    
    useShinyjs(),
    
    tabItems(
      
      # ========================================================================
      # TAB 1: NUEVA EVALUACIÃ“N
      # ========================================================================
      
      tabItem(
        tabName = "evaluacion",
        
        fluidRow(
          column(
            width = 12,
            box(
              title = HTML("<i class='fa fa-plus-circle'></i> NUEVA EVALUACIÃ“N - CASH-IA v2.0"),
              width = NULL,
              solidHeader = TRUE,
              status = "primary",
              
              fluidRow(
                column(
                  width = 12,
                  div(
                    style = "background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 20px; border-radius: 12px; margin-bottom: 20px; border-left: 5px solid #2196F3;",
                    tags$h4(
                      style = "margin: 0 0 10px 0; color: #1976D2; font-weight: 600;",
                      icon("info-circle"), " InformaciÃ³n del Sistema"
                    ),
                    tags$p(
                      style = "margin: 0; color: #424242; line-height: 1.6;",
                      "â–ª Sistema calibrado con ", tags$strong("18 evaluaciones humanas reales"), tags$br(),
                      "â–ª Score objetivo: ", tags$strong("88-95 puntos"), " (Promedio: 90.5)", tags$br(),
                      "â–ª Total de criterios: ", tags$strong("14"), " (100 puntos totales)", tags$br(),
                      "â–ª Multicanal: ", tags$strong("Audio | WhatsApp | SMS | Texto")
                    )
                  )
                )
              ),
              
              fluidRow(
                column(
                  width = 6,
                  selectInput(
                    "canal_evaluacion",
                    label = div(icon("broadcast-tower"), strong(" Canal de ComunicaciÃ³n")),
                    choices = c(
                      "Audio (Llamada telefÃ³nica)" = "AUDIO",
                      "WhatsApp (Chat)" = "WHATSAPP",
                      "SMS (Mensaje texto)" = "SMS",
                      "Texto directo" = "TEXTO"
                    ),
                    selected = "AUDIO",
                    width = "100%"
                  )
                ),
                column(
                  width = 6,
                  textInput(
                    "id_llamada_input",
                    label = div(icon("hashtag"), strong(" ID de Llamada (Opcional)")),
                    value = "",
                    placeholder = "Ej: 12345, CALL-2024-001, etc.",
                    width = "100%"
                  )
                )
              ),
              
              fluidRow(
                column(
                  width = 6,
                  textInput(
                    "gestor_nombre",
                    label = div(icon("user"), strong(" Nombre del Gestor (Opcional)")),
                    value = "",
                    placeholder = "Ej: Juan, MarÃ­a, etc.",
                    width = "100%"
                  )
                ),
                column(
                  width = 6,
                  textInput(
                    "gestor_apellido",
                    label = div(icon("user-tag"), strong(" Apellido del Gestor (Opcional)")),
                    value = "",
                    placeholder = "Ej: PÃ©rez, GonzÃ¡lez, etc.",
                    width = "100%"
                  )
                )
              ),
              
              conditionalPanel(
                condition = "input.canal_evaluacion == 'AUDIO'",
                
                fluidRow(
                  column(
                    width = 12,
                    div(
                      style = "background: linear-gradient(135deg, #fff3cd 0%, #ffe89a 100%); padding: 15px; border-radius: 10px; margin: 15px 0; border-left: 5px solid #ff9800;",
                      tags$p(
                        style = "margin: 0; color: #856404; font-weight: 500;",
                        icon("headphones"), " Sube un archivo de audio para transcripciÃ³n y evaluaciÃ³n automÃ¡tica."
                      )
                    ),
                    fileInput(
                      "audio_file",
                      label = div(icon("file-audio"), strong(" Archivo de Audio")),
                      accept = c(".mp3", ".wav", ".m4a", ".ogg", ".flac"),
                      width = "100%",
                      buttonLabel = "Buscar archivo...",
                      placeholder = "NingÃºn archivo seleccionado"
                    )
                  )
                )
              ),
              
              conditionalPanel(
                condition = "input.canal_evaluacion != 'AUDIO'",
                
                fluidRow(
                  column(
                    width = 12,
                    div(
                      style = "background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); padding: 15px; border-radius: 10px; margin: 15px 0; border-left: 5px solid #4caf50;",
                      tags$p(
                        style = "margin: 0; color: #2e7d32; font-weight: 500;",
                        icon("keyboard"), " Pega o escribe la conversaciÃ³n completa para evaluaciÃ³n."
                      )
                    ),
                    textAreaInput(
                      "texto_conversacion",
                      label = div(icon("comments"), strong(" Texto de la ConversaciÃ³n")),
                      value = "",
                      placeholder = "Pega aquÃ­ el texto completo de la conversaciÃ³n (WhatsApp, SMS o transcripciÃ³n manual)...",
                      rows = 12,
                      width = "100%"
                    )
                  )
                )
              ),
              
              fluidRow(
                column(
                  width = 12,
                  div(
                    style = "text-align: center; margin-top: 30px;",
                    actionButton(
                      "btn_evaluar",
                      label = div(
                        icon("star", style = "font-size: 18px;"),
                        " EVALUAR CON IA",
                        style = "font-size: 16px; font-weight: 700; padding: 5px 15px;"
                      ),
                      class = "btn-primary",
                      style = "width: 400px; height: 60px; font-size: 18px; border-radius: 30px; box-shadow: 0 6px 20px rgba(0,48,135,0.3);"
                    )
                  )
                )
              )
            )
          )
        ),
        
        # Resultados (se mostrarÃ¡n dinÃ¡micamente)
        uiOutput("resultado_evaluacion")
      ),
      
      # ========================================================================
      # TAB 2: DASHBOARD EJECUTIVO MEJORADO
      # ========================================================================
      
      tabItem(
        tabName = "dashboard",
        
        # KPIs principales
        fluidRow(
          valueBoxOutput("kpi_total_evaluaciones", width = 3),
          valueBoxOutput("kpi_promedio_score", width = 3),
          valueBoxOutput("kpi_nivel_promedio", width = 3),
          valueBoxOutput("kpi_total_gestores", width = 3)
        ),
        
        # Filtros globales
        fluidRow(
          column(
            width = 12,
            box(
              title = HTML("<i class='fa fa-filter'></i> FILTROS GLOBALES"),
              width = NULL,
              solidHeader = TRUE,
              collapsible = TRUE,
              collapsed = FALSE,
              
              fluidRow(
                column(
                  width = 3,
                  selectInput(
                    "filtro_gestor_global",
                    label = "Gestor:",
                    choices = c("Todos"),
                    selected = "Todos",
                    width = "100%"
                  )
                ),
                column(
                  width = 3,
                  pickerInput(
                    "filtro_mes_global",
                    label = "Mes:",
                    choices = c("Todos"),
                    selected = "Todos",
                    multiple = FALSE,
                    options = list(
                      `live-search` = TRUE,
                      title = "Seleccionar mes..."
                    ),
                    width = "100%"
                  )
                ),
                column(
                  width = 3,
                  pickerInput(
                    "filtro_llamada_global",
                    label = "ID Llamada:",
                    choices = c("Todas"),
                    selected = "Todas",
                    multiple = FALSE,
                    options = list(
                      `live-search` = TRUE,
                      title = "Buscar llamada..."
                    ),
                    width = "100%"
                  )
                ),
                column(
                  width = 3,
                  div(
                    style = "margin-top: 25px;",
                    actionButton(
                      "btn_limpiar_filtros",
                      "Limpiar Filtros",
                      icon = icon("eraser"),
                      class = "btn-warning btn-block"
                    )
                  )
                )
              )
            )
          )
        ),
        
        # GrÃ¡ficos principales
        fluidRow(
          column(
            width = 6,
            box(
              title = HTML("<i class='fa fa-chart-line'></i> EVOLUCIÃ“N DEL SCORE TOTAL POR MES"),
              width = NULL,
              solidHeader = TRUE,
              status = "primary",
              shinycssloaders::withSpinner(
                plotlyOutput("grafico_evolucion_criterios", height = "400px"),
                type = 4,
                color = "#00A8E1"
              )
            )
          ),
          column(
            width = 6,
            box(
              title = HTML("<i class='fa fa-users'></i> COMPARATIVA DE GESTORES"),
              width = NULL,
              solidHeader = TRUE,
              status = "info",
              shinycssloaders::withSpinner(
                plotlyOutput("grafico_comparativa_gestores", height = "400px"),
                type = 4,
                color = "#00A8E1"
              )
            )
          )
        ),
        
        # NUEVO: GrÃ¡fico de evoluciÃ³n por gestor mejorado
        fluidRow(
          column(
            width = 12,
            box(
              title = HTML("<i class='fa fa-chart-area'></i> EVOLUCIÃ“N INDIVIDUAL POR GESTOR + PROMEDIO GENERAL"),
              width = NULL,
              solidHeader = TRUE,
              status = "success",
              collapsible = TRUE,
              collapsed = FALSE,
              shinycssloaders::withSpinner(
                plotlyOutput("grafico_evolucion_por_gestor_mejorado", height = "500px"),
                type = 4,
                color = "#28a745"
              )
            )
          )
        ),
        
        # NUEVO: Mapa de calor (heatmap) gestor x criterio
        fluidRow(
          column(
            width = 12,
            box(
              title = HTML("<i class='fa fa-th'></i> MAPA DE CALOR: RENDIMIENTO POR GESTOR Y CRITERIO"),
              width = NULL,
              solidHeader = TRUE,
              status = "warning",
              collapsible = TRUE,
              collapsed = TRUE,
              shinycssloaders::withSpinner(
                plotlyOutput("grafico_heatmap_gestor_criterio", height = "600px"),
                type = 4,
                color = "#ffc107"
              )
            )
          )
        ),
        
        # NUEVO: GrÃ¡fico de evoluciÃ³n por criterio individual
        fluidRow(
          column(
            width = 12,
            box(
              title = HTML("<i class='fa fa-chart-line'></i> EVOLUCIÃ“N DETALLADA POR CRITERIO INDIVIDUAL"),
              width = NULL,
              solidHeader = TRUE,
              status = "info",
              collapsible = TRUE,
              collapsed = TRUE,
              shinycssloaders::withSpinner(
                plotlyOutput("grafico_evolucion_criterios_individual", height = "600px"),
                type = 4,
                color = "#00A8E1"
              )
            )
          )
        ),
        
        # Criterios con mejor y peor desempeÃ±o
        fluidRow(
          column(
            width = 6,
            box(
              title = HTML("<i class='fa fa-trophy'></i> TOP 5: CRITERIOS MÃS FUERTES"),
              width = NULL,
              solidHeader = TRUE,
              status = "success",
              shinycssloaders::withSpinner(
                plotlyOutput("grafico_criterios_altos", height = "350px"),
                type = 4,
                color = "#28a745"
              )
            )
          ),
          column(
            width = 6,
            box(
              title = HTML("<i class='fa fa-exclamation-triangle'></i> TOP 5: CRITERIOS A MEJORAR"),
              width = NULL,
              solidHeader = TRUE,
              status = "danger",
              shinycssloaders::withSpinner(
                plotlyOutput("grafico_criterios_bajos", height = "350px"),
                type = 4,
                color = "#dc3545"
              )
            )
          )
        )
      ),
      
      # ========================================================================
      # TAB 3: HISTÃ“RICO COMPLETO
      # ========================================================================
      
      tabItem(
        tabName = "historico",
        
        fluidRow(
          column(
            width = 12,
            box(
              title = HTML("<i class='fa fa-history'></i> HISTÃ“RICO COMPLETO DE EVALUACIONES"),
              width = NULL,
              solidHeader = TRUE,
              status = "primary",
              
              fluidRow(
                column(
                  width = 6,
                  selectInput(
                    "filtro_gestor",
                    "Filtrar por Gestor:",
                    choices = c("Todos"),
                    selected = "Todos",
                    width = "100%"
                  )
                ),
                column(
                  width = 6,
                  div(
                    style = "margin-top: 25px;",
                    downloadButton(
                      "btn_export_excel",
                      "Exportar a Excel",
                      class = "btn-success btn-block",
                      icon = icon("file-excel")
                    )
                  )
                )
              ),
              
              hr(),
              
              shinycssloaders::withSpinner(
                DT::dataTableOutput("tabla_resultados"),
                type = 4,
                color = "#00A8E1"
              )
            )
          )
        )
      ),
      
      # ========================================================================
      # TAB 4: CONFIGURACIÃ“N
      # ========================================================================
      
      tabItem(
        tabName = "config",
        
        fluidRow(
          column(
            width = 6,
            box(
              title = HTML("<i class='fa fa-info-circle'></i> INFORMACIÃ“N DEL SISTEMA"),
              width = NULL,
              solidHeader = TRUE,
              status = "info",
              verbatimTextOutput("info_sistema")
            )
          ),
          column(
            width = 6,
            box(
              title = HTML("<i class='fa fa-list-ul'></i> CRITERIOS DE EVALUACIÃ“N"),
              width = NULL,
              solidHeader = TRUE,
              status = "primary",
              collapsible = TRUE,
              collapsed = FALSE,
              uiOutput("lista_criterios")
            )
          )
        )
      )
    )
  )
)

cat("âœ“ UI (Interfaz de Usuario) cargada\n\n")

# ==============================================================================
# BLOQUE 7B: SERVER - LÃ“GICA MEJORADA CON GRÃFICOS AVANZADOS
# ==============================================================================

server <- function(input, output, session) {
  
  # Valores reactivos
  rv <- reactiveValues(
    evaluaciones = data.frame(),
    evaluacion_actual = NULL,
    historial_cargado = FALSE,
    plan_mejora = NULL,
    plan_generando = FALSE
  )
  
  # Cargar historial al iniciar
  observe({
    if (!rv$historial_cargado) {
      historial <- cargar_historial()
      if (nrow(historial) > 0) {
        rv$evaluaciones <- historial
      }
      rv$historial_cargado <- TRUE
    }
  })
  
  # ===========================
  # EVALUACIÃ“N PRINCIPAL
  # ===========================
  
  observeEvent(input$btn_evaluar, {
    
    # Validar inputs
    if (input$canal_evaluacion == "AUDIO") {
      if (is.null(input$audio_file)) {
        showNotification(
          "Debes subir un archivo de audio para canal AUDIO",
          type = "error",
          duration = 5
        )
        return()
      }
    } else {
      if (is.null(input$texto_conversacion) || nchar(stringr::str_trim(input$texto_conversacion)) < 20) {
        showNotification(
          "Debes ingresar al menos 20 caracteres de conversaciÃ³n",
          type = "error",
          duration = 5
        )
        return()
      }
    }
    
    showModal(modalDialog(
      title = HTML("<i class='fa fa-cog fa-spin'></i> Procesando EvaluaciÃ³n..."),
      size = "l",
      easyClose = FALSE,
      footer = NULL,
      div(
        style = "text-align: center; padding: 30px;",
        tags$div(
          style = "font-size: 48px; color: #00A8E1; margin-bottom: 20px;",
          icon("robot", class = "fa-spin")
        ),
        tags$h4(
          style = "color: #003087; margin-bottom: 15px;",
          "EvaluaciÃ³n en Progreso"
        ),
        tags$p(
          style = "color: #666; font-size: 14px;",
          if(input$canal_evaluacion == "AUDIO") {
            "â–ª Transcribiendo audio con Whisper API..."
          } else {
            "â–ª Analizando texto de conversaciÃ³n..."
          },
          tags$br(),
          "â–ª Evaluando con Claude Sonnet 4.5...",
          tags$br(),
          "â–ª Calculando scores por criterio...",
          tags$br(),
          "â–ª Generando informe completo..."
        ),
        tags$div(
          class = "progress",
          style = "margin-top: 20px;",
          tags$div(
            class = "progress-bar progress-bar-striped active",
            role = "progressbar",
            style = "width: 100%; background: linear-gradient(90deg, #003087 0%, #00A8E1 50%, #003087 100%); background-size: 200% 100%; animation: gradient-shift 2s linear infinite;"
          )
        ),
        tags$style(HTML("
          @keyframes gradient-shift {
            0% { background-position: 0% 50%; }
            100% { background-position: 200% 50%; }
          }
        "))
      )
    ))
    
    # Procesar en segundo plano
    tryCatch({
      
      # Generar ID Ãºnico
      id_eval <- digest::digest(paste0(Sys.time(), runif(1)), algo = "md5", serialize = FALSE)
      id_eval <- substr(id_eval, 1, 12)
      
      transcripcion_texto <- ""
      audio_info <- NULL
      
      # Obtener transcripciÃ³n segÃºn canal
      if (input$canal_evaluacion == "AUDIO") {
        
        # Guardar audio en temporal
        audio_info <- guardar_audio_temporal(input$audio_file$datapath, id_eval)
        
        # Transcribir
        result_transcripcion <- transcribir_audio_whisper(input$audio_file$datapath)
        
        if (!result_transcripcion$success) {
          removeModal()
          showNotification(
            paste("Error en transcripciÃ³n:", result_transcripcion$transcripcion),
            type = "error",
            duration = 10
          )
          return()
        }
        
        transcripcion_texto <- result_transcripcion$transcripcion
        
      } else {
        # Usar texto directo
        transcripcion_texto <- stringr::str_trim(input$texto_conversacion)
      }
      
      # Evaluar con Claude
      result_evaluacion <- evaluar_con_claude_calibrado(transcripcion_texto, input$canal_evaluacion)
      
      if (!result_evaluacion$success) {
        removeModal()
        showNotification(
          paste("Error en evaluaciÃ³n:", result_evaluacion$error),
          type = "error",
          duration = 10
        )
        return()
      }
      
      eval_data <- result_evaluacion$evaluacion
      
      # Preparar datos completos
      eval_completa <- list(
        id_evaluacion = id_eval,
        id_llamada = ifelse(is.null(input$id_llamada_input) || input$id_llamada_input == "", 
                            id_eval, 
                            input$id_llamada_input),
        gestor_nombre = input$gestor_nombre,
        gestor_apellido = input$gestor_apellido,
        canal = input$canal_evaluacion,
        timestamp = Sys.time(),
        audio_path = if(!is.null(audio_info)) audio_info$path_absoluto else NULL,
        duracion_segundos = if(!is.null(audio_info)) audio_info$duracion_segundos else NULL,
        transcripcion = transcripcion_texto,
        criterios = eval_data$criterios,
        score_total = eval_data$score_total,
        nivel_calidad = eval_data$nivel_calidad,
        resumen = eval_data$resumen,
        fortalezas = eval_data$fortalezas,
        areas_mejora = eval_data$areas_mejora
      )
      
      # Guardar en historial
      guardar_historial(eval_completa)
      
      # Recargar historial
      historial_actualizado <- cargar_historial()
      rv$evaluaciones <- historial_actualizado
      
      # Guardar evaluaciÃ³n actual para mostrar
      rv$evaluacion_actual <- eval_completa
      
      removeModal()
      
      showNotification(
        HTML(paste0(
          "<strong><i class='fa fa-check-circle'></i> EvaluaciÃ³n Completada</strong><br>",
          "Score Total: <strong>", eval_data$score_total, "/100 puntos</strong><br>",
          "Nivel: <strong>", eval_data$nivel_calidad, "</strong>"
        )),
        type = "message",
        duration = 8
      )
      
    }, error = function(e) {
      removeModal()
      showNotification(
        paste("Error general:", e$message),
        type = "error",
        duration = 10
      )
    })
  })
  
  # ===========================
  # V21: PLAN DE MEJORA POST-LLAMADA
  # ===========================

  observeEvent(input$btn_generar_plan_mejora, {

    req(rv$evaluacion_actual)

    if (isTRUE(rv$plan_generando)) {
      showNotification("Ya hay un plan generandose, espera un momento...",
                       type = "warning", duration = 4)
      return()
    }

    rv$plan_generando <- TRUE
    rv$plan_mejora    <- NULL

    showModal(modalDialog(
      title     = HTML("<i class='fa fa-magic'></i> Generando Plan de Mejora..."),
      size      = "m",
      easyClose = FALSE,
      footer    = NULL,
      div(
        style = "text-align:center; padding:25px;",
        tags$div(style = "font-size:40px; color:#FFB81C; margin-bottom:15px;",
                 icon("clipboard-check")),
        tags$h4(style = "color:#003087; margin-bottom:10px;",
                "IA analizando la llamada..."),
        tags$p(style = "color:#666; font-size:13px; line-height:2;",
          icon("check", style="color:#28a745;"), " Identificando criterios clave...", tags$br(),
          icon("check", style="color:#28a745;"), " Generando frases modelo...", tags$br(),
          icon("check", style="color:#28a745;"), " Preparando plan de accion..."
        ),
        div(class = "progress", style = "margin-top:15px; height:8px;",
          div(class = "progress-bar progress-bar-striped active",
              style = "width:100%; background:linear-gradient(90deg,#FFB81C,#003087,#FFB81C); background-size:200%; animation:gradient-shift 1.5s linear infinite;")
        )
      )
    ))

    tryCatch({

      resultado_plan        <- generar_plan_mejora_postcall(rv$evaluacion_actual)
      rv$plan_mejora        <- resultado_plan
      rv$plan_generando     <- FALSE
      removeModal()

      if (resultado_plan$success) {
        hay_alerta <- isTRUE(resultado_plan$plan$alerta_supervisor)
        showNotification(
          HTML(paste0(
            "<strong>", if (hay_alerta) "ALERTA " else "OK ",
            "Plan de mejora generado</strong><br>",
            if (hay_alerta)
              "<span style='color:#dc3545;'>Alerta activada para supervisor</span>"
            else
              "Sin alertas - gestion dentro del rango esperado"
          )),
          type     = if (hay_alerta) "warning" else "message",
          duration = 6
        )
      } else {
        showNotification(
          paste("Error al generar plan:", resultado_plan$error),
          type = "error", duration = 8
        )
      }

    }, error = function(e) {
      rv$plan_generando <- FALSE
      removeModal()
      showNotification(paste("Error:", e$message), type = "error", duration = 8)
    })
  })

  output$panel_postcall <- renderUI({

    if (is.null(rv$plan_mejora)) {
      return(div(
        style = "padding:20px; text-align:center; color:#adb5bd; background:#f8f9fa; border-radius:8px; margin:10px 0;",
        icon("info-circle", style = "font-size:20px;"),
        tags$p("Presiona GENERAR PLAN POST-LLAMADA para obtener el analisis de cierre.")
      ))
    }

    pm <- rv$plan_mejora

    if (!pm$success) {
      return(div(
        style = "background:#f8d7da; padding:20px; border-radius:10px; margin:10px 0; border:2px solid #dc3545;",
        icon("times-circle", style = "color:#dc3545;"),
        tags$strong(" Error generando el plan"),
        tags$p(style = "margin-top:8px; color:#721c24;", pm$error)
      ))
    }

    plan <- pm$plan

    tagList(

      # ALERTA SUPERVISOR
      if (isTRUE(plan$alerta_supervisor)) {
        fluidRow(column(width = 12,
          div(
            style = "background:linear-gradient(135deg,#dc3545,#c82333); color:white; padding:15px 20px; border-radius:10px; margin:10px 0; display:flex; align-items:center; gap:15px;",
            icon("exclamation-triangle", style = "font-size:26px;"),
            div(
              tags$strong(style = "font-size:16px; display:block;", "ALERTA PARA SUPERVISOR"),
              tags$span(style = "font-size:13px; opacity:0.9;",
                if (!is.null(plan$motivo_alerta) && nchar(plan$motivo_alerta) > 0)
                  plan$motivo_alerta
                else
                  paste0("Score ", pm$score, "/100 pts - por debajo del umbral minimo (80 pts)")
              )
            )
          )
        ))
      },

      # RESUMEN + MENSAJE AL GESTOR
      fluidRow(
        column(width = 7,
          box(title = HTML("<i class='fa fa-file-alt'></i> Resumen Ejecutivo"),
              width = NULL, status = "primary", solidHeader = TRUE,
            div(style = "padding:15px; background:linear-gradient(135deg,#f8f9fa,#e9ecef); border-radius:8px; border-left:5px solid #003087;",
              tags$p(style = "font-size:14px; line-height:1.7; margin:0; color:#333;",
                     plan$resumen_ejecutivo))
          )
        ),
        column(width = 5,
          box(title = HTML("<i class='fa fa-comment-dots'></i> Mensaje al Gestor"),
              width = NULL, status = "warning", solidHeader = TRUE,
            div(style = "padding:15px; background:linear-gradient(135deg,#fff8e1,#fff3cd); border-radius:8px; border-left:5px solid #FFB81C; font-style:italic;",
              tags$p(style = "font-size:14px; line-height:1.7; margin:0; color:#555;",
                     plan$mensaje_gestor))
          )
        )
      ),

      # TOP 3 MEJORAS
      fluidRow(
        column(width = 12,
          box(title = HTML("<i class='fa fa-arrow-up'></i> Top 3 Acciones de Mejora Inmediata"),
              width = NULL, status = "warning", solidHeader = TRUE,
            fluidRow(
              lapply(seq_along(plan$top3_mejoras), function(i) {
                m <- plan$top3_mejoras[[i]]
                prio <- toupper(ifelse(is.null(m$prioridad), "MEDIA", m$prioridad))
                col_p <- switch(prio, "ALTA" = "#dc3545", "MEDIA" = "#ff9800", "BAJA" = "#28a745", "#6c757d")
                column(width = 4,
                  div(
                    style = paste0("border:2px solid ", col_p, "; border-radius:12px; padding:18px; ",
                                   "background:white; box-shadow:0 4px 12px rgba(0,0,0,0.08); margin-bottom:10px; min-height:300px;"),
                    div(style = "margin-bottom:10px;",
                      span(style = paste0("background:", col_p, "; color:white; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:700;"), prio),
                      span(style = "font-size:16px; font-weight:700; color:#003087; margin-left:8px;", paste0("#", i))
                    ),
                    tags$h5(style = "color:#003087; font-weight:700; margin-bottom:8px;",
                             icon("bullseye"), " ", m$criterio),
                    div(style = "margin-bottom:10px;",
                      tags$strong(style = "font-size:11px; color:#dc3545;",
                                   icon("times-circle"), " SITUACION ACTUAL:"),
                      tags$p(style = "font-size:13px; color:#555; margin:4px 0; line-height:1.5;", m$problema)
                    ),
                    div(style = "margin-bottom:10px;",
                      tags$strong(style = "font-size:11px; color:#28a745;",
                                   icon("check-circle"), " ACCION CONCRETA:"),
                      tags$p(style = "font-size:13px; color:#555; margin:4px 0; line-height:1.5;", m$accion_concreta)
                    ),
                    div(
                      style = "background:linear-gradient(135deg,#e3f2fd,#bbdefb); border-radius:8px; padding:10px; border-left:4px solid #00A8E1;",
                      tags$strong(style = "font-size:11px; color:#1976D2;",
                                   icon("microphone"), " FRASE MODELO:"),
                      tags$p(style = "font-size:13px; color:#1565C0; margin:5px 0 0 0; font-style:italic; line-height:1.5;",
                             m$frase_modelo)
                    )
                  )
                )
              })
            )
          )
        )
      ),

      # COMPROMISO + RECONOCIMIENTO + TENDENCIA
      fluidRow(
        column(width = 5,
          box(title = HTML("<i class='fa fa-handshake'></i> Compromiso Proxima Llamada"),
              width = NULL, status = "success", solidHeader = TRUE,
            div(style = "background:linear-gradient(135deg,#e8f5e9,#c8e6c9); padding:18px; border-radius:10px; border-left:5px solid #28a745;",
              icon("calendar-check", style = "font-size:22px; color:#28a745; margin-bottom:10px; display:block;"),
              tags$p(style = "font-size:14px; font-weight:600; color:#2e7d32; margin:0; line-height:1.6;",
                     plan$compromiso_proxima_llamada))
          )
        ),
        column(width = 5,
          box(title = HTML("<i class='fa fa-star'></i> Reconocimiento"),
              width = NULL, status = "info", solidHeader = TRUE,
            div(style = "background:linear-gradient(135deg,#e3f2fd,#bbdefb); padding:18px; border-radius:10px; border-left:5px solid #00A8E1;",
              icon("award", style = "font-size:22px; color:#00A8E1; margin-bottom:10px; display:block;"),
              tags$p(style = "font-size:14px; color:#1565C0; margin:0; line-height:1.6;",
                     plan$reconocimiento))
          )
        ),
        column(width = 2,
          box(title = HTML("<i class='fa fa-chart-line'></i> Tendencia"),
              width = NULL, status = "primary", solidHeader = TRUE,
            div(style = "text-align:center; padding:10px;",
              {
                tend <- toupper(ifelse(is.null(plan$score_tendencia), "MANTIENE", plan$score_tendencia))
                t_icon <- switch(tend,
                  "MEJORA"            = list(i = "arrow-up",            col = "#28a745"),
                  "MANTIENE"          = list(i = "minus",               col = "#00A8E1"),
                  "REQUIERE_ATENCION" = list(i = "exclamation-triangle", col = "#dc3545"),
                  list(i = "minus", col = "#6c757d")
                )
                tagList(
                  icon(t_icon$i, style = paste0("font-size:30px; color:", t_icon$col, ";")),
                  tags$p(style = paste0("font-size:12px; font-weight:700; color:", t_icon$col, "; margin-top:6px;"),
                         gsub("_", " ", tend))
                )
              }
            )
          )
        )
      ),

      # FOOTER
      fluidRow(
        column(width = 12,
          div(
            style = "background:#f8f9fa; padding:10px 20px; border-radius:8px; margin-top:5px; border:1px solid #dee2e6; display:flex; justify-content:space-between; align-items:center;",
            tags$span(style = "font-size:11px; color:#6c757d;",
              icon("clock"), " Plan generado: ", format(pm$timestamp, "%d/%m/%Y %H:%M:%S"),
              " | Gestor: ", pm$gestor, " | Score: ", pm$score, "/100"
            ),
            tags$span(style = "font-size:11px; color:#003087; font-weight:600;",
              "CASH-IA Control de Calidad v2.1")
          )
        )
      )
    )
  })

  # ===========================
  # RENDERIZAR RESULTADO DE EVALUACIÃ“N
  # ===========================
  
  output$resultado_evaluacion <- renderUI({
    
    req(rv$evaluacion_actual)
    eval <- rv$evaluacion_actual
    
    tagList(
      
      # KPIs de resultado
      fluidRow(
        column(
          width = 4,
          valueBox(
            value = paste0(eval$score_total, "/100"),
            subtitle = "SCORE TOTAL",
            icon = icon("star"),
            color = if(eval$score_total >= 93) "green" 
                    else if(eval$score_total >= 85) "yellow" 
                    else if(eval$score_total >= 70) "orange" 
                    else "red",
            width = NULL
          )
        ),
        column(
          width = 4,
          valueBox(
            value = eval$nivel_calidad,
            subtitle = "NIVEL DE CALIDAD",
            icon = icon("award"),
            color = if(eval$nivel_calidad == "EXCELENTE") "green" 
                    else if(eval$nivel_calidad == "BUENO") "yellow" 
                    else if(eval$nivel_calidad == "REGULAR") "orange" 
                    else "red",
            width = NULL
          )
        ),
        column(
          width = 4,
          valueBox(
            value = length(eval$criterios),
            subtitle = "CRITERIOS EVALUADOS",
            icon = icon("list-check"),
            color = "blue",
            width = NULL
          )
        )
      ),
      
      # Resumen ejecutivo
      fluidRow(
        column(
          width = 12,
          box(
            title = "â–ª Resumen Ejecutivo",
            width = NULL,
            status = "primary",
            solidHeader = TRUE,
            div(
              style = "padding: 15px; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 8px; border-left: 5px solid #003087;",
              tags$p(
                style = "font-size: 15px; line-height: 1.7; margin: 0; color: #333;",
                eval$resumen
              )
            )
          )
        )
      ),
      
      # Reproductor de audio (si aplica)
      if (eval$canal == "AUDIO" && !is.null(input$audio_file)) {
        fluidRow(
          column(
            width = 12,
            box(
              title = "â–ª Audio Original de la Llamada",
              width = NULL,
              status = "info",
              solidHeader = TRUE,
              
              tryCatch({
                audio_base64 <- convertir_audio_a_base64(input$audio_file$datapath)
                
                if (!is.null(audio_base64)) {
                  formato_archivo <- tolower(tools::file_ext(input$audio_file$name))
                  if (formato_archivo == "") formato_archivo <- "mp3"
                  
                  generar_reproductor_audio_avanzado(
                    audio_base64 = audio_base64,
                    duracion = eval$duracion_segundos,
                    formato = formato_archivo,
                    id_player = paste0("audio_player_", eval$id_llamada)
                  )
                } else {
                  div(
                    style = "background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 15px; margin: 20px 0;",
                    icon("exclamation-triangle", style = "color: #ffc107;"),
                    span(" No se pudo cargar el reproductor de audio.")
                  )
                }
              }, error = function(e) {
                div(
                  style = "background: #f8d7da; border: 1px solid #dc3545; border-radius: 8px; padding: 15px; margin: 20px 0;",
                  icon("times-circle", style = "color: #dc3545;"),
                  span(sprintf(" Error al cargar audio: %s", e$message))
                )
              })
            )
          )
        )
      },
      
      # Fortalezas y Ã¡reas de mejora
      fluidRow(
        column(
          width = 6,
          box(
            title = "â–ª Fortalezas Identificadas",
            width = NULL,
            status = "success",
            solidHeader = TRUE,
            background = "green",
            tags$ul(
              style = "margin: 10px 0; padding-left: 20px; line-height: 1.8;",
              lapply(eval$fortalezas, function(f) tags$li(style = "margin-bottom: 8px;", f))
            )
          )
        ),
        column(
          width = 6,
          box(
            title = "â–ª Ãreas de Mejora",
            width = NULL,
            status = "warning",
            solidHeader = TRUE,
            background = "orange",
            tags$ul(
              style = "margin: 10px 0; padding-left: 20px; line-height: 1.8;",
              lapply(eval$areas_mejora, function(a) tags$li(style = "margin-bottom: 8px;", a))
            )
          )
        )
      ),
      
      # GrÃ¡fico de radar
      fluidRow(
        column(
          width = 12,
          box(
            title = "â–ª GrÃ¡fico de DesempeÃ±o por Criterio",
            width = NULL,
            status = "primary",
            solidHeader = TRUE,
            plotlyOutput("grafico_radar_evaluacion", height = "450px")
          )
        )
      ),
      
      # TranscripciÃ³n
      fluidRow(
        column(
          width = 12,
          box(
            title = "â–ª TranscripciÃ³n de la ConversaciÃ³n",
            width = NULL,
            status = "info",
            solidHeader = TRUE,
            collapsible = TRUE,
            collapsed = FALSE,
            
            if (!is.null(input$audio_file) && input$canal_evaluacion == "AUDIO") {
              tagList(
                div(
                  style = "margin-bottom: 20px; padding: 15px; background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border-radius: 10px; border: 2px solid #2196F3;",
                  h5(
                    style = "margin: 0 0 10px 0; color: #1976D2; font-weight: 600;",
                    icon("headphones"), " Audio Original - Reproducir mientras lees"
                  ),
                  tryCatch({
                    audio_base64 <- convertir_audio_a_base64(input$audio_file$datapath)
                    if (!is.null(audio_base64)) {
                      formato_archivo <- tolower(tools::file_ext(input$audio_file$name))
                      if (formato_archivo == "") formato_archivo <- "mp3"
                      mime_type <- switch(formato_archivo, "mp3" = "audio/mpeg", "wav" = "audio/wav", "m4a" = "audio/mp4", "audio/mpeg")
                      
                      tags$audio(
                        id = "audio_transcription_player",
                        controls = "controls",
                        preload = "metadata",
                        style = "width: 100%; outline: none; border-radius: 6px;",
                        tags$source(
                          src = glue::glue("data:{mime_type};base64,{audio_base64}"),
                          type = mime_type
                        )
                      )
                    }
                  }, error = function(e) {
                    div(style = "color: #d32f2f;", "Error al cargar audio")
                  })
                ),
                
                div(
                  style = "background: #f8f9fa; padding: 20px; border-radius: 8px; max-height: 500px; overflow-y: auto; font-family: 'Courier New', monospace; font-size: 14px; line-height: 1.8; white-space: pre-wrap; border: 1px solid #dee2e6;",
                  eval$transcripcion
                )
              )
            } else {
              div(
                style = "background: #f8f9fa; padding: 20px; border-radius: 8px; max-height: 500px; overflow-y: auto; font-family: 'Courier New', monospace; font-size: 14px; line-height: 1.8; white-space: pre-wrap; border: 1px solid #dee2e6;",
                eval$transcripcion
              )
            }
          )
        )
      ),
      
      # Detalle por criterio
      fluidRow(
        column(
          width = 12,
          box(
            title = "â–ª Detalle Completo por Criterio",
            width = NULL,
            status = "primary",
            solidHeader = TRUE,
            collapsible = TRUE,
            collapsed = FALSE,
            DT::dataTableOutput("tabla_detalle_criterios")
          )
        )
      ),
      
      # Botones de exportaciÃ³n
      fluidRow(
        column(
          width = 12,
          box(
            title = "â–ª Exportar EvaluaciÃ³n",
            width = NULL,
            status = "success",
            solidHeader = TRUE,
            fluidRow(
              column(
                width = 4,
                downloadButton(
                  "btn_export_word_individual",
                  "â–ª Exportar a Word",
                  class = "btn-primary btn-block",
                  style = "height: 60px; font-size: 16px;"
                )
              ),
              column(
                width = 4,
                downloadButton(
                  "btn_export_pdf_individual",
                  "â–ª Exportar a PDF",
                  class = "btn-warning btn-block",
                  style = "height: 60px; font-size: 16px;"
                )
              ),
              column(
                width = 4,
                downloadButton(
                  "btn_export_json_individual",
                  "â–ª Exportar JSON",
                  class = "btn-info btn-block",
                  style = "height: 60px; font-size: 16px;"
                )
              )
            )
          )
        )
      ),

      # === V21: BOTON + PANEL DE CIERRE POST-LLAMADA ===
      fluidRow(
        column(
          width = 12,
          div(
            style = "margin:30px 0 10px 0;",
            tags$hr(style = "border:2px solid #003087; margin:0;"),
            div(
              style = "background:linear-gradient(135deg,#003087 0%,#00A8E1 100%); padding:15px 25px; border-radius:0 0 12px 12px; display:flex; align-items:center; justify-content:space-between;",
              div(
                style = "color:white;",
                tags$h4(
                  style = "margin:0; font-weight:700; font-size:18px;",
                  icon("clipboard-check"), " CIERRE DE LLAMADA - PLAN DE MEJORA IA"
                ),
                tags$p(
                  style = "margin:5px 0 0 0; font-size:13px; opacity:0.85;",
                  "Genera automaticamente el resumen ejecutivo y plan de mejora personalizado"
                )
              ),
              div(
                actionButton(
                  "btn_generar_plan_mejora",
                  label = div(
                    icon("magic", style = "font-size:16px;"),
                    " GENERAR PLAN POST-LLAMADA",
                    style = "font-size:14px; font-weight:700;"
                  ),
                  class = "btn-warning",
                  style = "height:50px; border-radius:25px; padding:0 25px; box-shadow:0 4px 15px rgba(255,184,28,0.4); color:#003087; background:#FFB81C; border:2px solid #FFB81C;"
                )
              )
            )
          )
        )
      ),
      uiOutput("panel_postcall")

    )
  })
  
  # ===========================
  # GRÃFICO RADAR DE EVALUACIÃ“N
  # ===========================
  
  output$grafico_radar_evaluacion <- renderPlotly({
    
    req(rv$evaluacion_actual)
    eval <- rv$evaluacion_actual
    
    if (is.null(eval$criterios) || length(eval$criterios) == 0) {
      return(plot_ly() %>% layout(title = "No hay datos para mostrar"))
    }
    
    tryCatch({
      
      criterios_lista <- list()
      
      for (i in seq_along(eval$criterios)) {
        c <- eval$criterios[[i]]
        
        if (!is.list(c) || is.null(c$id) || is.null(c$nombre) || is.null(c$puntos_obtenidos)) {
          next
        }
        
        crit_config <- CRITERIOS_EVALUACION$criterios[[c$id]]
        if (is.null(crit_config)) next
        
        max_pts <- crit_config$max_puntos
        promedio_humano <- crit_config$promedio_humano
        
        criterios_lista[[length(criterios_lista) + 1]] <- list(
          id = c$id,
          criterio = substr(c$nombre, 1, 30),
          obtenido = as.numeric(c$puntos_obtenidos),
          maximo = max_pts,
          promedio_humano = promedio_humano,
          porcentaje_obtenido = round((as.numeric(c$puntos_obtenidos) / max_pts) * 100, 1),
          promedio_humano_pct = round((promedio_humano / max_pts) * 100, 1)
        )
      }
      
      if (length(criterios_lista) == 0) {
        return(plot_ly() %>% layout(title = "No hay criterios procesables"))
      }
      
      datos_radar <- data.frame(
        do.call(rbind, lapply(criterios_lista, function(x) {
          data.frame(
            criterio = x$criterio,
            porcentaje_obtenido = x$porcentaje_obtenido,
            promedio_humano_pct = x$promedio_humano_pct,
            stringsAsFactors = FALSE
          )
        })),
        stringsAsFactors = FALSE
      )
      
      fig <- plot_ly(
        type = 'scatterpolar',
        fill = 'toself'
      )
      
      fig <- fig %>%
        add_trace(
          r = datos_radar$porcentaje_obtenido,
          theta = datos_radar$criterio,
          name = 'EvaluaciÃ³n Actual',
          fillcolor = 'rgba(0, 168, 225, 0.25)',
          line = list(color = '#003087', width = 2),
          marker = list(color = '#003087', size = 8)
        )
      
      fig <- fig %>%
        add_trace(
          r = datos_radar$promedio_humano_pct,
          theta = datos_radar$criterio,
          name = 'Promedio Humano',
          fillcolor = 'rgba(40, 167, 69, 0.15)',
          line = list(color = '#28a745', width = 2, dash = 'dash'),
          marker = list(color = '#28a745', size = 6)
        )
      
      fig <- fig %>%
        layout(
          polar = list(
            radialaxis = list(
              visible = TRUE,
              range = c(0, 100),
              ticksuffix = "%",
              tickfont = list(size = 11)
            ),
            angularaxis = list(
              tickfont = list(size = 10)
            )
          ),
          showlegend = TRUE,
          legend = list(
            orientation = "h",
            x = 0.5,
            xanchor = "center",
            y = -0.15,
            font = list(size = 12)
          ),
          margin = list(l = 80, r = 80, t = 40, b = 120),
          font = list(family = "Arial, sans-serif")
        )
      
      return(fig)
      
    }, error = function(e) {
      return(plot_ly() %>% layout(title = paste("Error:", e$message)))
    })
  })
  
  # ===========================
  # TABLA DETALLE CRITERIOS
  # ===========================
  
  output$tabla_detalle_criterios <- DT::renderDataTable({
    
    req(rv$evaluacion_actual)
    eval <- rv$evaluacion_actual
    
    if (is.null(eval$criterios) || length(eval$criterios) == 0) {
      return(DT::datatable(
        data.frame(Mensaje = "No hay criterios disponibles"),
        options = list(dom = 't'),
        rownames = FALSE
      ))
    }
    
    tryCatch({
      
      tabla_criterios <- data.frame(
        ID = integer(),
        Criterio = character(),
        Puntos_Obtenidos = numeric(),
        Puntos_Maximos = numeric(),
        Porcentaje = numeric(),
        Justificacion = character(),
        stringsAsFactors = FALSE
      )
      
      for (i in seq_along(eval$criterios)) {
        crit <- eval$criterios[[i]]
        
        if (!is.list(crit) || is.null(crit$id)) next
        
        crit_config <- CRITERIOS_EVALUACION$criterios[[crit$id]]
        if (is.null(crit_config)) next
        
        max_pts <- crit_config$max_puntos
        obtenidos <- as.numeric(crit$puntos_obtenidos)
        porcentaje <- round((obtenidos / max_pts) * 100, 1)
        
        tabla_criterios <- rbind(tabla_criterios, data.frame(
          ID = as.integer(crit$id),
          Criterio = as.character(crit$nombre),
          Puntos_Obtenidos = obtenidos,
          Puntos_Maximos = max_pts,
          Porcentaje = porcentaje,
          Justificacion = as.character(crit$justificacion),
          stringsAsFactors = FALSE
        ))
      }
      
      if (nrow(tabla_criterios) == 0) {
        return(DT::datatable(
          data.frame(Mensaje = "No se pudieron procesar los criterios"),
          options = list(dom = 't'),
          rownames = FALSE
        ))
      }
      
      tabla_criterios <- tabla_criterios[order(tabla_criterios$ID), ]
      
      DT::datatable(
        tabla_criterios,
        options = list(
          pageLength = 14,
          lengthMenu = c(14, 20, 50),
          dom = 't',
          ordering = FALSE,
          columnDefs = list(
            list(width = '40px', targets = 0),
            list(width = '250px', targets = 1),
            list(width = '80px', targets = 2),
            list(width = '80px', targets = 3),
            list(width = '80px', targets = 4),
            list(width = '350px', targets = 5)
          )
        ),
        rownames = FALSE,
        colnames = c('ID', 'Criterio', 'Obtenidos', 'MÃ¡ximos', '%', 'JustificaciÃ³n')
      ) %>%
        DT::formatStyle(
          'Porcentaje',
          backgroundColor = DT::styleInterval(
            c(50, 70, 85),
            c('#dc3545', '#ffc107', '#FFB81C', '#28a745')
          ),
          color = 'white',
          fontWeight = 'bold',
          textAlign = 'center'
        ) %>%
        DT::formatStyle(
          'Puntos_Obtenidos',
          fontWeight = 'bold',
          textAlign = 'center'
        ) %>%
        DT::formatStyle(
          'Puntos_Maximos',
          textAlign = 'center',
          color = '#6c757d'
        ) %>%
        DT::formatRound(
          columns = c('Puntos_Obtenidos', 'Puntos_Maximos'),
          digits = 1
        )
      
    }, error = function(e) {
      return(DT::datatable(
        data.frame(Error = paste("Error:", e$message)),
        options = list(dom = 't'),
        rownames = FALSE
      ))
    })
  })
  
  # ===========================
  # DASHBOARD: KPIs PRINCIPALES
  # ===========================
  
  datos_filtrados <- reactive({
    datos <- rv$evaluaciones
    
    if (nrow(datos) == 0) return(NULL)
    
    # Aplicar filtros
    if (!is.null(input$filtro_gestor_global) && input$filtro_gestor_global != "Todos") {
      datos <- datos %>%
        dplyr::filter(gestor_completo == input$filtro_gestor_global)
    }
    
    if (!is.null(input$filtro_mes_global) && input$filtro_mes_global != "Todos") {
      datos <- datos %>%
        dplyr::filter(mes_nombre == input$filtro_mes_global)
    }
    
    if (!is.null(input$filtro_llamada_global) && input$filtro_llamada_global != "Todas") {
      datos <- datos %>%
        dplyr::filter(id_llamada == input$filtro_llamada_global)
    }
    
    return(datos)
  })
  
  output$kpi_total_evaluaciones <- renderValueBox({
    datos <- datos_filtrados()
    valor <- if(is.null(datos)) 0 else nrow(datos)
    
    valueBox(
      value = valor,
      subtitle = "EVALUACIONES TOTALES",
      icon = icon("list-check"),
      color = "blue"
    )
  })
  
  output$kpi_promedio_score <- renderValueBox({
    datos <- datos_filtrados()
    
    if (is.null(datos) || nrow(datos) == 0) {
      valor <- "N/A"
      color <- "light-blue"
    } else {
      promedio <- mean(datos$score_total, na.rm = TRUE)
      valor <- round(promedio, 1)
      
      color <- if(promedio >= 93) "green" 
              else if(promedio >= 85) "yellow" 
              else if(promedio >= 70) "orange" 
              else "red"
    }
    
    valueBox(
      value = valor,
      subtitle = "SCORE PROMEDIO",
      icon = icon("star"),
      color = color
    )
  })
  
  output$kpi_nivel_promedio <- renderValueBox({
    datos <- datos_filtrados()
    
    if (is.null(datos) || nrow(datos) == 0) {
      valor <- "N/A"
      color <- "light-blue"
    } else {
      # Contar niveles
      niveles <- table(datos$nivel_calidad)
      nivel_mas_comun <- names(which.max(niveles))
      valor <- nivel_mas_comun
      
      color <- if(nivel_mas_comun == "EXCELENTE") "green" 
              else if(nivel_mas_comun == "BUENO") "yellow" 
              else if(nivel_mas_comun == "REGULAR") "orange" 
              else "red"
    }
    
    valueBox(
      value = valor,
      subtitle = "NIVEL MÃS FRECUENTE",
      icon = icon("award"),
      color = color
    )
  })
  
  output$kpi_total_gestores <- renderValueBox({
    datos <- datos_filtrados()
    
    if (is.null(datos) || nrow(datos) == 0 || !"gestor_completo" %in% names(datos)) {
      valor <- 0
    } else {
      gestores_unicos <- datos %>%
        dplyr::filter(!is.na(gestor_completo) & gestor_completo != "" & gestor_completo != " ") %>%
        dplyr::pull(gestor_completo) %>%
        unique()
      valor <- length(gestores_unicos)
    }
    
    valueBox(
      value = valor,
      subtitle = "GESTORES EVALUADOS",
      icon = icon("users"),
      color = "purple"
    )
  })
  
  # ===========================
  # LIMPIAR FILTROS
  # ===========================
  
  observeEvent(input$btn_limpiar_filtros, {
    updateSelectInput(session, "filtro_gestor_global", selected = "Todos")
    updatePickerInput(session, "filtro_mes_global", selected = "Todos")
    updatePickerInput(session, "filtro_llamada_global", selected = "Todas")
    
    showNotification(
      "Filtros restablecidos",
      type = "message",
      duration = 3
    )
  })
  
  # ===========================
  # GRÃFICO: CRITERIOS MÃS ALTOS
  # ===========================
  
  output$grafico_criterios_altos <- renderPlotly({
    
    if (is.null(datos_filtrados()) || nrow(datos_filtrados()) == 0) {
      return(plot_ly() %>% layout(title = "No hay datos"))
    }
    
    promedios <- sapply(CRITERIOS_EVALUACION$criterios, function(c) {
      c$promedio_humano / c$max_puntos * 100
    })
    
    nombres <- sapply(CRITERIOS_EVALUACION$criterios, function(c) {
      nombre <- c$nombre
      if (nchar(nombre) > 30) {
        nombre <- paste0(substr(nombre, 1, 27), "...")
      }
      nombre
    })
    
    indices_altos <- order(promedios, decreasing = TRUE)[1:5]
    
    plot_ly(
      x = promedios[indices_altos],
      y = nombres[indices_altos],
      type = "bar",
      orientation = "h",
      marker = list(
        color = COLORES_CASH$verde,
        line = list(color = COLORES_CASH$verde_oscuro, width = 2)
      ),
      text = ~paste0(round(promedios[indices_altos], 1), "%"),
      textposition = "outside"
    ) %>%
      layout(
        title = "",
        xaxis = list(title = "% Cumplimiento", range = c(0, 100)),
        yaxis = list(title = ""),
        margin = list(l = 200)
      )
  })
  
  # ===========================
  # GRÃFICO: CRITERIOS MÃS BAJOS
  # ===========================
  
  output$grafico_criterios_bajos <- renderPlotly({
    
    if (is.null(datos_filtrados()) || nrow(datos_filtrados()) == 0) {
      return(plot_ly() %>% layout(title = "No hay datos"))
    }
    
    promedios <- sapply(CRITERIOS_EVALUACION$criterios, function(c) {
      c$promedio_humano / c$max_puntos * 100
    })
    
    nombres <- sapply(CRITERIOS_EVALUACION$criterios, function(c) {
      nombre <- c$nombre
      if (nchar(nombre) > 30) {
        nombre <- paste0(substr(nombre, 1, 27), "...")
      }
      nombre
    })
    
    indices_bajos <- order(promedios, decreasing = FALSE)[1:5]
    
    plot_ly(
      x = promedios[indices_bajos],
      y = nombres[indices_bajos],
      type = "bar",
      orientation = "h",
      marker = list(
        color = COLORES_CASH$rojo,
        line = list(color = COLORES_CASH$rojo_claro, width = 2)
      ),
      text = ~paste0(round(promedios[indices_bajos], 1), "%"),
      textposition = "outside"
    ) %>%
      layout(
        title = "",
        xaxis = list(title = "% Cumplimiento", range = c(0, 100)),
        yaxis = list(title = ""),
        margin = list(l = 200)
      )
  })
  
  # ===========================
  # GRÃFICO: EVOLUCIÃ“N MES A MES
  # ===========================
  
  output$grafico_evolucion_criterios <- renderPlotly({
    
    datos <- datos_filtrados()
    
    if (is.null(datos) || nrow(datos) == 0 || !"mes_nombre" %in% names(datos)) {
      return(plot_ly() %>%
               layout(
                 title = "No hay datos suficientes",
                 annotations = list(
                   text = "Realiza evaluaciones en mÃºltiples meses",
                   xref = "paper",
                   yref = "paper",
                   x = 0.5,
                   y = 0.5,
                   showarrow = FALSE
                 )
               ))
    }
    
    datos_evol <- datos %>%
      dplyr::filter(!is.na(mes_nombre)) %>%
      dplyr::group_by(mes_nombre) %>%
      dplyr::summarise(
        promedio_score = mean(score_total, na.rm = TRUE),
        min_score = min(score_total, na.rm = TRUE),
        max_score = max(score_total, na.rm = TRUE),
        sd_score = sd(score_total, na.rm = TRUE),
        n = n(),
        .groups = "drop"
      ) %>%
      dplyr::arrange(mes_nombre)
    
    if (nrow(datos_evol) == 0) {
      return(plot_ly() %>% layout(title = "Sin datos de evoluciÃ³n"))
    }
    
    if (nrow(datos_evol) >= 2) {
      ultimo <- datos_evol$promedio_score[nrow(datos_evol)]
      anterior <- datos_evol$promedio_score[nrow(datos_evol)-1]
      tendencia <- ifelse(ultimo > anterior, "â†—ï¸ Mejorando", 
                         ifelse(ultimo < anterior, "â†˜ï¸ Decayendo", "â†’ Estable"))
      cambio_pct <- round(((ultimo - anterior) / anterior) * 100, 1)
    } else {
      tendencia <- ""
      cambio_pct <- 0
    }
    
    fig <- plot_ly()
    
    # Ãrea sombreada (rango min-max)
    if (nrow(datos_evol) >= 2) {
      fig <- fig %>%
        add_trace(
          data = datos_evol,
          x = ~mes_nombre,
          y = ~max_score,
          type = "scatter",
          mode = "lines",
          line = list(width = 0),
          showlegend = FALSE,
          hoverinfo = "skip",
          fillcolor = 'rgba(0, 168, 225, 0.15)'
        ) %>%
        add_trace(
          data = datos_evol,
          x = ~mes_nombre,
          y = ~min_score,
          type = "scatter",
          mode = "lines",
          line = list(width = 0),
          fill = "tonexty",
          fillcolor = 'rgba(0, 168, 225, 0.15)',
          showlegend = FALSE,
          hoverinfo = "skip"
        )
    }
    
    # LÃ­nea principal con gradiente
    fig <- fig %>%
      add_trace(
        data = datos_evol,
        x = ~mes_nombre,
        y = ~promedio_score,
        type = "scatter",
        mode = "lines+markers",
        name = "Promedio",
        line = list(
          color = COLORES_CASH$azul_principal,
          width = 4,
          shape = "spline"
        ),
        marker = list(
          size = ~sqrt(n) * 5,
          color = ~promedio_score,
          colorscale = list(
            list(0, '#dc3545'),
            list(0.7, '#ffc107'),
            list(0.85, '#8bc34a'),
            list(1, '#28a745')
          ),
          cmin = 70,
          cmax = 100,
          line = list(color = '#003087', width = 2),
          showscale = TRUE,
          colorbar = list(
            title = "Score",
            x = 1.02,
            thickness = 15,
            len = 0.7
          )
        ),
        text = ~paste0("<b>", mes_nombre, "</b><br>",
                      "â”â”â”â”â”â”â”â”â”â”â”â”â”<br>",
                      "â–ª Promedio: <b>", round(promedio_score, 1), " pts</b><br>",
                      "â–ª MÃ¡ximo: ", round(max_score, 1), " pts<br>",
                      "â–ª MÃ­nimo: ", round(min_score, 1), " pts<br>",
                      "â–ª N evaluaciones: ", n),
        hovertemplate = "%{text}<extra></extra>"
      )
    
    # LÃ­nea objetivo
    fig <- fig %>%
      add_trace(
        x = datos_evol$mes_nombre,
        y = rep(90.5, nrow(datos_evol)),
        type = "scatter",
        mode = "lines",
        name = "Objetivo (90.5 pts)",
        line = list(
          color = '#28a745',
          width = 2,
          dash = "dash"
        ),
        hovertemplate = "Objetivo: 90.5 pts<extra></extra>"
      )
    
    titulo_completo <- paste0(
      "â–ª EvoluciÃ³n del Score Total por Mes",
      if(nrow(datos_evol) >= 2) paste0(" | ", tendencia, " (", 
                                       ifelse(cambio_pct > 0, "+", ""),
                                       cambio_pct, "%)") else ""
    )
    
    fig <- fig %>%
      layout(
        title = list(
          text = titulo_completo,
          font = list(size = 14, color = '#003087')
        ),
        xaxis = list(
          title = "<b>Mes</b>",
          tickangle = -45,
          tickfont = list(size = 11),
          showgrid = TRUE,
          gridcolor = 'rgba(0,0,0,0.05)'
        ),
        yaxis = list(
          title = "<b>Score (puntos)</b>",
          range = c(max(60, min(datos_evol$min_score, na.rm=TRUE) - 5), 100),
          tickfont = list(size = 11),
          showgrid = TRUE,
          gridcolor = 'rgba(0,0,0,0.1)'
        ),
        shapes = list(
          list(
            type = "rect",
            xref = "paper",
            x0 = 0, x1 = 1,
            y0 = 88, y1 = 95,
            fillcolor = 'rgba(40, 167, 69, 0.08)',
            opacity = 1,
            line = list(width = 0),
            layer = "below"
          )
        ),
        annotations = list(
          list(
            x = 0.98,
            y = 91.5,
            xref = "paper",
            yref = "y",
            text = "<b>Zona Objetivo</b><br>88-95 pts",
            showarrow = FALSE,
            font = list(color = '#28a745', size = 10),
            bgcolor = 'rgba(255,255,255,0.8)',
            bordercolor = '#28a745',
            borderwidth = 1,
            borderpad = 4
          )
        ),
        showlegend = TRUE,
        legend = list(
          orientation = "v",
          x = 0.02,
          y = 0.98,
          bgcolor = 'rgba(255,255,255,0.9)',
          bordercolor = '#003087',
          borderwidth = 1
        ),
        margin = list(l = 70, r = 80, t = 70, b = 100),
        hovermode = "x unified",
        plot_bgcolor = '#f8f9fa',
        paper_bgcolor = 'white'
      )
    
    return(fig)
  })
  
  # ===========================
  # GRÃFICO: COMPARATIVA GESTORES
  # ===========================
  
  output$grafico_comparativa_gestores <- renderPlotly({
    
    datos <- datos_filtrados()
    
    if (is.null(datos) || nrow(datos) == 0 || !"gestor_completo" %in% names(datos)) {
      return(plot_ly() %>%
               layout(
                 title = "No hay datos disponibles",
                 annotations = list(
                   text = "Realiza evaluaciones",
                   xref = "paper",
                   yref = "paper",
                   x = 0.5,
                   y = 0.5,
                   showarrow = FALSE
                 )
               ))
    }
    
    datos_gestores <- datos %>%
      dplyr::filter(!is.na(gestor_completo) & gestor_completo != "" & gestor_completo != " ") %>%
      dplyr::group_by(gestor_completo) %>%
      dplyr::summarise(
        promedio = mean(score_total, na.rm = TRUE),
        n = n(),
        min_score = min(score_total, na.rm = TRUE),
        max_score = max(score_total, na.rm = TRUE),
        .groups = "drop"
      ) %>%
      dplyr::arrange(desc(promedio))
    
    if (nrow(datos_gestores) == 0) {
      return(plot_ly() %>% layout(title = "Sin datos de gestores"))
    }
    
    datos_gestores$color <- sapply(datos_gestores$promedio, function(p) {
      if (p >= 90) return('#28a745')
      else if (p >= 80) return('#ffc107')
      else if (p >= 70) return('#ff9800')
      else return('#dc3545')
    })
    
    plot_ly(
      datos_gestores,
      x = ~gestor_completo,
      y = ~promedio,
      type = "bar",
      marker = list(
        color = ~color,
        line = list(color = '#003087', width = 1.5)
      ),
      text = ~paste0(round(promedio, 1), " pts<br>(n=", n, ")"),
      textposition = "outside",
      hovertemplate = paste(
        "<b>%{x}</b><br>",
        "Promedio: %{y:.1f} pts<br>",
        "Rango: %{customdata[0]:.0f} - %{customdata[1]:.0f}<br>",
        "N evaluaciones: %{customdata[2]}<br>",
        "<extra></extra>"
      ),
      customdata = ~cbind(min_score, max_score, n)
    ) %>%
      layout(
        title = "",
        xaxis = list(title = "Gestor", tickangle = -45),
        yaxis = list(title = "Score Promedio", range = c(0, 100)),
        shapes = list(
          list(
            type = "line",
            x0 = 0, x1 = 1,
            xref = "paper",
            y0 = 90, y1 = 90,
            line = list(color = COLORES_CASH$verde, width = 2, dash = "dash")
          ),
          list(
            type = "line",
            x0 = 0, x1 = 1,
            xref = "paper",
            y0 = 80, y1 = 80,
            line = list(color = COLORES_CASH$dorado, width = 2, dash = "dash")
          )
        )
      )
  })
  
  # ===========================
  # GRÃFICO: EVOLUCIÃ“N POR GESTOR MEJORADO (V20)
  # ===========================
  
  output$grafico_evolucion_por_gestor_mejorado <- renderPlotly({
    
    datos <- datos_filtrados()
    
    if (is.null(datos) || nrow(datos) == 0 || 
        !"mes_nombre" %in% names(datos) || 
        !"gestor_completo" %in% names(datos)) {
      return(plot_ly() %>%
               layout(
                 title = "No hay datos suficientes",
                 annotations = list(
                   text = "Realiza evaluaciones de mÃºltiples gestores en varios meses",
                   xref = "paper",
                   yref = "paper",
                   x = 0.5,
                   y = 0.5,
                   showarrow = FALSE
                 )
               ))
    }
    
    datos_validos <- datos %>%
      dplyr::filter(
        !is.na(mes_nombre) & 
        !is.na(gestor_completo) & 
        gestor_completo != "" & 
        gestor_completo != " "
      )
    
    if (nrow(datos_validos) == 0) {
      return(plot_ly() %>% layout(title = "Sin datos vÃ¡lidos"))
    }
    
    datos_evol_gestor <- datos_validos %>%
      dplyr::group_by(mes_nombre, gestor_completo) %>%
      dplyr::summarise(
        promedio = mean(score_total, na.rm = TRUE),
        n = n(),
        min_score = min(score_total, na.rm = TRUE),
        max_score = max(score_total, na.rm = TRUE),
        .groups = "drop"
      ) %>%
      dplyr::arrange(mes_nombre)
    
    datos_evol_general <- datos_validos %>%
      dplyr::group_by(mes_nombre) %>%
      dplyr::summarise(
        promedio_general = mean(score_total, na.rm = TRUE),
        n_total = n(),
        .groups = "drop"
      ) %>%
      dplyr::arrange(mes_nombre)
    
    if (nrow(datos_evol_gestor) == 0) {
      return(plot_ly() %>% layout(title = "Sin datos de evoluciÃ³n"))
    }
    
    fig <- plot_ly()
    
    gestores_unicos <- unique(datos_evol_gestor$gestor_completo)
    
    # Agregar lÃ­nea por cada gestor con estilos mejorados
    for (i in seq_along(gestores_unicos)) {
      gestor <- gestores_unicos[i]
      datos_gestor <- datos_evol_gestor %>%
        dplyr::filter(gestor_completo == gestor)
      
      # Color del gestor de la paleta
      color_gestor <- PALETA_GESTORES[((i-1) %% length(PALETA_GESTORES)) + 1]
      
      fig <- fig %>%
        add_trace(
          data = datos_gestor,
          x = ~mes_nombre,
          y = ~promedio,
          type = "scatter",
          mode = "lines+markers",
          name = gestor,
          line = list(
            color = color_gestor,
            width = 3,
            shape = "spline"  # LÃ­nea suavizada
          ),
          marker = list(
            size = 10,
            color = color_gestor,
            line = list(color = 'white', width = 2),
            symbol = 'circle'
          ),
          text = ~paste0(
            "<b>", gestor, "</b><br>",
            "â”â”â”â”â”â”â”â”â”â”â”â”â”<br>",
            "â–ª Mes: ", mes_nombre, "<br>",
            "â–ª Promedio: <b>", round(promedio, 1), " pts</b><br>",
            "â–ª Rango: ", round(min_score, 1), " - ", round(max_score, 1), " pts<br>",
            "â–ª N evaluaciones: ", n
          ),
          hovertemplate = "%{text}<extra></extra>"
        )
    }
    
    # Agregar lÃ­nea de PROMEDIO GENERAL (destacada)
    fig <- fig %>%
      add_trace(
        data = datos_evol_general,
        x = ~mes_nombre,
        y = ~promedio_general,
        type = "scatter",
        mode = "lines+markers",
        name = "â–ª PROMEDIO GENERAL â–ª",
        line = list(
          color = '#000000',
          width = 5,
          dash = "dash"
        ),
        marker = list(
          size = 15,
          color = '#FFB81C',
          line = list(color = '#000000', width = 2),
          symbol = 'diamond'
        ),
        text = ~paste0(
          "<b style='color:#FFB81C;'>â–ª PROMEDIO GENERAL â–ª</b><br>",
          "â”â”â”â”â”â”â”â”â”â”â”â”â”<br>",
          "â–ª Mes: ", mes_nombre, "<br>",
          "â–ª Promedio: <b>", round(promedio_general, 1), " pts</b><br>",
          "â–ª Total evaluaciones: ", n_total
        ),
        hovertemplate = "%{text}<extra></extra>"
      )
    
    # TÃ­tulo dinÃ¡mico
    titulo_html <- paste0(
      "<b style='font-size:15px;'>â–ª EVOLUCIÃ“N INDIVIDUAL POR GESTOR + PROMEDIO GENERAL</b><br>",
      "<span style='font-size:11px; color:#666;'>",
      "Visualiza el rendimiento de cada gestor a lo largo del tiempo comparado con el promedio del equipo",
      "</span>"
    )
    
    fig <- fig %>%
      layout(
        title = list(
          text = titulo_html,
          font = list(size = 13, family = "Arial, sans-serif")
        ),
        xaxis = list(
          title = "<b>Mes</b>",
          tickangle = -45,
          tickfont = list(size = 11),
          showgrid = TRUE,
          gridcolor = 'rgba(0,0,0,0.05)'
        ),
        yaxis = list(
          title = "<b>Score Promedio (puntos)</b>",
          range = c(max(70, min(datos_evol_gestor$min_score, na.rm=TRUE) - 5), 100),
          tickfont = list(size = 11),
          showgrid = TRUE,
          gridcolor = 'rgba(0,0,0,0.1)'
        ),
        shapes = list(
          # Banda objetivo 88-95
          list(
            type = "rect",
            xref = "paper",
            x0 = 0, x1 = 1,
            y0 = 88, y1 = 95,
            fillcolor = 'rgba(40, 167, 69, 0.08)',
            opacity = 1,
            line = list(width = 0),
            layer = "below"
          ),
          # LÃ­nea promedio real 90.5
          list(
            type = "line",
            x0 = 0, x1 = 1,
            xref = "paper",
            y0 = 90.5, y1 = 90.5,
            line = list(color = '#28a745', width = 2, dash = "dot")
          )
        ),
        annotations = list(
          list(
            x = 0.02,
            y = 90.5,
            xref = "paper",
            yref = "y",
            text = "<b>Target: 90.5 pts</b>",
            showarrow = FALSE,
            font = list(color = '#28a745', size = 10),
            bgcolor = 'rgba(255,255,255,0.9)',
            bordercolor = '#28a745',
            borderwidth = 1,
            borderpad = 3
          )
        ),
        hovermode = "closest",
        showlegend = TRUE,
        legend = list(
          orientation = "v",
          x = 1.02,
          y = 1,
          font = list(size = 10),
          bgcolor = 'rgba(255,255,255,0.95)',
          bordercolor = '#003087',
          borderwidth = 2,
          title = list(
            text = "<b>GESTORES</b>",
            font = list(size = 11, color = '#003087')
          )
        ),
        margin = list(l = 70, r = 200, t = 90, b = 100),
        plot_bgcolor = '#fafafa',
        paper_bgcolor = 'white'
      )
    
    return(fig)
  })
  
  # ===========================
  # GRÃFICO: HEATMAP GESTOR X CRITERIO (V20 NUEVO)
  # ===========================
  
  output$grafico_heatmap_gestor_criterio <- renderPlotly({
    
    datos <- datos_filtrados()
    
    if (is.null(datos) || nrow(datos) == 0) {
      return(plot_ly() %>% layout(title = "No hay datos disponibles"))
    }
    
    # Verificar que existan columnas de scores por criterio
    cols_scores <- grep("^pct_criterio_", names(datos), value = TRUE)
    
    if (length(cols_scores) == 0) {
      return(plot_ly() %>%
               layout(
                 title = "Datos de criterios no disponibles",
                 annotations = list(
                   text = "Este grÃ¡fico requiere evaluaciones con desglose por criterio",
                   xref = "paper",
                   yref = "paper",
                   x = 0.5,
                   y = 0.5,
                   showarrow = FALSE
                 )
               ))
    }
    
    # Filtrar solo gestores vÃ¡lidos
    datos_validos <- datos %>%
      dplyr::filter(!is.na(gestor_completo) & gestor_completo != "" & gestor_completo != " ")
    
    if (nrow(datos_validos) == 0) {
      return(plot_ly() %>% layout(title = "Sin gestores con datos vÃ¡lidos"))
    }
    
    # Calcular promedios por gestor y criterio
    matriz_heatmap <- data.frame()
    
    gestores_unicos <- unique(datos_validos$gestor_completo)
    
    for (gestor in gestores_unicos) {
      datos_gestor <- datos_validos %>%
        dplyr::filter(gestor_completo == gestor)
      
      fila_gestor <- data.frame(Gestor = gestor)
      
      for (i in 1:14) {
        col_name <- sprintf("pct_criterio_%02d", i)
        if (col_name %in% names(datos_gestor)) {
          valor_promedio <- mean(datos_gestor[[col_name]], na.rm = TRUE)
          crit_nombre <- CRITERIOS_EVALUACION$criterios[[i]]$nombre
          fila_gestor[[paste0("C", i)]] <- if(!is.nan(valor_promedio)) valor_promedio else 0
        } else {
          fila_gestor[[paste0("C", i)]] <- 0
        }
      }
      
      matriz_heatmap <- rbind(matriz_heatmap, fila_gestor)
    }
    
    # Preparar matriz para heatmap
    gestores <- matriz_heatmap$Gestor
    matriz_valores <- as.matrix(matriz_heatmap[, -1])
    rownames(matriz_valores) <- gestores
    
    # Nombres cortos de criterios
    nombres_criterios <- sapply(1:14, function(i) {
      nombre <- CRITERIOS_EVALUACION$criterios[[i]]$nombre
      if (nchar(nombre) > 25) {
        nombre <- paste0(substr(nombre, 1, 22), "...")
      }
      paste0("C", i, ": ", nombre)
    })
    
    colnames(matriz_valores) <- nombres_criterios
    
    # Crear heatmap con plotly
    plot_ly(
      x = nombres_criterios,
      y = gestores,
      z = matriz_valores,
      type = "heatmap",
      colors = colorRamp(c("#dc3545", "#ffc107", "#FFB81C", "#8bc34a", "#28a745")),
      colorbar = list(
        title = "% Cumplimiento",
        thickness = 20,
        len = 0.8
      ),
      hovertemplate = paste(
        "<b>%{y}</b><br>",
        "%{x}<br>",
        "<b>%{z:.1f}%</b> de cumplimiento<br>",
        "<extra></extra>"
      )
    ) %>%
      layout(
        title = list(
          text = "<b>MAPA DE CALOR: Rendimiento por Gestor y Criterio</b><br><span style='font-size:11px;'>Visualiza fortalezas y Ã¡reas de mejora de cada gestor</span>",
          font = list(size = 13)
        ),
        xaxis = list(
          title = "<b>Criterios de EvaluaciÃ³n</b>",
          tickangle = -45,
          tickfont = list(size = 9)
        ),
        yaxis = list(
          title = "<b>Gestores</b>",
          tickfont = list(size = 10)
        ),
        margin = list(l = 150, r = 100, t = 100, b = 200)
      )
  })
  
  # ===========================
  # GRÃFICO: EVOLUCIÃ“N POR CRITERIO INDIVIDUAL (V20 MEJORADO)
  # ===========================
  
  output$grafico_evolucion_criterios_individual <- renderPlotly({
    
    datos <- datos_filtrados()
    
    if (is.null(datos) || nrow(datos) == 0 || !"mes_nombre" %in% names(datos)) {
      return(plot_ly() %>%
               layout(
                 title = "No hay datos suficientes",
                 annotations = list(
                   text = "Realiza evaluaciones en mÃºltiples meses",
                   xref = "paper",
                   yref = "paper",
                   x = 0.5,
                   y = 0.5,
                   showarrow = FALSE
                 )
               ))
    }
    
    # Verificar columnas de criterios
    cols_scores <- grep("^pct_criterio_", names(datos), value = TRUE)
    
    if (length(cols_scores) == 0) {
      return(plot_ly() %>%
               layout(
                 title = "Datos de criterios individuales no disponibles",
                 annotations = list(
                   text = "Este grÃ¡fico requiere evaluaciones con desglose por criterio",
                   xref = "paper",
                   yref = "paper",
                   x = 0.5,
                   y = 0.5,
                   showarrow = FALSE
                 )
               ))
    }
    
    # Obtener meses Ãºnicos
    meses <- datos %>%
      dplyr::filter(!is.na(mes_nombre)) %>%
      dplyr::pull(mes_nombre) %>%
      unique() %>%
      sort()
    
    if (length(meses) < 1) {
      return(plot_ly() %>% layout(title = "Sin datos de evoluciÃ³n"))
    }
    
    fig <- plot_ly()
    
    # Agregar lÃ­nea por cada criterio
    for (i in 1:14) {
      col_pct <- sprintf("pct_criterio_%02d", i)
      
      if (!col_pct %in% names(datos)) next
      
      # Calcular promedio por mes para este criterio
      datos_criterio <- datos %>%
        dplyr::filter(!is.na(mes_nombre) & !is.na(.data[[col_pct]])) %>%
        dplyr::group_by(mes_nombre) %>%
        dplyr::summarise(
          promedio_pct = mean(.data[[col_pct]], na.rm = TRUE),
          n = n(),
          .groups = "drop"
        ) %>%
        dplyr::arrange(mes_nombre)
      
      if (nrow(datos_criterio) == 0) next
      
      crit_info <- CRITERIOS_EVALUACION$criterios[[i]]
      nombre_corto <- crit_info$nombre
      if (nchar(nombre_corto) > 30) {
        nombre_corto <- paste0(substr(nombre_corto, 1, 27), "...")
      }
      
      color_criterio <- PALETA_CRITERIOS[((i-1) %% length(PALETA_CRITERIOS)) + 1]
      
      fig <- fig %>%
        add_trace(
          data = datos_criterio,
          x = ~mes_nombre,
          y = ~promedio_pct,
          type = "scatter",
          mode = "lines+markers",
          name = paste0("C", i, ": ", nombre_corto),
          line = list(color = color_criterio, width = 2),
          marker = list(size = 7, color = color_criterio),
          hovertemplate = paste0(
            "<b>", nombre_corto, "</b><br>",
            "Mes: %{x}<br>",
            "% Cumplimiento: <b>%{y:.1f}%</b><br>",
            "N evaluaciones: %{customdata}<br>",
            "<extra></extra>"
          ),
          customdata = ~n
        )
    }
    
    fig <- fig %>%
      layout(
        title = list(
          text = "<b>EVOLUCIÃ“N DETALLADA POR CRITERIO INDIVIDUAL</b><br><span style='font-size:11px;'>Seguimiento mensual del % de cumplimiento de cada criterio</span>",
          font = list(size = 13)
        ),
        xaxis = list(
          title = "<b>Mes</b>",
          tickangle = -45,
          tickfont = list(size = 10)
        ),
        yaxis = list(
          title = "<b>% Cumplimiento</b>",
          range = c(0, 100),
          tickfont = list(size = 10)
        ),
        hovermode = "closest",
        showlegend = TRUE,
        legend = list(
          orientation = "v",
          x = 1.02,
          y = 1,
          font = list(size = 9),
          bgcolor = 'rgba(255,255,255,0.95)',
          bordercolor = '#003087',
          borderwidth = 2
        ),
        margin = list(l = 70, r = 250, t = 90, b = 100),
        shapes = list(
          # LÃ­nea objetivo 85%
          list(
            type = "line",
            x0 = 0, x1 = 1,
            xref = "paper",
            y0 = 85, y1 = 85,
            line = list(color = '#28a745', width = 2, dash = "dash")
          )
        ),
        annotations = list(
          list(
            x = 0.02,
            y = 85,
            xref = "paper",
            yref = "y",
            text = "<b>Objetivo: 85%</b>",
            showarrow = FALSE,
            font = list(color = '#28a745', size = 10),
            bgcolor = 'rgba(255,255,255,0.8)',
            bordercolor = '#28a745',
            borderwidth = 1,
            borderpad = 3
          )
        ),
        plot_bgcolor = '#fafafa',
        paper_bgcolor = 'white'
      )
    
    return(fig)
  })
  
  # ===========================
  # ACTUALIZAR FILTROS DINÃMICAMENTE
  # ===========================
  
  observe({
    if (nrow(rv$evaluaciones) > 0) {
      
      if ("gestor_completo" %in% names(rv$evaluaciones)) {
        gestores_unicos <- rv$evaluaciones %>%
          dplyr::filter(!is.na(gestor_completo) & gestor_completo != "" & gestor_completo != " ") %>%
          dplyr::pull(gestor_completo) %>%
          unique() %>%
          sort()
        
        if (length(gestores_unicos) > 0) {
          updateSelectInput(
            session,
            "filtro_gestor_global",
            choices = c("Todos", gestores_unicos),
            selected = input$filtro_gestor_global
          )
        }
      }
      
      if ("mes_nombre" %in% names(rv$evaluaciones)) {
        meses_unicos <- rv$evaluaciones %>%
          dplyr::filter(!is.na(mes_nombre)) %>%
          dplyr::pull(mes_nombre) %>%
          unique() %>%
          sort()
        
        if (length(meses_unicos) > 0) {
          updatePickerInput(
            session,
            "filtro_mes_global",
            choices = c("Todos", meses_unicos)
          )
        }
      }
      
      if ("id_llamada" %in% names(rv$evaluaciones)) {
        llamadas_unicas <- rv$evaluaciones %>%
          dplyr::filter(!is.na(id_llamada) & id_llamada != "" & id_llamada != " ") %>%
          dplyr::pull(id_llamada) %>%
          unique() %>%
          sort()
        
        if (length(llamadas_unicas) > 0) {
          updatePickerInput(
            session,
            "filtro_llamada_global",
            choices = c("Todas", llamadas_unicas)
          )
        }
      }
    }
  })
  
  # ===========================
  # TABLA HISTÃ“RICO
  # ===========================
  
  output$tabla_resultados <- DT::renderDataTable({
    
    datos <- datos_filtrados()
    
    if (is.null(datos) || nrow(datos) == 0) {
      return(DT::datatable(
        data.frame(Mensaje = "No hay evaluaciones registradas"),
        options = list(dom = 't'),
        rownames = FALSE
      ))
    }
    
    datos_tabla <- datos %>%
      dplyr::mutate(
        ID = ifelse(is.na(id_llamada), "-", as.character(id_llamada)),
        Gestor = ifelse(!is.na(gestor_completo) & gestor_completo != "" & gestor_completo != " ", 
                       gestor_completo, 
                       "-"),
        Canal = toupper(canal),
        Fecha = format(timestamp, "%d/%m/%Y %H:%M"),
        Score = paste0(score_total, "/100"),
        Nivel = nivel_calidad,
        Resumen = substr(resumen, 1, 80)
      ) %>%
      dplyr::select(ID, Gestor, Canal, Fecha, Score, Nivel, Resumen)
    
    if (!is.null(input$filtro_gestor) && input$filtro_gestor != "Todos") {
      datos_tabla <- datos_tabla %>%
        dplyr::filter(Gestor == input$filtro_gestor)
    }
    
    DT::datatable(
      datos_tabla,
      options = list(
        pageLength = 25,
        lengthMenu = c(10, 25, 50, 100),
        order = list(list(3, 'desc')),
        language = list(
          url = '//cdn.datatables.net/plug-ins/1.10.11/i18n/Spanish.json'
        ),
        columnDefs = list(
          list(width = '80px', targets = 0),
          list(width = '150px', targets = 1),
          list(width = '80px', targets = 2),
          list(width = '120px', targets = 3),
          list(width = '80px', targets = 4),
          list(width = '100px', targets = 5),
          list(width = '300px', targets = 6)
        )
      ),
      rownames = FALSE,
      selection = 'single',
      filter = 'top'
    ) %>%
      DT::formatStyle(
        'Nivel',
        backgroundColor = DT::styleEqual(
          c('EXCELENTE', 'BUENO', 'REGULAR', 'DEFICIENTE'),
          c(COLORES_CASH$verde, COLORES_CASH$amarillo, COLORES_CASH$dorado, COLORES_CASH$rojo)
        ),
        color = 'white',
        fontWeight = 'bold'
      )
  })
  
  # ===========================
  # EXPORTACIÃ“N EXCEL
  # ===========================
  
  output$btn_export_excel <- downloadHandler(
    filename = function() {
      glue::glue("CASH_Evaluaciones_{format(Sys.Date(), '%Y%m%d')}.xlsx")
    },
    content = function(file) {
      
      req(nrow(datos_filtrados()) > 0)
      
      wb <- openxlsx::createWorkbook()
      openxlsx::addWorksheet(wb, "Evaluaciones")
      openxlsx::writeData(wb, "Evaluaciones", rv$evaluaciones)
      
      headerStyle <- openxlsx::createStyle(
        fgFill = COLORES_CASH$azul_principal,
        fontColour = "#FFFFFF",
        textDecoration = "bold",
        border = "TopBottomLeftRight"
      )
      
      openxlsx::addStyle(
        wb, "Evaluaciones", headerStyle,
        rows = 1,
        cols = 1:ncol(rv$evaluaciones),
        gridExpand = TRUE
      )
      
      openxlsx::saveWorkbook(wb, file, overwrite = TRUE)
    }
  )
  
  # ===========================
  # EXPORTACIÃ“N WORD INDIVIDUAL
  # ===========================
  
  output$btn_export_word_individual <- downloadHandler(
    filename = function() {
      eval <- rv$evaluacion_actual
      id_str <- ifelse(is.na(eval$id_llamada), "SIN_ID", as.character(eval$id_llamada))
      glue::glue("CASH_Evaluacion_{id_str}_{format(Sys.Date(), '%Y%m%d')}.docx")
    },
    content = function(file) {
      
      req(rv$evaluacion_actual)
      eval <- rv$evaluacion_actual
      
      withProgress(message = 'Generando reporte Word...', value = 0, {
        
        doc <- officer::read_docx()
        
        incProgress(0.2, detail = "Estructura...")
        
        doc <- doc %>%
          officer::body_add_par("CASH Uruguay", style = "heading 1") %>%
          officer::body_add_par("EvaluaciÃ³n de Calidad - GestiÃ³n de Cobranza", style = "heading 2") %>%
          officer::body_add_par(glue::glue("Fecha: {format(eval$timestamp, '%d/%m/%Y %H:%M')}"), style = "Normal") %>%
          officer::body_add_par(glue::glue("ID: {ifelse(is.na(eval$id_llamada), 'N/A', eval$id_llamada)}"), style = "Normal") %>%
          officer::body_add_par(glue::glue("Canal: {eval$canal}"), style = "Normal") %>%
          officer::body_add_par("", style = "Normal")
        
        incProgress(0.3, detail = "Resultado...")
        
        doc <- doc %>%
          officer::body_add_par("RESULTADO", style = "heading 2") %>%
          officer::body_add_par(glue::glue("Nivel: {eval$nivel_calidad}"), style = "Normal") %>%
          officer::body_add_par(glue::glue("Score: {eval$score_total}/100 puntos"), style = "Normal") %>%
          officer::body_add_par(glue::glue("Resumen: {eval$resumen}"), style = "Normal") %>%
          officer::body_add_par("", style = "Normal")
        
        incProgress(0.5, detail = "Fortalezas...")
        
        doc <- doc %>%
          officer::body_add_par("FORTALEZAS", style = "heading 2")
        
        for (f in eval$fortalezas) {
          doc <- doc %>% officer::body_add_par(paste0("â€¢ ", f), style = "Normal")
        }
        
        doc <- doc %>% officer::body_add_par("", style = "Normal")
        
        incProgress(0.7, detail = "Ãreas de mejora...")
        
        doc <- doc %>%
          officer::body_add_par("ÃREAS DE MEJORA", style = "heading 2")
        
        for (a in eval$areas_mejora) {
          doc <- doc %>% officer::body_add_par(paste0("â€¢ ", a), style = "Normal")
        }
        
        incProgress(0.9, detail = "Guardando...")
        
        print(doc, target = file)
        
        incProgress(1, detail = "Completado")
      })
    }
  )
  
  # ===========================
  # EXPORTACIÃ“N JSON INDIVIDUAL
  # ===========================
  
  output$btn_export_json_individual <- downloadHandler(
    filename = function() {
      eval <- rv$evaluacion_actual
      id_str <- ifelse(is.na(eval$id_llamada), "SIN_ID", as.character(eval$id_llamada))
      glue::glue("CASH_Evaluacion_{id_str}_{format(Sys.Date(), '%Y%m%d')}.json")
    },
    content = function(file) {
      req(rv$evaluacion_actual)
      
      json_data <- jsonlite::toJSON(rv$evaluacion_actual, pretty = TRUE, auto_unbox = TRUE)
      writeLines(json_data, file)
    }
  )
  
  # ===========================
  # CONFIGURACIÃ“N
  # ===========================
  
  output$info_sistema <- renderPrint({
    cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n")
    cat("  INFORMACIÃ“N DEL SISTEMA\n")
    cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n")
    cat("VersiÃ³n R:", R.version.string, "\n")
    cat("VersiÃ³n App: 2.0 MEJORADA CON GRÃFICOS\n")
    cat("Fecha:", format(Sys.Date(), "%d/%m/%Y"), "\n")
    cat("Target Score: 88-95 puntos\n")
    cat("Total Criterios: 14\n")
    cat("Base: 18 evaluaciones humanas\n\n")
    cat("Paquetes:\n")
    cat("  - dplyr:", as.character(packageVersion("dplyr")), "\n")
    cat("  - shiny:", as.character(packageVersion("shiny")), "\n")
    cat("  - plotly:", as.character(packageVersion("plotly")), "\n")
    cat("  - httr:", as.character(packageVersion("httr")), "\n")
    cat("  - av:", as.character(packageVersion("av")), "\n\n")
    cat("Memoria:", round(sum(gc()[,2])/1024, 2), "GB\n")
  })
  
  output$lista_criterios <- renderUI({
    
    criterios_html <- lapply(CRITERIOS_EVALUACION$criterios, function(crit) {
      tags$div(
        class = "criterio-item",
        style = "margin-bottom: 15px; padding: 10px; background: #f9f9fa; border-left: 4px solid #003087; border-radius: 4px;",
        tags$strong(
          glue::glue("{crit$id}. {crit$nombre} ({crit$max_puntos} pts)"),
          if(isTRUE(crit$critico)) tags$span(" â–ª CRÃTICO", style = "color: red; font-size: 11px;")
        ),
        tags$p(
          style = "margin: 5px 0 0 0; font-size: 12px; color: #555;",
          crit$descripcion
        ),
        tags$p(
          style = "margin: 5px 0 0 0; font-size: 11px; color = #777;",
          glue::glue("Promedio humano: {crit$promedio_humano}/{crit$max_puntos} pts ({round(crit$pct_promedio,1)}%)")
        )
      )
    })
    
    tags$div(criterios_html)
  })
  
  # Cleanup al cerrar
  onStop(function() {
    cat("\nâ–ª Cerrando aplicaciÃ³n...\n")
  })
}

cat("âœ“ SERVER (LÃ³gica del servidor) cargado\n\n")

# ==============================================================================
# BLOQUE 8: LANZAR APLICACIÃ“N
# ==============================================================================

#' Lanzar aplicaciÃ³n CASH-IA v2.0 Mejorada
run_cash_quality_analyzer <- function(port = 3838,
                                       host = "127.0.0.1",
                                       launch_browser = TRUE) {
  
  cat("\n")
  cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n")
  cat("   INICIANDO CASH-IA v2.0 - GRÃFICOS MEJORADOS\n")
  cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n")
  cat("  â–ª Calibrado con 18 evaluaciones reales\n")
  cat("  â–ª Target: 88-92 puntos\n")
  cat("  â–ª 14 Criterios exactos\n")
  cat("  â–ª NUEVO: GrÃ¡ficos mejorados de evoluciÃ³n\n")
  cat("  â–ª NUEVO: HistÃ³rico por criterio\n")
  cat("  â–ª NUEVO: Mapa de calor gestor x criterio\n")
  cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n")
  
  dependencias_criticas <- c(
    "shiny", "shinydashboard", "dplyr", "plotly",
    "DT", "httr", "jsonlite", "openxlsx", "av"
  )
  
  missing <- dependencias_criticas[!sapply(dependencias_criticas, requireNamespace, quietly = TRUE)]
  
  if (length(missing) > 0) {
    stop(glue::glue("âœ— Faltan paquetes: {paste(missing, collapse = ', ')}"))
  }
  
  cat("â–ª Dependencias verificadas\n\n")
  
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
# FIN DEL SCRIPT V20
# ==============================================================================

cat("\n")
cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n")
cat("  â–ª Script CASH-IA v2.0 MEJORADO Cargado Exitosamente\n")
cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n")
cat("   Estado: PRODUCCIÃ“N READY - GRÃFICOS MEJORADOS\n")
cat("   Mejoras V20:\n")
cat("   âœ“ Error 'spec' de stats corregido\n")
cat("   âœ“ GrÃ¡ficos de evoluciÃ³n mejorados visualmente\n")
cat("   âœ“ HistÃ³rico por criterio individual mantenido\n")
cat("   âœ“ Nuevo mapa de calor gestor x criterio\n")
cat("   âœ“ EvoluciÃ³n detallada por criterio\n")
cat("   âœ“ DiseÃ±o profesional con gradientes\n")
cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n")
cat("   Para ejecutar: run_cash_quality_analyzer()\n")
cat("â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n")

# Ejecutar automÃ¡ticamente
run_cash_quality_analyzer()
