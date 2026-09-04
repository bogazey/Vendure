@echo off
setlocal enabledelayedexpansion

echo == Local Media Downloader ==

set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
set "BACKEND_DIR=%ROOT_DIR%\backend"
set "FRONTEND_DIR=%ROOT_DIR%\frontend"
set "FRONTEND_URL=http://127.0.0.1:5173"

REM 1. Verify Python
where python >nul 2>nul
if errorlevel 1 (
  echo Error: python was not found on PATH. Install Python 3.12+ and try again.
  exit /b 1
)
echo -^> Python found.

REM 2. Create virtual environment if missing
if not exist "%BACKEND_DIR%\.venv" (
  echo -^> Creating Python virtual environment...
  python -m venv "%BACKEND_DIR%\.venv"
)

call "%BACKEND_DIR%\.venv\Scripts\activate.bat"

REM 3. Install backend requirements if needed
echo -^> Installing backend dependencies...
pip install --disable-pip-version-check -q -r "%BACKEND_DIR%\requirements.txt"

REM 4. Verify FFmpeg
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo Warning: FFmpeg was not found on PATH. The app will start, but downloads
  echo requiring merging/conversion will fail until FFmpeg is installed.
  echo See the README for installation instructions.
) else (
  echo -^> FFmpeg found.
)

REM 5. Install frontend dependencies if needed
if not exist "%FRONTEND_DIR%\node_modules" (
  echo -^> Installing frontend dependencies...
  pushd "%FRONTEND_DIR%"
  call npm install
  popd
)

REM 6. Launch backend
echo -^> Starting backend on http://127.0.0.1:8000 ...
start "Local Media Downloader - Backend" cmd /k "cd /d "%BACKEND_DIR%" && call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

REM 7. Launch frontend
echo -^> Starting frontend on %FRONTEND_URL% ...
start "Local Media Downloader - Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev -- --host 127.0.0.1 --port 5173"

REM 8. Open the browser after a short delay
timeout /t 5 /nobreak >nul
start "" "%FRONTEND_URL%"

echo.
echo Backend and frontend are starting in separate windows.
echo Close those windows to stop the application.
endlocal
