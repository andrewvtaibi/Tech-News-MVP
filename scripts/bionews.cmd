@echo off
setlocal
REM Use the venv python if present
set PYEXE=%~dp0..\ .venv\Scripts\python.exe
if not exist "%PYEXE%" set PYEXE=python

REM Pass through args to cli.py
"%PYEXE%" "%~dp0..\cli.py" %*
endlocal
