//+------------------------------------------------------------------+
//|                                   ICC_Swing_EA_Simplified.mq5     |
//|      Simplified MT5 EA port of "ICC Swing Strategy                |
//|      (Daily/4H/1H) - Trades By Sci" TradingView indicator         |
//|                                                                    |
//|  CONCEPT: Both "HTF" and "LTF" pivots are calculated on the SAME  |
//|  chart timeframe the EA is running on - only the pivot LENGTH     |
//|  differs (2 bars = "HTF" macro structure, 1 bar = "LTF" fine      |
//|  structure). Attach to whichever timeframe you want to trade      |
//|  (H1, H4, D1...) exactly like you would with the indicator.       |
//|                                                                    |
//|  SIMPLIFIED TRADE MANAGEMENT (compared to the full EA):           |
//|  - Single position per signal (no triple-target runner mode)      |
//|  - Take profit is always a FIXED PIP distance from entry          |
//|  - Lot size is a FIXED input (no risk % sizing)                   |
//|  - No session filter, no long/short toggle, no signal-quality     |
//|    (SL distance) filter, no CSV / ML feature logging              |
//+------------------------------------------------------------------+
#property copyright "Ported from Pine Script - Trades By Sci"
#property version   "4.00"
#property strict

#include <Trade\Trade.mqh>

CTrade trade;

//====================================================================
// 1. INPUTS
//====================================================================
input group "=== Market Structure (Pivot) Settings ==="
input int      HTF_PivotLen        = 2;      // HTF pivot length (Daily/4H structure) - matches htf_len
input int      LTF_PivotLen        = 1;      // LTF pivot length (1H structure)       - matches ltf_len

input group "=== Trade Management ==="
input double   FixedLots           = 0.10;   // Fixed lot size per trade
input bool     OnePositionAtATime  = true;   // Block new signals while a trade is open
input int      MaxSpreadPoints     = 0;      // 0 = no spread filter, else max allowed spread in points
input ulong    MagicNumber         = 774411; // EA identifier
input string   TradeComment        = "ICC_Swing_EA";

input group "=== Take Profit (fixed pips) ==="
input double   TP_Pips             = 2500;   // Take profit distance from entry, in pips
// NOTE ON PIP CONVENTION: PipSize() below returns 10*_Point on 3/5-digit quotes
// and 1*_Point on 2/4-digit quotes. So 2500 "pips" means very different things
// per symbol:
//    XAUUSD (2 digits) -> 2500 * 0.01   = $25.00 move      <- sane swing target
//    US30   (1-2 digits)-> 2500 * 0.01  = 25 index points
//    EURUSD (5 digits) -> 2500 * 0.0001 = 0.2500 (2500 pips) <- essentially never hit
// If you attach this to a 5-digit FX pair with TP_Pips=2500 the take profit will
// effectively never trigger and every trade resolves at the stop loss instead.
// Check the "tp_hit_rate" diagnostic printed by the Python pipeline before
// trusting backtest results on any new symbol.

input group "=== Swing-Point Stop Loss (custom timeframe) ==="
// Places the SL at an actual confirmed swing high/low found on a SEPARATE,
// user-chosen timeframe - e.g. trade off H1 but stop off a real H4 or D1
// structural swing - instead of just requiring a minimum pip distance. Uses
// the exact same "len bars confirmed on both sides" pivot definition as
// HTF_PivotLen/LTF_PivotLen above, just evaluated on SL_SwingTimeframe. Only
// fully-closed bars on that timeframe are ever read, so this stays
// no-lookahead even when SL_SwingTimeframe is finer than the chart's own
// timeframe.
input bool             UseCustomSwingSL      = true;         // false = keep the original LTF-pivot SL (sl_level) unchanged
input ENUM_TIMEFRAMES  SL_SwingTimeframe     = PERIOD_H4;     // Timeframe to search for the swing point that becomes the SL
input int              SL_SwingPivotLen      = 2;             // Bars required on each side to confirm a swing point on SL_SwingTimeframe
input int              SL_MaxCandidates      = 20;            // How many confirmed swing points to look back through if the most recent one is on the wrong side of price
input double           SL_BufferPips         = 0;             // Extra pips added beyond the swing point (spread/noise buffer), in chart-symbol pips
input bool             RequireCustomSwingSL  = false;         // true = reject the signal outright if no valid swing point is found on SL_SwingTimeframe; false = fall back to the original LTF-pivot sl_level

input group "=== Visuals ==="
input bool     ShowChartObjects    = true;   // Draw HTF/LTF levels, trigger zone, SL like the indicator

//====================================================================
// 2. PERSISTENT STATE (mirrors Pine's "var" variables - these keep
//    their value across bars exactly like the state machine in the
//    original script)
//====================================================================
int    stage               = 0;      // 0 neutral, 1/2 bullish phases, -1/-2 bearish phases
double indication_extremum = 0.0;
bool   hasIndicationExt    = false;
double trigger_zone        = 0.0;
bool   hasTriggerZone      = false;
double sl_level            = 0.0;
bool   hasSlLevel          = false;

double htf_res = 0.0;  bool hasHtfRes = false;
double htf_sup = 0.0;  bool hasHtfSup = false;
double ltf_res = 0.0;  bool hasLtfRes = false;
double ltf_sup = 0.0;  bool hasLtfSup = false;

datetime lastProcessedBarTime = 0;

// --- single open trade state ---
bool     trade_active   = false;
ulong    trade_ticket   = 0;
int      trade_dir      = 0;     // 1 = long, -1 = short

//====================================================================
// 3. PIVOT DETECTION
//    Replicates ta.pivothigh(high, len, len) / ta.pivotlow(low, len, len)
//    A pivot at candidate bar C is confirmed once C has `len` closed
//    bars on both sides. When a NEW bar closes, the bar that becomes
//    confirmable is exactly (len+1) bars back from the freshly closed
//    bar (shift 1 in an as-series array where shift 0 = current
//    forming bar).
//====================================================================
bool GetPivotHigh(int len, double &pivotValue)
{
   int candidate = 1 + len;
   int needed    = candidate + len + 1;

   double high[];
   ArraySetAsSeries(high, true);
   if(CopyHigh(_Symbol, _Period, 0, needed, high) < needed) return false;

   double c = high[candidate];
   for(int i = 1; i <= len; i++)
   {
      if(!(c > high[candidate - i])) return false; // right side (more recent bars)
      if(!(c > high[candidate + i])) return false; // left side (older bars)
   }
   pivotValue = c;
   return true;
}

bool GetPivotLow(int len, double &pivotValue)
{
   int candidate = 1 + len;
   int needed    = candidate + len + 1;

   double low[];
   ArraySetAsSeries(low, true);
   if(CopyLow(_Symbol, _Period, 0, needed, low) < needed) return false;

   double c = low[candidate];
   for(int i = 1; i <= len; i++)
   {
      if(!(c < low[candidate - i])) return false;
      if(!(c < low[candidate + i])) return false;
   }
   pivotValue = c;
   return true;
}

//====================================================================
// 3a. CUSTOM-TIMEFRAME SWING SEARCH (used for Swing-Point Stop Loss)
//    Unlike GetPivotHigh/GetPivotLow above (which only ever check the ONE
//    bar that just became confirmable), these search backward through up
//    to SL_MaxCandidates confirmed pivots on an arbitrary timeframe, so
//    the EA can find "the most recent real swing point", not just "was
//    the current bar a pivot".
//====================================================================
double PipsToPrice(double pips); // forward decl - defined in section 3b below, used by ResolveSwingSL

// Returns the shift (on tf, as-series, shift 0 = tf's current forming bar)
// of the OLDEST bar on tf that is guaranteed fully closed as of asOfTime.
int GetSwingSearchStartShift(ENUM_TIMEFRAMES tf, datetime asOfTime)
{
   int shift = iBarShift(_Symbol, tf, asOfTime, false);
   if(shift < 0) return -1;
   return shift + 1;
}

bool FindSwingHigh(ENUM_TIMEFRAMES tf, int len, datetime asOfTime, int maxCandidates,
                    double &swingPrice, datetime &swingTime)
{
   int startShift = GetSwingSearchStartShift(tf, asOfTime);
   if(startShift < 0) return false;

   int needed = startShift + len + maxCandidates + len + 1;
   double high[];
   ArraySetAsSeries(high, true);
   int copied = CopyHigh(_Symbol, tf, 0, needed, high);
   if(copied < startShift + 2*len + 1) return false; // not enough history to confirm even one pivot

   int lastCand = MathMin(startShift + len + maxCandidates, copied - len - 1);
   for(int cand = startShift + len; cand <= lastCand; cand++)
   {
      double c = high[cand];
      bool isPivot = true;
      for(int i = 1; i <= len; i++)
      {
         if(!(c > high[cand-i]) || !(c > high[cand+i])) { isPivot = false; break; }
      }
      if(isPivot)
      {
         swingPrice = c;
         swingTime  = iTime(_Symbol, tf, cand);
         return true;
      }
   }
   return false;
}

bool FindSwingLow(ENUM_TIMEFRAMES tf, int len, datetime asOfTime, int maxCandidates,
                   double &swingPrice, datetime &swingTime)
{
   int startShift = GetSwingSearchStartShift(tf, asOfTime);
   if(startShift < 0) return false;

   int needed = startShift + len + maxCandidates + len + 1;
   double low[];
   ArraySetAsSeries(low, true);
   int copied = CopyLow(_Symbol, tf, 0, needed, low);
   if(copied < startShift + 2*len + 1) return false;

   int lastCand = MathMin(startShift + len + maxCandidates, copied - len - 1);
   for(int cand = startShift + len; cand <= lastCand; cand++)
   {
      double c = low[cand];
      bool isPivot = true;
      for(int i = 1; i <= len; i++)
      {
         if(!(c < low[cand-i]) || !(c < low[cand+i])) { isPivot = false; break; }
      }
      if(isPivot)
      {
         swingPrice = c;
         swingTime  = iTime(_Symbol, tf, cand);
         return true;
      }
   }
   return false;
}

// Resolves the final SL for one signal: tries the custom-timeframe swing
// point first (if enabled), validates it's actually on the correct side of
// price, applies the buffer, and falls back to the original LTF-pivot
// fallbackSL if no valid swing point is found (unless RequireCustomSwingSL
// forces a reject instead). asOfTime should be the closed bar time the
// signal was evaluated on.
bool ResolveSwingSL(ENUM_ORDER_TYPE type, double entryEstimate, double fallbackSL,
                     datetime asOfTime, double &outSL)
{
   if(!UseCustomSwingSL)
   {
      outSL = fallbackSL;
      return true;
   }

   double swingPrice; datetime swingTime;
   bool found = (type == ORDER_TYPE_BUY)
                ? FindSwingLow (SL_SwingTimeframe, SL_SwingPivotLen, asOfTime, SL_MaxCandidates, swingPrice, swingTime)
                : FindSwingHigh(SL_SwingTimeframe, SL_SwingPivotLen, asOfTime, SL_MaxCandidates, swingPrice, swingTime);

   if(found)
   {
      double buffer = PipsToPrice(SL_BufferPips);
      double sl = (type == ORDER_TYPE_BUY) ? swingPrice - buffer : swingPrice + buffer;
      bool validSide = (type == ORDER_TYPE_BUY) ? (sl < entryEstimate) : (sl > entryEstimate);
      if(validSide)
      {
         outSL = sl;
         return true;
      }
      // Most recent confirmed swing is already on the wrong side of current
      // price (e.g. price broke past it) - fall through to fallback/reject.
   }

   if(RequireCustomSwingSL) return false;

   outSL = fallbackSL;
   return true;
}

//====================================================================
// 3b. PIP SIZE HELPER
//     A "pip" is 10 points on a 3/5-digit (fractional) broker quote and
//     1 point on a 2/4-digit quote - matches the conventional definition
//     used by most retail FX brokers (e.g. EURUSD 1 pip = 0.0001, not
//     0.00001; XAUUSD/JPY pairs with fewer digits fall back to 1 point).
//====================================================================
double PipSize()
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   return (digits == 3 || digits == 5) ? _Point * 10.0 : _Point;
}

double PipsToPrice(double pips)
{
   return pips * PipSize();
}

//====================================================================
// 4. LOT SIZE
//====================================================================
double NormalizeLots(double lots)
{
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   lots = MathFloor(lots/stepLot + 1e-8) * stepLot;
   if(lots < minLot) lots = minLot;
   if(lots > maxLot) lots = maxLot;
   return NormalizeDouble(lots, 2);
}

//====================================================================
// 5. POSITION HELPERS
//====================================================================
bool HasOpenPosition()
{
   for(int i = PositionsTotal()-1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == (long)MagicNumber)
         return true;
   }
   return false;
}

bool SpreadOk()
{
   if(MaxSpreadPoints <= 0) return true;
   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   return (spread <= MaxSpreadPoints);
}

bool IsPositionOpen(ulong ticket)
{
   if(ticket == 0) return false;
   return PositionSelectByTicket(ticket);
}

//====================================================================
// 6. CHART VISUALS (optional, mirrors the indicator's plots)
//====================================================================
void DrawHLine(string name, double price, color clr, int style=STYLE_SOLID)
{
   if(!ShowChartObjects) return;
   if(price <= 0) { ObjectDelete(0, name); return; }

   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
}

void UpdateVisuals()
{
   if(!ShowChartObjects) return;
   DrawHLine("ICC_HTF_Res", hasHtfRes ? htf_res : 0, clrRed);
   DrawHLine("ICC_HTF_Sup", hasHtfSup ? htf_sup : 0, clrLime);
   DrawHLine("ICC_TriggerZone", (stage==2 || stage==-2) && hasTriggerZone ? trigger_zone : 0, clrDodgerBlue, STYLE_DOT);
}

//====================================================================
// 7. TRADE EXECUTION
//====================================================================
void OpenTrade(ENUM_ORDER_TYPE type, double slPrice)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double entryPrice = (type == ORDER_TYPE_BUY) ? ask : bid;

   double dist = PipsToPrice(TP_Pips);
   double tpPrice = (type == ORDER_TYPE_BUY) ? entryPrice + dist : entryPrice - dist;

   if(type == ORDER_TYPE_BUY)
   { if(slPrice >= entryPrice || tpPrice <= entryPrice) return; }
   else
   { if(slPrice <= entryPrice || tpPrice >= entryPrice) return; }

   double lots = NormalizeLots(FixedLots);
   if(lots <= 0) return;

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(20);

   double slN = NormalizeDouble(slPrice, _Digits);
   double tpN = NormalizeDouble(tpPrice, _Digits);

   bool ok = (type == ORDER_TYPE_BUY) ? trade.Buy(lots, _Symbol, entryPrice, slN, tpN, TradeComment)
                                       : trade.Sell(lots, _Symbol, entryPrice, slN, tpN, TradeComment);
   if(!ok)
   {
      Print("ICC_Swing_EA: order failed - ", trade.ResultRetcodeDescription());
      return;
   }

   ulong dealTicket = trade.ResultDeal();
   ulong posId = 0;
   if(dealTicket != 0 && HistoryDealSelect(dealTicket))
      posId = (ulong)HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);

   trade_active = true;
   trade_ticket  = posId;
   trade_dir     = (type == ORDER_TYPE_BUY) ? 1 : -1;
}

//====================================================================
// 8. CORE STATE MACHINE - runs ONCE PER NEW CLOSED BAR
//    Section numbers below map directly to the Pine script.
//====================================================================
void ProcessNewBar()
{
   // ---- snapshots of "previous bar" values (needed for crossover logic) ----
   double htf_res_prev = htf_res, htf_sup_prev = htf_sup, trigger_zone_prev = trigger_zone;
   bool   hasHtfRes_prev = hasHtfRes, hasHtfSup_prev = hasHtfSup, hasTrig_prev = hasTriggerZone;

   double closeArr[];
   ArraySetAsSeries(closeArr, true);
   if(CopyClose(_Symbol, _Period, 0, 5, closeArr) < 5) return;
   double closeThisBar = closeArr[1]; // the bar that just closed  == Pine's "current" bar
   double closePrevBar = closeArr[2]; // one bar before that       == Pine's close[1]

   double highArr[], lowArr[];
   ArraySetAsSeries(highArr, true);
   ArraySetAsSeries(lowArr, true);
   CopyHigh(_Symbol, _Period, 0, 3, highArr);
   CopyLow(_Symbol, _Period, 0, 3, lowArr);
   double highThisBar = highArr[1];
   double lowThisBar  = lowArr[1];

   //---------------------------------------------------------------
   // SECTION 3: Support & Resistance Pivots - update persistent levels
   //---------------------------------------------------------------
   double pv;
   bool htf_ph = GetPivotHigh(HTF_PivotLen, pv);
   if(htf_ph) { htf_res = pv; hasHtfRes = true; }
   bool htf_pl = GetPivotLow (HTF_PivotLen, pv);
   if(htf_pl) { htf_sup = pv; hasHtfSup = true; }
   bool ltf_ph = GetPivotHigh(LTF_PivotLen, pv); if(ltf_ph){ ltf_res = pv; hasLtfRes = true; }
   bool ltf_pl = GetPivotLow (LTF_PivotLen, pv); if(ltf_pl){ ltf_sup = pv; hasLtfSup = true; }

   //---------------------------------------------------------------
   // SECTION 4a: bull_break / bear_break (crossover of close vs htf levels)
   // Pine: crossover(x,y) => x[1] < y[1] and x[0] > y[0]
   //---------------------------------------------------------------
   bool bull_break = hasHtfRes_prev && hasHtfRes &&
                      (closePrevBar < htf_res_prev) && (closeThisBar > htf_res);
   bool bear_break = hasHtfSup_prev && hasHtfSup &&
                      (closePrevBar > htf_sup_prev) && (closeThisBar < htf_sup);

   // Phase 1: Indication Breaks
   if(bull_break && stage <= 0)
   {
      stage = 1;
      indication_extremum = highThisBar;
      hasIndicationExt = true;
   }
   if(bear_break && stage >= 0)
   {
      stage = -1;
      indication_extremum = lowThisBar;
      hasIndicationExt = true;
   }

   // Update extremes & switch to Correction Phase
   if(stage == 1)
   {
      if(hasIndicationExt) indication_extremum = MathMax(indication_extremum, highThisBar);
      if(ltf_ph)
      {
         stage = 2;
         trigger_zone = ltf_res;
         hasTriggerZone = true;
      }
   }
   if(stage == -1)
   {
      if(hasIndicationExt) indication_extremum = MathMin(indication_extremum, lowThisBar);
      if(ltf_pl)
      {
         stage = -2;
         trigger_zone = ltf_sup;
         hasTriggerZone = true;
      }
   }

   //---------------------------------------------------------------
   // SECTION 4b: Phase 2 - track corrections / trailing trigger & SL
   //---------------------------------------------------------------
   if(stage == 2)
   {
      if(hasHtfSup && closeThisBar < htf_sup) stage = 0; // invalidated
      if(ltf_pl && hasLtfSup && hasHtfSup && ltf_sup > htf_sup)
      {
         sl_level = ltf_sup;
         hasSlLevel = true;
      }
      if(ltf_ph)
      {
         trigger_zone = ltf_res;
         hasTriggerZone = true;
      }
   }
   if(stage == -2)
   {
      if(hasHtfRes && closeThisBar > htf_res) stage = 0; // invalidated
      if(ltf_ph && hasLtfRes && hasHtfRes && ltf_res < htf_res)
      {
         sl_level = ltf_res;
         hasSlLevel = true;
      }
      if(ltf_pl)
      {
         trigger_zone = ltf_sup;
         hasTriggerZone = true;
      }
   }

   //---------------------------------------------------------------
   // SECTION 5: Entry trigger - crossover(close, trigger_zone)
   //---------------------------------------------------------------
   bool long_cond  = false;
   bool short_cond = false;

   if(stage == 2 && hasTrig_prev && hasTriggerZone && hasSlLevel)
      long_cond = (closePrevBar < trigger_zone_prev) && (closeThisBar > trigger_zone);

   if(stage == -2 && hasTrig_prev && hasTriggerZone && hasSlLevel)
      short_cond = (closePrevBar > trigger_zone_prev) && (closeThisBar < trigger_zone);

   bool blocked = HasOpenPosition();

   if(long_cond && (!OnePositionAtATime || !blocked))
   {
      double entryEstimate = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double finalSL;
      if(SpreadOk() && ResolveSwingSL(ORDER_TYPE_BUY, entryEstimate, sl_level, iTime(_Symbol,_Period,1), finalSL))
      {
         OpenTrade(ORDER_TYPE_BUY, finalSL);
      }
      stage = 0;
      hasSlLevel = false;
   }
   else if(short_cond && (!OnePositionAtATime || !blocked))
   {
      double entryEstimate = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double finalSL;
      if(SpreadOk() && ResolveSwingSL(ORDER_TYPE_SELL, entryEstimate, sl_level, iTime(_Symbol,_Period,1), finalSL))
      {
         OpenTrade(ORDER_TYPE_SELL, finalSL);
      }
      stage = 0;
      hasSlLevel = false;
   }

   UpdateVisuals();
}

//====================================================================
// 9. EXPERT LIFECYCLE
//====================================================================
int OnInit()
{
   if(HTF_PivotLen < 1 || LTF_PivotLen < 1)
   {
      Print("Pivot lengths must be >= 1");
      return(INIT_PARAMETERS_INCORRECT);
   }
   if(TP_Pips <= 0)
   {
      Print("TP_Pips must be > 0");
      return(INIT_PARAMETERS_INCORRECT);
   }
   if(UseCustomSwingSL)
   {
      if(SL_SwingPivotLen < 1)
      {
         Print("SL_SwingPivotLen must be >= 1");
         return(INIT_PARAMETERS_INCORRECT);
      }
      if(SL_MaxCandidates < 1)
      {
         Print("SL_MaxCandidates must be >= 1");
         return(INIT_PARAMETERS_INCORRECT);
      }
      if(SL_SwingTimeframe != PERIOD_CURRENT && SL_SwingTimeframe < _Period)
         Print("ICC_Swing_EA: warning - SL_SwingTimeframe is FINER than the chart's own "
               "timeframe. That searches for swing points on smaller/noisier structure than "
               "HTF_PivotLen/LTF_PivotLen already use, which usually defeats the point of a "
               "separate custom-timeframe stop. Typically SL_SwingTimeframe should be the same "
               "as or wider than the chart timeframe (e.g. H4/D1 stops on an H1 chart).");
   }

   lastProcessedBarTime = 0;
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   if(ShowChartObjects)
   {
      ObjectDelete(0, "ICC_HTF_Res");
      ObjectDelete(0, "ICC_HTF_Sup");
      ObjectDelete(0, "ICC_TriggerZone");
   }
}

void OnTick()
{
   if(trade_active && !IsPositionOpen(trade_ticket))
      trade_active = false;

   datetime currentBarTime = iTime(_Symbol, _Period, 0);
   if(currentBarTime == lastProcessedBarTime) return; // wait for a new bar to close

   lastProcessedBarTime = currentBarTime;
   ProcessNewBar();
}
//+------------------------------------------------------------------+
