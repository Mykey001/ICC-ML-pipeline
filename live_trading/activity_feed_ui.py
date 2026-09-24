"""
Live activity feed system for UI integration.

Provides real-time activity streaming and formatting for Streamlit UI.
"""
from __future__ import annotations
from typing import List, Optional
from datetime import datetime, timedelta
import pandas as pd

from .pipeline_logger import get_pipeline_logger, ActivityEntry, ActivityLevel


class ActivityFeedUI:
    """
    UI adapter for activity feed.
    
    Provides formatted activity data for Streamlit display.
    """
    
    def __init__(self):
        """Initialize activity feed UI."""
        self.plogger = get_pipeline_logger()
        self.feed = self.plogger.feed
    
    def get_recent_activity(self, count: int = 50) -> List[ActivityEntry]:
        """
        Get recent activity entries.
        
        Args:
            count: Number of recent entries to retrieve
        
        Returns:
            List of recent activity entries
        """
        if self.feed is None:
            return []
        return self.feed.get_recent(count)
    
    def get_activity_dataframe(self, count: int = 50) -> pd.DataFrame:
        """
        Get recent activity as DataFrame for display.
        
        Args:
            count: Number of recent entries
        
        Returns:
            DataFrame with formatted activity
        """
        entries = self.get_recent_activity(count)
        
        if not entries:
            return pd.DataFrame(columns=["Time", "Category", "Operation", "Message", "Duration"])
        
        data = []
        for entry in entries:
            data.append({
                "Time": entry.timestamp.strftime("%H:%M:%S.%f")[:-3],
                "Category": entry.category,
                "Operation": entry.operation,
                "Message": entry.message,
                "Duration": f"{entry.duration_ms:.0f}ms" if entry.duration_ms else "",
                "Level": entry.level.value,
            })
        
        return pd.DataFrame(data)
    
    def get_formatted_activity(self, count: int = 50, colorize: bool = True) -> str:
        """
        Get formatted activity as text.
        
        Args:
            count: Number of recent entries
            colorize: Add color codes for HTML display
        
        Returns:
            Formatted text suitable for display
        """
        entries = self.get_recent_activity(count)
        
        if not entries:
            return "No activity yet. Start trading to see live updates."
        
        lines = []
        for entry in entries:
            formatted = entry.format()
            
            if colorize:
                # Add color based on level
                if entry.level == ActivityLevel.ERROR or entry.level == ActivityLevel.CRITICAL:
                    formatted = f'<span style="color: #ff4444;">{formatted}</span>'
                elif entry.level == ActivityLevel.WARNING:
                    formatted = f'<span style="color: #ffaa00;">{formatted}</span>'
                elif entry.level == ActivityLevel.SUCCESS:
                    formatted = f'<span style="color: #44ff44;">{formatted}</span>'
                elif entry.level == ActivityLevel.INFO:
                    formatted = f'<span style="color: #4499ff;">{formatted}</span>'
                else:  # DEBUG
                    formatted = f'<span style="color: #888888;">{formatted}</span>'
            
            lines.append(formatted)
        
        return "\n".join(lines)
    
    def get_activity_by_category(self, minutes: int = 5) -> dict:
        """
        Get activity counts by category for recent time period.
        
        Args:
            minutes: Time window in minutes
        
        Returns:
            Dict of category -> count
        """
        if self.feed is None:
            return {}
        
        cutoff = datetime.now() - timedelta(minutes=minutes)
        entries = self.feed.get_all()
        
        recent = [e for e in entries if e.timestamp >= cutoff]
        
        counts = {}
        for entry in recent:
            counts[entry.category] = counts.get(entry.category, 0) + 1
        
        return counts
    
    def get_pipeline_stats(self) -> dict:
        """
        Get pipeline execution statistics.
        
        Returns:
            Dict with pipeline stats
        """
        if self.feed is None:
            return {
                "total_operations": 0,
                "avg_duration_ms": 0,
                "last_activity": None,
            }
        
        entries = self.feed.get_all()
        
        if not entries:
            return {
                "total_operations": 0,
                "avg_duration_ms": 0,
                "last_activity": None,
            }
        
        # Calculate stats
        timed_entries = [e for e in entries if e.duration_ms is not None]
        
        avg_duration = (
            sum(e.duration_ms for e in timed_entries) / len(timed_entries)
            if timed_entries else 0
        )
        
        # Get operation counts by category
        category_counts = {}
        for entry in entries:
            category_counts[entry.category] = category_counts.get(entry.category, 0) + 1
        
        # Find longest operations
        longest = sorted(timed_entries, key=lambda e: e.duration_ms, reverse=True)[:5]
        
        return {
            "total_operations": len(entries),
            "timed_operations": len(timed_entries),
            "avg_duration_ms": avg_duration,
            "last_activity": entries[-1].timestamp if entries else None,
            "category_counts": category_counts,
            "longest_operations": [
                {
                    "category": e.category,
                    "operation": e.operation,
                    "duration_ms": e.duration_ms,
                }
                for e in longest
            ],
        }
    
    def get_current_operation(self) -> Optional[str]:
        """
        Get description of current operation (most recent INFO/START message).
        
        Returns:
            Description of current operation or None
        """
        if self.feed is None:
            return None
        
        entries = self.feed.get_recent(10)
        
        # Look for most recent operation start
        for entry in reversed(entries):
            if entry.level in [ActivityLevel.INFO, ActivityLevel.SUCCESS]:
                if "Started" in entry.message or "Computing" in entry.message or "Processing" in entry.message:
                    return f"{entry.category}: {entry.operation}"
        
        return None
    
    def get_error_count(self, minutes: int = 60) -> int:
        """
        Get error count in recent time period.
        
        Args:
            minutes: Time window in minutes
        
        Returns:
            Number of errors
        """
        if self.feed is None:
            return 0
        
        cutoff = datetime.now() - timedelta(minutes=minutes)
        entries = self.feed.get_all()
        
        recent = [e for e in entries if e.timestamp >= cutoff]
        errors = [e for e in recent if e.level in [ActivityLevel.ERROR, ActivityLevel.CRITICAL]]
        
        return len(errors)
    
    def get_success_count(self, minutes: int = 60) -> int:
        """
        Get success count in recent time period.
        
        Args:
            minutes: Time window in minutes
        
        Returns:
            Number of successful operations
        """
        if self.feed is None:
            return 0
        
        cutoff = datetime.now() - timedelta(minutes=minutes)
        entries = self.feed.get_all()
        
        recent = [e for e in entries if e.timestamp >= cutoff]
        successes = [e for e in recent if e.level == ActivityLevel.SUCCESS]
        
        return len(successes)
    
    def get_recent_errors(self, count: int = 5) -> List[dict]:
        """
        Get recent error messages.
        
        Args:
            count: Number of errors to return
        
        Returns:
            List of error dicts
        """
        if self.feed is None:
            return []
        
        entries = self.feed.get_all()
        errors = [e for e in entries if e.level in [ActivityLevel.ERROR, ActivityLevel.CRITICAL]]
        
        recent_errors = errors[-count:]
        
        return [
            {
                "timestamp": e.timestamp.strftime("%H:%M:%S"),
                "category": e.category,
                "operation": e.operation,
                "message": e.message,
            }
            for e in recent_errors
        ]
    
    def clear_activity(self):
        """Clear all activity history."""
        if self.feed:
            self.feed.clear()
    
    def get_bar_processing_summary(self) -> Optional[dict]:
        """
        Get summary of last bar processing.
        
        Returns:
            Dict with bar processing summary or None
        """
        if self.feed is None:
            return None
        
        entries = self.feed.get_all()
        
        # Find last "ProcessBar" operation
        process_bar_entries = [e for e in entries if e.operation == "ProcessBar"]
        
        if not process_bar_entries:
            return None
        
        last_process = process_bar_entries[-1]
        
        # Find all operations after this ProcessBar start until completion
        start_idx = entries.index(last_process)
        
        # Get all entries from this bar processing
        bar_entries = []
        for e in entries[start_idx:]:
            bar_entries.append(e)
            if e.operation == "ProcessBar" and e.level == ActivityLevel.SUCCESS and e != last_process:
                break
        
        # Extract stats
        categories_processed = set()
        total_duration = 0
        operations_count = 0
        
        for e in bar_entries:
            if e.category not in ["ENGINE", "PIPELINE"]:
                categories_processed.add(e.category)
            if e.duration_ms:
                total_duration += e.duration_ms
                operations_count += 1
        
        return {
            "timestamp": last_process.timestamp,
            "categories": list(categories_processed),
            "total_duration_ms": total_duration,
            "operations_count": operations_count,
            "completed": any(e.level == ActivityLevel.SUCCESS and e.operation == "ProcessBar" for e in bar_entries),
        }
    
    def export_activity_log(self, filepath: str):
        """
        Export activity log to file.
        
        Args:
            filepath: Path to save log file
        """
        if self.feed is None:
            return
        
        entries = self.feed.get_all()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("ICC ML Pipeline Activity Log\n")
            f.write(f"Generated: {datetime.now()}\n")
            f.write(f"Total entries: {len(entries)}\n")
            f.write("="*80 + "\n\n")
            
            for entry in entries:
                f.write(entry.format() + "\n")
