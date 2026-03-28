# terminal.py

> Trade KuCoin Futures directly from your terminal — open positions, set TP/SL, add margin, and cancel stops with a single command. No web UI needed.

> 💬 **I develop custom trading bots, scanners, and automation tools.**  
> Reach out on Telegram: [@smmgotop](https://t.me/smmgotop)

---

## Why this exists

Most traders rely on a browser to manage positions — which means slow clicks, accidental misclicks, and no scriptability. This tool lets you manage KuCoin Futures positions directly from the terminal: one command to open, one to adjust, one to check status. Fast, reproducible, and easy to integrate into scripts or cron jobs.

---

## Architecture

```
terminal.py
    │
    ├── sign_request()      HMAC-SHA256 + Base64 (KuCoin API v2 auth)
    │
    ├── api()               Generic signed request dispatcher (GET / POST / DELETE)
    │        │
    │        ├── get_position()         Open position for symbol
    │        ├── get_stop_orders()      Active TP/SL stop orders
    │        ├── get_contract()         Contract spec (multiplier, tick size)
    │        ├── get_funding_rate()     Current funding rate
    │        ├── place_order()          Market or limit entry order
    │        ├── place_stop_order()     TP or SL stop-market order
    │        ├── cancel_stop_orders()   Bulk cancel all stops for symbol
    │        └── add_margin_to_position()  Add isolated margin
    │
    └── main()  ──  argument parser  ──►  command handlers
                                               │
                                    ┌──────────┼──────────┐
                              cmd_open   cmd_set_tp_sl  cmd_cancel_stops
                              _position                 cmd_add_margin
                                               │
                                         print_summary()
                                    (always shown after any action)
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/goodgamefinder/kucointerminaltrade.git
cd kucointerminaltrade
```

### 2. Create and activate a virtual environment (recommended)

```bash
python3 -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate.bat       # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add your API credentials

Open `terminal.py` and fill in your KuCoin Futures API key, secret, and passphrase:

```python
API_KEY        = "your_api_key"
API_SECRET     = "your_api_secret"
API_PASSPHRASE = "your_passphrase"
```

> **Where to create API keys:**  
> KuCoin → Account → API Management → Create API → select **Futures** permissions.  
> Enable **Trade** permission. IP whitelist is recommended.  
> ⚠️ Never share your API secret or commit it to a public repository.

---

## All arguments

| Argument | Short | Type | Description |
|---|---|---|---|
| `--pair` | `-p` | str | Coin ticker: `BTC`, `ETH`, `DOGE` — `USDTM` is appended automatically |
| `--info` | `-i` | flag | Show position status only, take no action |
| `--long` | `-l` | flag | Open a long (buy) position |
| `--short` | `-s` | flag | Open a short (sell) position |
| `--lots` | | int | Number of contracts to trade |
| `--leverage` | | int | Leverage multiplier |
| `--price` | | float | Limit entry price — omit for market order |
| `--tp` | | float | Take-profit price (placed immediately after open) |
| `--sl` | | float | Stop-loss price (placed immediately after open) |
| `--tplots` | | int | Contracts to close at TP — defaults to full position |
| `--sllots` | | int | Contracts to close at SL — defaults to full position |
| `--settp` | | float | Set TP on an existing open position |
| `--setsl` | | float | Set SL on an existing open position |
| `--addmargin` | | float | Add USDT margin to an open position |
| `--cancelstops` | | flag | Cancel all stop orders for the symbol |
| `--yes` | `-y` | flag | Skip all confirmation prompts |

---

## Usage examples

### Check position status

```bash
# View current BTC position (read-only, no trades placed)
python3 terminal.py --pair BTC

# Same for ETH
python3 terminal.py -p ETH --info
```

**Example output:**

```
📊 POSITION SUMMARY:

Symbol      Side   Lots       Entry        Price        Liq.         PnL                      Margin     Added      Lev.         $/lot    Fund.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
BTCUSDTM    LONG   10         61842.50     62140.00     58300.00     $+29.75 (+19.83%)        $62.10     $0.00      10x          $62.14   0.0023%
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  🛑 Active stop orders:
  Type       Price           Lots       Trigger
  ──────────────────────────────────────────────
  TP         65000.00        10         up
  SL         59000.00        10         down
```

---

### Open a long position

```bash
# Market long: 10 lots of BTC at 5x leverage
python3 terminal.py --pair BTC --long --lots 10 --leverage 5

# Market long with auto-confirm (no prompt)
python3 terminal.py --pair BTC --long --lots 10 --leverage 5 -y
```

---

### Open a short position

```bash
# Market short: 5 lots of ETH at 10x leverage
python3 terminal.py --pair ETH --short --lots 5 --leverage 10

# Short with limit entry price
python3 terminal.py --pair ETH --short --lots 5 --leverage 10 --price 3500
```

---

### Open with TP and SL in one command

```bash
# Long BTC: 10 lots, 5x leverage, TP at $70 000, SL at $58 000
python3 terminal.py --pair BTC --long --lots 10 --leverage 5 --tp 70000 --sl 58000

# Short ETH: 8 lots, 10x, TP at $2 800, SL at $3 600
python3 terminal.py --pair ETH --short --lots 8 --leverage 10 --tp 2800 --sl 3600 -y

# Long with partial TP (close 5 lots at TP, all lots at SL)
python3 terminal.py --pair BTC --long --lots 10 --leverage 5 --tp 70000 --tplots 5 --sl 58000
```

---

### Set TP / SL on an existing position

```bash
# Add a take-profit to an open BTC position at $95 000 (all lots)
python3 terminal.py --pair BTC --settp 95000

# Add a stop-loss at $85 000
python3 terminal.py --pair BTC --setsl 85000

# Set both at once, auto-confirm
python3 terminal.py --pair BTC --settp 95000 --setsl 85000 -y

# Partial TP: close only 3 lots at the TP level
python3 terminal.py --pair BTC --settp 95000 --tplots 3
```

---

### Add margin to an open position

```bash
# Add $20 USDT of margin to reduce liquidation risk on BTC
python3 terminal.py --pair BTC --addmargin 20

# Add margin without confirmation prompt
python3 terminal.py --pair BTC --addmargin 50 -y
```

**Example output:**

```
═══════════════════════════════════════════════════════════════
  💰 ADD MARGIN
═══════════════════════════════════════════════════════════════

  Current margin: $62.10  →  +$20
  Confirm? (y/n): y
  ✅ Done
```

---

### Cancel all stop orders

```bash
# Cancel all TP and SL orders for BTC
python3 terminal.py --pair BTC --cancelstops

# Cancel without confirmation
python3 terminal.py --pair BTC --cancelstops -y
```

---

### Scripting and automation

Because every action supports `-y` to skip prompts, the tool integrates cleanly into shell scripts:

```bash
#!/bin/bash
# Example: open a BTC long and set stops in one shot
python3 terminal.py --pair BTC --long --lots 10 --leverage 5 \
  --tp 70000 --sl 58000 -y

# Check status every 30 seconds
while true; do
  python3 terminal.py --pair BTC
  sleep 30
done
```

---

## How it works

1. **Authentication** — every request is signed using HMAC-SHA256. The timestamp, HTTP method, endpoint path, and request body are concatenated and signed with your `API_SECRET`. The passphrase is also signed (KuCoin API v2 requirement).
2. **Symbol normalization** — `BTC` → `BTCUSDTM`, `ETH` → `ETHUSDTM` automatically. Full symbols like `BTCUSDTM` are passed through unchanged.
3. **Position detection** — `GET /api/v1/positions` returns all open positions; the script filters for the requested symbol and `isOpen == true`.
4. **Order placement** — market orders omit the `price` field; limit orders include `price` and `timeInForce: GTC`. All orders use `marginMode: ISOLATED`.
5. **Stop orders** — both TP and SL use the same stop-market order endpoint. Direction is inferred from position side: for longs, TP triggers `stop: up` and SL triggers `stop: down`; for shorts it is reversed.
6. **Summary table** — always printed after any action. Columns include entry price, mark price, liquidation price, unrealized PnL (absolute + %), margin, added margin, leverage, contract value per lot, and the current funding rate.

---

## Notes

- **Isolated margin only** — the script always sets `marginMode: ISOLATED` before opening a position.
- **Market orders by default** — omit `--price` for instant fills at market price.
- **Partial closes** — use `--tplots` / `--sllots` to close only part of a position at the stop level; the remainder stays open.
- **No WebSocket** — the script is stateless and makes REST calls only. For real-time monitoring wrap it in a shell loop.
- **Rate limits** — KuCoin Futures enforces rate limits per endpoint. The `enableRateLimit` option in ccxt is not used here (direct `requests`), so avoid calling the script in a tight loop without a sleep.

---

## License

MIT
