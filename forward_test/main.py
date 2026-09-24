"""
CLI Entry Point for the Forward Test System.

Usage:
    # Dry run (logs decisions, no real orders)
    python -m forward_test.main --config forward_test/config.yaml --dry-run
    
    # Live forward test (places real orders on the logged-in MT5 terminal)
    python -m forward_test.main --config forward_test/config.yaml
"""
import argparse
import logging
import sys
from pathlib import Path

import yaml

from .engine import ForwardTestEngine

def setup_logging(config_path: str):
    """Configure logging based on the yaml config."""
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        log_cfg = config.get("logging", {})
        level_str = log_cfg.get("level", "INFO")
        log_dir = Path(config_path).parent.parent / log_cfg.get("log_dir", "forward_test/logs")
    except Exception:
        level_str = "INFO"
        log_dir = Path("forward_test/logs")

    level = getattr(logging, level_str.upper(), logging.INFO)
    
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "forward_test.log"

    # Fix Windows console encoding for emojis
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )

def main():
    parser = argparse.ArgumentParser(description="ICC ML Forward Test System")
    parser.add_argument(
        "--config",
        type=str,
        default="forward_test/config.yaml",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run mode (override config.yaml)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Force live mode (override config.yaml)"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    setup_logging(args.config)
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize engine
        engine = ForwardTestEngine(args.config)
        
        # Override dry_run if passed via CLI
        if args.dry_run:
            engine.dry_run = True
        elif args.live:
            engine.dry_run = False
            
        # Start engine (blocks until stopped via Ctrl+C)
        engine.start()
        
    except FileNotFoundError as e:
        logger.error(f"Configuration or model file not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
