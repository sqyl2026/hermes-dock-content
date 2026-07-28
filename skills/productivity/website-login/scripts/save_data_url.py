#!/usr/bin/env python3

import base64
import binascii
import json
import os
import re
import sys
from pathlib import Path

MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_INPUT_SIZE = 12 * 1024 * 1024
DATA_URL_RE = re.compile(
    r"^data:(image/(?:png|jpeg|jpg|gif|webp));base64,([A-Za-z0-9+/=\r\n]+)$",
    re.IGNORECASE,
)
MIME_SUFFIXES = {
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/jpg": {".jpg", ".jpeg"},
    "image/gif": {".gif"},
    "image/webp": {".webp"},
}


def fail(message: str) -> int:
    print(f"验证码图片保存失败：{message}", file=sys.stderr)
    return 2


def extract_data_url(raw: bytes) -> str:
    if len(raw) > MAX_INPUT_SIZE:
        raise ValueError("agent-browser JSON 输出超过 12 MiB")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("agent-browser 输出不是有效 JSON") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("agent-browser eval 未成功")
    data = payload.get("data")
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, str):
        raise ValueError("agent-browser eval 没有返回图片 data URL")
    return result


def validate_output(raw_path: str, mime: str) -> Path:
    if not raw_path:
        raise ValueError("缺少输出图片路径")
    raw_profile_home = os.environ.get("HERMES_DOCK_PROFILE_HOME")
    if not raw_profile_home:
        raise ValueError("缺少 HERMES_DOCK_PROFILE_HOME")

    safe_root = Path(os.environ.get("HERMES_WRITE_SAFE_ROOT", "/opt/data")).resolve(strict=True)
    profile_home = Path(raw_profile_home).resolve(strict=True)
    try:
        profile_home.relative_to(safe_root)
    except ValueError as exc:
        raise ValueError(f"当前 profile 目录必须位于安全根 {safe_root} 内") from exc
    output = Path(raw_path).expanduser()
    if not output.is_absolute():
        raise ValueError("输出图片路径必须是绝对路径")
    parent = output.parent.resolve(strict=True)
    output = parent / output.name
    try:
        output.relative_to(profile_home)
    except ValueError as exc:
        raise ValueError(f"输出图片必须位于当前 profile 目录 {profile_home}") from exc
    if output.suffix.lower() not in MIME_SUFFIXES[mime]:
        allowed = "、".join(sorted(MIME_SUFFIXES[mime]))
        raise ValueError(f"{mime} 图片扩展名必须是 {allowed}")
    if output.exists():
        raise ValueError(f"拒绝覆盖已有文件：{output}")
    return output


def validate_signature(image: bytes, mime: str) -> None:
    valid = {
        "image/png": image.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": image.startswith(b"\xff\xd8\xff"),
        "image/jpg": image.startswith(b"\xff\xd8\xff"),
        "image/gif": image.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": image.startswith(b"RIFF")
        and len(image) >= 12
        and image[8:12] == b"WEBP",
    }
    if not valid[mime]:
        raise ValueError(f"图片内容与声明的 MIME 类型 {mime} 不一致")


def main() -> int:
    if len(sys.argv) != 2:
        return fail("用法：save_data_url.py <输出图片路径>")
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_SIZE + 1)
        data_url = extract_data_url(raw)
        match = DATA_URL_RE.fullmatch(data_url)
        if not match:
            raise ValueError("只接受 PNG、JPEG、GIF 或 WebP 的 base64 data URL")
        mime = match.group(1).lower()
        output = validate_output(sys.argv[1], mime)
        try:
            image = base64.b64decode(match.group(2), validate=True)
        except binascii.Error as exc:
            raise ValueError("图片 base64 无效") from exc
        if not image:
            raise ValueError("图片内容为空")
        if len(image) > MAX_IMAGE_SIZE:
            raise ValueError("图片超过 8 MiB")
        validate_signature(image, mime)
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(image)
        print(output)
        return 0
    except (OSError, ValueError) as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
