@echo off
echo ============================================
echo MT5 LIVE TRADER - LIVE MODE
echo ============================================
echo.
echo ******** WARNING ********
echo REAL ORDERS WILL BE PLACED!
echo ************************
echo.
echo Make sure:
echo 1. You have tested on DEMO for at least 1 month
echo 2. MT5 terminal is open and logged in
echo 3. You understand the risks
echo 4. Risk settings are appropriate
echo.

set /p CONFIRM="Type YES to continue with LIVE trading: "

if not "%CONFIRM%"=="YES" (
    echo.
    echo Cancelled. Use START_MT5_LIVE_DRY_RUN.bat for testing.
    pause
    exit
)

echo.
echo Starting LIVE trading in 10 seconds...
echo Press Ctrl+C to cancel!
timeout /t 10

cd /d "%~dp0"

REM Update these paths
set MODEL_PATH=C:\Users\MYCkey98\Downloads\models\model_icc_meta.joblib
set SYMBOL=XAUUSDm
set TIMEFRAME=H1
set LOT_SIZE=0.01

python mt5_live_trader.py --model "%MODEL_PATH%" --symbol %SYMBOL% --timeframe %TIMEFRAME% --lot-size %LOT_SIZE% --live

pause
