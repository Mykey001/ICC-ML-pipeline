@echo off
echo ============================================
echo ICC ML - Live Trading Dashboard
echo ============================================
echo.
echo Starting Streamlit interface...
echo Navigate to Tab 9 for Live Trading
echo.
echo Press Ctrl+C to stop
echo ============================================
echo.

cd /d "%~dp0"
streamlit run streamlit_app.py

pause
