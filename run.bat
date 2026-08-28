@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PROJECT_PYTHON=%~dp0venv\Scripts\python.exe"
set "OFFLINE_WHEELS=%~dp0vendor\wheels"

if exist "%PROJECT_PYTHON%" goto ensure_dependencies

echo Chua co moi truong Python. Dang tao venv va cai dependencies...
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv "%~dp0venv"
    goto venv_created
)

where python >nul 2>&1
if errorlevel 1 goto python_missing
python -m venv "%~dp0venv"

:venv_created
if errorlevel 1 goto setup_failed

:ensure_dependencies
"%PROJECT_PYTHON%" -c "import sys, struct; raise SystemExit(0 if sys.version_info[:2] in [(3,11),(3,12),(3,13),(3,14)] and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 goto python_unsupported

"%PROJECT_PYTHON%" -c "import copilot, keyboard, mss" >nul 2>&1
if not errorlevel 1 goto run_project

if not exist "%OFFLINE_WHEELS%" goto offline_wheels_missing

echo Dang cai dependencies tu goi offline trong repo...
"%PROJECT_PYTHON%" -m pip install --no-index --find-links="%OFFLINE_WHEELS%" -r "%~dp0requirements.txt"
if errorlevel 1 goto setup_failed

:run_project
"%PROJECT_PYTHON%" "%~dp0main.py" %*
set "PROJECT_EXIT_CODE=%ERRORLEVEL%"

if not "%PROJECT_EXIT_CODE%"=="0" (
    echo.
    echo Project dung voi ma loi %PROJECT_EXIT_CODE%.
    pause
)

exit /b %PROJECT_EXIT_CODE%

:setup_failed
echo.
echo [LOI] Khong the khoi tao project.
pause
exit /b 1

:python_missing
echo [LOI] Khong tim thay Python. Hay cai Python 3.11 tro len.
pause
exit /b 1

:python_unsupported
echo [LOI] Can Python 64-bit phien ban 3.11, 3.12, 3.13 hoac 3.14.
pause
exit /b 1

:offline_wheels_missing
echo [LOI] Thieu thu muc vendor\wheels chua cac thu vien offline.
echo Hay tai lai day du repository.
pause
exit /b 1
