@echo off
chcp 65001 >NUL
cd /d "%~dp0"
set "PY="
where py >NUL 2>&1 && set "PY=py"
if not defined PY where python >NUL 2>&1 && set "PY=python"
if not defined PY (
  echo Python was not found. See README.md
  pause
  exit /b 1
)
%PY% -m unittest discover -s tests -v
echo.
pause
