"""
Instrumented pipeline logger for transparent real-time tracking.

Every step of the ML pipeline logs its progress with:
- Timestamps
- Operation names
- Progress indicators
- Values computed
- Durations
"""
from __future__ import annotations
import logging
import time
from datetime import datetime
from typing import Optional, Any, Dict, List
from dataclasses import dataclass, field
from enum import Enum
import threading
from collections import deque


class ActivityLevel(Enum):
    """Activity log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class ActivityEntry:
    """Single activity log entry."""
    timestamp: datetime
    level: ActivityLevel
    category: str  # e.g., "DATA", "INDICATORS", "FEATURES", "MODEL", "RISK", "EXECUTION"
    operation: str  # e.g., "Fetching bars", "Computing RSI"
    message: str
    details: Optional[Dict[str, Any]] = None
    duration_ms: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "category": self.category,
            "operation": self.operation,
            "message": self.message,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }
    
    def format(self) -> str:
        """Format for display."""
        time_str = self.timestamp.strftime("%H:%M:%S.%f")[:-3]
        duration_str = f" ({self.duration_ms:.0f}ms)" if self.duration_ms else ""
        details_str = ""
        if self.details:
            details_str = " | " + ", ".join(f"{k}={v}" for k, v in self.details.items())
        
        return f"[{time_str}] {self.category:12s} {self.operation:30s} → {self.message}{details_str}{duration_str}"


class ActivityFeed:
    """
    Thread-safe activity feed for real-time pipeline monitoring.
    
    Stores recent activity entries and provides real-time access.
    """
    
    def __init__(self, max_entries: int = 1000):
        """
        Initialize activity feed.
        
        Args:
            max_entries: Maximum entries to keep in memory
        """
        self.max_entries = max_entries
        self._entries: deque[ActivityEntry] = deque(maxlen=max_entries)
        self._lock = threading.Lock()
        self._listeners: List[callable] = []
    
    def add(
        self,
        level: ActivityLevel,
        category: str,
        operation: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
    ):
        """Add entry to feed."""
        entry = ActivityEntry(
            timestamp=datetime.now(),
            level=level,
            category=category,
            operation=operation,
            message=message,
            details=details,
            duration_ms=duration_ms,
        )
        
        with self._lock:
            self._entries.append(entry)
        
        # Notify listeners
        for listener in self._listeners:
            try:
                listener(entry)
            except Exception as e:
                logging.error(f"Error notifying activity listener: {e}")
    
    def get_recent(self, count: int = 50) -> List[ActivityEntry]:
        """Get most recent entries."""
        with self._lock:
            entries = list(self._entries)
        return entries[-count:] if len(entries) > count else entries
    
    def get_all(self) -> List[ActivityEntry]:
        """Get all entries."""
        with self._lock:
            return list(self._entries)
    
    def clear(self):
        """Clear all entries."""
        with self._lock:
            self._entries.clear()
    
    def add_listener(self, callback: callable):
        """Add listener for new entries."""
        self._listeners.append(callback)
    
    def remove_listener(self, callback: callable):
        """Remove listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)


class PipelineLogger:
    """
    Instrumented logger for ML trading pipeline.
    
    Provides:
    - Detailed step-by-step logging
    - Activity feed for real-time monitoring
    - Performance timing
    - Structured logging
    """
    
    def __init__(self, name: str = "pipeline", enable_feed: bool = True):
        """
        Initialize pipeline logger.
        
        Args:
            name: Logger name
            enable_feed: Enable activity feed for UI
        """
        self.logger = logging.getLogger(name)
        self.feed = ActivityFeed() if enable_feed else None
        self._operation_stack = []
        self._start_times = {}
    
    def start_operation(self, category: str, operation: str, message: str = "Started"):
        """Start a timed operation."""
        op_id = f"{category}:{operation}"
        self._start_times[op_id] = time.time()
        
        self.log(ActivityLevel.INFO, category, operation, message)
    
    def end_operation(self, category: str, operation: str, message: str = "Completed", details: Optional[Dict] = None):
        """End a timed operation."""
        op_id = f"{category}:{operation}"
        
        duration_ms = None
        if op_id in self._start_times:
            duration_ms = (time.time() - self._start_times[op_id]) * 1000
            del self._start_times[op_id]
        
        self.log(ActivityLevel.SUCCESS, category, operation, message, details=details, duration_ms=duration_ms)
    
    def log(
        self,
        level: ActivityLevel,
        category: str,
        operation: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
    ):
        """Log activity."""
        # Log to standard logger
        log_msg = f"[{category}] {operation}: {message}"
        if details:
            log_msg += f" | {details}"
        if duration_ms:
            log_msg += f" ({duration_ms:.0f}ms)"
        
        if level == ActivityLevel.DEBUG:
            self.logger.debug(log_msg)
        elif level == ActivityLevel.INFO:
            self.logger.info(log_msg)
        elif level == ActivityLevel.SUCCESS:
            self.logger.info(f"✓ {log_msg}")
        elif level == ActivityLevel.WARNING:
            self.logger.warning(log_msg)
        elif level == ActivityLevel.ERROR:
            self.logger.error(log_msg)
        elif level == ActivityLevel.CRITICAL:
            self.logger.critical(log_msg)
        
        # Add to feed
        if self.feed:
            self.feed.add(level, category, operation, message, details, duration_ms)
    
    def debug(self, category: str, operation: str, message: str, **kwargs):
        """Log debug message."""
        self.log(ActivityLevel.DEBUG, category, operation, message, **kwargs)
    
    def info(self, category: str, operation: str, message: str, **kwargs):
        """Log info message."""
        self.log(ActivityLevel.INFO, category, operation, message, **kwargs)
    
    def success(self, category: str, operation: str, message: str, **kwargs):
        """Log success message."""
        self.log(ActivityLevel.SUCCESS, category, operation, message, **kwargs)
    
    def warning(self, category: str, operation: str, message: str, **kwargs):
        """Log warning message."""
        self.log(ActivityLevel.WARNING, category, operation, message, **kwargs)
    
    def error(self, category: str, operation: str, message: str, **kwargs):
        """Log error message."""
        self.log(ActivityLevel.ERROR, category, operation, message, **kwargs)
    
    def critical(self, category: str, operation: str, message: str, **kwargs):
        """Log critical message."""
        self.log(ActivityLevel.CRITICAL, category, operation, message, **kwargs)


# Global pipeline logger instance
_global_logger: Optional[PipelineLogger] = None


def get_pipeline_logger() -> PipelineLogger:
    """Get global pipeline logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = PipelineLogger(name="icc_pipeline", enable_feed=True)
    return _global_logger


def set_pipeline_logger(logger: PipelineLogger):
    """Set global pipeline logger instance."""
    global _global_logger
    _global_logger = logger


class OperationTimer:
    """Context manager for timing operations."""
    
    def __init__(self, logger: PipelineLogger, category: str, operation: str, start_message: str = "Started"):
        self.logger = logger
        self.category = category
        self.operation = operation
        self.start_message = start_message
        self.details = {}
    
    def __enter__(self):
        self.logger.start_operation(self.category, self.operation, self.start_message)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.logger.end_operation(self.category, self.operation, "Completed", details=self.details)
        else:
            self.logger.error(self.category, self.operation, f"Failed: {exc_val}")
        return False
    
    def add_detail(self, key: str, value: Any):
        """Add detail to be logged on completion."""
        self.details[key] = value
