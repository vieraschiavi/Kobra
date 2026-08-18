; MV Kobra AI - paginas propias del instalador (NSIS / electron-builder)
; =================================================================================
; Dos cosas que el asistente de serie no hace y que rompian instalaciones reales:
;
; 1. ACCESOS DIRECTOS: el cliente ELIGE con checkboxes si quiere el acceso en el
;    Escritorio y/o en el Menu Inicio. Ambos vienen marcados por defecto.
;
; 2. CARPETA DE DATOS Y ESPACIO EN DISCO. Elegir donde INSTALAR ya se podia
;    (boton Examinar), pero no alcanzaba: los datos —cartera, exports, backups,
;    modelos, auditoria— iban siempre a %LOCALAPPDATA%, o sea al disco del
;    perfil de Windows, o sea C: en la practica totalidad de las maquinas. El
;    que instalaba en D: porque su C: estaba lleno chocaba igual contra C: en el
;    primer import de cartera, y el error aparecia lejos de la causa. Ahora se
;    elige, se avisa cuanto lugar queda, y la eleccion se anota en el mismo
;    puntero que lee kobra/rutas.py (carpeta_datos.txt).
;
;    Ademas se revisa el espacio ANTES de empezar a copiar. Un instalador NSIS
;    que se queda sin disco a mitad muere con "error escribiendo al archivo" y
;    un nombre de .tmp: un mensaje que no le dice a nadie que el problema es el
;    disco. Mas vale preguntarlo al principio.
;
; En instalaciones silenciosas o actualizaciones las paginas no aparecen y todo
; toma los valores de siempre.
;
; Como funciona lo de los accesos: installSection.nsh (plantilla de
; electron-builder) SIEMPRE crea ambos; el hook customInstall corre despues y
; borra los que el cliente desmarco. Textos sin acentos a proposito: este .nsh
; se compila como ANSI y los caracteres no-ASCII se romperian segun la codepage
; del runner.

; El mismo include se compila tambien para el DESINSTALADOR (BUILD_UNINSTALLER),
; donde nada de esto aplica: sin la guarda, las Var quedan sin referenciar y
; makensis lo trata como error (warning 6001 + warnings-as-errors).
!ifndef BUILD_UNINSTALLER

!include "nsDialogs.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

; Lo mismo que MIN_LIBRE_MB en kobra/rutas.py. No es el tamano del programa:
; es lo que consume trabajar (importar cartera, entrenar, exportar, backup).
!define MVK_MIN_DATOS_MB 500
; Para instalar hacen falta el payload descomprimido mas el .7z temporal.
!define MVK_MIN_INSTALL_MB 900

Var mvkCrearEscritorio
Var mvkCrearMenuInicio
Var mvkChkEscritorio
Var mvkChkMenuInicio

Var mvkDirDatos
Var mvkTxtDatos
Var mvkLblEspacio
Var mvkMejorDisco
Var mvkMejorLibre

; Deja en $R9 los MB libres del disco donde cae la ruta $R8.
!macro MvkLibresMB
  StrCpy $R7 $R8 3          ; "D:\" — la raiz de esa ruta
  StrCpy $R9 0
  ${DriveSpace} "$R7" "/D=F /S=M" $R9
!macroend

; --- El disco por defecto para los DATOS --------------------------------------
; La carpeta de instalacion la sigue eligiendo el asistente (boton Examinar) y su
; valor por defecto lo impone electron-builder: sale de `setInstallModePerUser`
; en multiUser.nsh, que reescribe $INSTDIR al salir de la pagina "para quien
; instalar". No hay hook libre para cambiarlo — el `PRE` de la pagina de
; directorio ya lo ocupa `skipPageIfUpdated` y redefinirlo no compila.
;
; Pero el disco de instalacion casi no importa: el programa pesa ~270 MB fijos.
; Lo que crece es la carpeta de DATOS —cartera, exportaciones, modelos, backups,
; auditoria— y esa si es nuestra. Por defecto va al disco fijo con MAS lugar, no
; al del perfil de Windows. En una maquina de un solo disco eso sigue siendo C:
; y no cambia nada; en una con C: chico y D: grande, arranca en D:.
Function mvkMirarDisco
  ; ${GetDrives} llama aca una vez por unidad: $9 = "D:\", $8 = tipo.
  StrCpy $R8 "$9"
  !insertmacro MvkLibresMB
  ${if} $R9 > $mvkMejorLibre
    StrCpy $mvkMejorLibre $R9
    StrCpy $mvkMejorDisco "$9"
  ${endif}
  Push $0                 ; $0 vacio = seguir con la proxima unidad
FunctionEnd

!macro customInit
  ; Defaults (instalacion silenciosa, update, o si la pagina no llega a verse):
  ; se crean los dos accesos y los datos van donde iban siempre.
  StrCpy $mvkCrearEscritorio "1"
  StrCpy $mvkCrearMenuInicio "1"
  StrCpy $mvkDirDatos "$LOCALAPPDATA\MV Kobra AI"

  ; Solo discos fijos: un pendrive o una unidad de red con mucho lugar no es
  ; donde queres que viva la base de una empresa.
  StrCpy $mvkMejorDisco ""
  StrCpy $mvkMejorLibre 0
  ${GetDrives} "HDD" mvkMirarDisco

  ; Si el disco con mas lugar NO es el del perfil, los datos arrancan ahi.
  StrCpy $R8 "$LOCALAPPDATA"
  !insertmacro MvkLibresMB
  StrCpy $R6 $R7                      ; raiz del disco del perfil ("C:\")
  ${if} $mvkMejorDisco != ""
  ${andif} $mvkMejorDisco != $R6
  ${andif} $mvkMejorLibre > $R9
    ; En dos pasos y no "$mvkMejorDiscoMV Kobra AI": pegado a una letra, el
    ; nombre de la variable se vuelve ambiguo para el parser de NSIS. Lo
    ; resuelve bien, pero depender de eso en un instalador que nadie puede
    ; depurar comodo no vale los dos caracteres que ahorra.
    StrCpy $R5 "MV Kobra AI\datos"
    StrCpy $mvkDirDatos "$mvkMejorDisco$R5"
  ${endif}

  ; El disco de los temporales. NSIS se auto-descomprime ahi ANTES de correr
  ; una sola linea de este script, asi que si ya no hubiera lugar no llegariamos
  ; hasta aca; lo que si se puede es avisar antes de la extraccion del payload,
  ; que es la parte grande y la que suele reventar.
  StrCpy $R8 "$TEMP"
  !insertmacro MvkLibresMB
  ${if} $R9 < ${MVK_MIN_INSTALL_MB}
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
      "En el disco de archivos temporales ($R7) quedan $R9 MB libres.$\r$\n$\r$\n\
Windows descomprime todo instalador ahi antes de copiar nada, asi que con \
menos de ${MVK_MIN_INSTALL_MB} MB la instalacion puede cortarse a mitad con un \
error de escritura.$\r$\n$\r$\n\
Podes liberar espacio en $R7, o cerrar y usar Instalar_en_otro_disco.bat, que \
manda los temporales al disco donde esta el instalador.$\r$\n$\r$\n\
Continuar igual?" IDOK +2
    Abort
  ${endIf}
!macroend

!macro customPageAfterChangeDir
  Page custom mvkPaginaDatosCrear mvkPaginaDatosSalir
  Page custom mvkPaginaAccesosCrear mvkPaginaAccesosSalir

  ; --- Pagina: donde guardar los datos --------------------------------------
  Function mvkPaginaDatosRefrescar
    ; Muestra cuanto queda en el disco elegido. Sin este numero, "elegi un
    ; disco" es adivinar: el usuario no tiene por que saber cual tiene lugar.
    StrCpy $R8 $mvkDirDatos
    !insertmacro MvkLibresMB
    ${if} $LANGUAGE == 1046
      ${if} $R9 < ${MVK_MIN_DATOS_MB}
        StrCpy $R6 "Atencao: em $R7 restam apenas $R9 MB livres (recomendado: ${MVK_MIN_DATOS_MB} MB)."
      ${else}
        StrCpy $R6 "Espaco livre em $R7: $R9 MB."
      ${endIf}
    ${else}
      ${if} $R9 < ${MVK_MIN_DATOS_MB}
        StrCpy $R6 "Atencion: en $R7 quedan solo $R9 MB libres (recomendado: ${MVK_MIN_DATOS_MB} MB)."
      ${else}
        StrCpy $R6 "Espacio libre en $R7: $R9 MB."
      ${endIf}
    ${endIf}
    ${NSD_SetText} $mvkLblEspacio $R6
  FunctionEnd

  Function mvkPaginaDatosExaminar
    nsDialogs::SelectFolderDialog "" $mvkDirDatos
    Pop $0
    ${if} $0 != error
      StrCpy $mvkDirDatos $0
      ${NSD_SetText} $mvkTxtDatos $mvkDirDatos
      Call mvkPaginaDatosRefrescar
    ${endIf}
  FunctionEnd

  Function mvkPaginaDatosCrear
    ; En updates la carpeta ya esta elegida y mover datos por su cuenta seria
    ; peor que el problema: no se vuelve a preguntar.
    ${if} ${isUpdated}
      Abort
    ${endIf}

    ${if} $LANGUAGE == 1046
      !insertmacro MUI_HEADER_TEXT "Pasta de dados" "Escolha em qual disco o MV Kobra AI vai guardar seus dados"
      StrCpy $R5 "Carteira, exportacoes, modelos e backups sao gravados aqui. Escolha um disco com espaco: instalar em D: nao ajuda se os dados forem para um C: lotado."
      StrCpy $R4 "Procurar..."
    ${else}
      !insertmacro MUI_HEADER_TEXT "Carpeta de datos" "Elegi en que disco va a guardar sus datos MV Kobra AI"
      StrCpy $R5 "Aca se graban la cartera, las exportaciones, los modelos y los backups. Elegi un disco con lugar: instalar en D: no sirve de nada si los datos van a un C: lleno."
      StrCpy $R4 "Examinar..."
    ${endIf}

    nsDialogs::Create 1018
    Pop $0
    ${If} $0 == error
      Abort
    ${EndIf}

    ${NSD_CreateLabel} 0 0 100% 28u $R5
    Pop $1

    ${NSD_CreateText} 0 34u 78% 13u $mvkDirDatos
    Pop $mvkTxtDatos

    ${NSD_CreateButton} 80% 33u 20% 15u $R4
    Pop $2
    ${NSD_OnClick} $2 mvkPaginaDatosExaminar

    ${NSD_CreateLabel} 0 54u 100% 20u ""
    Pop $mvkLblEspacio
    Call mvkPaginaDatosRefrescar

    nsDialogs::Show
  FunctionEnd

  Function mvkPaginaDatosSalir
    ${NSD_GetText} $mvkTxtDatos $mvkDirDatos
    ${if} $mvkDirDatos == ""
      StrCpy $mvkDirDatos "$LOCALAPPDATA\MV Kobra AI"
    ${endIf}
    ; Poco espacio no bloquea —puede ser una maquina de prueba, o el usuario
    ; sabe que va a liberar—, pero no puede pasar en silencio.
    StrCpy $R8 $mvkDirDatos
    !insertmacro MvkLibresMB
    ${if} $R9 < ${MVK_MIN_DATOS_MB}
      MessageBox MB_YESNO|MB_ICONEXCLAMATION \
        "En $R7 quedan $R9 MB libres, por debajo de los ${MVK_MIN_DATOS_MB} MB \
recomendados.$\r$\n$\r$\nEs muy probable que se quede sin espacio al importar \
una cartera o al exportar.$\r$\n$\r$\nUsar esta carpeta igual?" IDYES +2
      Abort
    ${endIf}
  FunctionEnd

  ; --- Pagina: accesos directos ---------------------------------------------
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

  ; El puntero a la carpeta de datos. Vive SIEMPRE en la ubicacion por defecto
  ; y no en la elegida: si viviera en el disco elegido y ese disco se
  ; desconecta, no habria forma de saber a donde apuntaba. Lo lee
  ; kobra/rutas.py::carpeta_elegida(), que ademas valida que siga escribible
  ; antes de usarla — y si no lo esta, cae al default en vez de no abrir.
  CreateDirectory "$LOCALAPPDATA\MV Kobra AI"
  ${if} $mvkDirDatos != ""
    CreateDirectory "$mvkDirDatos"
    FileOpen $0 "$LOCALAPPDATA\MV Kobra AI\carpeta_datos.txt" w
    ${if} $0 != ""
      FileWrite $0 "$mvkDirDatos"
      FileClose $0
    ${endIf}
  ${endIf}
!macroend

!endif
