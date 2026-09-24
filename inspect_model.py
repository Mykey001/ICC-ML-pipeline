"""
Inspect the trained model bundle to verify deployment readiness.
"""
import joblib
import sys
from pathlib import Path

def inspect_model_bundle(model_path):
    """Comprehensive model bundle inspection."""
    
    print("=" * 80)
    print("MODEL BUNDLE INSPECTION")
    print("=" * 80)
    print(f"\nModel path: {model_path}")
    
    try:
        # Load the model bundle
        bundle = joblib.load(model_path)
        print("✓ Model loaded successfully")
        
    except Exception as e:
        print(f"✗ FAILED to load model: {e}")
        return
    
    print("\n" + "-" * 80)
    print("1. BUNDLE STRUCTURE")
    print("-" * 80)
    
    # Check bundle type
    if not isinstance(bundle, dict):
        print(f"✗ CRITICAL: Bundle is {type(bundle)}, expected dict")
        print("   Model may not be compatible with live_inference.py")
        return
    else:
        print("✓ Bundle is a dict")
    
    # List all keys
    print(f"\nKeys in bundle: {list(bundle.keys())}")
    
    # Check required keys
    required_keys = ["model", "feature_cols", "threshold"]
    missing_keys = [k for k in required_keys if k not in bundle]
    
    if missing_keys:
        print(f"\n✗ CRITICAL: Missing required keys: {missing_keys}")
    else:
        print("\n✓ All required keys present")
    
    print("\n" + "-" * 80)
    print("2. MODEL OBJECT")
    print("-" * 80)
    
    if "model" in bundle:
        model = bundle["model"]
        print(f"Model type: {type(model).__name__}")
        print(f"Module: {type(model).__module__}")
        
        # Check if it's a calibrated model
        if "CalibratedClassifier" in str(type(model)):
            print("✓ Model is calibrated (good for probabilities)")
            if hasattr(model, "estimator"):
                print(f"  Base estimator: {type(model.estimator).__name__}")
        
        # Check required methods
        required_methods = ["predict", "predict_proba"]
        has_methods = [hasattr(model, m) for m in required_methods]
        
        if all(has_methods):
            print("✓ Model has predict() and predict_proba() methods")
        else:
            missing = [m for m, has in zip(required_methods, has_methods) if not has]
            print(f"✗ CRITICAL: Model missing methods: {missing}")
    else:
        print("✗ CRITICAL: No 'model' key in bundle")
    
    print("\n" + "-" * 80)
    print("3. FEATURE COLUMNS")
    print("-" * 80)
    
    if "feature_cols" in bundle:
        feature_cols = bundle["feature_cols"]
        print(f"Number of features: {len(feature_cols)}")
        print(f"Feature columns type: {type(feature_cols)}")
        
        if len(feature_cols) == 0:
            print("✗ CRITICAL: No feature columns defined")
        elif len(feature_cols) < 10:
            print("⚠ WARNING: Very few features (< 10). Is this expected?")
        else:
            print("✓ Feature count looks reasonable")
        
        print(f"\nFirst 10 features:")
        for i, col in enumerate(feature_cols[:10], 1):
            print(f"  {i:2d}. {col}")
        
        if len(feature_cols) > 10:
            print(f"  ... and {len(feature_cols) - 10} more")
        
        print(f"\nLast 5 features:")
        for col in feature_cols[-5:]:
            print(f"  - {col}")
            
    else:
        print("✗ CRITICAL: No 'feature_cols' key in bundle")
    
    print("\n" + "-" * 80)
    print("4. THRESHOLD")
    print("-" * 80)
    
    if "threshold" in bundle:
        threshold = bundle["threshold"]
        print(f"Threshold: {threshold}")
        print(f"Type: {type(threshold)}")
        
        if not isinstance(threshold, (int, float)):
            print(f"✗ WARNING: Threshold is {type(threshold)}, expected number")
        elif threshold < 0 or threshold > 1:
            print(f"✗ WARNING: Threshold {threshold} outside [0, 1] range")
        elif threshold == 0.5:
            print("⚠ Threshold is 0.5 (default). Was it optimized on pips?")
        else:
            print("✓ Threshold looks optimized")
    else:
        print("⚠ No 'threshold' key (will default to 0.5)")
    
    print("\n" + "-" * 80)
    print("5. METADATA")
    print("-" * 80)
    
    metadata_keys = ["n_training_trades", "model_type", "fold_results", 
                     "training_date", "symbol", "timeframe"]
    
    found_metadata = {k: bundle.get(k) for k in metadata_keys if k in bundle}
    
    if found_metadata:
        for key, value in found_metadata.items():
            print(f"{key}: {value}")
    else:
        print("⚠ No metadata found (optional but useful)")
    
    # Show all other keys
    other_keys = [k for k in bundle.keys() if k not in required_keys + metadata_keys]
    if other_keys:
        print(f"\nOther keys in bundle: {other_keys}")
    
    print("\n" + "-" * 80)
    print("6. TEST MODEL PREDICTION")
    print("-" * 80)
    
    if "model" in bundle and "feature_cols" in bundle:
        try:
            import numpy as np
            
            model = bundle["model"]
            n_features = len(bundle["feature_cols"])
            
            # Create dummy input
            X_test = np.random.randn(1, n_features)
            
            # Try prediction
            pred = model.predict(X_test)
            proba = model.predict_proba(X_test)
            
            print("✓ Model can make predictions")
            print(f"  Test prediction: {pred[0]}")
            print(f"  Test probabilities: {proba[0]}")
            
        except Exception as e:
            print(f"✗ FAILED prediction test: {e}")
    
    print("\n" + "=" * 80)
    print("DEPLOYMENT READINESS SUMMARY")
    print("=" * 80)
    
    # Final verdict
    critical_checks = []
    
    if not isinstance(bundle, dict):
        critical_checks.append("Bundle is not a dict")
    
    if "model" not in bundle:
        critical_checks.append("Missing 'model' key")
    
    if "feature_cols" not in bundle:
        critical_checks.append("Missing 'feature_cols' key")
    elif len(bundle["feature_cols"]) == 0:
        critical_checks.append("Zero feature columns")
    
    if "model" in bundle:
        model = bundle["model"]
        if not hasattr(model, "predict_proba"):
            critical_checks.append("Model lacks predict_proba()")
    
    if critical_checks:
        print("\n✗ MODEL NOT READY FOR DEPLOYMENT")
        print("\nCritical issues:")
        for issue in critical_checks:
            print(f"  - {issue}")
        print("\nFix these issues before using in live trading.")
    else:
        print("\n✓ MODEL PASSES BASIC CHECKS")
        print("\nNext steps:")
        print("  1. Run live_trading_checklist() with recent data")
        print("  2. Verify fold results show positive edge")
        print("  3. Test on demo account for ≥1 month")
        print("  4. Monitor for train/live divergence")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    model_path = r"c:\Users\MYCkey98\Downloads\models\model_icc_meta.joblib"
    inspect_model_bundle(model_path)
