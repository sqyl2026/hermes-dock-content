# /// script
# requires-python = ">=3.13,<3.14"
# dependencies = [
#   "akshare==1.18.81",
# ]
# ///

import argparse
import json
import math
import platform
import signal
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 60
MAX_QUOTE_CODES = 20
MAX_LIST_ROWS = 500
MAX_HISTORY_ROWS = 5000
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

INDEX_SERIES = {
    "important": "沪深重要指数",
    "shanghai": "上证系列指数",
    "shenzhen": "深证系列指数",
    "constituents": "指数成份",
    "csi": "中证系列指数",
}
PERIODS = ("daily", "weekly", "monthly")
MINUTE_PERIODS = ("1", "5", "15", "30", "60")
ADJUSTMENTS = ("none", "qfq", "hfq")
SORT_ORDERS = ("asc", "desc")

STOCK_SORT_COLUMNS = {
    "price": "最新价",
    "change": "涨跌幅",
    "amount": "成交额",
    "volume": "成交量",
    "turnover": "换手率",
    "market-cap": "总市值",
    "pe": "市盈率-动态",
}
ETF_SORT_COLUMNS = {
    "price": "最新价",
    "change": "涨跌幅",
    "amount": "成交额",
    "volume": "成交量",
    "turnover": "换手率",
    "market-cap": "总市值",
    "discount": "基金折价率",
}
INDEX_SORT_COLUMNS = {
    "price": "最新价",
    "change": "涨跌幅",
    "amount": "成交额",
    "volume": "成交量",
}
BOARD_SORT_COLUMNS = {
    "price": "最新价",
    "change": "涨跌幅",
    "turnover": "换手率",
    "market-cap": "总市值",
    "advancers": "上涨家数",
    "decliners": "下跌家数",
}


class InputError(Exception):
    pass


class DataError(Exception):
    pass


class RuntimeSetupError(Exception):
    pass


class MarketArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def date_default(days_ago: int) -> str:
    return (now_shanghai().date() - timedelta(days=days_ago)).strftime("%Y%m%d")


def positive_int(maximum: int) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("必须是整数") from exc
        if parsed < 1 or parsed > maximum:
            raise argparse.ArgumentTypeError(f"必须在 1 到 {maximum} 之间")
        return parsed

    return parse


def non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是整数") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("不能小于 0")
    return parsed


def stock_code(value: str) -> str:
    normalized = value.strip()
    if len(normalized) != 6 or not normalized.isascii() or not normalized.isdigit():
        raise argparse.ArgumentTypeError(f"证券代码必须是 6 位数字：{value}")
    return normalized


def non_empty_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise argparse.ArgumentTypeError("文本不能为空")
    return normalized


def compact_date(value: str) -> str:
    if len(value) != 8 or not value.isdigit():
        raise argparse.ArgumentTypeError(f"日期必须使用 YYYYMMDD：{value}")
    try:
        date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:]}")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"日期必须使用 YYYYMMDD：{value}") from exc
    return value


def minute_datetime(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=SHANGHAI_TZ
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"时间必须使用 YYYY-MM-DD HH:MM:SS：{value}"
        ) from exc
    if parsed.strftime("%Y-%m-%d %H:%M:%S") != value:
        raise argparse.ArgumentTypeError(f"时间必须使用 YYYY-MM-DD HH:MM:SS：{value}")
    return value


def validate_range(start: str, end: str) -> None:
    if start > end:
        raise InputError("开始时间不能晚于结束时间")


def adjustment(value: str) -> str:
    return "" if value == "none" else value


def configure_linux_arm_mini_racer(mini_racer: Any = None) -> None:
    if sys.platform != "linux" or platform.machine().lower() not in {
        "aarch64",
        "arm64",
    }:
        return
    if mini_racer is None:
        import py_mini_racer.py_mini_racer as mini_racer

    extension_path = Path(mini_racer.__file__).with_name("armlibmini_racer.glibc.so")
    if not extension_path.is_file():
        raise RuntimeSetupError(f"AKShare ARM JavaScript 运行库缺失：{extension_path}")
    mini_racer.EXTENSION_NAME = extension_path.name
    mini_racer.EXTENSION_PATH = str(extension_path)


def require_columns(frame: Any, required: tuple[str, ...], command: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DataError(f"{command} 返回结构已变化，缺少字段：{', '.join(missing)}")


def normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if type(value).__name__ in {"NAType", "NaTType"}:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return normalize_value(value.item())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    return str(value)


def frame_records(frame: Any) -> list[dict[str, Any]]:
    return [
        {str(key): normalize_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def apply_query(frame: Any, query: str | None, columns: tuple[str, ...]) -> Any:
    if not query:
        return frame
    normalized_query = "".join(query.split()).casefold()
    mask = None
    for column in columns:
        if column not in frame.columns:
            continue
        values = (
            frame[column]
            .fillna("")
            .astype(str)
            .str.replace(r"\s+", "", regex=True)
            .str.casefold()
            .str.contains(normalized_query, regex=False)
        )
        mask = values if mask is None else mask | values
    if mask is None:
        raise DataError(f"无法在字段 {', '.join(columns)} 中查询")
    return frame[mask]


def apply_sort(frame: Any, column: str | None, order: str) -> Any:
    if column is None:
        return frame
    if column not in frame.columns:
        raise DataError(f"返回数据缺少排序字段：{column}")
    return frame.sort_values(
        by=column,
        ascending=order == "asc",
        na_position="last",
        kind="stable",
    )


def page_frame(frame: Any, offset: int, limit: int) -> tuple[Any, dict[str, Any]]:
    total = len(frame)
    paged = frame.iloc[offset : offset + limit]
    return paged, {
        "total": total,
        "offset": offset,
        "limit": limit,
        "returned": len(paged),
        "truncated": offset + len(paged) < total,
    }


def tail_frame(frame: Any, limit: int) -> tuple[Any, dict[str, Any]]:
    total = len(frame)
    result = frame.tail(limit)
    return result, {
        "total": total,
        "returned": len(result),
        "limit": limit,
        "truncated": len(result) < total,
        "selection": "latest",
    }


def source(ak: Any, upstream: str) -> dict[str, str]:
    return {
        "library": "AKShare",
        "library_version": str(ak.__version__),
        "upstream": upstream,
    }


def success(
    command: str,
    ak: Any,
    upstream: str,
    data: Any,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "success": True,
        "command": command,
        "source": source(ak, upstream),
        "fetched_at": now_shanghai().isoformat(timespec="seconds"),
        "meta": meta or {},
        "data": data,
    }


def emit(payload: dict[str, Any], stream: Any = None) -> None:
    if stream is None:
        stream = sys.stdout
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ),
        file=stream,
    )


def stock_search(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    frame = ak.stock_info_a_code_name()
    require_columns(frame, ("code", "name"), "stock-search")
    frame = apply_query(frame, args.query, ("code", "name")).copy()
    normalized = "".join(args.query.split()).casefold()
    frame["_exact"] = frame["code"].astype(str).str.casefold().eq(normalized) | frame[
        "name"
    ].fillna("").astype(str).str.replace(r"\s+", "", regex=True).str.casefold().eq(
        normalized
    )
    frame = frame.sort_values("_exact", ascending=False, kind="stable").drop(
        columns="_exact"
    )
    frame, meta = page_frame(frame, 0, args.limit)
    meta["query"] = args.query
    return success(
        "stock-search",
        ak,
        "上海证券交易所、深圳证券交易所、北京证券交易所",
        frame_records(frame),
        meta,
    )


def vertical_frame_to_dict(frame: Any, command: str) -> dict[str, Any]:
    require_columns(frame, ("item", "value"), command)
    return {
        str(row["item"]): normalize_value(row["value"])
        for row in frame.to_dict(orient="records")
    }


def catalog_name(
    frame: Any,
    code: str,
    code_column: str,
    name_column: str,
    asset_name: str,
) -> str:
    require_columns(frame, (code_column, name_column), f"{asset_name}代码校验")
    for row in frame.to_dict(orient="records"):
        if str(row[code_column]).strip() == code:
            return str(row[name_column])
    raise InputError(f"未找到属于“{asset_name}”的代码：{code}")


def stock_name(ak: Any, code: str) -> str:
    return catalog_name(ak.stock_info_a_code_name(), code, "code", "name", "A 股")


def index_name(ak: Any, code: str) -> str:
    for label in INDEX_SERIES.values():
        frame = ak.stock_zh_index_spot_em(symbol=label)
        require_columns(frame, ("代码", "名称"), "A 股指数代码校验")
        for row in frame.to_dict(orient="records"):
            if str(row["代码"]).strip() == code:
                return str(row["名称"])
    raise InputError(f"未找到属于“A 股指数”的代码：{code}")


def etf_name(ak: Any, code: str) -> str:
    return catalog_name(ak.fund_etf_spot_em(), code, "代码", "名称", "ETF")


def stock_quote(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    names_frame = ak.stock_info_a_code_name()
    require_columns(names_frame, ("code", "name"), "stock-quote")
    names = dict(zip(names_frame["code"].astype(str), names_frame["name"].astype(str)))
    missing = [code for code in args.codes if code not in names]
    if missing:
        raise InputError(f"未找到 A 股代码：{', '.join(missing)}")

    rows = []
    for code in args.codes:
        quote = vertical_frame_to_dict(ak.stock_bid_ask_em(symbol=code), "stock-quote")
        if not quote or normalize_value(quote.get("最新")) is None:
            raise DataError(f"{code} 行情为空")
        rows.append({"代码": code, "名称": names[code], **quote})
    return success(
        "stock-quote",
        ak,
        "东方财富",
        rows,
        {"requested": len(args.codes), "returned": len(rows)},
    )


def stock_snapshot(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    frame = ak.stock_zh_a_spot_em()
    require_columns(frame, ("代码", "名称", "最新价", "涨跌幅"), "stock-snapshot")
    frame = apply_query(frame, args.query, ("代码", "名称"))
    frame = apply_sort(frame, STOCK_SORT_COLUMNS[args.sort], args.order)
    frame, meta = page_frame(frame, args.offset, args.limit)
    meta.update({"query": args.query, "sort": args.sort, "order": args.order})
    return success("stock-snapshot", ak, "东方财富", frame_records(frame), meta)


def stock_history(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    validate_range(args.start, args.end)
    name = stock_name(ak, args.code)
    frame = ak.stock_zh_a_hist(
        symbol=args.code,
        period=args.period,
        start_date=args.start,
        end_date=args.end,
        adjust=adjustment(args.adjust),
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    if not frame.empty:
        require_columns(frame, ("日期", "股票代码", "收盘"), "stock-history")
    frame, meta = tail_frame(frame, args.limit)
    meta.update(
        {
            "code": args.code,
            "name": name,
            "period": args.period,
            "adjust": args.adjust,
            "start": args.start,
            "end": args.end,
        }
    )
    return success("stock-history", ak, "东方财富", frame_records(frame), meta)


def stock_intraday(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    validate_range(args.start, args.end)
    name = stock_name(ak, args.code)
    frame = ak.stock_zh_a_hist_min_em(
        symbol=args.code,
        start_date=args.start,
        end_date=args.end,
        period=args.period,
        adjust=adjustment(args.adjust),
    )
    if not frame.empty:
        require_columns(frame, ("时间", "收盘"), "stock-intraday")
    frame, meta = tail_frame(frame, args.limit)
    meta.update(
        {
            "code": args.code,
            "name": name,
            "period_minutes": args.period,
            "adjust": args.adjust,
            "start": args.start,
            "end": args.end,
        }
    )
    return success("stock-intraday", ak, "东方财富", frame_records(frame), meta)


def market_overview(_args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    import pandas as pd

    frame = ak.stock_zh_a_spot_em()
    require_columns(frame, ("代码", "最新价", "涨跌幅", "成交额"), "market-overview")
    price = pd.to_numeric(frame["最新价"], errors="coerce")
    change = pd.to_numeric(frame["涨跌幅"], errors="coerce")
    active = price.notna() & change.notna()
    if not active.any():
        raise DataError("全市场行情为空")
    change = change[active]
    amount = pd.to_numeric(frame["成交额"], errors="coerce")
    summary = {
        "股票总数": len(frame),
        "有效行情数": int(active.sum()),
        "上涨家数": int((change > 0).sum()),
        "下跌家数": int((change < 0).sum()),
        "平盘家数": int((change == 0).sum()),
        "平均涨跌幅": normalize_value(change.mean()),
        "涨跌幅中位数": normalize_value(change.median()),
        "成交额合计": normalize_value(amount.sum(min_count=1)),
    }
    return success("market-overview", ak, "东方财富", summary)


def stock_rank(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    frame = ak.stock_zh_a_spot_em()
    require_columns(frame, ("代码", "名称", "最新价", "涨跌幅"), "stock-rank")
    column = STOCK_SORT_COLUMNS[args.by]
    frame = apply_sort(frame, column, args.order)
    frame, meta = page_frame(frame, 0, args.limit)
    meta.update({"by": args.by, "order": args.order})
    return success("stock-rank", ak, "东方财富", frame_records(frame), meta)


def index_snapshot(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    import pandas as pd

    requested = (
        list(INDEX_SERIES.items())
        if args.series == "all"
        else [(args.series, INDEX_SERIES[args.series])]
    )
    frames = []
    for key, label in requested:
        frame = ak.stock_zh_index_spot_em(symbol=label).copy()
        require_columns(frame, ("代码", "名称", "最新价", "涨跌幅"), "index-snapshot")
        frame.insert(0, "系列", key)
        frames.append(frame)
    frame = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["代码"], keep="first"
    )
    frame = apply_query(frame, args.query, ("代码", "名称"))
    frame = apply_sort(frame, INDEX_SORT_COLUMNS[args.sort], args.order)
    frame, meta = page_frame(frame, args.offset, args.limit)
    meta.update(
        {
            "series": args.series,
            "query": args.query,
            "sort": args.sort,
            "order": args.order,
        }
    )
    return success("index-snapshot", ak, "东方财富", frame_records(frame), meta)


def index_history(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    validate_range(args.start, args.end)
    name = index_name(ak, args.code)
    frame = ak.index_zh_a_hist(
        symbol=args.code,
        period=args.period,
        start_date=args.start,
        end_date=args.end,
    )
    if not frame.empty:
        require_columns(frame, ("日期", "收盘"), "index-history")
    frame, meta = tail_frame(frame, args.limit)
    meta.update(
        {
            "code": args.code,
            "name": name,
            "period": args.period,
            "start": args.start,
            "end": args.end,
        }
    )
    return success("index-history", ak, "东方财富", frame_records(frame), meta)


def index_intraday(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    validate_range(args.start, args.end)
    name = index_name(ak, args.code)
    frame = ak.index_zh_a_hist_min_em(
        symbol=args.code,
        period=args.period,
        start_date=args.start,
        end_date=args.end,
    )
    if not frame.empty:
        require_columns(frame, ("时间", "收盘"), "index-intraday")
    frame, meta = tail_frame(frame, args.limit)
    meta.update(
        {
            "code": args.code,
            "name": name,
            "period_minutes": args.period,
            "start": args.start,
            "end": args.end,
        }
    )
    return success("index-intraday", ak, "东方财富", frame_records(frame), meta)


def etf_snapshot(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    frame = ak.fund_etf_spot_em()
    require_columns(frame, ("代码", "名称", "最新价", "涨跌幅"), "etf-snapshot")
    frame = apply_query(frame, args.query, ("代码", "名称"))
    frame = apply_sort(frame, ETF_SORT_COLUMNS[args.sort], args.order)
    frame, meta = page_frame(frame, args.offset, args.limit)
    meta.update({"query": args.query, "sort": args.sort, "order": args.order})
    return success("etf-snapshot", ak, "东方财富", frame_records(frame), meta)


def etf_history(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    validate_range(args.start, args.end)
    name = etf_name(ak, args.code)
    frame = ak.fund_etf_hist_em(
        symbol=args.code,
        period=args.period,
        start_date=args.start,
        end_date=args.end,
        adjust=adjustment(args.adjust),
    )
    if not frame.empty:
        require_columns(frame, ("日期", "收盘"), "etf-history")
    frame, meta = tail_frame(frame, args.limit)
    meta.update(
        {
            "code": args.code,
            "name": name,
            "period": args.period,
            "adjust": args.adjust,
            "start": args.start,
            "end": args.end,
        }
    )
    return success("etf-history", ak, "东方财富", frame_records(frame), meta)


def etf_intraday(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    validate_range(args.start, args.end)
    name = etf_name(ak, args.code)
    frame = ak.fund_etf_hist_min_em(
        symbol=args.code,
        start_date=args.start,
        end_date=args.end,
        period=args.period,
        adjust=adjustment(args.adjust),
    )
    if not frame.empty:
        require_columns(frame, ("时间", "收盘"), "etf-intraday")
    frame, meta = tail_frame(frame, args.limit)
    meta.update(
        {
            "code": args.code,
            "name": name,
            "period_minutes": args.period,
            "adjust": args.adjust,
            "start": args.start,
            "end": args.end,
        }
    )
    return success("etf-intraday", ak, "东方财富", frame_records(frame), meta)


def board_snapshot(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    function = (
        ak.stock_board_industry_name_em
        if args.kind == "industry"
        else ak.stock_board_concept_name_em
    )
    frame = function()
    require_columns(
        frame, ("板块代码", "板块名称", "最新价", "涨跌幅"), "board-snapshot"
    )
    frame = apply_query(frame, args.query, ("板块代码", "板块名称"))
    frame = apply_sort(frame, BOARD_SORT_COLUMNS[args.sort], args.order)
    frame, meta = page_frame(frame, args.offset, args.limit)
    meta.update(
        {
            "kind": args.kind,
            "query": args.query,
            "sort": args.sort,
            "order": args.order,
        }
    )
    return success("board-snapshot", ak, "东方财富", frame_records(frame), meta)


def board_history(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    validate_range(args.start, args.end)
    if args.kind == "industry":
        period = {"daily": "日k", "weekly": "周k", "monthly": "月k"}[args.period]
        frame = ak.stock_board_industry_hist_em(
            symbol=args.name,
            start_date=args.start,
            end_date=args.end,
            period=period,
            adjust=adjustment(args.adjust),
        )
    else:
        frame = ak.stock_board_concept_hist_em(
            symbol=args.name,
            period=args.period,
            start_date=args.start,
            end_date=args.end,
            adjust=adjustment(args.adjust),
        )
    if not frame.empty:
        require_columns(frame, ("日期", "收盘"), "board-history")
    frame, meta = tail_frame(frame, args.limit)
    meta.update(
        {
            "kind": args.kind,
            "name": args.name,
            "period": args.period,
            "adjust": args.adjust,
            "start": args.start,
            "end": args.end,
        }
    )
    return success("board-history", ak, "东方财富", frame_records(frame), meta)


def board_intraday(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    function = (
        ak.stock_board_industry_hist_min_em
        if args.kind == "industry"
        else ak.stock_board_concept_hist_min_em
    )
    frame = function(symbol=args.name, period=args.period)
    if not frame.empty:
        require_columns(frame, ("日期时间", "收盘"), "board-intraday")
    frame, meta = tail_frame(frame, args.limit)
    meta.update({"kind": args.kind, "name": args.name, "period_minutes": args.period})
    return success("board-intraday", ak, "东方财富", frame_records(frame), meta)


def limit_pool(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    functions = {
        "up": ak.stock_zt_pool_em,
        "down": ak.stock_zt_pool_dtgc_em,
        "broken": ak.stock_zt_pool_zbgc_em,
        "previous": ak.stock_zt_pool_previous_em,
    }
    frame = functions[args.kind](date=args.date)
    if not frame.empty:
        require_columns(frame, ("代码", "名称", "最新价", "涨跌幅"), "limit-pool")
    if args.query and not frame.empty:
        frame = apply_query(frame, args.query, ("代码", "名称", "所属行业"))
    frame, meta = page_frame(frame, args.offset, args.limit)
    meta.update(
        {
            "kind": args.kind,
            "date": args.date,
            "query": args.query,
        }
    )
    return success("limit-pool", ak, "东方财富", frame_records(frame), meta)


def trade_calendar(args: argparse.Namespace, ak: Any) -> dict[str, Any]:
    validate_range(args.start, args.end)
    frame = ak.tool_trade_date_hist_sina()
    require_columns(frame, ("trade_date",), "trade-calendar")
    text_dates = frame["trade_date"].astype(str).str.replace("-", "", regex=False)
    frame = frame[(text_dates >= args.start) & (text_dates <= args.end)]
    frame, meta = page_frame(frame, args.offset, args.limit)
    meta.update({"start": args.start, "end": args.end})
    return success("trade-calendar", ak, "新浪财经", frame_records(frame), meta)


def add_paging(parser: argparse.ArgumentParser, default_limit: int = 20) -> None:
    parser.add_argument("--offset", type=non_negative_int, default=0)
    parser.add_argument(
        "--limit", type=positive_int(MAX_LIST_ROWS), default=default_limit
    )


def add_history_range(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", type=compact_date, default=date_default(90))
    parser.add_argument("--end", type=compact_date, default=date_default(0))
    parser.add_argument("--limit", type=positive_int(MAX_HISTORY_ROWS), default=300)


def add_minute_range(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--start",
        type=minute_datetime,
        default=f"{date_default(7)[:4]}-{date_default(7)[4:6]}-{date_default(7)[6:]} 09:30:00",
    )
    parser.add_argument(
        "--end",
        type=minute_datetime,
        default=f"{date_default(0)[:4]}-{date_default(0)[4:6]}-{date_default(0)[6:]} 15:00:00",
    )
    parser.add_argument("--limit", type=positive_int(MAX_HISTORY_ROWS), default=500)


def add_sort(
    parser: argparse.ArgumentParser,
    choices: dict[str, str],
    default: str,
) -> None:
    parser.add_argument("--sort", choices=tuple(choices), default=default)
    parser.add_argument("--order", choices=SORT_ORDERS, default="desc")


def build_parser() -> argparse.ArgumentParser:
    parser = MarketArgumentParser(
        description="无需 API Key 的沪深京 A 股、指数、ETF 和板块行情查询"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    command = subparsers.add_parser("stock-search", help="按股票代码或名称查询")
    command.add_argument("query", type=non_empty_text)
    command.add_argument("--limit", type=positive_int(100), default=20)
    command.set_defaults(handler=stock_search)

    command = subparsers.add_parser("stock-quote", help="查询一只或多只股票报价")
    command.add_argument(
        "codes", nargs="+", type=stock_code, help="最多 20 个六位股票代码"
    )
    command.set_defaults(handler=stock_quote)

    command = subparsers.add_parser("stock-snapshot", help="查询和排序全市场股票快照")
    command.add_argument("--query", type=non_empty_text)
    add_sort(command, STOCK_SORT_COLUMNS, "change")
    add_paging(command, 20)
    command.set_defaults(handler=stock_snapshot)

    command = subparsers.add_parser("stock-history", help="查询股票日/周/月行情")
    command.add_argument("code", type=stock_code)
    command.add_argument("--period", choices=PERIODS, default="daily")
    command.add_argument("--adjust", choices=ADJUSTMENTS, default="none")
    add_history_range(command)
    command.set_defaults(handler=stock_history)

    command = subparsers.add_parser("stock-intraday", help="查询股票分钟行情")
    command.add_argument("code", type=stock_code)
    command.add_argument("--period", choices=MINUTE_PERIODS, default="5")
    command.add_argument("--adjust", choices=ADJUSTMENTS, default="none")
    add_minute_range(command)
    command.set_defaults(handler=stock_intraday)

    command = subparsers.add_parser("market-overview", help="统计全市场涨跌概况")
    command.set_defaults(handler=market_overview)

    command = subparsers.add_parser("stock-rank", help="查询股票行情排行")
    command.add_argument("--by", choices=tuple(STOCK_SORT_COLUMNS), default="change")
    command.add_argument("--order", choices=SORT_ORDERS, default="desc")
    command.add_argument("--limit", type=positive_int(100), default=20)
    command.set_defaults(handler=stock_rank)

    command = subparsers.add_parser("index-snapshot", help="查询指数行情快照")
    command.add_argument(
        "--series", choices=("all", *INDEX_SERIES), default="important"
    )
    command.add_argument("--query", type=non_empty_text)
    add_sort(command, INDEX_SORT_COLUMNS, "change")
    add_paging(command, 20)
    command.set_defaults(handler=index_snapshot)

    command = subparsers.add_parser("index-history", help="查询指数日/周/月行情")
    command.add_argument("code", type=stock_code)
    command.add_argument("--period", choices=PERIODS, default="daily")
    add_history_range(command)
    command.set_defaults(handler=index_history)

    command = subparsers.add_parser("index-intraday", help="查询指数分钟行情")
    command.add_argument("code", type=stock_code)
    command.add_argument("--period", choices=MINUTE_PERIODS, default="5")
    add_minute_range(command)
    command.set_defaults(handler=index_intraday)

    command = subparsers.add_parser("etf-snapshot", help="查询 ETF 行情快照")
    command.add_argument("--query", type=non_empty_text)
    add_sort(command, ETF_SORT_COLUMNS, "change")
    add_paging(command, 20)
    command.set_defaults(handler=etf_snapshot)

    command = subparsers.add_parser("etf-history", help="查询 ETF 日/周/月行情")
    command.add_argument("code", type=stock_code)
    command.add_argument("--period", choices=PERIODS, default="daily")
    command.add_argument("--adjust", choices=ADJUSTMENTS, default="none")
    add_history_range(command)
    command.set_defaults(handler=etf_history)

    command = subparsers.add_parser("etf-intraday", help="查询 ETF 分钟行情")
    command.add_argument("code", type=stock_code)
    command.add_argument("--period", choices=MINUTE_PERIODS, default="5")
    command.add_argument("--adjust", choices=ADJUSTMENTS, default="none")
    add_minute_range(command)
    command.set_defaults(handler=etf_intraday)

    command = subparsers.add_parser("board-snapshot", help="查询行业或概念板块")
    command.add_argument("--kind", choices=("industry", "concept"), required=True)
    command.add_argument("--query", type=non_empty_text)
    add_sort(command, BOARD_SORT_COLUMNS, "change")
    add_paging(command, 20)
    command.set_defaults(handler=board_snapshot)

    command = subparsers.add_parser("board-history", help="查询板块日/周/月行情")
    command.add_argument("--kind", choices=("industry", "concept"), required=True)
    command.add_argument("name", type=non_empty_text)
    command.add_argument("--period", choices=PERIODS, default="daily")
    command.add_argument("--adjust", choices=ADJUSTMENTS, default="none")
    add_history_range(command)
    command.set_defaults(handler=board_history)

    command = subparsers.add_parser("board-intraday", help="查询板块分钟行情")
    command.add_argument("--kind", choices=("industry", "concept"), required=True)
    command.add_argument("name", type=non_empty_text)
    command.add_argument("--period", choices=MINUTE_PERIODS, default="5")
    command.add_argument("--limit", type=positive_int(MAX_HISTORY_ROWS), default=500)
    command.set_defaults(handler=board_intraday)

    command = subparsers.add_parser(
        "limit-pool", help="查询涨停、跌停、炸板或昨日涨停股池"
    )
    command.add_argument(
        "--kind", choices=("up", "down", "broken", "previous"), required=True
    )
    command.add_argument("--date", type=compact_date, default=date_default(0))
    command.add_argument("--query", type=non_empty_text)
    add_paging(command, 100)
    command.set_defaults(handler=limit_pool)

    command = subparsers.add_parser("trade-calendar", help="查询 A 股交易日")
    command.add_argument("--start", type=compact_date, default=date_default(30))
    command.add_argument("--end", type=compact_date, default=date_default(0))
    add_paging(command, 100)
    command.set_defaults(handler=trade_calendar)
    return parser


def run_with_timeout(handler: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    if not hasattr(signal, "SIGALRM"):
        return handler()

    def timeout(_signum: int, _frame: Any) -> None:
        raise TimeoutError(f"上游查询超过 {DEFAULT_TIMEOUT_SECONDS} 秒")

    previous = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(DEFAULT_TIMEOUT_SECONDS)
    try:
        return handler()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "stock-quote" and len(args.codes) > MAX_QUOTE_CODES:
            raise InputError(f"stock-quote 一次最多查询 {MAX_QUOTE_CODES} 个代码")
        configure_linux_arm_mini_racer()
        import akshare as ak

        payload = run_with_timeout(lambda: args.handler(args, ak))
        emit(payload)
        return 0
    except InputError as exc:
        emit(
            {
                "schema_version": SCHEMA_VERSION,
                "success": False,
                "error": {"code": "invalid_input", "message": str(exc)},
            }
        )
        return 64
    except RuntimeSetupError as exc:
        emit(
            {
                "schema_version": SCHEMA_VERSION,
                "success": False,
                "error": {"code": "runtime_error", "message": str(exc)},
            }
        )
        return 70
    except (DataError, TimeoutError) as exc:
        emit(
            {
                "schema_version": SCHEMA_VERSION,
                "success": False,
                "error": {"code": "data_unavailable", "message": str(exc)},
            }
        )
        return 69
    except Exception as exc:  # noqa: BLE001 - AKShare surfaces many upstream exception types.
        emit(
            {
                "schema_version": SCHEMA_VERSION,
                "success": False,
                "error": {
                    "code": "upstream_error",
                    "message": f"{type(exc).__name__}: {exc}",
                },
            }
        )
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
