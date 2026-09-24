@echo off
echo ============================================
echo MT5 LIVE TRADER - DRY RUN MODE
echo ============================================
echo.
echo This will connect to MT5 and monitor for signals
echo NO REAL ORDERS will be placed (dry-run mode)
echo.
echo Make sure:
echo 1. MT5 terminal is open and logged in
echo 2. Symbol XAUUSDm is in Market Watch
echo 3. You have selected the correct model
echo.
echo Press Ctrl+C to stop at any time
echo ============================================
echo.

cd /d "%~dp0"

REM Update these paths
set MODEL_PATH=C:\Users\MYCkey98\Downloads\models\model_icc_meta.joblib
set SYMBOL=XAUUSDm
set TIMEFRAME=H1
set LOT_SIZE=0.01

python mt5_live_trader.py --model "%MODEL_PATH%" --symbol %SYMBOL% --timeframe %TIMEFRAME% --lot-size %LOT_SIZE%

pause
