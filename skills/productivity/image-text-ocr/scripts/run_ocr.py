#!/usr/bin/env python3

import fcntl
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
PACKAGE_JSON = SCRIPT_ROOT / "package.json"
PACKAGE_LOCK = SCRIPT_ROOT / "package-lock.json"
PACKAGE_NAME = "@arcships/light-ocr"
MAX_FILE_SIZE = 25 * 1024 * 1024
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png"}


class InputError(Exception):
    pass


def fail(message: str, code: int) -> int:
    print(f"[image-text-ocr] {message}", file=sys.stderr)
    return code


def package_version() -> str:
    with PACKAGE_JSON.open(encoding="utf-8") as package_file:
        package = json.load(package_file)
    version = package.get("dependencies", {}).get(PACKAGE_NAME)
    if not isinstance(version, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise RuntimeError("light-ocr 依赖版本未固定")
    return version


def safe_root() -> Path:
    return Path(os.environ.get("HERMES_WRITE_SAFE_ROOT", "/opt/data")).resolve(strict=True)


def validate_image(raw_path: str, root: Path) -> Path:
    if raw_path.startswith(("http://", "https://", "data:")):
        raise InputError("只支持本地图片路径")
    try:
        image_path = Path(raw_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise InputError(f"图片不存在或无法访问：{raw_path}") from exc
    if not image_path.is_file():
        raise InputError("图片路径不是普通文件")
    try:
        image_path.relative_to(root)
    except ValueError as exc:
        raise InputError(f"图片必须位于 {root} 内") from exc
    if image_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise InputError("只支持 PNG、JPG 和 JPEG 图片")
    if image_path.stat().st_size > MAX_FILE_SIZE:
        raise InputError("图片超过 25 MiB 限制")
    return image_path


def require_command(name: str) -> str:
    command = shutil.which(name)
    if command is None:
        raise RuntimeError(f"未找到 {name}")
    return command


def require_supported_node(node: str) -> None:
    result = subprocess.run(
        [node, "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    version = result.stdout.strip().lstrip("v")
    try:
        major = int(version.split(".", 1)[0])
    except ValueError as exc:
        raise RuntimeError(f"无法识别 Node.js 版本：{version}") from exc
    if major not in {22, 24}:
        raise RuntimeError(f"light-ocr 需要 Node.js 22 或 24，当前为 {version}")


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


def validate_runtime_directory(path: Path, root: Path) -> None:
    if path.is_symlink():
        raise RuntimeError(f"OCR runtime 不能是符号链接：{path}")
    if not path.exists():
        return
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise RuntimeError(f"OCR runtime 不是普通目录：{path}")
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"OCR runtime 必须位于 {root} 内：{path}") from exc


def open_install_lock(path: Path):
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise RuntimeError(f"安装锁不是普通文件：{path}")
    return os.fdopen(descriptor, "a+")


def runtime_ready(runtime: Path, node: str, version: str) -> bool:
    package_path = runtime / "node_modules" / "@arcships" / "light-ocr" / "package.json"
    cli = runtime / "node_modules" / ".bin" / "light-ocr"
    if not package_path.is_file() or not cli.is_file():
        return False
    result = subprocess.run(
        [
            node,
            "-e",
            "const p=require(process.argv[1]); process.exit(p.version===process.argv[2]?0:1)",
            str(package_path),
            version,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return False
    result = subprocess.run(
        [str(cli), "info", "--model-info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def install_runtime(root: Path, node: str, npm: str, version: str) -> Path:
    runtime_root = require_managed_directory(root, ".dock", root)
    runtime_parent = require_managed_directory(runtime_root, "image-text-ocr-runtime", root)
    runtime = runtime_parent / version
    validate_runtime_directory(runtime, root)
    install_lock = runtime_root / "image-text-ocr-install.lock"
    with open_install_lock(install_lock) as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        validate_runtime_directory(runtime, root)
        if runtime_ready(runtime, node, version):
            return runtime

        print(f"[image-text-ocr] 首次使用，正在安装 light-ocr {version}...", file=sys.stderr)
        staging = Path(tempfile.mkdtemp(prefix=f".image-text-ocr-{version}-", dir=runtime_parent))
        try:
            shutil.copy2(PACKAGE_JSON, staging / "package.json")
            shutil.copy2(PACKAGE_LOCK, staging / "package-lock.json")
            subprocess.run(
                [
                    npm,
                    "ci",
                    "--omit=dev",
                    "--include=optional",
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                    "--prefix",
                    str(staging),
                ],
                stdout=sys.stderr,
                stderr=sys.stderr,
                check=True,
            )
            if not runtime_ready(staging, node, version):
                raise RuntimeError("light-ocr 安装后校验失败")
            validate_runtime_directory(staging, root)
            validate_runtime_directory(runtime, root)
            if runtime.exists():
                shutil.rmtree(runtime)
            os.replace(staging, runtime)
        finally:
            if staging.exists():
                validate_runtime_directory(staging, root)
                shutil.rmtree(staging)
        return runtime


def main() -> int:
    if len(sys.argv) != 2:
        return fail("用法：run_ocr.py <本地图片路径>", 64)
    try:
        root = safe_root()
        image_path = validate_image(sys.argv[1], root)
        version = package_version()
        node = require_command("node")
        npm = require_command("npm")
        require_supported_node(node)
        runtime = install_runtime(root, node, npm, version)
        cli = runtime / "node_modules" / ".bin" / "light-ocr"
        return subprocess.call(
            [str(cli), "recognize", str(image_path), "--format", "json", "--schema-version", "1"]
        )
    except InputError as exc:
        return fail(str(exc), 65)
    except (OSError, RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        return fail(f"light-ocr 运行环境准备失败：{type(exc).__name__}: {exc}", 70)


if __name__ == "__main__":
    raise SystemExit(main())
