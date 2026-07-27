#!/usr/bin/env python3

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_DIMENSION = 10_000
MODEL_NAMES = {
    "detection": "PP-OCRv6_small_det",
    "recognition": "PP-OCRv6_small_rec",
}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def fail(message: str, code: int = 1) -> int:
    emit({"success": False, "error": message, "model": MODEL_NAMES})
    return code


def validate_image(raw_path: str) -> Path:
    if raw_path.startswith(("http://", "https://", "data:")):
        raise ValueError("只支持本地图片路径")

    image_path = Path(raw_path).expanduser().resolve(strict=True)
    if not image_path.is_file():
        raise ValueError("图片路径不是普通文件")

    safe_root = Path(os.environ.get("HERMES_WRITE_SAFE_ROOT", "/opt/data")).resolve(strict=True)
    try:
        image_path.relative_to(safe_root)
    except ValueError as exc:
        raise ValueError(f"图片必须位于 {safe_root} 内") from exc

    if image_path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError("图片超过 25 MiB 限制")

    from PIL import Image

    with Image.open(image_path) as image:
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError("图片尺寸无效")
        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            raise ValueError("图片单边超过 10000 像素限制")
        if width * height > MAX_PIXELS:
            raise ValueError("图片超过 2500 万像素限制")
        image.verify()

    return image_path


def model_directories() -> tuple[Path, Path]:
    model_root = Path(__file__).resolve().parent.parent / "assets" / "models"
    detection = model_root / "PP-OCRv6_small_det_infer"
    recognition = model_root / "PP-OCRv6_small_rec_infer"
    for model_dir in (detection, recognition):
        for name in ("inference.json", "inference.pdiparams", "inference.yml"):
            if not (model_dir / name).is_file():
                raise FileNotFoundError(f"内置 OCR 模型文件缺失：{model_dir / name}")
    return detection, recognition


def builtin(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def run_ocr(image_path: Path) -> dict[str, Any]:
    detection_dir, recognition_dir = model_directories()

    with contextlib.redirect_stdout(sys.stderr):
        from paddleocr import PaddleOCR

        pipeline = PaddleOCR(
            text_detection_model_name=MODEL_NAMES["detection"],
            text_detection_model_dir=str(detection_dir),
            text_recognition_model_name=MODEL_NAMES["recognition"],
            text_recognition_model_dir=str(recognition_dir),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
        )
        results = list(pipeline.predict(str(image_path)))

    lines: list[dict[str, Any]] = []
    for result in results:
        page = result.json
        data = page.get("res", page)
        texts = data.get("rec_texts", [])
        scores = data.get("rec_scores", [])
        polygons = data.get("rec_polys", [])
        for index, raw_text in enumerate(texts):
            text = str(raw_text).strip()
            if not text:
                continue
            score = float(scores[index]) if index < len(scores) else None
            polygon = builtin(polygons[index]) if index < len(polygons) else None
            lines.append({"text": text, "score": score, "polygon": polygon})

    text = "\n".join(line["text"] for line in lines)
    return {
        "success": True,
        "textFound": bool(lines),
        "text": text,
        "lines": lines,
        "model": MODEL_NAMES,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="使用内置 PP-OCRv6_small 模型识别本地图片文字")
    parser.add_argument("image", help="HERMES_WRITE_SAFE_ROOT 内的本地图片路径")
    args = parser.parse_args()

    try:
        image_path = validate_image(args.image)
        emit(run_ocr(image_path))
        return 0
    except (FileNotFoundError, ValueError) as exc:
        return fail(str(exc), 2)
    except Exception as exc:
        return fail(f"本地 OCR 执行失败：{type(exc).__name__}: {exc}", 3)


if __name__ == "__main__":
    raise SystemExit(main())
