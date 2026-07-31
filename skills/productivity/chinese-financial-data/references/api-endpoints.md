# A 股行情命令与数据语义

## 目录

1. [统一返回契约](#统一返回契约)
2. [股票命令](#股票命令)
3. [指数命令](#指数命令)
4. [ETF 命令](#etf-命令)
5. [板块命令](#板块命令)
6. [股池与交易日历](#股池与交易日历)
7. [字段单位与复权](#字段单位与复权)
8. [数据源和限制](#数据源和限制)

## 统一返回契约

成功时 stdout 只输出一个 JSON 对象：

```json
{
  "schema_version": 1,
  "success": true,
  "command": "stock-history",
  "source": {
    "library": "AKShare",
    "library_version": "1.18.81",
    "upstream": "东方财富"
  },
  "fetched_at": "2026-07-31T14:30:00+08:00",
  "meta": {
    "total": 140,
    "returned": 140,
    "truncated": false
  },
  "data": []
}
```

失败仍只输出一个 JSON 对象，并返回非零退出码：

```json
{
  "schema_version": 1,
  "success": false,
  "error": {
    "code": "upstream_error",
    "message": "ConnectionError: ..."
  }
}
```

错误码：

| 错误码 | 含义 |
|---|---|
| `invalid_input` | 代码格式、代码所属资产类别、日期、范围或数量非法 |
| `data_unavailable` | 超时、空行情或上游字段结构变化 |
| `upstream_error` | AKShare 或公开数据源请求失败 |
| `runtime_error` | `uv`、Hermes Python、脚本或锁文件不可用 |

列表命令用 `meta.total` 表示筛选后的总行数，用 `offset`、`limit`、`returned` 和 `truncated` 描述分页。历史命令在超出 `--limit` 时保留最新记录，并把 `meta.selection` 设为 `latest`。

## 股票命令

### `stock-search`

```bash
run_market.py stock-search <代码或名称> [--limit 1..100]
```

从沪深京 A 股代码和简称中做不区分空格的包含匹配，完全匹配排在前面。

### `stock-quote`

```bash
run_market.py stock-quote <六位代码> [<六位代码> ...]
```

一次最多 20 只，返回最新、涨幅、涨跌、今开、最高、最低、昨收、成交金额、总手、换手、量比、涨跌停价、内外盘和五档买卖价量。该命令会先校验代码是否存在。

### `stock-snapshot`

```bash
run_market.py stock-snapshot \
  [--query <代码或名称>] \
  [--sort price|change|amount|volume|turnover|market-cap|pe] \
  [--order asc|desc] [--offset N] [--limit 1..500]
```

用于全市场筛选、排序和分页。不要在只查一两只股票时使用它替代 `stock-quote`。

### `stock-history`

```bash
run_market.py stock-history <代码> \
  [--period daily|weekly|monthly] \
  [--adjust none|qfq|hfq] \
  [--start YYYYMMDD] [--end YYYYMMDD] [--limit 1..5000]
```

默认查询最近 90 个自然日，最多输出最新 300 行。

查询前会用当前沪深京 A 股名录校验代码，并在 `meta.name` 返回证券简称。未上市、已退市或传入 ETF/指数代码时返回 `invalid_input`；代码有效但日期区间没有行情时可以成功返回空数组。

### `stock-intraday`

```bash
run_market.py stock-intraday <代码> \
  [--period 1|5|15|30|60] \
  [--adjust none|qfq|hfq] \
  [--start "YYYY-MM-DD HH:MM:SS"] \
  [--end "YYYY-MM-DD HH:MM:SS"] [--limit 1..5000]
```

默认查询最近 7 个自然日，最多输出最新 500 行。1 分钟数据不复权，且只覆盖上游近期可用范围。

### `market-overview`

统计有效行情中的上涨、下跌、平盘家数、平均涨跌幅、涨跌幅中位数和成交额合计。

### `stock-rank`

```bash
run_market.py stock-rank \
  [--by price|change|amount|volume|turnover|market-cap|pe] \
  [--order asc|desc] [--limit 1..100]
```

排行基于一次全市场快照。使用 `order=asc` 获取跌幅、最低成交额或最低估值等反向排行。

## 指数命令

### `index-snapshot`

```bash
run_market.py index-snapshot \
  [--series important|shanghai|shenzhen|constituents|csi|all] \
  [--query <代码或名称>] \
  [--sort price|change|amount|volume] \
  [--order asc|desc] [--offset N] [--limit 1..500]
```

`all` 会完整请求所有系列；任一系列失败都会让本次命令失败，不返回不完整集合。

### `index-history` 与 `index-intraday`

```bash
run_market.py index-history <六位代码> \
  [--period daily|weekly|monthly] \
  [--start YYYYMMDD] [--end YYYYMMDD] [--limit 1..5000]

run_market.py index-intraday <六位代码> \
  [--period 1|5|15|30|60] \
  [--start "YYYY-MM-DD HH:MM:SS"] \
  [--end "YYYY-MM-DD HH:MM:SS"] [--limit 1..5000]
```

对不确定的指数代码，先用 `index-snapshot --series all --query <名称>` 查找。

历史和分钟查询会先联合查询东方财富的沪深重要、上证、深证、指数成份和中证系列校验代码，并在 `meta.name` 返回指数名称；会覆盖 `899050` 北证 50、`932000` 中证 2000 等较新指数。股票或 ETF 代码不会被当作指数查询。

## ETF 命令

### `etf-snapshot`

```bash
run_market.py etf-snapshot \
  [--query <代码或名称>] \
  [--sort price|change|amount|volume|turnover|market-cap|discount] \
  [--order asc|desc] [--offset N] [--limit 1..500]
```

除通用行情字段外，上游可能返回 `IOPV实时估值`、`基金折价率`、买卖一档、份额和资金流字段。字段为 `null` 表示上游没有值，不得当作 0。

### `etf-history` 与 `etf-intraday`

参数与对应股票命令一致。ETF 溢价或折价应优先使用同一条快照中的最新价和 IOPV 字段；只计算差值，不给出买卖结论。

历史和分钟查询会先用当前 ETF 行情名录校验代码，并在 `meta.name` 返回基金名称。股票或指数代码不会被当作 ETF 查询。

## 板块命令

`--kind industry` 表示行业板块，`--kind concept` 表示概念板块。

```bash
run_market.py board-snapshot --kind industry \
  [--query <板块代码或名称>] \
  [--sort price|change|turnover|market-cap|advancers|decliners] \
  [--order asc|desc] [--offset N] [--limit 1..500]

run_market.py board-history --kind concept <板块名称> \
  [--period daily|weekly|monthly] [--adjust none|qfq|hfq] \
  [--start YYYYMMDD] [--end YYYYMMDD] [--limit 1..5000]

run_market.py board-intraday --kind industry <板块名称> \
  [--period 1|5|15|30|60] [--limit 1..5000]
```

历史和分钟命令要求准确板块名称；先用 `board-snapshot --query` 解析名称。

## 股池与交易日历

### `limit-pool`

```bash
run_market.py limit-pool \
  --kind up|down|broken|previous \
  [--date YYYYMMDD] [--query <代码、名称或行业>] \
  [--offset N] [--limit 1..500]
```

- `up`：涨停股池。
- `down`：跌停股池。
- `broken`：炸板股池。
- `previous`：昨日涨停股池。

跌停和炸板接口通常只支持近期交易日。非交易日或没有符合条件的股票时可以返回空数组。

### `trade-calendar`

```bash
run_market.py trade-calendar \
  [--start YYYYMMDD] [--end YYYYMMDD] \
  [--offset N] [--limit 1..500]
```

返回所选闭区间内的历史交易日。来源是新浪财经维护的历史交易日历；不要把它当作交易所未来休市公告。

## 字段单位与复权

- 股票历史和快照中的 `成交量` 通常以“手”为单位，`成交额` 以“元”为单位。
- ETF 和指数的具体字段单位以 AKShare 对应接口文档为准；不要仅凭字段名称假设。
- `涨跌幅`、`振幅`、`换手率`、`基金折价率` 的数值单位通常是百分比，例如 `2.5` 表示 `2.5%`。
- `none`：不复权，是真实历史成交价。
- `qfq`：前复权，保持当前价格不变，历史数据会在以后除权除息后变化。
- `hfq`：后复权，保持历史价格不变，当前数值可能远离实际成交价。

## 数据源和限制

- 股票、指数、ETF、板块及涨跌停股池通过 AKShare 调用东方财富公开数据。
- 股票代码名称来自沪深京三家交易所数据，交易日历来自新浪财经。
- 这些接口无需 API Key，但依赖公网、目标站点可用性和访问策略。
- 输出是公开网页行情参考数据，不是交易所授权的逐笔行情，不承诺实时性和 SLA。
- 每次命令整体超时为 60 秒。超时、限流、IP 拒绝、响应损坏或字段变化会明确失败。
- 脚本固定 AKShare 版本并锁定传递依赖；Linux ARM64 会显式选择 `akracer` 提供的 ARM JavaScript 运行库，避免被同目录的 x86 兼容包覆盖。更新版本时必须重新生成相邻的 `a_share_market.py.lock`，并在 Hermes 的 Linux AMD64、ARM64 镜像中重新验证依赖安装和交易日历。
- 包装器会验证子进程 stdout。依赖下载、锁、哈希、平台 wheel 或缓存准备失败且业务脚本没有返回 JSON 时，包装器输出单个 `runtime_error` JSON，而不是留下空 stdout。
