#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path
from typing import Any

MAX_FILE_SIZE = 8 * 1024 * 1024
MAX_DIMENSION = 4096
MAX_PIXELS = MAX_DIMENSION * MAX_DIMENSION
MODEL = {
    "name": "ddddocr",
    "version": "1.6.1",
    "variant": "beta",
}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def fail(message: str, code: int = 1) -> int:
    emit({"success": False, "error": message, "model": MODEL})
    return code


def validate_image(raw_path: str) -> Path:
    if raw_path.startswith(("http://", "https://", "data:")):
        raise ValueError("只支持本地图片路径")

    image_path = Path(raw_path).expanduser().resolve(strict=True)
    if not image_path.is_file():
        raise ValueError("图片路径不是普通文件")

    raw_profile_home = os.environ.get("HERMES_DOCK_PROFILE_HOME")
    if not raw_profile_home:
        raise ValueError("缺少 HERMES_DOCK_PROFILE_HOME，无法确认当前 profile")
    safe_root = Path(os.environ.get("HERMES_WRITE_SAFE_ROOT", "/opt/data")).resolve(strict=True)
    profile_home = Path(raw_profile_home).resolve(strict=True)
    try:
        profile_home.relative_to(safe_root)
    except ValueError as exc:
        raise ValueError(f"当前 profile 目录必须位于安全根 {safe_root} 内") from exc
    try:
        image_path.relative_to(profile_home)
    except ValueError as exc:
        raise ValueError(f"图片必须位于当前 profile 目录 {profile_home} 内") from exc

    if image_path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError("图片超过 8 MiB 限制")

    from PIL import Image

    with Image.open(image_path) as image:
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError("图片尺寸无效")
        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            raise ValueError("图片单边超过 4096 像素限制")
        if width * height > MAX_PIXELS:
            raise ValueError("图片超过 1677 万像素限制")
        image.verify()

    return image_path


def recognize(image_path: Path) -> dict[str, Any]:
    import ddddocr

    ocr = ddddocr.DdddOcr(
        beta=True,
        show_ad=False,
    )
    text = str(ocr.classification(image_path.read_bytes(), png_fix=True)).strip()
    return {
        "success": True,
        "textFound": bool(text),
        "text": text,
        "model": MODEL,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="使用 ddddocr beta 模型识别简单静态图片验证码")
    parser.add_argument("image", help="HERMES_DOCK_PROFILE_HOME 内的本地验证码图片路径")
    args = parser.parse_args()

    try:
        image_path = validate_image(args.image)
        emit(recognize(image_path))
        return 0
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc), 2)
    except Exception as exc:
        return fail(f"验证码识别失败：{type(exc).__name__}: {exc}", 3)


if __name__ == "__main__":
    raise SystemExit(main())
