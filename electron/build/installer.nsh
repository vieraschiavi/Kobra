; MV Kobra AI - pagina "Accesos directos" del instalador (NSIS / electron-builder)
; =================================================================================
; El cliente ELIGE con checkboxes si quiere el acceso directo en el Escritorio
; y/o en el Menu Inicio (la lista de programas de Windows). Ambos vienen
; marcados por defecto. En instalaciones silenciosas o actualizaciones la
; pagina no aparece y se crean los dos, como siempre.
;
; Como funciona: installSection.nsh (plantilla de electron-builder) SIEMPRE
; crea ambos accesos; el hook customInstall corre despues y borra los que el
; cliente desmarco. Textos sin acentos a proposito: este .nsh se compila como
; ANSI y los caracteres no-ASCII se romperian segun la codepage del runner.

; El mismo include se compila tambien para el DESINSTALADOR (BUILD_UNINSTALLER),
; donde nada de esto aplica: sin la guarda, las Var quedan sin referenciar y
; makensis lo trata como error (warning 6001 + warnings-as-errors).
!ifndef BUILD_UNINSTALLER

!include "nsDialogs.nsh"

Var mvkCrearEscritorio
Var mvkCrearMenuInicio
Var mvkChkEscritorio
Var mvkChkMenuInicio

!macro customInit
  ; Defaults (instalacion silenciosa, update, o si la pagina no llega a verse):
  ; se crean los dos accesos, igual que antes de existir esta pagina.
  StrCpy $mvkCrearEscritorio "1"
  StrCpy $mvkCrearMenuInicio "1"
!macroend

!macro customPageAfterChangeDir
  Page custom mvkPaginaAccesosCrear mvkPaginaAccesosSalir

  Function mvkPaginaAccesosCrear
    ; En updates no se vuelve a preguntar (y KeepShortcuts ya respeta lo elegido).
    ${if} ${isUpdated}
      Abort
    ${endIf}

    ${if} $LANGUAGE == 1046
      ; Portugues (Brasil)
      !insertmacro MUI_HEADER_TEXT "Atalhos" "Escolha onde criar os atalhos do MV Kobra AI"
      StrCpy $R7 "Criar atalho na Area de Trabalho"
      StrCpy $R8 "Criar atalho no Menu Iniciar (lista de programas do Windows)"
    ${else}
      !insertmacro MUI_HEADER_TEXT "Accesos directos" "Elegi donde crear los accesos directos de MV Kobra AI"
      StrCpy $R7 "Crear acceso directo en el Escritorio"
      StrCpy $R8 "Crear acceso directo en el Menu Inicio (lista de programas de Windows)"
    ${endIf}

    nsDialogs::Create 1018
    Pop $0
    ${If} $0 == error
      Abort
    ${EndIf}

    ${NSD_CreateCheckbox} 0 24u 100% 12u $R7
    Pop $mvkChkEscritorio
    ${NSD_Check} $mvkChkEscritorio

    ${NSD_CreateCheckbox} 0 44u 100% 12u $R8
    Pop $mvkChkMenuInicio
    ${NSD_Check} $mvkChkMenuInicio

    nsDialogs::Show
  FunctionEnd

  Function mvkPaginaAccesosSalir
    ${NSD_GetState} $mvkChkEscritorio $mvkCrearEscritorio
    ${NSD_GetState} $mvkChkMenuInicio $mvkCrearMenuInicio
  FunctionEnd
!macroend

!macro customInstall
  ; installSection.nsh ya creo ambos accesos ($newDesktopLink/$newStartMenuLink,
  ; ver plantillas nsis de app-builder-lib); aca se borran los NO elegidos.
  ${if} $mvkCrearEscritorio != "1"
    Delete "$newDesktopLink"
    System::Call 'Shell32::SHChangeNotify(i 0x8000000, i 0, i 0, i 0)'
  ${endIf}
  ${if} $mvkCrearMenuInicio != "1"
    Delete "$newStartMenuLink"
  ${endIf}
!macroend

!endif
