"""
MT5 Bridge — Single-responsibility interface for all MetaTrader 5 API calls.

Handles connection, data fetching, order execution, position tracking,
and auto-detection of the broker's supported filling mode.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List

import pandas as pd

logger = logging.getLogger(__name__)


# ── Typed return values ─────────────────────────────────────────────────────

@dataclass
class AccountInfo:
    """Snapshot of MT5 account state."""
    login: int
    server: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    currency: str
    leverage: int
    name: str
    trade_mode: int  # 0=demo, 1=contest, 2=real


@dataclass
class TickInfo:
    """Latest tick for a symbol."""
    bid: float
    ask: float
    last: float
    time: datetime


@dataclass
class PositionInfo:
    """An open position on MT5."""
    ticket: int
    symbol: str
    direction: int       # 1=BUY, -1=SELL
    volume: float
    open_price: float
    sl: float
    tp: float
    profit: float
    swap: float
    magic: int
    comment: str
    open_time: datetime


@dataclass
class OrderResult:
    """Result of an order execution attempt."""
    success: bool
    ticket: Optional[int] = None
    price: Optional[float] = None
    volume: Optional[float] = None
    retcode: Optional[int] = None
    error: Optional[str] = None


@dataclass
class DealInfo:
    """A closed deal from trade history."""
    ticket: int
    order: int
    symbol: str
    direction: int       # 1=BUY, -1=SELL
    volume: float
    price: float
    profit: float
    swap: float
    commission: float
    magic: int
    comment: str
    time: datetime
    entry: int           # 0=IN, 1=OUT, 2=INOUT, 3=OUT_BY


# ── MT5 Bridge ──────────────────────────────────────────────────────────────

class MT5Bridge:
    """
    Manages MT5 connection, data fetching, order execution, and position tracking.

    Uses the already logged-in MT5 terminal. Supports account discovery
    and auto-detection of broker filling mode.
    """

    # Timeframe string → MT5 constant mapping
    _TIMEFRAME_MAP = {
        "M1": "TIMEFRAME_M1",
        "M5": "TIMEFRAME_M5",
        "M15": "TIMEFRAME_M15",
        "M30": "TIMEFRAME_M30",
        "H1": "TIMEFRAME_H1",
        "H4": "TIMEFRAME_H4",
        "D1": "TIMEFRAME_D1",
        "W1": "TIMEFRAME_W1",
    }

    def __init__(self):
        self._mt5 = None          # MetaTrader5 module (lazy import)
        self._initialized = False
        self._filling_type = None  # Cached auto-detected filling mode
        self._account_info: Optional[AccountInfo] = None

    # ── Connection ──────────────────────────────────────────────────────

    def connect(self) -> AccountInfo:
        """
        Connect to the already logged-in MT5 terminal.

        Returns:
            AccountInfo for the active account.

        Raises:
            RuntimeError: If MT5 terminal is not running or connection fails.
        """
        import MetaTrader5 as mt5
        self._mt5 = mt5

        if not mt5.initialize():
            error = mt5.last_error()
            raise RuntimeError(
                f"MT5 initialization failed: {error}. "
                f"Ensure the MT5 terminal is running and logged in."
            )

        self._initialized = True

        # Get account info
        info = mt5.account_info()
        if info is None:
            mt5.shutdown()
            self._initialized = False
            raise RuntimeError("Failed to get account info. Is an account logged in?")

        self._account_info = AccountInfo(
            login=info.login,
            server=info.server,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            currency=info.currency,
            leverage=info.leverage,
            name=info.name,
            trade_mode=info.trade_mode,
        )

        mode_names = {0: "DEMO", 1: "CONTEST", 2: "REAL"}
        mode_str = mode_names.get(info.trade_mode, "UNKNOWN")

        logger.info(f"Connected to MT5 account {info.login} ({mode_str})")
        logger.info(f"  Server: {info.server}")
        logger.info(f"  Balance: {info.balance:.2f} {info.currency}")
        logger.info(f"  Leverage: 1:{info.leverage}")

        return self._account_info

    def disconnect(self):
        """Shutdown MT5 connection."""
        if self._initialized and self._mt5 is not None:
            self._mt5.shutdown()
            self._initialized = False
            logger.info("MT5 connection closed")

    def is_connected(self) -> bool:
        """Check if MT5 is connected."""
        return self._initialized

    def _ensure_connected(self):
        """Raise if not connected."""
        if not self._initialized or self._mt5 is None:
            raise RuntimeError("MT5 not connected. Call connect() first.")

    # ── Account Discovery ───────────────────────────────────────────────

    def get_account_info(self) -> AccountInfo:
        """
        Get fresh account info from MT5.

        Returns:
            Current AccountInfo snapshot.
        """
        self._ensure_connected()
        mt5 = self._mt5

        info = mt5.account_info()
        if info is None:
            raise RuntimeError(f"Failed to get account info: {mt5.last_error()}")

        self._account_info = AccountInfo(
            login=info.login,
            server=info.server,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            currency=info.currency,
            leverage=info.leverage,
            name=info.name,
            trade_mode=info.trade_mode,
        )
        return self._account_info

    # ── Symbol Setup ────────────────────────────────────────────────────

    def ensure_symbol_visible(self, symbol: str) -> dict:
        """
        Ensure symbol is in Market Watch and return its specification.

        Args:
            symbol: Trading symbol name (e.g., "XAUUSDm")

        Returns:
            Dict with symbol info (digits, point, spread, etc.)
        """
        self._ensure_connected()
        mt5 = self._mt5

        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Symbol '{symbol}' not found on this broker.")

        if not info.visible:
            logger.info(f"Adding {symbol} to Market Watch...")
            if not mt5.symbol_select(symbol, True):
                raise RuntimeError(f"Failed to add {symbol} to Market Watch")

        logger.info(f"Symbol {symbol}: digits={info.digits}, point={info.point}, spread={info.spread}")

        return {
            "name": symbol,
            "digits": info.digits,
            "point": info.point,
            "spread": info.spread,
            "filling_mode": info.filling_mode,
            "trade_mode": info.trade_mode,
        }

    # ── Filling Mode Auto-Detection ────────────────────────────────────

    def detect_filling_mode(self, symbol: str) -> int:
        """
        Auto-detect the broker's supported filling mode for a symbol.

        MT5 filling modes:
            ORDER_FILLING_FOK (0): Fill or Kill — entire order must fill or cancel
            ORDER_FILLING_IOC (1): Immediate or Cancel — partial fill ok, rest cancelled
            ORDER_FILLING_RETURN (2): Return — partial fill ok, unfilled portion stays as order

        Args:
            symbol: Trading symbol to check.

        Returns:
            MT5 filling type constant.
        """
        self._ensure_connected()
        mt5 = self._mt5

        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Symbol '{symbol}' not found")

        filling_mode = info.filling_mode

        # filling_mode is a bitmask of supported filling types
        # Bit 0 (1): FOK supported
        # Bit 1 (2): IOC supported
        # Bit 2 (4): RETURN supported (some brokers/builds use this differently)

        if filling_mode & 1:  # FOK supported
            self._filling_type = mt5.ORDER_FILLING_FOK
            logger.info(f"Filling mode for {symbol}: FOK (Fill or Kill)")
        elif filling_mode & 2:  # IOC supported
            self._filling_type = mt5.ORDER_FILLING_IOC
            logger.info(f"Filling mode for {symbol}: IOC (Immediate or Cancel)")
        else:  # Fall back to RETURN
            self._filling_type = mt5.ORDER_FILLING_RETURN
            logger.info(f"Filling mode for {symbol}: RETURN")

        return self._filling_type

    # ── Data Fetching ───────────────────────────────────────────────────

    def fetch_bars(self, symbol: str, timeframe: str, count: int = 2000) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV bars from MT5.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe string (e.g., "H1", "M15")
            count: Number of bars to fetch

        Returns:
            DataFrame with columns [time, open, high, low, close, volume]
            or None on failure.
        """
        self._ensure_connected()
        mt5 = self._mt5

        tf_const = getattr(mt5, self._TIMEFRAME_MAP.get(timeframe, "TIMEFRAME_H1"))
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, count)

        if rates is None or len(rates) == 0:
            logger.error(f"Failed to fetch bars for {symbol} {timeframe}: {mt5.last_error()}")
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(columns={"tick_volume": "volume"})
        df = df[["time", "open", "high", "low", "close", "volume"]]

        return df

    # ── Tick Data ───────────────────────────────────────────────────────

    def get_tick(self, symbol: str) -> Optional[TickInfo]:
        """Get the latest tick for a symbol."""
        self._ensure_connected()
        mt5 = self._mt5

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Failed to get tick for {symbol}: {mt5.last_error()}")
            return None

        return TickInfo(
            bid=tick.bid,
            ask=tick.ask,
            last=tick.last,
            time=datetime.fromtimestamp(tick.time),
        )

    # ── Order Execution ─────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        direction: int,
        lot_size: float,
        sl: float,
        tp: float,
        magic: int = 202609,
        comment: str = "",
        deviation: int = 20,
    ) -> OrderResult:
        """
        Place a market order on MT5.

        Args:
            symbol: Trading symbol
            direction: 1 for BUY, -1 for SELL
            lot_size: Position size in lots
            sl: Stop loss price
            tp: Take profit price
            magic: Magic number for order identification
            comment: Order comment (max 31 chars)
            deviation: Max slippage in broker points

        Returns:
            OrderResult with success status and details.
        """
        self._ensure_connected()
        mt5 = self._mt5

        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return OrderResult(
                success=False,
                error=f"Failed to get tick for {symbol}: {mt5.last_error()}"
            )

        # Determine order type and price
        if direction == 1:  # BUY
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:  # SELL
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid

        # Auto-detect filling mode if not cached
        if self._filling_type is None:
            self.detect_filling_mode(symbol)

        # Build request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": deviation,
            "magic": magic,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_type,
        }

        logger.info(
            f"Placing order: {'BUY' if direction == 1 else 'SELL'} "
            f"{lot_size} lots {symbol} @ {price:.5f}, SL={sl:.5f}, TP={tp:.5f}"
        )

        result = mt5.order_send(request)

        if result is None:
            return OrderResult(
                success=False,
                error=f"order_send returned None: {mt5.last_error()}"
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                success=False,
                retcode=result.retcode,
                error=f"Order failed: retcode={result.retcode}, {result.comment}",
            )

        logger.info(f"Order executed: ticket={result.order}, price={result.price}, volume={result.volume}")

        return OrderResult(
            success=True,
            ticket=result.order,
            price=result.price,
            volume=result.volume,
            retcode=result.retcode,
        )

    # ── Position Tracking ───────────────────────────────────────────────

    def get_open_positions(self, symbol: str = None, magic: int = None) -> List[PositionInfo]:
        """
        Get currently open positions, optionally filtered by symbol and magic number.

        Args:
            symbol: Filter by symbol (optional)
            magic: Filter by magic number (optional)

        Returns:
            List of PositionInfo objects.
        """
        self._ensure_connected()
        mt5 = self._mt5

        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []

        result = []
        for pos in positions:
            # Filter by magic number
            if magic is not None and pos.magic != magic:
                continue

            direction = 1 if pos.type == mt5.ORDER_TYPE_BUY else -1

            result.append(PositionInfo(
                ticket=pos.ticket,
                symbol=pos.symbol,
                direction=direction,
                volume=pos.volume,
                open_price=pos.price_open,
                sl=pos.sl,
                tp=pos.tp,
                profit=pos.profit,
                swap=pos.swap,
                magic=pos.magic,
                comment=pos.comment,
                open_time=datetime.fromtimestamp(pos.time),
            ))

        return result

    def close_position(self, ticket: int) -> OrderResult:
        """
        Close an open position by ticket number.

        Args:
            ticket: Position ticket to close.

        Returns:
            OrderResult with success status.
        """
        self._ensure_connected()
        mt5 = self._mt5

        # Get the position
        position = mt5.positions_get(ticket=ticket)
        if position is None or len(position) == 0:
            return OrderResult(success=False, error=f"Position {ticket} not found")

        pos = position[0]

        # Reverse direction to close
        if pos.type == mt5.ORDER_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(pos.symbol).bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol).ask

        if self._filling_type is None:
            self.detect_filling_mode(pos.symbol)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": pos.magic,
            "comment": "FT_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_type,
        }

        result = mt5.order_send(request)

        if result is None:
            return OrderResult(success=False, error=f"Close order returned None: {mt5.last_error()}")

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                success=False,
                retcode=result.retcode,
                error=f"Close failed: {result.retcode}, {result.comment}",
            )

        logger.info(f"Position {ticket} closed at {result.price}")
        return OrderResult(success=True, ticket=result.order, price=result.price)

    # ── Trade History ───────────────────────────────────────────────────

    def get_trade_history(
        self,
        from_date: datetime = None,
        to_date: datetime = None,
        symbol: str = None,
        magic: int = None,
    ) -> List[DealInfo]:
        """
        Get closed trade history from MT5.

        Args:
            from_date: Start date (default: 24h ago)
            to_date: End date (default: now)
            symbol: Filter by symbol (optional)
            magic: Filter by magic number (optional)

        Returns:
            List of DealInfo objects for closed trades.
        """
        self._ensure_connected()
        mt5 = self._mt5

        if from_date is None:
            from_date = datetime.now() - timedelta(days=1)
        if to_date is None:
            to_date = datetime.now() + timedelta(hours=1)

        deals = mt5.history_deals_get(from_date, to_date)

        if deals is None:
            return []

        result = []
        for deal in deals:
            # Filter
            if symbol and deal.symbol != symbol:
                continue
            if magic is not None and deal.magic != magic:
                continue

            direction = 1 if deal.type == mt5.DEAL_TYPE_BUY else -1

            result.append(DealInfo(
                ticket=deal.ticket,
                order=deal.order,
                symbol=deal.symbol,
                direction=direction,
                volume=deal.volume,
                price=deal.price,
                profit=deal.profit,
                swap=deal.swap,
                commission=deal.commission,
                magic=deal.magic,
                comment=deal.comment,
                time=datetime.fromtimestamp(deal.time),
                entry=deal.entry,
            ))

        return result
