---
name: chinese-financial-data
description: 查询无需 API Key 的沪深京 A 股市场数据。用于按代码或名称查股票，获取股票、指数、ETF、行业板块和概念板块的行情快照、日周月历史行情、分钟行情、全市场涨跌概况与排行、涨停跌停炸板股池及交易日历。也用于回答“现在多少钱”“今天涨跌如何”“最近一段时间走势”“涨幅榜”“成交额榜”“某板块表现”“今天是否交易日”等中国证券市场查数请求。
---

# A 股行情查数

只通过随技能提供的包装器查询，不直接拼接网页接口，不临时安装依赖，也不让模型编写 AKShare 调用：

```bash
/opt/hermes/.venv/bin/python \
  skills/productivity/chinese-financial-data/scripts/run_market.py \
  <command> [arguments]
```

首次运行使用锁文件安装 AKShare 及依赖，并把下载缓存保存在 `/opt/data/.dock/chinese-financial-data-uv-cache/`；后续运行复用缓存。所有业务结果只在 stdout 输出一个 JSON 对象，进度信息可能出现在 stderr。

## 查询流程

1. 用户给出股票名称但没有代码时，先执行 `stock-search`。不要猜代码。
2. 根据资产和粒度选择下表中的命令。股票、指数和 ETF 历史命令会先校验代码所属类别；类别不匹配时修正命令，不要绕过校验。
3. 检查 JSON 的 `success`。失败时向用户说明 `error.message`，不要伪造数据或静默改用其他来源。
4. 检查 `meta.truncated`。为 `true` 时，按需增大 `--limit`、调整 `--offset` 或缩小日期范围；不得把截断结果描述成完整结果。
5. 回答当前行情时注明 `source.upstream` 和 `fetched_at`。`fetched_at` 是抓取时间，不是交易所逐笔时间；休市时“最新价”通常是最近成交价或收盘价。
6. 保留 AKShare 返回的字段单位。需要换算“亿元”“万手”等展示单位时，明确写出换算结果，不覆盖原始值。

## 命令选择

| 用户需求 | 命令 |
|---|---|
| 名称或代码找股票 | `stock-search` |
| 单股或少量股票五档及最新报价 | `stock-quote` |
| 按名称筛选、排序或分页浏览全市场 | `stock-snapshot` |
| 股票日、周、月行情 | `stock-history` |
| 股票 1/5/15/30/60 分钟行情 | `stock-intraday` |
| 上涨、下跌、平盘家数和成交额 | `market-overview` |
| 涨跌幅、成交额、换手率、市值等排行 | `stock-rank` |
| 指数快照、历史或分钟行情 | `index-snapshot`、`index-history`、`index-intraday` |
| ETF 快照、历史或分钟行情 | `etf-snapshot`、`etf-history`、`etf-intraday` |
| 行业或概念板块 | `board-snapshot`、`board-history`、`board-intraday` |
| 涨停、跌停、炸板、昨日涨停股池 | `limit-pool` |
| 某日期区间是否为交易日 | `trade-calendar` |

## 常用调用

```bash
MARKET="skills/productivity/chinese-financial-data/scripts/run_market.py"

# 查询股票代码
/opt/hermes/.venv/bin/python "$MARKET" stock-search 贵州茅台

# 查询多只股票报价；一次最多 20 只
/opt/hermes/.venv/bin/python "$MARKET" stock-quote 600519 000001

# 涨幅前 20 和成交额前 10
/opt/hermes/.venv/bin/python "$MARKET" stock-rank --by change --order desc --limit 20
/opt/hermes/.venv/bin/python "$MARKET" stock-rank --by amount --order desc --limit 10

# 股票前复权日线
/opt/hermes/.venv/bin/python "$MARKET" stock-history 600519 \
  --start 20260101 --end 20260731 --period daily --adjust qfq --limit 500

# 最近的 5 分钟行情
/opt/hermes/.venv/bin/python "$MARKET" stock-intraday 600519 \
  --start "2026-07-31 09:30:00" --end "2026-07-31 15:00:00" \
  --period 5 --limit 500

# 沪深重要指数中查沪深 300
/opt/hermes/.venv/bin/python "$MARKET" index-snapshot \
  --series important --query 沪深300

# ETF 中查代码或名称
/opt/hermes/.venv/bin/python "$MARKET" etf-snapshot --query 510300

# 行业板块涨幅榜与指定板块历史
/opt/hermes/.venv/bin/python "$MARKET" board-snapshot \
  --kind industry --sort change --order desc --limit 20
/opt/hermes/.venv/bin/python "$MARKET" board-history \
  --kind industry 半导体 --start 20260101 --end 20260731

# 当日涨停池和近一个月交易日
/opt/hermes/.venv/bin/python "$MARKET" limit-pool \
  --kind up --date 20260731 --limit 100
/opt/hermes/.venv/bin/python "$MARKET" trade-calendar \
  --start 20260701 --end 20260731
```

需要完整选项、排序字段、复权定义、返回契约和数据限制时，读取 [references/api-endpoints.md](references/api-endpoints.md)。

## 严格约束

- 只把结果用于信息查询和研究参考，不把行情、排行、涨跌停或溢价率直接解释成买卖建议。
- 不执行下单，不索取证券账户、交易密码、Cookie 或 API Key。
- 不把 `fetched_at` 当成交易所行情时间，不承诺逐笔实时性、低延迟或可用性 SLA。
- 不对网络失败、空响应、字段变化或超时做静默重试和数据源降级。
- 不把“无数据”改写成 0，不用上一轮结果冒充本轮查询。
- `adjust=qfq` 的历史值会随以后除权除息重新计算；比较或导出时注明复权方式。
- 一分钟行情仅覆盖 AKShare 上游可提供的近期数据；超出范围返回空数据时缩小日期范围，不猜补。
