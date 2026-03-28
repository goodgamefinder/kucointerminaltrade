#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
terminal.py
KuCoin Futures position manager — open positions, set TP/SL,
add margin, and cancel stops directly from the command line.

Usage:
  # View current position status (read-only)
  python3 terminal.py --pair BTC
  python3 terminal.py --pair ETH --info

  # Open a position
  python3 terminal.py --pair BTC --long  --lots 10 --leverage 5
  python3 terminal.py --pair ETH --short --lots 5  --leverage 10

  # Open with limit price
  python3 terminal.py --pair BTC --long --lots 10 --leverage 5 --price 60000

  # Open with TP and SL in a single command
  python3 terminal.py --pair BTC --long --lots 10 --leverage 5 --tp 70000 --sl 55000

  # Set TP / SL on an existing position
  python3 terminal.py --pair BTC --settp 95000 --tplots 1
  python3 terminal.py --pair BTC --setsl 85000

  # Add margin to an open position
  python3 terminal.py --pair BTC --addmargin 20

  # Cancel all stop orders
  python3 terminal.py --pair BTC --cancelstops

  # Skip confirmation prompts
  python3 terminal.py --pair BTC --long --lots 5 --leverage 10 -y
"""

import argparse
import base64
import hashlib
import hmac
import json
import sys
import time
import uuid
from typing import Dict, Any, Optional, List

import requests

# === API CREDENTIALS ===
# Replace these with your actual KuCoin Futures API credentials.
# Create them at: https://www.kucoin.com/account/api
API_KEY        = "YOUR_HERE"
API_SECRET     = "YOUR_HERE"
API_PASSPHRASE = "YOUR_HERE"
API_KEY_VERSION = "2"

BASE_URL = "https://api-futures.kucoin.com"
TIMEOUT  = 10

# === Terminal colors (ANSI escape codes) ===
R   = "\033[0m"   # reset
B   = "\033[1m"   # bold
RED = "\033[91m"
GRN = "\033[92m"
YEL = "\033[93m"
CYN = "\033[96m"
MAG = "\033[95m"
WHT = "\033[97m"


def now_ms() -> int:
    """Return current Unix timestamp in milliseconds."""
    return int(time.time() * 1000)


def sign_request(timestamp: str, method: str, endpoint: str, body_str: str) -> Dict[str, str]:
    """
    Build KuCoin API v2 authentication headers.
    Signs the request using HMAC-SHA256 and encodes the result in Base64.
    """
    str_to_sign = f"{timestamp}{method.upper()}{endpoint}{body_str}"
    signature = base64.b64encode(
        hmac.new(API_SECRET.encode(), str_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    pass_sig = base64.b64encode(
        hmac.new(API_SECRET.encode(), API_PASSPHRASE.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "KC-API-KEY":         API_KEY,
        "KC-API-SIGN":        signature,
        "KC-API-TIMESTAMP":   timestamp,
        "KC-API-PASSPHRASE":  pass_sig,
        "KC-API-KEY-VERSION": API_KEY_VERSION,
        "Content-Type":       "application/json"
    }


def api(method: str, endpoint: str, params: Optional[Dict] = None, body: Optional[Dict] = None) -> Any:
    """
    Generic signed API request helper.
    Raises RuntimeError on non-200000 KuCoin response codes.
    Position endpoints that return no data are handled gracefully (return []).
    """
    full_endpoint = endpoint
    body_str = ""
    if params:
        query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        full_endpoint = f"{endpoint}?{query_string}"
    if body:
        body_str = json.dumps(body, separators=(',', ':'), ensure_ascii=False)

    ts = str(now_ms())
    headers = sign_request(ts, method, full_endpoint, body_str)
    url = BASE_URL + full_endpoint

    if method in ("GET", "DELETE"):
        resp = requests.request(method, url, headers=headers, timeout=TIMEOUT)
    else:
        resp = requests.request(method, url, headers=headers, data=body_str, timeout=TIMEOUT)

    data = resp.json()
    if resp.status_code == 200 and data.get("code") == "200000":
        return data.get("data")
    # If querying positions returns a non-200000 code, no position is open — return gracefully
    if "position" in endpoint and data.get("code") != "200000":
        return []
    raise RuntimeError(f"API Error: {data}")


# ── Market data helpers ───────────────────────────────────────────────────────

def get_contract(symbol: str) -> Dict:
    """Fetch contract specification (multiplier, tick size, etc.)."""
    return api("GET", f"/api/v1/contracts/{symbol}")


def get_ticker(symbol: str) -> float:
    """Return the current mark price for a symbol."""
    data = api("GET", "/api/v1/ticker", {"symbol": symbol})
    return float(data.get("price", 0))


def get_funding_rate(symbol: str) -> float:
    """Return the current funding rate. Returns 0.0 on any error."""
    try:
        data = api("GET", f"/api/v1/funding-rate/{symbol}/current")
        return float(data.get("value", 0)) if data else 0.0
    except:
        return 0.0


def get_position(symbol: str) -> Optional[Dict]:
    """Return the open position for the symbol, or None if no position exists."""
    positions = api("GET", "/api/v1/positions")
    if not positions:
        return None
    for pos in positions:
        if pos.get("symbol") == symbol and pos.get("isOpen"):
            return pos
    return None


def get_stop_orders(symbol: str) -> List[Dict]:
    """Return all active stop orders for the symbol."""
    try:
        data = api("GET", "/api/v1/stopOrders", {"symbol": symbol})
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "items" in data:
            return data.get("items", [])
    except:
        pass
    return []


# ── Order / position management ───────────────────────────────────────────────

def add_margin_to_position(symbol: str, amount: float) -> bool:
    """Deposit additional isolated margin into an open position."""
    body = {
        "symbol": symbol,
        "margin": str(amount),
        "bizNo":  str(uuid.uuid4())
    }
    api("POST", "/api/v1/position/margin/deposit-margin", body=body)
    return True


def set_isolated_margin(symbol: str, leverage: int):
    """Switch the position margin mode to ISOLATED (silently ignores errors)."""
    try:
        api("POST", "/api/v2/position/changeMarginMode", body={
            "symbol":     symbol,
            "marginMode": "ISOLATED"
        })
    except Exception:
        pass


def place_order(symbol: str, side: str, size: int, leverage: int,
                limit_price: Optional[float] = None) -> Dict:
    """
    Place a market or limit order.
    side: 'long' → buy | 'short' → sell
    """
    kucoin_side = "buy" if side == "long" else "sell"
    order = {
        "clientOid":  str(uuid.uuid4()),
        "symbol":     symbol,
        "side":       kucoin_side,
        "size":       size,
        "leverage":   leverage,
        "marginMode": "ISOLATED"
    }
    if limit_price:
        order["type"]        = "limit"
        order["price"]       = str(limit_price)
        order["timeInForce"] = "GTC"
    else:
        order["type"] = "market"
    return api("POST", "/api/v1/orders", body=order)


def place_stop_order(symbol: str, side: str, size: int, stop_price: float,
                     stop_type: str = "down", reduce_only: bool = True) -> Dict:
    """
    Place a stop-market order (used for both TP and SL).
    stop_type: 'up' triggers when price rises above stopPrice,
               'down' triggers when price falls below stopPrice.
    """
    order = {
        "clientOid":    str(uuid.uuid4()),
        "symbol":       symbol,
        "side":         side,
        "size":         size,
        "stop":         stop_type,
        "stopPrice":    str(stop_price),
        "stopPriceType":"TP",
        "type":         "market",
        "reduceOnly":   reduce_only,
        "marginMode":   "ISOLATED"
    }
    return api("POST", "/api/v1/orders", body=order)


def cancel_stop_orders(symbol: str) -> int:
    """Cancel all active stop orders for the symbol. Returns list of cancelled IDs."""
    result = api("DELETE", "/api/v1/stopOrders", {"symbol": symbol})
    return result.get("cancelledOrderIds", []) if result else []


# ── Formatting helpers ────────────────────────────────────────────────────────

def normalize_symbol(symbol: str) -> str:
    """Append USDTM suffix if not already present (e.g. BTC → BTCUSDTM)."""
    symbol = symbol.upper()
    if not symbol.endswith("USDTM") and not symbol.endswith("USDCM"):
        symbol = symbol + "USDTM"
    return symbol


def print_header(title: str):
    """Print a cyan section header."""
    print()
    print(f"{B}{CYN}═══════════════════════════════════════════════════════════════{R}")
    print(f"{B}{CYN}  {title}{R}")
    print(f"{B}{CYN}═══════════════════════════════════════════════════════════════{R}")
    print()


def format_price(price: float) -> str:
    """
    Adaptive price formatting:
    - price < 10  → up to 8 significant decimal places (trailing zeros stripped)
    - price >= 10 → 2 decimal places
    """
    if price < 10:
        return f"{price:.8f}".rstrip('0').rstrip('.')
    else:
        return f"{price:.2f}"


def print_summary(symbol: str):
    """Fetch and display a full position + stop-orders summary table."""
    time.sleep(0.5)  # Allow exchange data to refresh after an action
    pos   = get_position(symbol)
    stops = get_stop_orders(symbol)

    print(f"\n{B}📊 POSITION SUMMARY:{R}\n")

    headers = [
        "Symbol", "Side", "Lots", "Entry", "Price", "Liq.",
        "PnL", "Margin", "Added", "Lev.", "$/lot", "Fund."
    ]

    header_fmt = "  {:<11} {:<6} {:<10} {:<12} {:<12} {:<12} {:<24} {:<10} {:<10} {:<12} {:<8} {:<7}"
    print(f"{B}" + header_fmt.format(*headers) + f"{R}")
    print(f"  {WHT}{'─'*130}{R}")

    if not pos:
        # No open position — print an empty row
        print(f"  {YEL}{symbol:<11} {'-':<6} {'-':<10} {'-':<12} {'-':<12} {'-':<12} {'NO POSITION':<24}{R}")
    else:
        contract   = get_contract(symbol)
        multiplier = float(contract.get("multiplier", 1))

        is_long  = pos.get("currentQty", 0) > 0
        side_str = "LONG" if is_long else "SHORT"
        side_col = GRN if is_long else RED

        qty   = abs(pos.get("currentQty", 0))
        entry = float(pos.get("avgEntryPrice", 0))
        mark  = float(pos.get("markPrice", 0))
        liq   = float(pos.get("liquidationPrice", 0))

        pnl     = float(pos.get("unrealisedPnl", 0))
        pnl_pct = float(pos.get("unrealisedRoePcnt", 0)) * 100
        pnl_col = GRN if pnl >= 0 else RED

        margin   = float(pos.get("posMargin", 0))
        added    = float(pos.get("marginAdd", 0))
        leverage = float(pos.get("leverage", 0))

        val_per_lot = multiplier * mark
        funding     = get_funding_rate(symbol) * 100

        # Build colored field strings
        s_symbol = f"{B}{symbol}{R}"
        s_side   = f"{side_col}{side_str}{R}"
        s_qty    = f"{qty}"
        s_entry  = format_price(entry)
        s_mark   = format_price(mark)
        s_liq    = format_price(liq)
        s_pnl    = f"{pnl_col}${pnl:+.2f} ({pnl_pct:+.2f}%){R}"
        s_margin = f"${margin:.2f}"
        s_added  = f"${added:.2f}"
        s_lev    = f"{leverage:.0f}x"
        s_vpl    = f"${val_per_lot:.4f}"
        s_fund   = f"{funding:.4f}%"

        # Manual column alignment — ANSI codes inflate len(), so fixed widths are used
        print(
            f"  {s_symbol:<20} "
            f"{s_side:<15} "
            f"{s_qty:<10} "
            f"{s_entry:<12} "
            f"{s_mark:<12} "
            f"{s_liq:<12} "
            f"{s_pnl:<33} "
            f"{s_margin:<10} "
            f"{s_added:<10} "
            f"{s_lev:<12} "
            f"{s_vpl:<8} "
            f"{s_fund:<7}"
        )

    print(f"  {WHT}{'─'*130}{R}")

    # Stop orders table
    if stops:
        print(f"\n  {B}🛑 Active stop orders:{R}")
        print(f"  {B}{'Type':<10} {'Price':<15} {'Lots':<10} {'Trigger':<10}{R}")
        print(f"  {'─'*50}")

        for s in stops:
            price     = float(s.get("stopPrice", 0))
            amount    = s.get("size", 0)
            stop_side = s.get("stop", "")  # "up" or "down"

            color    = YEL
            type_lbl = "STOP"

            if pos:
                entry   = float(pos.get("avgEntryPrice", 0))
                is_long = pos.get("currentQty", 0) > 0
                # Long: TP if trigger price > entry, SL if below
                # Short: TP if trigger price < entry, SL if above
                is_tp    = (price > entry) if is_long else (price < entry)
                type_lbl = "TP" if is_tp else "SL"
                color    = GRN if is_tp else RED

            print(f"  {color}{type_lbl:<10} {format_price(price):<15} {amount:<10} {stop_side:<10}{R}")
    else:
        if pos:
            print(f"\n  {YEL}📭 No stop orders set{R}")

    print("\n")


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_add_margin(symbol: str, amount: float, skip_confirm: bool = False):
    """Add isolated margin to an open position."""
    print_header("💰 ADD MARGIN")
    position = get_position(symbol)
    if not position:
        print(f"  {RED}❌ No open position for {symbol}{R}")
        return
    current_margin = position.get("posMargin", 0)
    print(f"  Current margin: {B}${current_margin:.2f}{R}  →  +${amount}")
    if not skip_confirm:
        if input(f"  {YEL}Confirm? (y/n): {R}").strip().lower() != 'y':
            return
    add_margin_to_position(symbol, amount)
    print(f"  {GRN}✅ Done{R}")


def cmd_set_tp_sl(symbol: str, tp_price: Optional[float], sl_price: Optional[float],
                  tp_lots: Optional[int], sl_lots: Optional[int],
                  skip_confirm: bool = False):
    """Place TP and/or SL stop orders on an existing position."""
    print_header("🎯 SET TP / SL")
    position = get_position(symbol)
    if not position:
        print(f"  {RED}❌ No open position for {symbol}{R}")
        return
    qty      = abs(position.get("currentQty", 0))
    is_long  = position.get("currentQty", 0) > 0
    tp_size  = tp_lots if tp_lots else qty
    sl_size  = sl_lots if sl_lots else qty

    if tp_price:
        print(f"  TP: {GRN}${tp_price}{R}  ({tp_size} lot(s))")
    if sl_price:
        print(f"  SL: {RED}${sl_price}{R}  ({sl_size} lot(s))")

    if not skip_confirm:
        if input(f"  {YEL}Confirm? (y/n): {R}").strip().lower() != 'y':
            return

    close_side = "sell" if is_long else "buy"
    if tp_price:
        try:
            place_stop_order(symbol, close_side, tp_size, tp_price, "up" if is_long else "down")
        except Exception as e:
            print(f"  {RED}TP error: {e}{R}")
    if sl_price:
        try:
            place_stop_order(symbol, close_side, sl_size, sl_price, "down" if is_long else "up")
        except Exception as e:
            print(f"  {RED}SL error: {e}{R}")


def cmd_cancel_stops(symbol: str, skip_confirm: bool = False):
    """Cancel all active stop orders for the symbol."""
    print_header("❌ CANCEL STOPS")
    if not skip_confirm:
        if input(f"  {YEL}Cancel all stop orders? (y/n): {R}").strip().lower() != 'y':
            return
    cancel_stop_orders(symbol)
    print(f"  {GRN}✅ Stop orders cancelled{R}")


def cmd_open_position(symbol: str, side: str, lots: int, leverage: int,
                      limit_price: Optional[float], tp_price: Optional[float], sl_price: Optional[float],
                      tp_lots: Optional[int], sl_lots: Optional[int],
                      skip_confirm: bool = False):
    """Open a new position, optionally setting TP/SL immediately after fill."""
    print_header("🚀 OPEN POSITION")
    print(f"  {side.upper()} {symbol} x{leverage} | Lots: {lots}")
    if limit_price:
        print(f"  Limit price: ${limit_price}")
    if tp_price:
        print(f"  TP: {GRN}${tp_price}{R}")
    if sl_price:
        print(f"  SL: {RED}${sl_price}{R}")

    if not skip_confirm:
        if input(f"  {YEL}Confirm? (y/n): {R}").strip().lower() != 'y':
            return

    try:
        set_isolated_margin(symbol, leverage)
        place_order(symbol, side, lots, leverage, limit_price)
        print(f"  {GRN}✅ Order sent{R}")

        if tp_price or sl_price:
            time.sleep(1)  # Wait for position to be confirmed by the exchange
            pos = get_position(symbol)
            if pos:
                is_long    = side == "long"
                close_side = "sell" if is_long else "buy"
                tp_sz      = tp_lots if tp_lots else lots
                sl_sz      = sl_lots if sl_lots else lots
                if tp_price:
                    try:
                        place_stop_order(symbol, close_side, tp_sz, tp_price, "up" if is_long else "down")
                    except:
                        pass
                if sl_price:
                    try:
                        place_stop_order(symbol, close_side, sl_sz, sl_price, "down" if is_long else "up")
                    except:
                        pass
    except Exception as e:
        print(f"  {RED}Error: {e}{R}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="KuCoin Futures terminal — manage positions from the command line"
    )
    parser.add_argument("--pair", "-p", required=True,
                        help="Trading pair ticker, e.g. BTC or BTCUSDTM")
    parser.add_argument("--info", "-i", action="store_true",
                        help="Only display position status, take no action")

    direction = parser.add_mutually_exclusive_group()
    direction.add_argument("--long",  "-l", action="store_true", help="Open a long position")
    direction.add_argument("--short", "-s", action="store_true", help="Open a short position")

    parser.add_argument("--lots",      type=int,   help="Number of contracts")
    parser.add_argument("--leverage",  type=int,   help="Leverage multiplier")
    parser.add_argument("--price",     type=float, help="Limit entry price (omit for market)")
    parser.add_argument("--tp",        type=float, help="Take-profit price (set on open)")
    parser.add_argument("--sl",        type=float, help="Stop-loss price (set on open)")
    parser.add_argument("--tplots",    type=int,   help="Lots to close at TP (default: all)")
    parser.add_argument("--sllots",    type=int,   help="Lots to close at SL (default: all)")
    parser.add_argument("--addmargin", type=float, help="Add margin (USDT) to open position")
    parser.add_argument("--settp",     type=float, help="Set TP on existing position")
    parser.add_argument("--setsl",     type=float, help="Set SL on existing position")
    parser.add_argument("--cancelstops", action="store_true",
                        help="Cancel all stop orders for this symbol")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Skip confirmation prompts")

    args   = parser.parse_args()
    symbol = normalize_symbol(args.pair)

    action_performed = False

    if args.addmargin:
        cmd_add_margin(symbol, args.addmargin, args.yes)
        action_performed = True
    elif args.settp or args.setsl:
        cmd_set_tp_sl(symbol, args.settp, args.setsl, args.tplots, args.sllots, args.yes)
        action_performed = True
    elif args.cancelstops:
        cmd_cancel_stops(symbol, args.yes)
        action_performed = True
    elif args.long or args.short:
        if not args.lots or not args.leverage:
            print(f"  {RED}--lots and --leverage are required to open a position{R}")
            return
        side = "long" if args.long else "short"
        cmd_open_position(
            symbol, side, args.lots, args.leverage,
            args.price, args.tp, args.sl,
            args.tplots, args.sllots, args.yes
        )
        action_performed = True

    # Always print the position summary after any action (or when just checking status)
    print_summary(symbol)


if __name__ == "__main__":
    main()
