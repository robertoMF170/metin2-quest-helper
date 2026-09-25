@echo off
rem MT2Guide - instalador do Quest Helper puro
rem Copia a pasta MT2Guide + troca o init.py (guarda o dos bots)
set /p GAMEDIR=Pasta do jogo (ex: D:\metin2\tr-TR):
if not exist "%GAMEDIR%\metin2client.exe" (
  echo Nao encontrei o metin2client.exe nessa pasta!
  pause
  exit /b 1
)
echo A copiar MT2Guide...
xcopy /E /I /Y "%~dp0MT2Guide" "%GAMEDIR%\MT2Guide"
echo A guardar o init.py dos bots (init_bots.py)...
if exist "%GAMEDIR%\init.py" copy /Y "%GAMEDIR%\init.py" "%GAMEDIR%\init_bots.py"
echo A instalar o init do guia...
copy /Y "%~dp0init_guide.py" "%GAMEDIR%\init.py"
echo.
echo PRONTO! Abre o jogo - o guia abre sozinho no mundo.
echo (voltar aos bots: copiar init_bots.py de volta para init.py)
pause
