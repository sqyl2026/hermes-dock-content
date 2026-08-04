#!/usr/bin/env python3

import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
DECODE_SCRIPT = SCRIPT_ROOT / "_sherpa_decode.py"
RUNTIME_NAME = "speech-to-text-runtime"
SHERPA_ONNX_VERSION = "1.13.4"
MODEL_VERSION = "2024-07-17"
RUNTIME_VERSION = f"{SHERPA_ONNX_VERSION}-{MODEL_VERSION}"
GITHUB_TARBALL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    f"sherpa-onnx-sense-voice-zh-en-ja-ko-yue-{MODEL_VERSION}.tar.bz2"
)
HF_MIRROR_BASE = (
    f"https://hf-mirror.com/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-{MODEL_VERSION}/resolve/main"
)
MODELSCOPE_BASE = (
    f"https://www.modelscope.cn/models/fengge2024/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-{MODEL_VERSION}/resolve/master"
)
MODEL_FILES = {"model.int8.onnx", "tokens.txt"}
MAX_FILE_SIZE = 25 * 1024 * 1024
SUPPORTED_SUFFIXES = {
    ".wav", ".mp3", ".ogg", ".opus", ".m4a", ".aac", ".flac",
    ".amr", ".silk", ".wma", ".webm",
}


class InputError(Exception):
    pass


def fail(message: str, code: int) -> int:
    print(f"[speech-to-text] {message}", file=sys.stderr)
    return code


def safe_root() -> Path:
    return Path(os.environ.get("HERMES_WRITE_SAFE_ROOT", "/opt/data")).resolve(strict=True)


def validate_audio(raw_path: str, root: Path) -> Path:
    if raw_path.startswith(("http://", "https://", "data:")):
        raise InputError("只支持本地音频路径")
    try:
        audio_path = Path(raw_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise InputError(f"音频不存在或无法访问：{raw_path}") from exc
    if not audio_path.is_file():
        raise InputError("音频路径不是普通文件")
    try:
        audio_path.relative_to(root)
    except ValueError as exc:
        raise InputError(f"音频必须位于 {root} 内") from exc
    if audio_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise InputError("不支持的音频格式，请使用 WAV、MP3、OGG、OPUS、M4A、AAC、FLAC、AMR、SILK、WMA 或 WebM")
    if audio_path.stat().st_size > MAX_FILE_SIZE:
        raise InputError("音频超过 25 MiB 限制")
    return audio_path


def require_command(name: str) -> str:
    command = shutil.which(name)
    if command is None:
        raise RuntimeError(f"未找到 {name}，无法转码音频")
    return command


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
        raise RuntimeError(f"转写 runtime 不能是符号链接：{path}")
    if not path.exists():
        return
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise RuntimeError(f"转写 runtime 不是普通目录：{path}")
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"转写 runtime 必须位于 {root} 内：{path}") from exc


def open_install_lock(path: Path):
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise RuntimeError(f"安装锁不是普通文件：{path}")
    return os.fdopen(descriptor, "a+")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_model_hashes(model_dir: Path) -> None:
    hashes = model_dir / "sha256.txt"
    lines = []
    for name in sorted(MODEL_FILES):
        lines.append(f"{sha256_of(model_dir / name)}  {name}\n")
    hashes.write_text("".join(lines), encoding="utf-8")


def model_files_match(model_dir: Path) -> bool:
    hashes = model_dir / "sha256.txt"
    if not hashes.is_file():
        return False
    try:
        for line in hashes.read_text(encoding="utf-8").splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2:
                return False
            digest, name = parts
            if name not in MODEL_FILES:
                return False
            if not (model_dir / name).is_file():
                return False
            if sha256_of(model_dir / name) != digest:
                return False
    except OSError:
        return False
    return True


def sherpa_onnx_dist_installed(runtime: Path) -> bool:
    site_root = runtime / "venv" / "lib"
    if not site_root.is_dir():
        return False
    for python_dir in site_root.iterdir():
        site_packages = python_dir / "site-packages"
        if not site_packages.is_dir():
            continue
        for package in site_packages.iterdir():
            if package.name == f"sherpa_onnx-{SHERPA_ONNX_VERSION}.dist-info":
                return True
    return False


def runtime_ready(runtime: Path, root: Path) -> bool:
    if runtime.is_symlink() or not runtime.exists():
        return False
    marker = runtime / ".installed"
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != RUNTIME_VERSION:
        return False
    if not sherpa_onnx_dist_installed(runtime):
        return False
    return model_files_match(runtime / "model")


def model_sources() -> list:
    """返回有序的模型下载源，每个元素为 (kind, base)。

    kind 为 "tarball" 时 base 是单个 tar.bz2 包；kind 为 "files" 时 base 是
    分文件目录，逐个下载 model.int8.onnx 与 tokens.txt。可用环境变量覆盖或
    追加：HERMES_ASR_MODEL_URL 指定 tarball 地址，HERMES_ASR_MODEL_MIRROR
    指定分文件镜像目录（中国大陆可指向 hf-mirror 或 ModelScope 镜像）。
    """
    sources = []
    override = os.environ.get("HERMES_ASR_MODEL_URL")
    if override:
        sources.append(("tarball", override))
    mirror = os.environ.get("HERMES_ASR_MODEL_MIRROR")
    if mirror:
        sources.append(("files", mirror))
    sources.append(("tarball", GITHUB_TARBALL_URL))
    sources.append(("files", HF_MIRROR_BASE))
    sources.append(("files", MODELSCOPE_BASE))
    return sources


def download_url(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=300) as response:
        with dest.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)


def download_tarball(model_dir: Path, url: str) -> None:
    tarball = model_dir / "model.tar.bz2"
    try:
        download_url(url, tarball)
        with tarfile.open(tarball, "r:bz2") as archive:
            for member in archive.getmembers():
                if member.name.endswith(tuple(MODEL_FILES)) and member.isfile():
                    source = archive.extractfile(member)
                    with (model_dir / Path(member.name).name).open("wb") as output:
                        shutil.copyfileobj(source, output)
    finally:
        if tarball.exists():
            tarball.unlink()


def download_files(model_dir: Path, base: str) -> None:
    for name in sorted(MODEL_FILES):
        download_url(f"{base}/{name}", model_dir / name)


def download_model(model_dir: Path) -> None:
    for kind, base in model_sources():
        print(
            f"[speech-to-text] 正在从 {base} 下载 SenseVoice {MODEL_VERSION} 模型...",
            file=sys.stderr,
        )
        try:
            if kind == "tarball":
                download_tarball(model_dir, base)
            else:
                download_files(model_dir, base)
            missing = [name for name in MODEL_FILES if not (model_dir / name).is_file()]
            if missing:
                raise RuntimeError(f"模型文件缺失：{', '.join(missing)}")
            return
        except (OSError, RuntimeError, tarfile.TarError, urllib.error.HTTPError, urllib.error.URLError) as exc:
            print(f"[speech-to-text] 从该源下载失败：{exc}", file=sys.stderr)
            for name in MODEL_FILES:
                (model_dir / name).unlink(missing_ok=True)
            (model_dir / "model.tar.bz2").unlink(missing_ok=True)
    raise RuntimeError(
        "所有模型下载源均失败。可设置 HERMES_ASR_MODEL_URL 指向单个 tar.bz2 地址，"
        "或 HERMES_ASR_MODEL_MIRROR 指向分文件镜像目录后重试。"
    )


def install_runtime(root: Path, python: str) -> Path:
    runtime_root = require_managed_directory(root, ".dock", root)
    runtime_parent = require_managed_directory(runtime_root, RUNTIME_NAME, root)
    runtime = runtime_parent / RUNTIME_VERSION
    validate_runtime_directory(runtime, root)
    install_lock = runtime_root / f"{RUNTIME_NAME}-install.lock"
    with open_install_lock(install_lock) as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        validate_runtime_directory(runtime, root)
        if runtime_ready(runtime, root):
            return runtime

        print(
            f"[speech-to-text] 首次使用，正在安装 sherpa-onnx {SHERPA_ONNX_VERSION} 与 SenseVoice {MODEL_VERSION}...",
            file=sys.stderr,
        )
        staging = Path(tempfile.mkdtemp(prefix=f".{RUNTIME_NAME}-{RUNTIME_VERSION}-", dir=runtime_parent))
        try:
            subprocess.run(
                [python, "-m", "venv", str(staging / "venv")],
                check=True,
                stdout=sys.stderr,
                stderr=sys.stderr,
            )
            subprocess.run(
                [
                    str(staging / "venv" / "bin" / "pip"),
                    "install",
                    "--no-input",
                    "--disable-pip-version-check",
                    f"sherpa-onnx=={SHERPA_ONNX_VERSION}",
                ],
                check=True,
                stdout=sys.stderr,
                stderr=sys.stderr,
            )
            model_dir = staging / "model"
            model_dir.mkdir()
            download_model(model_dir)
            write_model_hashes(model_dir)
            (staging / ".installed").write_text(RUNTIME_VERSION + "\n", encoding="utf-8")
            if not runtime_ready(staging, root):
                raise RuntimeError("转写运行时安装后校验失败")
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


def convert_to_wav(ffmpeg: str, audio: Path, root: Path) -> Path:
    tmp_root = require_managed_directory(root, "tmp", root)
    descriptor, tmp_path = tempfile.mkstemp(prefix="speech-to-text-", suffix=".wav", dir=str(tmp_root))
    os.close(descriptor)
    wav_path = Path(tmp_path)
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(audio),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            str(wav_path),
        ],
        check=True,
        stdout=sys.stderr,
        stderr=sys.stderr,
    )
    return wav_path


def run_decode(runtime: Path, wav_path: Path) -> dict:
    result = subprocess.run(
        [str(runtime / "venv" / "bin" / "python"), str(DECODE_SCRIPT), str(wav_path), str(runtime / "model")],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "解码失败"
        raise RuntimeError(f"语音识别失败：{detail}")
    return json.loads(result.stdout)


def main() -> int:
    arguments = [arg for arg in sys.argv[1:] if arg != "--plain"]
    plain = "--plain" in sys.argv[1:]
    if len(arguments) != 1:
        return fail("用法：transcribe.py <本地音频路径> [--plain]", 64)
    wav_path = None
    try:
        root = safe_root()
        audio = validate_audio(arguments[0], root)
        ffmpeg = require_command("ffmpeg")
        runtime = install_runtime(root, sys.executable)
        wav_path = convert_to_wav(ffmpeg, audio, root)
        result = run_decode(runtime, wav_path)
        if plain:
            print(result["text"])
        else:
            print(json.dumps(result, ensure_ascii=False))
        return 0
    except InputError as exc:
        return fail(str(exc), 65)
    except (OSError, RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        return fail(f"语音识别运行环境准备失败：{type(exc).__name__}: {exc}", 70)
    finally:
        if wav_path is not None:
            wav_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
