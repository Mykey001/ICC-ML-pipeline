"""
Verify that all components of the real-time trading system are installed correctly.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent

print("="*80)
print("ICC ML REAL-TIME TRADING SYSTEM - INSTALLATION VERIFICATION")
print("="*80)
print()

# Check directory structure
print("Checking directory structure...")
print()

required_dirs = [
    "live_trading",
    "live_trading/logs",
    "src/icc_ml",
    "data/raw",
    "models",
]

all_dirs_ok = True
for dir_path in required_dirs:
    full_path = ROOT / dir_path
    exists = full_path.exists()
    status = "✓" if exists else "✗"
    print(f"  {status} {dir_path}")
    if not exists and dir_path != "models":  # models might not exist yet
        all_dirs_ok = False
        if dir_path == "live_trading/logs":
            # Create it
            full_path.mkdir(parents=True, exist_ok=True)
            print(f"    → Created directory")

print()

# Check required files
print("Checking required files...")
print()

required_files = {
    "Core System": [
        "streamlit_app.py",
        "pyproject.toml",
    ],
    "Live Trading Components": [
        "live_trading/__init__.py",
        "live_trading/pipeline_logger.py",
        "live_trading/activity_feed_ui.py",
        "live_trading/data_manager.py",
        "live_trading/instrumented_indicators.py",
        "live_trading/instrumented_features.py",
        "live_trading/realtime_engine.py",
        "live_trading/streamlit_tab9_realtime.py",
        "live_trading/trading_engine.py",
        "live_trading/risk_manager.py",
        "live_trading/monitor.py",
        "live_trading/logging_config.py",
    ],
    "Source Modules": [
        "src/icc_ml/__init__.py",
        "src/icc_ml/config.py",
        "src/icc_ml/indicators.py",
        "src/icc_ml/features.py",
        "src/icc_ml/strategy_icc.py",
        "src/icc_ml/train.py",
    ],
    "Launchers & Docs": [
        "live_trading/START_REALTIME_TRADING.bat",
        "REALTIME_TRADING_SYSTEM.md",
    ],
}

all_files_ok = True
for category, files in required_files.items():
    print(f"{category}:")
    for file_path in files:
        full_path = ROOT / file_path
        exists = full_path.exists()
        status = "✓" if exists else "✗"
        print(f"  {status} {file_path}")
        if not exists:
            all_files_ok = False
    print()

# Check Python packages
print("Checking Python packages...")
print()

required_packages = [
    "pandas",
    "numpy",
    "scikit-learn",
    "streamlit",
    "joblib",
]

optional_packages = [
    ("MetaTrader5", "Required for live MT5 trading"),
]

packages_ok = True
for package in required_packages:
    try:
        __import__(package.replace("-", "_"))
        print(f"  ✓ {package}")
    except ImportError:
        print(f"  ✗ {package} - MISSING")
        packages_ok = False

print()
print("Optional packages:")
for package, note in optional_packages:
    try:
        __import__(package)
        print(f"  ✓ {package}")
    except ImportError:
        print(f"  ⚠ {package} - Not installed ({note})")

print()

# Check for trained models
print("Checking for trained models...")
print()

model_dirs = [
    ROOT / "models",
    Path("C:/Users/MYCkey98/Downloads/models"),
]

models_found = []
for model_dir in model_dirs:
    if model_dir.exists():
        models = list(model_dir.glob("*.joblib")) + list(model_dir.glob("*.pkl"))
        for model_file in models:
            models_found.append(model_file)
            print(f"  ✓ {model_file.name} ({model_file.stat().st_size / 1024 / 1024:.2f} MB)")

if not models_found:
    print("  ⚠ No trained models found")
    print("    Train a model using Tabs 1-8 in the UI first")

print()

# Check for data files
print("Checking for data files...")
print()

data_dir = ROOT / "data" / "raw"
if data_dir.exists():
    csv_files = list(data_dir.glob("*.csv"))
    if csv_files:
        for csv_file in csv_files:
            size_mb = csv_file.stat().st_size / 1024 / 1024
            print(f"  ✓ {csv_file.name} ({size_mb:.2f} MB)")
    else:
        print("  ⚠ No CSV data files found")
        print("    Download data or use MT5 for live data")
else:
    print("  ✗ data/raw directory not found")

print()

# Final verdict
print("="*80)
print("VERIFICATION SUMMARY")
print("="*80)
print()

if all_dirs_ok and all_files_ok and packages_ok:
    print("✅ ALL CHECKS PASSED")
    print()
    print("Your real-time trading system is ready to use!")
    print()
    print("Next steps:")
    print("1. Run end-to-end test:")
    print("   python live_trading/test_realtime_system.py")
    print()
    print("2. Start the UI:")
    print("   streamlit run streamlit_app.py")
    print("   or double-click: live_trading/START_REALTIME_TRADING.bat")
    print()
    print("3. Navigate to Tab 9 and configure settings")
    print()
    print("4. Test with CSV data first (dry-run mode)")
    print()
else:
    print("⚠️ SOME CHECKS FAILED")
    print()
    if not all_dirs_ok:
        print("Missing directories - some may have been created automatically")
    if not all_files_ok:
        print("Missing files - ensure all files were created correctly")
    if not packages_ok:
        print("Missing Python packages - install with:")
        print("  pip install pandas numpy scikit-learn streamlit joblib")
    print()
    print("Review the output above for details.")

print()
print("="*80)
print()
