#!/usr/bin/env python3

import fcntl
import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASE_PYTHON = Path("/opt/hermes/.venv/bin/python")
RUNTIME_ROOT = Path("/opt/data/.dock")
OCR_VENV = RUNTIME_ROOT / "captcha-ocr-venv"
OCR_PYTHON = OCR_VENV / "bin/python"
RUNTIME_MARKER = OCR_VENV / ".requirements.sha256"
INSTALL_LOCK = RUNTIME_ROOT / "captcha-ocr-install.lock"
SCRIPT_ROOT = Path(__file__).resolve().parent
OCR_SCRIPT = SCRIPT_ROOT / "captcha_ocr.py"
REQUIREMENTS = SCRIPT_ROOT / "requirements.lock"
MODEL = {
    "name": "ddddocr",
    "version": "1.6.1",
    "variant": "beta",
}
RUNTIME_CHECK = (
    'from importlib.metadata import version; '
    'assert version("ddddocr") == "1.6.1"; '
    "import ddddocr; from onnxruntime import InferenceSession"
)


def requirements_digest() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def emit_failure(message: str) -> int:
    print(
        json.dumps(
            {"success": False, "error": message, "model": MODEL},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 3


def runtime_ready() -> bool:
    if not OCR_PYTHON.is_file():
        return False
    try:
        if RUNTIME_MARKER.read_text(encoding="utf-8").strip() != requirements_digest():
            return False
    except OSError:
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

        print("[captcha-ocr] 首次使用，正在下载并安装验证码识别依赖...", file=sys.stderr)
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
        result = subprocess.run(
            [str(OCR_PYTHON), "-c", RUNTIME_CHECK],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("验证码识别依赖安装后校验失败")
        RUNTIME_MARKER.write_text(requirements_digest() + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        return emit_failure("用法：run_ocr.py <本地验证码图片路径>")
    try:
        if not runtime_ready():
            install_runtime()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        return emit_failure(f"验证码识别依赖安装失败：{type(exc).__name__}: {exc}")
    try:
        return subprocess.call([str(OCR_PYTHON), str(OCR_SCRIPT), sys.argv[1]])
    except OSError as exc:
        return emit_failure(f"验证码识别进程启动失败：{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
