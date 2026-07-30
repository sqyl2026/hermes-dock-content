#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


ANSI_ESCAPE = re.compile(r"\x1b(?:[@-_][0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
HTTPS_URL = re.compile(r"https://[^\s<>'\"`\x1b]+")
HOST_HINTS = {
    "cloudflare": ("trycloudflare.com",),
    "cpolar": ("cpolar",),
    "localhost-run": ("localhost.run", "lhr.life"),
    "pinggy": ("pinggy",),
}
MAX_LOG_BYTES = 256 * 1024


def select_url(urls: list[str], provider: str, trusted: bool) -> str | None:
    candidates = []
    for raw_url in urls:
        url = raw_url.rstrip(".,;:)]}")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            continue
        if not trusted:
            hints = HOST_HINTS.get(provider, ())
            if hints and not any(hint in parsed.hostname.lower() for hint in hints):
                continue
        candidates.append(url)
    return candidates[-1] if candidates else None


def urls_from_payload(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []

    urls = payload.get("urls")
    if isinstance(urls, list):
        return [url for url in urls if isinstance(url, str)]

    tunnels = payload.get("tunnels")
    if not isinstance(tunnels, list):
        return []

    result = []
    for tunnel in tunnels:
        if not isinstance(tunnel, dict):
            continue
        public_url = tunnel.get("public_url")
        if isinstance(public_url, str):
            result.append(public_url)
    return result


def read_api(opener, api_url: str) -> list[str]:
    request = Request(api_url, headers={"Accept": "application/json"})
    with opener.open(request, timeout=2) as response:
        return urls_from_payload(json.load(response))


def read_log_urls(paths: list[Path]) -> list[str]:
    urls = []
    for path in paths:
        try:
            with path.open("rb") as log_file:
                log_file.seek(0, 2)
                size = log_file.tell()
                log_file.seek(max(size - MAX_LOG_BYTES, 0))
                text = log_file.read().decode("utf-8", errors="replace")
        except FileNotFoundError:
            continue
        text = ANSI_ESCAPE.sub("", text)
        urls.extend(HTTPS_URL.findall(text))
    return urls


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wait for a public tunnel URL from a local API or captured process logs."
    )
    parser.add_argument(
        "provider",
        choices=["cloudflare", "cpolar", "generic", "localhost-run", "pinggy"],
    )
    parser.add_argument("--api-url")
    parser.add_argument("--log", action="append", default=[], type=Path)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.interval <= 0:
        parser.error("--interval must be greater than zero")
    if not args.api_url and not args.log:
        parser.error("provide --api-url, --log, or both")

    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + args.timeout
    last_api_error = None

    while True:
        if args.api_url:
            try:
                url = select_url(read_api(opener, args.api_url), args.provider, trusted=True)
                if url:
                    print(url)
                    return
                last_api_error = "API returned no HTTPS tunnel URL"
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
                last_api_error = str(error)

        url = select_url(read_log_urls(args.log), args.provider, trusted=False)
        if url:
            print(url)
            return

        if time.monotonic() >= deadline:
            break
        time.sleep(min(args.interval, max(deadline - time.monotonic(), 0)))

    details = f"; last API result: {last_api_error}" if last_api_error else ""
    print(
        f"No public HTTPS URL appeared within {args.timeout:g} seconds{details}",
        file=sys.stderr,
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
