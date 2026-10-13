@echo off
chcp 65001 >NUL
cd /d "%~dp0"
set "PY="
where py >NUL 2>&1 && set "PY=py"
if not defined PY where python >NUL 2>&1 && set "PY=python"
if not defined PY (
  echo Python was not found.
  echo Please install it: https://www.python.org/downloads/
  echo During installation tick "Add python.exe to PATH".
  pause
  exit /b 1
)
echo Converting every file in the input folder ...
echo.
%PY% notencode.py %*
echo.
echo Done. Results are in the output folder.
pause
