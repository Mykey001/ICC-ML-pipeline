@echo off
REM ============================================================================
REM ICC ML Real-Time Trading System Launcher
REM ============================================================================

echo.
echo ============================================================================
echo ICC ML REAL-TIME TRADING SYSTEM
echo ============================================================================
echo.
echo Starting Streamlit UI with complete pipeline transparency...
echo.
echo Features:
echo - Automatic bar monitoring (no manual clicking)
echo - Real-time activity feed
echo - Complete pipeline visibility
echo - Step-by-step logging with timing
echo.
echo ============================================================================
echo.

cd /d "%~dp0.."

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Set Python path
set PYTHONPATH=%CD%;%CD%\src;%CD%\live_trading

REM Start Streamlit
echo Starting Streamlit...
echo.
streamlit run streamlit_app.py

pause
