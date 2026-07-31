import importlib.util
import io
import json
import math
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = (
    REPOSITORY_ROOT / "skills" / "productivity" / "chinese-financial-data" / "scripts"
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MARKET = load_module("a_share_market", SCRIPT_ROOT / "a_share_market.py")
WRAPPER = load_module("run_market", SCRIPT_ROOT / "run_market.py")


class ChineseFinancialDataTests(unittest.TestCase):
    def test_parser_covers_production_commands(self):
        parser = MARKET.build_parser()
        cases = {
            "stock-search": ["stock-search", "贵州茅台"],
            "stock-quote": ["stock-quote", "600519", "000001"],
            "stock-snapshot": ["stock-snapshot", "--sort", "amount"],
            "stock-history": ["stock-history", "600519", "--adjust", "qfq"],
            "stock-intraday": ["stock-intraday", "600519", "--period", "5"],
            "market-overview": ["market-overview"],
            "stock-rank": ["stock-rank", "--by", "turnover"],
            "index-snapshot": ["index-snapshot", "--series", "all"],
            "index-history": ["index-history", "000300"],
            "index-intraday": ["index-intraday", "000300"],
            "etf-snapshot": ["etf-snapshot", "--query", "沪深300"],
            "etf-history": ["etf-history", "510300"],
            "etf-intraday": ["etf-intraday", "510300"],
            "board-snapshot": [
                "board-snapshot",
                "--kind",
                "industry",
            ],
            "board-history": [
                "board-history",
                "--kind",
                "concept",
                "机器人执行器",
            ],
            "board-intraday": [
                "board-intraday",
                "--kind",
                "industry",
                "半导体",
            ],
            "limit-pool": ["limit-pool", "--kind", "up"],
            "trade-calendar": ["trade-calendar"],
        }
        for expected, argv in cases.items():
            with self.subTest(command=expected):
                self.assertEqual(parser.parse_args(argv).command, expected)

    def test_parser_rejects_invalid_code_date_limit_and_choice(self):
        parser = MARKET.build_parser()
        cases = [
            ["stock-quote", "SH600519"],
            ["stock-quote", "６００５１９"],
            ["stock-history", "600519", "--start", "2026-01-01"],
            ["stock-rank", "--limit", "101"],
            ["board-snapshot", "--kind", "theme"],
            ["stock-search", "   "],
            ["board-history", "--kind", "industry", "   "],
        ]
        for argv in cases:
            with self.subTest(argv=argv), self.assertRaises(MARKET.InputError):
                parser.parse_args(argv)

    def test_main_returns_json_for_invalid_input(self):
        output = io.StringIO()
        codes = ["600519"] * (MARKET.MAX_QUOTE_CODES + 1)
        with mock.patch("sys.stdout", output):
            return_code = MARKET.main(["stock-quote", *codes])
        self.assertEqual(return_code, 64)
        self.assertIn('"success":false', output.getvalue())
        self.assertIn('"code":"invalid_input"', output.getvalue())

    def test_validate_range_rejects_reversed_ranges(self):
        with self.assertRaisesRegex(MARKET.InputError, "开始时间"):
            MARKET.validate_range("20260731", "20260701")
        with self.assertRaisesRegex(MARKET.InputError, "开始时间"):
            MARKET.validate_range("2026-07-31 15:00:00", "2026-07-31 09:30:00")

    def test_normalize_value_produces_strict_json_values(self):
        self.assertIsNone(MARKET.normalize_value(float("nan")))
        self.assertIsNone(MARKET.normalize_value(float("inf")))
        na_type = type("NAType", (), {})
        nat_type = type("NaTType", (datetime,), {})
        self.assertIsNone(MARKET.normalize_value(na_type()))
        self.assertIsNone(MARKET.normalize_value(nat_type(2026, 7, 31)))
        self.assertEqual(MARKET.normalize_value(1.25), 1.25)
        timestamp = datetime(2026, 7, 31, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(
            MARKET.normalize_value(timestamp),
            "2026-07-31T15:00:00+08:00",
        )

        class Scalar:
            def item(self):
                return 7

        self.assertEqual(MARKET.normalize_value(Scalar()), 7)
        self.assertTrue(math.isfinite(MARKET.normalize_value(3.5)))

    def test_success_contract_includes_source_and_fetch_time(self):
        akshare = SimpleNamespace(__version__="1.18.81")
        payload = MARKET.success(
            "stock-history",
            akshare,
            "东方财富",
            [{"代码": "600519"}],
            {"truncated": False},
        )
        self.assertEqual(payload["schema_version"], 1)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["source"]["library_version"], "1.18.81")
        self.assertEqual(payload["source"]["upstream"], "东方财富")
        self.assertEqual(payload["meta"]["truncated"], False)
        self.assertEqual(payload["data"][0]["代码"], "600519")
        self.assertTrue(payload["fetched_at"].endswith("+08:00"))

    def test_linux_arm_uses_akracer_native_library(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            package = Path(temporary_directory)
            module_file = package / "py_mini_racer.py"
            extension = package / "armlibmini_racer.glibc.so"
            module_file.write_text("", encoding="utf-8")
            extension.write_bytes(b"native")
            mini_racer = SimpleNamespace(
                __file__=str(module_file),
                EXTENSION_NAME="libmini_racer.glibc.so",
                EXTENSION_PATH=str(package / "libmini_racer.glibc.so"),
            )
            with (
                mock.patch.object(MARKET.sys, "platform", "linux"),
                mock.patch.object(MARKET.platform, "machine", return_value="aarch64"),
            ):
                MARKET.configure_linux_arm_mini_racer(mini_racer)
            self.assertEqual(mini_racer.EXTENSION_NAME, extension.name)
            self.assertEqual(mini_racer.EXTENSION_PATH, str(extension))

    def test_linux_arm_requires_akracer_native_library(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            module_file = Path(temporary_directory) / "py_mini_racer.py"
            module_file.write_text("", encoding="utf-8")
            mini_racer = SimpleNamespace(__file__=str(module_file))
            with (
                mock.patch.object(MARKET.sys, "platform", "linux"),
                mock.patch.object(MARKET.platform, "machine", return_value="aarch64"),
                self.assertRaisesRegex(MARKET.RuntimeSetupError, "运行库缺失"),
            ):
                MARKET.configure_linux_arm_mini_racer(mini_racer)

    def test_catalog_rejects_wrong_asset_code(self):
        class Frame:
            columns = ("代码", "名称")

            @staticmethod
            def to_dict(orient):
                self.assertEqual(orient, "records")
                return [{"代码": "510300", "名称": "沪深300ETF"}]

        self.assertEqual(
            MARKET.catalog_name(Frame(), "510300", "代码", "名称", "ETF"),
            "沪深300ETF",
        )
        with self.assertRaisesRegex(MARKET.InputError, "未找到属于“ETF”的代码"):
            MARKET.catalog_name(Frame(), "600519", "代码", "名称", "ETF")

    def test_index_catalog_uses_eastmoney_series_for_new_indices(self):
        class Frame:
            columns = ("代码", "名称")

            def __init__(self, records):
                self.records = records

            def to_dict(self, orient):
                if orient != "records":
                    raise AssertionError(f"unexpected orient: {orient}")
                return self.records

        class FakeAK:
            @staticmethod
            def stock_zh_index_spot_em(symbol):
                if symbol == MARKET.INDEX_SERIES["important"]:
                    return Frame(
                        [
                            {"代码": "899050", "名称": "北证50"},
                            {"代码": "932000", "名称": "中证2000"},
                        ]
                    )
                return Frame([])

        self.assertEqual(MARKET.index_name(FakeAK(), "899050"), "北证50")
        self.assertEqual(MARKET.index_name(FakeAK(), "932000"), "中证2000")

    def test_wrapper_uses_persistent_cache_and_frozen_script_lock(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            base_python = root / "python"
            market_script = root / "market.py"
            market_lock = root / "market.py.lock"
            for path in (base_python, market_script, market_lock):
                path.write_text("", encoding="utf-8")

            with (
                mock.patch.object(WRAPPER, "BASE_PYTHON", base_python),
                mock.patch.object(WRAPPER, "MARKET_SCRIPT", market_script),
                mock.patch.object(WRAPPER, "MARKET_LOCK", market_lock),
                mock.patch.object(WRAPPER, "safe_root", return_value=root),
                mock.patch.object(WRAPPER.shutil, "which", return_value="/usr/bin/uv"),
                mock.patch.object(
                    WRAPPER.subprocess,
                    "run",
                    return_value=SimpleNamespace(
                        returncode=0,
                        stdout='{"schema_version":1,"success":true}',
                    ),
                ) as run,
                mock.patch.object(sys, "argv", ["run_market.py", "market-overview"]),
                mock.patch("sys.stdout", io.StringIO()),
            ):
                self.assertEqual(WRAPPER.main(), 0)

            command = run.call_args.args[0]
            self.assertEqual(
                command,
                [
                    "/usr/bin/uv",
                    "run",
                    "--frozen",
                    "--no-project",
                    "--python",
                    str(base_python),
                    "--script",
                    str(market_script),
                    "market-overview",
                ],
            )
            environment = run.call_args.kwargs["env"]
            self.assertEqual(
                environment["UV_CACHE_DIR"],
                str(root / ".dock" / "chinese-financial-data-uv-cache"),
            )
            self.assertEqual(run.call_args.kwargs["stdout"], WRAPPER.subprocess.PIPE)
            self.assertTrue(run.call_args.kwargs["text"])

    def test_wrapper_emits_runtime_json_when_uv_has_no_stdout(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            base_python = root / "python"
            market_script = root / "market.py"
            market_lock = root / "market.py.lock"
            for path in (base_python, market_script, market_lock):
                path.write_text("", encoding="utf-8")
            output = io.StringIO()
            with (
                mock.patch.object(WRAPPER, "BASE_PYTHON", base_python),
                mock.patch.object(WRAPPER, "MARKET_SCRIPT", market_script),
                mock.patch.object(WRAPPER, "MARKET_LOCK", market_lock),
                mock.patch.object(WRAPPER, "safe_root", return_value=root),
                mock.patch.object(WRAPPER.shutil, "which", return_value="/usr/bin/uv"),
                mock.patch.object(
                    WRAPPER.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=2, stdout=""),
                ),
                mock.patch.object(sys, "argv", ["run_market.py", "trade-calendar"]),
                mock.patch("sys.stdout", output),
            ):
                self.assertEqual(WRAPPER.main(), 70)
            payload = json.loads(output.getvalue())
            self.assertFalse(payload["success"])
            self.assertEqual(payload["error"]["code"], "runtime_error")

    def test_wrapper_preserves_structured_business_failure(self):
        output = io.StringIO()
        child_output = json.dumps(
            {
                "schema_version": 1,
                "success": False,
                "error": {"code": "invalid_input", "message": "代码错误"},
            }
        )
        with mock.patch("sys.stdout", output):
            self.assertEqual(WRAPPER.emit_child_payload(child_output, 64), 64)
        self.assertEqual(
            json.loads(output.getvalue())["error"]["code"], "invalid_input"
        )

    def test_wrapper_rejects_symlinked_cache_parent(self):
        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            tempfile.TemporaryDirectory() as outside_directory,
        ):
            root = Path(temporary_directory).resolve()
            outside = Path(outside_directory).resolve()
            (root / ".dock").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "符号链接"):
                WRAPPER.runtime_environment(root)
            self.assertEqual(list(outside.iterdir()), [])

    def test_lock_pins_akshare_and_tencent_index(self):
        lock = (SCRIPT_ROOT / "a_share_market.py.lock").read_text(encoding="utf-8")
        self.assertIn('name = "akshare"', lock)
        self.assertIn('version = "1.18.81"', lock)
        self.assertIn("https://mirrors.cloud.tencent.com/pypi/simple/", lock)
        self.assertNotIn("https://pypi.org/simple", lock)


if __name__ == "__main__":
    unittest.main()
