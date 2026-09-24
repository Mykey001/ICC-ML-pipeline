"""
Comprehensive logging configuration for the ICC ML trading system.

Configures:
- File logging with rotation
- Console logging
- Structured logging format
- Different log levels for different modules
- Activity feed integration
"""
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logging(
    log_dir: str = "live_trading/logs",
    log_level: str = "INFO",
    console_level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 10,
) -> logging.Logger:
    """
    Setup comprehensive logging for the trading system.
    
    Args:
        log_dir: Directory for log files
        log_level: Default log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console_level: Console log level
        max_bytes: Maximum size per log file before rotation
        backup_count: Number of backup log files to keep
    
    Returns:
        Root logger instance
    """
    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # ==================================================================
    # File Handler - Main Log
    # ==================================================================
    main_log_file = log_path / f"icc_trading_{datetime.now():%Y%m%d}.log"
    
    file_handler = logging.handlers.RotatingFileHandler(
        main_log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, log_level.upper()))
    
    # Detailed format for file
    file_formatter = logging.Formatter(
        fmt='%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)-25s | %(funcName)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # ==================================================================
    # File Handler - Errors Only
    # ==================================================================
    error_log_file = log_path / f"icc_errors_{datetime.now():%Y%m%d}.log"
    
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    root_logger.addHandler(error_handler)
    
    # ==================================================================
    # Console Handler
    # ==================================================================
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, console_level.upper()))
    
    # Simpler format for console
    console_formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # ==================================================================
    # File Handler - Pipeline Activity (Detailed)
    # ==================================================================
    pipeline_log_file = log_path / f"pipeline_activity_{datetime.now():%Y%m%d}.log"
    
    pipeline_handler = logging.handlers.RotatingFileHandler(
        pipeline_log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    pipeline_handler.setLevel(logging.DEBUG)
    
    # Extra detailed format for pipeline
    pipeline_formatter = logging.Formatter(
        fmt='%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    pipeline_handler.setFormatter(pipeline_formatter)
    
    # Add to specific loggers
    pipeline_logger = logging.getLogger('icc_pipeline')
    pipeline_logger.addHandler(pipeline_handler)
    pipeline_logger.setLevel(logging.DEBUG)
    
    # ==================================================================
    # Module-specific log levels
    # ==================================================================
    
    # Data management
    logging.getLogger('live_trading.data_manager').setLevel(logging.INFO)
    logging.getLogger('live_trading.realtime_engine').setLevel(logging.INFO)
    
    # Indicators and features (can be verbose)
    logging.getLogger('icc_ml.indicators').setLevel(logging.WARNING)
    logging.getLogger('icc_ml.features').setLevel(logging.WARNING)
    
    # Strategy and signals
    logging.getLogger('icc_ml.strategy_icc').setLevel(logging.INFO)
    logging.getLogger('icc_ml.icc_labeling').setLevel(logging.INFO)
    
    # Model and training
    logging.getLogger('icc_ml.train').setLevel(logging.INFO)
    
    # Risk management
    logging.getLogger('live_trading.risk_manager').setLevel(logging.INFO)
    logging.getLogger('live_trading.monitor').setLevel(logging.INFO)
    
    # Execution
    logging.getLogger('live_trading.trading_engine').setLevel(logging.INFO)
    
    # Suppress overly verbose libraries
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)
    
    # Log startup message
    root_logger.info("="*80)
    root_logger.info("ICC ML TRADING SYSTEM - LOGGING INITIALIZED")
    root_logger.info("="*80)
    root_logger.info(f"Log directory: {log_path.absolute()}")
    root_logger.info(f"Main log: {main_log_file.name}")
    root_logger.info(f"Error log: {error_log_file.name}")
    root_logger.info(f"Pipeline log: {pipeline_log_file.name}")
    root_logger.info(f"Log level: {log_level}")
    root_logger.info(f"Console level: {console_level}")
    root_logger.info("="*80)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get logger for specific module.
    
    Args:
        name: Module name (e.g., __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def set_log_level(logger_name: str, level: str):
    """
    Set log level for specific logger.
    
    Args:
        logger_name: Name of logger
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, level.upper()))


def list_log_files(log_dir: str = "live_trading/logs") -> list:
    """
    List all log files in directory.
    
    Args:
        log_dir: Log directory path
    
    Returns:
        List of log file paths
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        return []
    
    return sorted(log_path.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)


def get_latest_log_file(log_dir: str = "live_trading/logs", prefix: str = "icc_trading") -> Optional[Path]:
    """
    Get most recent log file matching prefix.
    
    Args:
        log_dir: Log directory path
        prefix: Log file prefix to match
    
    Returns:
        Path to latest log file or None
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        return None
    
    log_files = sorted(
        log_path.glob(f"{prefix}*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    return log_files[0] if log_files else None


def tail_log_file(log_file: Path, lines: int = 50) -> list:
    """
    Get last N lines from log file.
    
    Args:
        log_file: Path to log file
        lines: Number of lines to retrieve
    
    Returns:
        List of log lines
    """
    if not log_file.exists():
        return []
    
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        all_lines = f.readlines()
    
    return all_lines[-lines:] if len(all_lines) > lines else all_lines


class LogCapture:
    """
    Context manager to capture log output.
    
    Useful for testing or capturing specific operation logs.
    """
    
    def __init__(self, logger_name: str = None, level: int = logging.INFO):
        """
        Initialize log capture.
        
        Args:
            logger_name: Specific logger to capture (None for root)
            level: Minimum log level to capture
        """
        self.logger_name = logger_name
        self.level = level
        self.handler = None
        self.log_output = []
    
    def __enter__(self):
        """Start capturing logs."""
        # Create memory handler
        self.handler = logging.handlers.MemoryHandler(capacity=1000)
        self.handler.setLevel(self.level)
        
        # Add to logger
        logger = logging.getLogger(self.logger_name)
        logger.addHandler(self.handler)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop capturing logs."""
        if self.handler:
            # Get captured records
            self.log_output = [
                self.handler.format(record)
                for record in self.handler.buffer
            ]
            
            # Remove handler
            logger = logging.getLogger(self.logger_name)
            logger.removeHandler(self.handler)
            self.handler.close()
        
        return False
    
    def get_output(self) -> list:
        """Get captured log output."""
        return self.log_output


# ==================================================================
# Quick Setup Function
# ==================================================================

def quick_setup(
    verbose: bool = False,
    log_dir: str = "live_trading/logs"
) -> logging.Logger:
    """
    Quick logging setup with sensible defaults.
    
    Args:
        verbose: If True, set DEBUG level
        log_dir: Log directory path
    
    Returns:
        Root logger
    """
    level = "DEBUG" if verbose else "INFO"
    console_level = "DEBUG" if verbose else "INFO"
    
    return setup_logging(
        log_dir=log_dir,
        log_level=level,
        console_level=console_level,
    )


# ==================================================================
# Example Usage
# ==================================================================

if __name__ == "__main__":
    # Setup logging
    logger = quick_setup(verbose=True)
    
    # Test logging
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")
    
    # Module-specific logging
    test_logger = get_logger(__name__)
    test_logger.info("Module-specific log message")
    
    # List log files
    log_files = list_log_files()
    print(f"\nLog files created: {len(log_files)}")
    for f in log_files:
        print(f"  - {f.name}")
    
    # Capture logs
    with LogCapture("test_logger") as capture:
        test_logger.info("Captured message 1")
        test_logger.info("Captured message 2")
    
    print(f"\nCaptured {len(capture.get_output())} log messages")
