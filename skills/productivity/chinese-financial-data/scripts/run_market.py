import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = 1
BASE_PYTHON = Path("/opt/hermes/.venv/bin/python")
SCRIPT_ROOT = Path(__file__).resolve().parent
MARKET_SCRIPT = SCRIPT_ROOT / "a_share_market.py"
MARKET_LOCK = SCRIPT_ROOT / "a_share_market.py.lock"


def emit_failure(message: str) -> int:
    print(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "success": False,
                "error": {"code": "runtime_error", "message": message},
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 70


def safe_root() -> Path:
    raw_root = os.environ.get("HERMES_WRITE_SAFE_ROOT", "/opt/data")
    return Path(raw_root).resolve(strict=True)


def require_managed_directory(parent: Path, name: str, root: Path) -> Path:
    path = parent / name
    if path.is_symlink():
        raise RuntimeError(f"运行目录不能是符号链接：{path}")
    path.mkdir(mode=0o755, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError(f"运行目录不能是符号链接：{path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise RuntimeError(f"运行目录不是普通目录：{path}")
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"运行目录必须位于 {root} 内：{path}") from exc
    return resolved


def runtime_environment(root: Path) -> dict[str, str]:
    dock = require_managed_directory(root, ".dock", root)
    cache = require_managed_directory(dock, "chinese-financial-data-uv-cache", root)
    environment = os.environ.copy()
    environment["UV_CACHE_DIR"] = str(cache)
    return environment


def require_runtime_files() -> None:
    if not MARKET_SCRIPT.is_file() or MARKET_SCRIPT.is_symlink():
        raise RuntimeError(f"行情脚本缺失或不是普通文件：{MARKET_SCRIPT}")
    if not MARKET_LOCK.is_file() or MARKET_LOCK.is_symlink():
        raise RuntimeError(f"行情依赖锁文件缺失或不是普通文件：{MARKET_LOCK}")
    if not BASE_PYTHON.is_file():
        raise RuntimeError(f"Hermes Python 不存在：{BASE_PYTHON}")


def emit_child_payload(output: str, return_code: int) -> int:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"行情进程退出码 {return_code}，但没有返回有效 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise TypeError(f"行情进程退出码 {return_code}，返回值不是 JSON 对象")
    if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(
        payload.get("success"), bool
    ):
        raise ValueError(f"行情进程退出码 {return_code}，返回契约无效")
    if (return_code == 0) != payload["success"]:
        raise ValueError(f"行情进程退出码 {return_code} 与返回结果不一致")
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    )
    return return_code


def main() -> int:
    try:
        require_runtime_files()
        uv = shutil.which("uv")
        if uv is None:
            raise RuntimeError("未找到 uv")
        environment = runtime_environment(safe_root())
        command = [
            uv,
            "run",
            "--frozen",
            "--no-project",
            "--python",
            str(BASE_PYTHON),
            "--script",
            str(MARKET_SCRIPT),
            *sys.argv[1:],
        ]
        result = subprocess.run(
            command,
            env=environment,
            stdout=subprocess.PIPE,
            text=True,
            check=False,
        )
        return emit_child_payload(result.stdout, result.returncode)
    except (OSError, RuntimeError, UnicodeError, TypeError, ValueError) as exc:
        return emit_failure(f"行情运行环境准备失败：{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
