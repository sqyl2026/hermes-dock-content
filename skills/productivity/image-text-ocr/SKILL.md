---
name: image-text-ocr
description: Extract visible text from local PNG and JPEG screenshots, photos, and image attachments with an on-demand local light-ocr runtime. Use for explicit image-to-text requests and as a local OCR fallback when image auto-analysis or vision_analyze fails but the user's request can be completed from the image text alone. Do not use as a substitute for object, person, scene, color, chart, or other visual-semantic understanding.
---

# Image Text OCR

Use light-ocr to extract text locally without sending the image to an external service. The first run installs the version-locked OCR runtime and model from npm; later runs work offline with the persistent local installation.

## Run OCR

Pass one local image under the current profile directory:

```bash
/opt/hermes/.venv/bin/python \
  skills/productivity/image-text-ocr/scripts/run_ocr.py \
  /opt/data/path/to/image.png
```

For a non-default profile, run the same relative `skills/...` script from that profile's working directory and pass an image path inside that profile directory.

Always use `run_ocr.py`; do not invoke `light-ocr` directly or install packages with an ad hoc command. If the managed runtime is missing or invalid, the wrapper installs the locked npm dependency under `/opt/data/.dock/image-text-ocr-runtime/0.5.5`, verifies it, and then runs OCR. Preserve stderr so installation and OCR failures remain visible.

Check the exit code before parsing stdout. Exit code `0` prints light-ocr schema version 1 JSON. Read recognized lines from `pages[].lines[]`; each line contains `text`, `confidence`, and `box`. An empty `lines` array is a valid image with no recognized text. On a non-zero exit, read stderr and do not invent results.

## Vision Fallback

Use OCR after image auto-analysis or `vision_analyze` explicitly fails only when reading visible text can satisfy the request. Do not retry the same failed vision call before using OCR.

Tell the user that local OCR was used because vision failed. OCR output supports claims about visible text only. Do not infer objects, people, actions, colors, layout meaning, chart trends, or other visual facts from OCR text.

If the request still needs visual understanding after OCR, return the extracted text if useful and explain which visual parts remain unavailable.

## Input Limits

- Accept one local PNG, JPG, or JPEG image.
- Reject URLs, PDFs, directories, files outside `HERMES_WRITE_SAFE_ROOT`, and files larger than 25 MiB.
- Keep the line order returned by light-ocr and preserve confidence scores and boxes.
- Allow npm access only when `run_ocr.py` needs to install or repair its managed runtime. Image recognition itself must remain offline.

The managed runtime uses `@arcships/light-ocr` 0.5.5, which bundles PP-OCRv6 Small and is distributed under Apache License 2.0. Do not add model files or `node_modules` to this skill.
