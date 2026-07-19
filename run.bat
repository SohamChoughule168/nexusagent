@echo off
REM NexusAgent - one-command local development launcher (Windows).
REM Mirrors run.sh: copies env files, launches the Docker stack, waits for
REM backend health, then seeds the Brightpath demo workspace.
cd /d %~dp0

if not exist .env (
  echo ==^> Creating .env from .env.example
  copy .env.example .env
)
if not exist frontend\.env.local (
  echo ==^> Creating frontend\.env.local from example
  copy frontend\.env.example frontend\.env.local
)

where docker >nul 2>nul
if %errorlevel%==0 (
  echo ==^> Docker detected - launching full stack
  docker compose up -d --build

  echo ==^> Waiting for backend health (http://localhost:8000/health)...
  :waitloop
  curl -fsS http://localhost:8000/health >nul 2>nul
  if %errorlevel%==0 (
    echo ==^> Backend is healthy.
    goto seed
  )
  timeout /t 2 >nul
  goto waitloop

  :seed
  echo ==^> Seeding demo workspace (Brightpath org + Aria agent)...
  docker compose run --rm backend python backend/scripts/seed_demo.py --init-db

  echo.
  echo NexusAgent is up:
  echo   Landing : http://localhost:3000/
  echo   Demo    : http://localhost:3000/demo
  echo   Sign in : http://localhost:3000/login  (demo@nexusagent.dev / nexusagent-demo)
  echo.
  echo Stop the stack later with:  docker compose down
  exit /b 0
)

echo Docker was not found. Use the non-Docker local workflow:
echo   1. Start PostgreSQL + Redis (e.g. "docker compose up -d db redis").
echo   2. setup.bat                       # install backend + frontend deps
echo   3. pip install -e .
echo   4. python backend/scripts/seed_demo.py --init-db
echo   5. uvicorn app.main:app --reload --port 8000
echo   6. cd frontend && npm run dev
echo See docs/user-guide/quickstart.md for the full guide.
exit /b 1
