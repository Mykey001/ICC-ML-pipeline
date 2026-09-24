"""
Quick test to verify streamlit imports work correctly.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "live_trading"))

print("Testing imports...")
print()

try:
    # Test core imports
    from icc_ml.config import StrategyConfig, SymbolSpec
    print("✓ icc_ml.config imports")
    
    # Test live trading imports
    from live_trading.streamlit_tab9_realtime import render_tab9_realtime
    print("✓ streamlit_tab9_realtime imports")
    
    from live_trading.pipeline_logger import get_pipeline_logger
    print("✓ pipeline_logger imports")
    
    from live_trading.activity_feed_ui import ActivityFeedUI
    print("✓ activity_feed_ui imports")
    
    print()
    print("✅ All imports successful!")
    print()
    print("The streamlit app should now work correctly.")
    
except Exception as e:
    print(f"✗ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
