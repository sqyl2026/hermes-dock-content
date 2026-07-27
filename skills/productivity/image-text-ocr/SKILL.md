---
name: image-text-ocr
description: Extract visible text from local screenshots, photos, and image attachments with bundled PP-OCRv6_small models and an on-demand local PaddleOCR runtime. Use for explicit image-to-text requests and as a local OCR fallback when image auto-analysis or vision_analyze fails but the user's request can be completed from the image text alone. Do not use as a substitute for object, person, scene, color, chart, or other visual-semantic understanding.
---

# Image Text OCR

Use the bundled local models to extract text without sending the image to an external service or downloading model files. The first run downloads hash-locked Python dependencies; later runs reuse the persistent local environment.

## Run OCR

Pass one local image under the current profile directory:

```bash
/opt/hermes/.venv/bin/python \
  skills/productivity/image-text-ocr/scripts/run_ocr.py \
  /opt/data/path/to/image.png
```

For a non-default profile, run the same relative `skills/...` script from that profile's working directory and pass an image path inside that profile directory.

Always use `run_ocr.py`; do not invoke `ocr_image.py` directly or install packages with an ad hoc command. If the managed OCR environment is missing, the wrapper creates it under `/opt/data/.dock/image-text-ocr-venv`, installs the pinned binary wheels, verifies the runtime, and then runs OCR. Preserve its stderr so dependency download or installation failures remain visible.

The script prints one JSON object containing:

- `success`: whether OCR completed.
- `textFound`: whether any non-empty text was recognized.
- `text`: recognized lines joined with newlines.
- `lines`: recognized text, confidence score, and polygon for each line.
- `model`: the bundled detection and recognition model names.

Treat `success: true` with `textFound: false` as a valid image with no recognized text. Treat `success: false` as an actual failure and report its `error` without inventing results.

## Vision Fallback

Use OCR after image auto-analysis or `vision_analyze` explicitly fails only when reading visible text can satisfy the request. Do not retry the same failed vision call before using OCR.

Tell the user that local OCR was used because vision failed. OCR output supports claims about visible text only. Do not infer objects, people, actions, colors, layout meaning, chart trends, or other visual facts from OCR text.

If the request still needs visual understanding after OCR, return the extracted text if useful and explain which visual parts remain unavailable.

## Input Limits

- Accept one local raster image readable by Pillow.
- Reject URLs, PDFs, directories, files outside `HERMES_WRITE_SAFE_ROOT`, files larger than 25 MiB, images larger than 25 million pixels, and images with either dimension above 10,000 pixels.
- Keep the original line order returned by PaddleOCR and preserve per-line confidence scores.
- Never download model files. Python dependencies may be downloaded only through `run_ocr.py` when its managed environment is missing or invalid.

## Bundled Models

Use only these local assets:

- `assets/models/PP-OCRv6_small_det_infer`
- `assets/models/PP-OCRv6_small_rec_infer`

The models come from the official PaddleOCR 3.7.0 release and are distributed under Apache License 2.0. The upstream archives are:

- `https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv6_small_det_infer.tar`
- `https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv6_small_rec_infer.tar`

The archive SHA-256 values are `bfb7c1e59f0faa6b540ebdca93aea3f4b1f2477805b389fbee117820d68fe9f5` for detection and `da460f968ce9f88325ac3a34fa302077d6e9b0dcefb16ba3137cd7796f879d06` for recognition. Keep the bundled `LICENSE` file with the skill.
