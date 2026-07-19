@echo off
REM NexusAgent - environment setup (Windows). Installs backend + frontend deps.
cd /d %~dp0

if not exist .env (
  echo ==^> Creating .env from .env.example
  copy .env.example .env
)
if not exist frontend\.env.local (
  echo ==^> Creating frontend\.env.local from example
  copy frontend\.env.example frontend\.env.local
)

echo ==^> Installing backend (editable^) + dev tools...
python -m pip install --upgrade pip
pip install -e ".[dev]"

echo ==^> Installing frontend dependencies (npm ci^)...
cd frontend
call npm ci

echo.
echo ==^> Setup complete.
echo     Docker users:        run.bat
echo     Non-Docker users:    see docs/user-guide/quickstart.md
