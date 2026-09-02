@echo off
rem MV Kobra AI - Construir el instalador OWNER haciendo doble clic.
rem
rem Es un envoltorio de dos lineas a proposito: la tuberia de compilacion
rem (Python, Node, dependencias, PyInstaller, electron-builder) vive en un
rem solo archivo -- construir_instalador.bat -- y esta edicion solo le pasa
rem el argumento. Duplicarla habria dejado dos tuberias que se separan solas
rem a la primera correccion que se haga en una y no en la otra.
rem
rem Antes de correrlo, una sola vez, deja el sello firmado a mano:
rem     setx KOBRA_OWNER_SELLO_ARCHIVO C:\ruta\sello_owner.txt
rem (ese archivo NO va al repo: es la credencial que hace owner a una copia)
call "%~dp0construir_instalador.bat" owner
