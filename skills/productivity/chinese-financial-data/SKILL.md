---
name: chinese-financial-data
description: "Query Chinese A-share ETFs/stocks, US markets (QQQ/NQ futures), and calculate QDII ETF premium rates."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [finance, stocks, ETF, QDII, premium, A-share, market-data]
    related_skills: []
---

# Chinese Financial Data

Query real-time and historical data for Chinese A-share ETFs, US markets, and QDII ETF premium calculations. This skill covers the data sources and API patterns needed for investment reference.

## Quick Reference

| Task | Method |
|------|--------|
| US stocks/ETF (QQQ) | Yahoo Finance API |
| US futures (NQ) | Yahoo Finance API |
| Chinese ETF price | Sina Finance |
| Chinese ETF IOPV/NAV | 天天基金 / East Money |
| QDII premium rate | Market price ÷ IOPV − 1 |

---

## US Market Data (Yahoo Finance)

### QQQ (Invesco QQQ Trust)

```bash
curl -s "https://query1.finance.yahoo.com/v8/finance/chart/QQQ?interval=5m&range=1d&includePrePost=true" \
  -H "User-Agent: Mozilla/5.0"
```

Key fields in response:
- `meta.regularMarketPrice` — closing price (regular session)
- `meta.chartPreviousClose` — previous session close
- `meta.regularMarketDayHigh/Low` — intraday range
- `meta.fiftyTwoWeekHigh/Low` — 52-week range
- `meta.currentTradingPeriod` — pre/regular/post session timestamps
- Timestamps after `regular.end` = after-hours data

**To include after-hours/pre-market data**, pass `includePrePost=true`.

### NQ Futures (E-mini Nasdaq 100)

```bash
curl -s "https://query1.finance.yahoo.com/v8/finance/chart/NQ=F?interval=5m&range=1d" \
  -H "User-Agent: Mozilla/5.0"
```

NQ futures trade nearly 24h — the `regularMarketPrice` is the latest tick.

---

## Chinese ETF Data (A-Share)

### Sina Finance (实时行情)

```bash
curl -s "https://hq.sinajs.cn/list=sz159941" -H "Referer: https://finance.sina.com.cn"
```

Response is GBK-encoded CSV. Parse with `iconv -f GBK -t UTF-8` then extract quoted fields:

```
var hq_str_sz159941="名称,今开,昨收,现价,最高,最低,买一,卖一,成交量,成交额,...";
```

Shenzhen ETF prices are in **元 with 3 decimal places** (e.g. 1.644). 
- Code prefix: `sz` for Shenzhen, `sh` for Shanghai
- IOPV code: `i159941` (Shenzhen IOPV) — often empty outside trading hours

### 天天基金 (净值估算)

```bash
curl -s "https://fundgz.1234567.com.cn/js/159941.js" -H "User-Agent: Mozilla/5.0"
```

Returns JSONP. Key fields:
- `gsz` — estimated real-time NAV
- `dwjz` — previous official NAV
- `gszzl` — estimated % change

### East Money (Push API)

```bash
curl -s "http://push2.eastmoney.com/api/qt/stock/get?secid=0.159941&fields=f43,f57,f58,f60"
```

- secid: `0.xxxxx` for Shenzhen, `1.xxxxx` for Shanghai
- `f43` — current price (0 before market opens)
- `f57` — code
- `f58` — name
- `f60` — IOPV (参考净值)
- ETF prices internally in 分 (÷1000 for 元)

---

## QDII ETF Premium Calculation

**Formula:** `溢价率 = (市场价格 ÷ IOPV - 1) × 100%`

Hard rule (from user's 定投清单): **溢价率 < 3%** to buy; ≥ 3% → skip.

```python
market_price = 1.644    # from Sina / East Money
iopv = 1.628             # from East Money f60 ÷ 1000
premium = (market_price / iopv - 1) * 100  # = +0.98%
```

**Caveats:**
- IOPV is an **estimate** — the official NAV (from 天天基金) is published after market close and may differ
- Premium data is only available during A-share trading hours (09:30-15:00 CST)
- QDII ETF premium is affected by: US market overnight moves, USD/CNY FX rate, QDII quota availability, and market supply/demand

---

## Trading Hours Reference

| Market | Session | Time (CST) |
|--------|---------|-----------|
| A-share open call auction | 集合竞价 | 09:15-09:25 |
| A-share continuous | 连续竞价 | 09:30-11:30, 13:00-14:57 |
| A-share close call auction | 收盘集合竞价 | 14:57-15:00 |
| US pre-market (EDT) | | 21:00-21:30 CST (夏令时) |
| US regular (EDT) | | 21:30-04:00 CST (夏令时) |
| NQ futures (CME) | | Nearly 24h, Sun-Fri |

---

## Pitfalls

- **Market closed = price = 0**: Chinese APIs return 0 for current price before 09:30 or after 15:00. Check `昨收` (previous close) instead.
- **GBK encoding**: Sina Finance returns GBK-encoded data. Use `iconv -f GBK -t UTF-8` before parsing.
- **Yahoo rate limits**: Yahoo Finance free API has no auth but may throttle. If it returns empty, retry with a different interval or range.
- **Premium ≠ NAV difference**: Market price premium over IOPV is NOT the same as the fund's NAV growth — they measure different things.
- **After-hours gaps**: QQQ after-hours price can move significantly before the next A-share session opens. Always re-check premium before buying at 14:57.
