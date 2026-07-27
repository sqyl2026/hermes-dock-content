#!/usr/bin/env python3

import fcntl
import json
import subprocess
import sys
from pathlib import Path

BASE_PYTHON = Path("/opt/hermes/.venv/bin/python")
RUNTIME_ROOT = Path("/opt/data/.dock")
OCR_VENV = RUNTIME_ROOT / "image-text-ocr-venv"
OCR_PYTHON = OCR_VENV / "bin/python"
INSTALL_LOCK = RUNTIME_ROOT / "image-text-ocr-install.lock"
SCRIPT_ROOT = Path(__file__).resolve().parent
OCR_SCRIPT = SCRIPT_ROOT / "ocr_image.py"
REQUIREMENTS = SCRIPT_ROOT / "requirements.lock"
MODEL_NAMES = {
    "detection": "PP-OCRv6_small_det",
    "recognition": "PP-OCRv6_small_rec",
}
RUNTIME_CHECK = (
    'from importlib.metadata import version; '
    'assert version("paddleocr") == "3.7.0"; '
    'assert version("paddlepaddle") == "3.1.1"; '
    'assert version("paddlex") == "3.7.2"; '
    'import paddle; from paddleocr import PaddleOCR'
)


def emit_failure(message: str) -> int:
    print(
        json.dumps(
            {"success": False, "error": message, "model": MODEL_NAMES},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 3


def runtime_ready() -> bool:
    if not OCR_PYTHON.is_file():
        return False
    result = subprocess.run(
        [str(OCR_PYTHON), "-c", RUNTIME_CHECK],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def install_runtime() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    with INSTALL_LOCK.open("a+") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        if runtime_ready():
            return

        print("[image-text-ocr] 首次使用，正在下载并安装 OCR 运行依赖...", file=sys.stderr)
        subprocess.run(
            ["uv", "venv", "--clear", "--python", str(BASE_PYTHON), str(OCR_VENV)],
            stdout=sys.stderr,
            check=True,
        )
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--require-hashes",
                "--no-deps",
                "--only-binary",
                ":all:",
                "--python",
                str(OCR_PYTHON),
                "--requirements",
                str(REQUIREMENTS),
            ],
            stdout=sys.stderr,
            check=True,
        )
        if not runtime_ready():
            raise RuntimeError("OCR 运行依赖安装后校验失败")


def main() -> int:
    if len(sys.argv) != 2:
        return emit_failure("用法：run_ocr.py <本地图片路径>")
    try:
        if not runtime_ready():
            install_runtime()
        return subprocess.call([str(OCR_PYTHON), str(OCR_SCRIPT), sys.argv[1]])
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        return emit_failure(f"OCR 运行依赖安装失败：{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
