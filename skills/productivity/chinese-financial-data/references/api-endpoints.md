# Chinese Financial Data API Endpoints

## Yahoo Finance (US Markets)

| Endpoint | Description |
|----------|-------------|
| `query1.finance.yahoo.com/v8/finance/chart/QQQ?interval=5m&range=1d&includePrePost=true` | QQQ with after-hours |
| `query1.finance.yahoo.com/v8/finance/chart/NQ=F?interval=5m&range=1d` | NQ e-mini futures |
| `query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?interval=1d&range=5d` | Multi-day range |

### Key Yahoo Meta Fields

```
meta.regularMarketPrice       — latest/closing price
meta.chartPreviousClose       — previous session close
meta.regularMarketDayHigh     — session high
meta.regularMarketDayLow      — session low
meta.fiftyTwoWeekHigh         — 52-week high
meta.fiftyTwoWeekLow          — 52-week low
meta.regularMarketVolume      — volume
meta.currentTradingPeriod     — {pre, regular, post} with start/end timestamps
meta.exchangeTimezoneName     — e.g. "America/New_York"
```

### Timestamp Handling

- Timestamps are Unix epoch seconds
- `regular.end` marks the end of US regular trading session (16:00 ET)
- After-hours data = timestamps > `regular.end`
- Pre-market data = timestamps < `regular.start` AND >= `pre.start`

---

## Sina Finance (A-Share 实时行情)

```bash
# Shenzhen stocks/ETFs
curl -s "https://hq.sinajs.cn/list=sz159941" -H "Referer: https://finance.sina.com.cn"

# Shanghai stocks/ETFs
curl -s "https://hq.sinajs.cn/list=sh510050" -H "Referer: https://finance.sina.com.cn"

# IOPV reference
curl -s "https://hq.sinajs.cn/list=i159941" -H "Referer: https://finance.sina.com.cn"
```

### CSV Field Index (Shenzhen)

Position | Field | Example
---------|-------|--------
0 | 名称 | 纳指ETF
1 | 今开 | 1.620
2 | 昨收 | 1.628
3 | 现价 | 1.644
4 | 最高 | 1.647
5 | 最低 | 1.616
6 | 买一价 | 1.644
7 | 卖一价 | 1.645
8 | 成交量(手) | 1472956302
9 | 成交额 | 2405221947.188
-3 | 日期 | 2026-06-24
-2 | 时间 | 15:00:03

### Encoding

⚠️ Sina Finance returns **GBK-encoded** text. Always pipe through iconv:
```bash
curl -s "https://hq.sinajs.cn/list=sz159941" -H "Referer: https://finance.sina.com.cn" | iconv -f GBK -t UTF-8
```

---

## 天天基金 (净值估算)

```bash
curl -s "https://fundgz.1234567.com.cn/js/159941.js" -H "User-Agent: Mozilla/5.0"
```

Returns JSONP: `jsonpgz({...})`

Key fields:
- `fundcode` — fund code
- `name` — fund name
- `jzrq` — NAV date
- `dwjz` — previous official NAV (单位净值)
- `gsz` — estimated current NAV
- `gszzl` — estimated % change
- `gztime` — estimation timestamp

---

## East Money Push API

```bash
curl -s "http://push2.eastmoney.com/api/qt/stock/get?secid=0.159941&fields=f43,f44,f45,f46,f47,f57,f58,f60"
```

- secid format: `0.XXXXX` for Shenzhen, `1.XXXXX` for Shanghai
- Fields: f43=现价, f44=最高, f45=最低, f46=今开, f47=昨收, f57=代码, f58=名称, f60=IOPV净值
- Returns empty/0 values when market is closed
- Price values are in **分** (÷1000 for 元 display)
- Hard rate-limited from datacenter IPs; may return empty without proper Referer

---

## QDII ETF Premium

```
溢价率 = (市场价格 / IOPV净值 - 1) × 100%
```

Premium sources:
- **Real-time (trading hours):** IOPV from East Money f60 or Sina i-prefix
- **Historical (post-close):** Official NAV from 天天基金

### Common QDII Nasdaq 100 ETFs

| Code | Name | Market |
|------|------|--------|
| 159941 | 纳指ETF广发 | Shenzhen |
| 513100 | 纳指ETF | Shanghai |
| 159632 | 纳斯达克ETF | Shenzhen |
| 513300 | 纳指ETF | Shanghai |
