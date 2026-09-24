"""
ICC-ML: Machine Learning Meta-Labeling for ICC Swing Strategy

A production-grade ML pipeline for trading signal filtering using meta-labeling.
The ICC strategy provides directional signals; ML decides whether to take or skip each signal.
"""

__version__ = "1.0.0"

from .config import StrategyConfig, ExecutionConfig, SymbolSpec, SYMBOL_PRESETS

__all__ = [
    "StrategyConfig",
    "ExecutionConfig", 
    "SymbolSpec",
    "SYMBOL_PRESETS",
]
