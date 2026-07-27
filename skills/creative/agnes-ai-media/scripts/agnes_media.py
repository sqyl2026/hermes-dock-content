#!/usr/bin/env python3
"""Agnes AI image/video helper.

Uses only Python standard library. Reads AGNES_API_KEY from the environment
unless --api-key is provided.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


API_BASE = "https://apihub.agnes-ai.com"
IMAGE_MODEL = "agnes-image-2.1-flash"
VIDEO_MODEL = "agnes-video-v2.0"


class AgnesError(RuntimeError):
    pass


def api_key(args: argparse.Namespace) -> str:
    key = (args.api_key or os.environ.get("AGNES_API_KEY") or "").strip()
    if not key:
        raise AgnesError("AGNES_API_KEY is not set")
    return key


def request_json(method: str, url: str, key: str, payload: dict[str, Any] | None = None, timeout: int = 120) -> dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AgnesError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise AgnesError(f"request failed: {exc.reason}") from exc
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise AgnesError("response is not valid JSON") from exc


def download(url: str, output_dir: Path, fallback_name: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    parsed = urllib.parse.urlparse(url)
    name = Path(parsed.path).name or fallback_name
    if "." not in name:
        ext = mimetypes.guess_extension(mimetypes.guess_type(url)[0] or "") or ""
        name = fallback_name + ext
    path = unique_path(output_dir / name)
    with urllib.request.urlopen(url, timeout=300) as resp:
        path.write_bytes(resp.read())
    return path


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise AgnesError(f"could not allocate unique output path for {path}")


def write_base64_image(data: str, output_dir: Path, name: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    if "," in data and data.strip().startswith("data:"):
        data = data.split(",", 1)[1]
    path = unique_path(output_dir / name)
    path.write_bytes(base64.b64decode(data))
    return path


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def image_command(args: argparse.Namespace) -> None:
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
    }
    extra_body: dict[str, Any] = {}
    if args.image:
        extra_body["image"] = args.image
    if args.response_format and (args.response_format == "url" or args.image):
        extra_body["response_format"] = args.response_format
    if extra_body:
        payload["extra_body"] = extra_body
    if args.response_format == "b64_json" and not args.image:
        payload["return_base64"] = True

    result = request_json("POST", f"{API_BASE}/v1/images/generations", api_key(args), payload, timeout=args.timeout)
    outputs: list[str] = []
    if args.download_dir:
        output_dir = Path(args.download_dir)
        for index, item in enumerate(result.get("data") or []):
            if item.get("url"):
                outputs.append(str(download(item["url"], output_dir, f"agnes-image-{index + 1}.png")))
            if item.get("b64_json"):
                outputs.append(str(write_base64_image(item["b64_json"], output_dir, f"agnes-image-{index + 1}.png")))
    print_json({"request": redact_payload(payload), "response": result, "outputs": outputs})


def validate_video_frames(num_frames: int) -> None:
    if num_frames > 441:
        raise AgnesError("num_frames must be <= 441")
    if (num_frames - 1) % 8 != 0:
        raise AgnesError("num_frames must follow 8n + 1, e.g. 81, 121, 241, 441")


def video_command(args: argparse.Namespace) -> None:
    validate_video_frames(args.num_frames)
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": args.prompt,
        "num_frames": args.num_frames,
        "frame_rate": args.frame_rate,
    }
    if args.width:
        payload["width"] = args.width
    if args.height:
        payload["height"] = args.height
    if args.seed is not None:
        payload["seed"] = args.seed
    if args.negative_prompt:
        payload["negative_prompt"] = args.negative_prompt

    if args.image:
        if len(args.image) == 1 and args.mode != "keyframes":
            payload["image"] = args.image[0]
        else:
            extra_body = {"image": args.image}
            if args.mode:
                extra_body["mode"] = args.mode
            payload["extra_body"] = extra_body

    result = request_json("POST", f"{API_BASE}/v1/videos", api_key(args), payload, timeout=args.timeout)
    final = None
    outputs: list[str] = []
    if args.wait:
        video_id = result.get("video_id") or result.get("id") or result.get("task_id")
        if not video_id:
            raise AgnesError("create response did not include video_id/task_id")
        final = wait_for_video(args, video_id)
        outputs = collect_video_output(final, args.download_dir)
    print_json({"request": redact_payload(payload), "response": result, "final": final, "outputs": outputs})


def poll_video_command(args: argparse.Namespace) -> None:
    result = wait_for_video(args, args.video_id) if args.wait else get_video_result(args, args.video_id)
    outputs = collect_video_output(result, args.download_dir)
    print_json({"response": result, "outputs": outputs})


def get_video_result(args: argparse.Namespace, video_id: str) -> dict[str, Any]:
    query = {"video_id": video_id}
    if args.model:
        query["model_name"] = args.model
    url = f"{API_BASE}/agnesapi?{urllib.parse.urlencode(query)}"
    return request_json("GET", url, api_key(args), timeout=args.timeout)


def wait_for_video(args: argparse.Namespace, video_id: str) -> dict[str, Any]:
    deadline = time.time() + args.max_wait
    while True:
        result = get_video_result(args, video_id)
        status = str(result.get("status") or "").lower()
        if status in {"completed", "failed"}:
            if status == "failed":
                raise AgnesError(f"video generation failed: {json.dumps(result, ensure_ascii=False)}")
            return result
        if time.time() >= deadline:
            raise AgnesError(f"timed out waiting for video {video_id}; last status: {status or 'unknown'}")
        time.sleep(args.poll_interval)


def collect_video_output(result: dict[str, Any], download_dir: str | None) -> list[str]:
    url = result.get("remixed_from_video_id")
    if not url or not download_dir:
        return []
    return [str(download(str(url), Path(download_dir), "agnes-video.mp4"))]


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call Agnes AI media APIs")
    parser.add_argument("--api-key", default="", help="Agnes API key. Defaults to AGNES_API_KEY.")
    parser.add_argument("--timeout", type=int, default=120)
    sub = parser.add_subparsers(dest="command", required=True)

    image = sub.add_parser("image", help="Generate or edit images")
    image.add_argument("--api-key", default="")
    image.add_argument("--timeout", type=int, default=120)
    image.add_argument("--model", default=IMAGE_MODEL)
    image.add_argument("--prompt", required=True)
    image.add_argument("--size", default="1024x768")
    image.add_argument("--image", action="append", default=[], help="Input image URL or Data URI. Repeat for multiple images.")
    image.add_argument("--response-format", choices=["url", "b64_json"], default="url")
    image.add_argument("--download-dir", default="")
    image.set_defaults(func=image_command)

    video = sub.add_parser("video", help="Create a video task")
    video.add_argument("--api-key", default="")
    video.add_argument("--timeout", type=int, default=120)
    video.add_argument("--model", default=VIDEO_MODEL)
    video.add_argument("--prompt", required=True)
    video.add_argument("--image", action="append", default=[], help="Input image URL. Repeat for keyframes.")
    video.add_argument("--mode", choices=["keyframes"], default="")
    video.add_argument("--width", type=int, default=0)
    video.add_argument("--height", type=int, default=0)
    video.add_argument("--num-frames", type=int, default=121)
    video.add_argument("--frame-rate", type=int, default=24)
    video.add_argument("--negative-prompt", default="")
    video.add_argument("--seed", type=int)
    video.add_argument("--wait", action="store_true")
    video.add_argument("--poll-interval", type=int, default=10)
    video.add_argument("--max-wait", type=int, default=1800)
    video.add_argument("--download-dir", default="")
    video.set_defaults(func=video_command)

    poll = sub.add_parser("poll-video", help="Poll a video task")
    poll.add_argument("--api-key", default="")
    poll.add_argument("--timeout", type=int, default=120)
    poll.add_argument("--model", default=VIDEO_MODEL)
    poll.add_argument("--video-id", required=True)
    poll.add_argument("--wait", action="store_true")
    poll.add_argument("--poll-interval", type=int, default=10)
    poll.add_argument("--max-wait", type=int, default=1800)
    poll.add_argument("--download-dir", default="")
    poll.set_defaults(func=poll_video_command)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except AgnesError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
