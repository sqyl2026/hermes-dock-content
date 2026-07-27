---
name: agnes-ai-media
description: Generate and edit images or videos with Agnes AI. Use when the user asks for Agnes AI media generation, text-to-image, image-to-image, multi-image composition, text-to-video, image-to-video, keyframe video, or wants an Agent to call Agnes image/video APIs directly.
---

# Agnes AI Media

Use Agnes AI for image and video generation through `AGNES_API_KEY`.

Default endpoints:

- Images: `POST https://apihub.agnes-ai.com/v1/images/generations`
- Videos: `POST https://apihub.agnes-ai.com/v1/videos`
- Video result: `GET https://apihub.agnes-ai.com/agnesapi?video_id=<VIDEO_ID>`

Use `scripts/agnes_media.py` for actual requests. It uses only Python standard library.

## Setup

Require an Agnes API key:

```bash
export AGNES_API_KEY="sk-..."
```

Do not print or save real API keys. If `AGNES_API_KEY` is absent, stop and ask the user to configure it.

## Workflow

1. Decide the task type:
   - Text-to-image: no input image.
   - Image-to-image: one input image URL or Data URI.
   - Multi-image composition: multiple input image URLs or Data URIs.
   - Text-to-video: no input image.
   - Image-to-video: one input image URL.
   - Keyframe video: multiple image URLs, `--mode keyframes`.
2. Choose a model:
   - Image default: `agnes-image-2.1-flash`.
   - Use `agnes-image-2.0-flash` when the user wants faster general generation or multi-image composition.
   - Video default: `agnes-video-v2.0`.
3. Write a concrete prompt. For edits, state both what to change and what to preserve.
4. Run the helper script and save outputs into a task-specific directory, e.g. `outputs/agnes-media`.
5. Return the local file path or final URL plus the important request IDs. Do not expose the API key.

## Image Commands

Text-to-image, URL output:

```bash
uv run --no-project python scripts/agnes_media.py image \
  --prompt "A clean product photo of a glass cube on a white studio background, soft shadows, high detail" \
  --size 1024x768 \
  --download-dir outputs/agnes-media
```

Text-to-image, Base64 output:

```bash
uv run --no-project python scripts/agnes_media.py image \
  --prompt "A luminous floating city above a misty canyon at sunrise, cinematic realism" \
  --size 1024x768 \
  --response-format b64_json \
  --download-dir outputs/agnes-media
```

Image-to-image:

```bash
uv run --no-project python scripts/agnes_media.py image \
  --prompt "Transform this image into a rain-soaked cyberpunk night while preserving the original composition" \
  --image "https://example.com/input-image.png" \
  --size 1024x768 \
  --download-dir outputs/agnes-media
```

Multi-image composition:

```bash
uv run --no-project python scripts/agnes_media.py image \
  --model agnes-image-2.0-flash \
  --prompt "Combine the two characters into a cinematic fantasy battle scene" \
  --image "https://example.com/character-1.png" \
  --image "https://example.com/character-2.png" \
  --size 1024x768 \
  --download-dir outputs/agnes-media
```

Important image rules:

- Put input images in `extra_body.image`; do not use top-level `image`.
- Put `response_format` in `extra_body.response_format`; do not put it at the request root.
- Do not send `tags: ["img2img"]`.
- Use public HTTPS image URLs when possible. If the image cannot be public, use a Data URI.
- For text-to-image Base64 output, `return_base64: true` is accepted. The helper sets the correct fields.

## Video Commands

Text-to-video:

```bash
uv run --no-project python scripts/agnes_media.py video \
  --prompt "A cinematic shot of a cat walking on the beach at sunset, soft ocean waves, warm golden lighting, realistic motion" \
  --width 1152 \
  --height 768 \
  --num-frames 121 \
  --frame-rate 24 \
  --wait \
  --download-dir outputs/agnes-media
```

Image-to-video:

```bash
uv run --no-project python scripts/agnes_media.py video \
  --prompt "The woman slowly turns around and looks back at the camera, natural facial expression, cinematic camera movement" \
  --image "https://example.com/image.png" \
  --num-frames 121 \
  --frame-rate 24 \
  --wait \
  --download-dir outputs/agnes-media
```

Keyframe video:

```bash
uv run --no-project python scripts/agnes_media.py video \
  --prompt "Generate a smooth cinematic transition between the keyframes, maintaining visual consistency and natural camera movement" \
  --image "https://example.com/keyframe1.png" \
  --image "https://example.com/keyframe2.png" \
  --mode keyframes \
  --num-frames 121 \
  --frame-rate 24 \
  --wait \
  --download-dir outputs/agnes-media
```

Poll an existing video:

```bash
uv run --no-project python scripts/agnes_media.py poll-video \
  --video-id "video_..." \
  --download-dir outputs/agnes-media
```

Important video rules:

- `num_frames` must be `<= 441` and follow `8n + 1`; use 81, 121, 241, or 441 unless the user specifies otherwise.
- Duration is `num_frames / frame_rate`.
- Common settings:
  - About 3 seconds: `num_frames=81`, `frame_rate=24`
  - About 5 seconds: `num_frames=121`, `frame_rate=24`
  - About 10 seconds: `num_frames=241`, `frame_rate=24`
  - About 18 seconds: `num_frames=441`, `frame_rate=24`
- Use `width=1152`, `height=768`, `num_frames=121`, `frame_rate=24` for standard landscape text-to-video.
- Use `negative_prompt` when the user names things to avoid.
- Use `--mode keyframes` only for multiple keyframe images.
- Completed video URLs are returned in `remixed_from_video_id`.

## Prompting

Image prompt structure:

```text
[subject] + [scene/background] + [style] + [lighting] + [composition] + [quality requirements]
```

Image edit prompt structure:

```text
[edit instruction] + [new style/scene] + [elements to add/remove] + [elements to preserve]
```

Video prompt structure:

```text
[subject] + [action over time] + [camera movement] + [scene] + [lighting] + [motion style]
```

Avoid vague prompts like "make it better". Convert user intent into a concrete visual brief before calling the API.
