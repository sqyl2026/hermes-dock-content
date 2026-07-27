---
name: market-data
description: "Retrieve real-time and historical market data for stocks, ETFs, indices, and futures using public APIs (Yahoo Finance)."
category: finance
platforms: [linux, macos, windows]
---

# Market Data Skill

## When to use

Use this skill any time the user asks for:
- Current **stock**, **ETF**, **futures**, or **index** prices
- Market data for US, HK, or global markets
- Pre-market, after-hours, or overnight futures pricing
- Price changes, percentage moves, day range, or 52-week range
- Any ticker symbol (QQQ, SPY, AAPL, NQ=F, ES=F, 159941.SZ, etc.)

## Quick Reference

The simplest recipe: curl Yahoo Finance → Python parse → formatted output.

```bash
curl -s "https://query1.finance.yahoo.com/v8/finance/chart/QQQ?interval=1d" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d['chart']['result'][0]
m=r['meta']
p=m['regularMarketPrice']
pc=m['chartPreviousClose']
chg=p-pc
pct=(p/pc-1)*100
print(f'价格: \${p:.2f}')
print(f'前收: \${pc:.2f}')
print(f'涨跌: {chg:+.2f} ({pct:+.2f}%)')
print(f'日内: \${m[\"regularMarketDayLow\"]} ~ \${m[\"regularMarketDayHigh\"]}')
print(f'52周: \${m[\"fiftyTwoWeekLow\"]} ~ \${m[\"fiftyTwoWeekHigh\"]}')
print(f'量: {m[\"regularMarketVolume\"]:,}')
"
```

## API Details

### Base URL

```
https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?interval=1d
```

| Parameter | Purpose | Example |
|-----------|---------|---------|
| `interval` | Bar size | `1d` (daily), `5m` (5-min), `15m`, `1h` |
| `range` | Lookback | `2d`, `5d`, `1mo`, `3mo`, `1y` |
| `includePrePost` | Include pre/post market | `true` |

### Response Structure

```json
{
  "chart": {
    "result": [{
      "meta": {
        "regularMarketPrice": 710.62,
        "chartPreviousClose": 737.95,
        "regularMarketDayHigh": 719.93,
        "regularMarketDayLow": 704.45,
        "fiftyTwoWeekHigh": 748.65,
        "fiftyTwoWeekLow": 539.38,
        "regularMarketVolume": 39714509,
        "regularMarketTime": 1782331203,
        "currency": "USD",
        "exchangeTimezoneName": "America/New_York",
        "currentTradingPeriod": {
          "pre": { "start": ..., "end": ... },
          "regular": { "start": ..., "end": ... },
          "post": { "start": ..., "end": ... }
        }
      }
    }]
  }
}
```

### Key Meta Fields

| Field | What it is |
|-------|------------|
| `regularMarketPrice` | Closing price (or current if market open) |
| `chartPreviousClose` | Previous trading day's close |
| `regularMarketDayHigh/Low` | Intraday range |
| `fiftyTwoWeekHigh/Low` | 52-week range |
| `regularMarketVolume` | Volume for the session |
| `regularMarketTime` | Last trade timestamp (Unix epoch, America/New_York tz) |
| `currentTradingPeriod` | Pre/regular/post market session boundaries (Unix timestamps for start/end) |
| `currency` | Trading currency (USD, HKD, CNY, etc.) |

### Common Ticker Symbols

| Ticker | Description |
|--------|-------------|
| `QQQ` | Invesco QQQ Trust (Nasdaq 100 ETF) |
| `SPY` | SPDR S&P 500 ETF |
| `DIA` | SPDR Dow Jones ETF |
| `IWM` | Russell 2000 ETF |
| `NQ=F` | E-mini Nasdaq 100 Futures |
| `ES=F` | E-mini S&P 500 Futures |
| `YM=F` | Mini Dow Futures |
| `GC=F` | Gold Futures |
| `CL=F` | Crude Oil Futures |
| `BTC-USD` | Bitcoin / USD |
| `159941.SZ` | 纳指ETF广发 (Shenzhen) |
| `513100.SS` | 纳指ETF (Shanghai) |
| `^IXIC` | Nasdaq Composite Index |
| `^DJI` | Dow Jones Industrial Average |
| `^GSPC` | S&P 500 Index |
| `^HSI` | Hang Seng Index |

## Advanced Usage

### With After-Hours Data

```bash
curl -s "https://query1.finance.yahoo.com/v8/finance/chart/QQQ?interval=5m&range=2d&includePrePost=true" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d['chart']['result'][0]
ts=r['timestamp']
c=r['indicators']['quote'][0]['close']
# Find after-hours: anything after regular market end
reg_end = r['meta']['currentTradingPeriod']['regular']['end']
for t,price in zip(ts,c):
    if price and t > reg_end:
        print(f'盘后 {t}: \${price:.2f}')
"
```

### Check if Market is Open

```bash
date "+北京时间: %Y-%m-%d %H:%M:%S"
echo "美股时间: $(TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z')"
```

- US market open: 9:30 AM - 4:00 PM Eastern
- Pre-market: 4:00 AM - 9:30 AM Eastern
- After-hours: 4:00 PM - 8:00 PM Eastern
- Futures trade nearly 24h on CME

### Batch Multiple Symbols

Fetch one by one — Yahoo doesn't support batch quotes in the chart endpoint. For batches, use the `/v7/finance/quote` endpoint:

```bash
curl -s "https://query1.finance.yahoo.com/v7/finance/quote?symbols=QQQ,SPY,NQ=F,^GSPC" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for q in d['quoteResponse']['result']:
    print(f\"{q['symbol']}: \${q['regularMarketPrice']:.2f} ({q.get('regularMarketChangePercent',0):+.2f}%)\")
"
```

## Pitfalls

1. **User-Agent is required** — always set `-H "User-Agent: Mozilla/5.0"` or Yahoo blocks the request.
2. **After-hours data** — the default `regularMarketPrice` is the closing print. To see after-hours movement, use `includePrePost=true` and compare prices after the regular session end timestamp.
3. **Ticker suffix matters for Chinese ETFs** — Shenzhen stocks use `.SZ`, Shanghai use `.SS`. Example: `159941.SZ`, `513100.SS`.
4. **Futures use `=F` suffix** — e.g., `NQ=F`, `ES=F`. Note that `chartPreviousClose` for futures is the **settlement price**, not the prior day's close.
5. **Yahoo rate limits** — if `query1` is slow, try `query2.finance.yahoo.com`. For heavy usage, consider adding delays between requests.
6. **`chartPreviousClose` vs `previousClose`** — always use `chartPreviousClose` from the meta object; `previousClose` at the root level may return a different value.
7. **Dividend-adjusted prices** — Yahoo returns adjusted close by default, so long-term historical comparisons are OK. For granular intraday, raw close is used.
