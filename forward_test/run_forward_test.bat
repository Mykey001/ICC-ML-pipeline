@echo off
setlocal

cd /d "%~dp0\.."

echo ===============================================================================
echo ICC ML Forward Test System
echo ===============================================================================

echo Select mode:
echo 1) Dry Run (Logs decisions, no orders placed)
echo 2) Live Forward Test (Real orders placed on active MT5 terminal)
echo.

set /p mode="Enter choice [1 or 2]: "

if "%mode%"=="1" (
    echo Starting in DRY RUN mode...
    python -m forward_test.main --config forward_test/config.yaml --dry-run
) else if "%mode%"=="2" (
    echo Starting in LIVE mode...
    python -m forward_test.main --config forward_test/config.yaml --live
) else (
    echo Invalid choice. Exiting.
)

pause
