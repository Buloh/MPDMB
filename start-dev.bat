@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === SYNERA vyvojovy server ===

if not exist ".venv\Scripts\python.exe" (
  echo Chyba: chybi .venv. Nejdrive vytvorte prostredi:
  echo   py -m venv .venv
  echo   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)

if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo Vytvoren .env z .env.example. Zkontrolujte SECRET_KEY a ALLOWED_HOSTS.
  ) else (
    echo Chyba: chybi .env i .env.example.
    exit /b 1
  )
)

echo Spoustim migrace (SQLite)...
".\.venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 (
  echo Chyba migrace.
  exit /b 1
)

echo Zajistuji vyvojovy ucet Holub...
".\.venv\Scripts\python.exe" manage.py ensure_dev_admin
if errorlevel 1 (
  echo Chyba pri vytvareni uctu Holub.
  exit /b 1
)

echo.
echo Prihlaseni do aplikace: Holub / 22552255
echo Server:   http://127.0.0.1:8000/
echo Admin:    http://127.0.0.1:8000/admin/
echo Napoveda: http://127.0.0.1:8000/napoveda/
echo.
".\.venv\Scripts\python.exe" manage.py runserver 0.0.0.0:8000
