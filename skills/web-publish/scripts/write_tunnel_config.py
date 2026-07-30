#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


PROVIDERS = {
    "cpolar": ("CPOLAR_AUTHTOKEN", ".yml"),
    "natapp": ("NATAPP_AUTHTOKEN", ".ini"),
}


def profile_tmp() -> Path:
    raw_home = os.environ.get("HERMES_DOCK_PROFILE_HOME", "").strip()
    if not raw_home:
        raise ValueError("HERMES_DOCK_PROFILE_HOME is not configured")

    profile_home = Path(raw_home)
    if not profile_home.is_absolute():
        raise ValueError("HERMES_DOCK_PROFILE_HOME must be an absolute path")
    profile_home = profile_home.resolve(strict=True)
    if not profile_home.is_dir():
        raise ValueError("HERMES_DOCK_PROFILE_HOME must be a directory")

    tmp_dir = profile_home / "tmp"
    if tmp_dir.is_symlink():
        raise ValueError("profile tmp directory must not be a symlink")
    tmp_dir.mkdir(mode=0o700, parents=False, exist_ok=True)
    return tmp_dir


def read_token(variable: str, token_stdin: bool) -> str:
    if token_stdin:
        token = sys.stdin.readline().strip()
        source = "standard input"
    else:
        token = os.environ.get(variable, "").strip()
        source = variable
    if not token:
        raise ValueError(f"token from {source} is empty")
    if len(token) > 4096 or "\n" in token or "\r" in token:
        raise ValueError(f"token from {source} has an invalid value")
    return token


def render(provider: str, token: str, config_path: str, web_port: int) -> str:
    client_log_path = f"{config_path}.client.log"
    if provider == "cpolar":
        return "\n".join(
            [
                f"authtoken: {json.dumps(token)}",
                "region: cn",
                "console_ui: true",
                "console_ui_color: transparent",
                "inspect_db_size: -1",
                f"log: {json.dumps(client_log_path)}",
                "log_level: info",
                "log_format: logfmt",
                "update: false",
                f"web_addr: 127.0.0.1:{web_port}",
                "",
            ]
        )
    return "\n".join(
        [
            "[default]",
            f"authtoken={token}",
            f"log={client_log_path}",
            "loglevel=ERROR",
            "http_proxy=",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a temporary tunnel client config without printing its token."
    )
    parser.add_argument("provider", choices=sorted(PROVIDERS))
    parser.add_argument(
        "--token-stdin",
        action="store_true",
        help="Read one service-token line from standard input instead of the profile environment.",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=4040,
        help="Local cpolar Web UI/API port. Defaults to 4040.",
    )
    args = parser.parse_args()
    if not 1 <= args.web_port <= 65535:
        parser.error("--web-port must be between 1 and 65535")

    variable, suffix = PROVIDERS[args.provider]
    token = read_token(variable, args.token_stdin)
    tmp_dir = profile_tmp()
    file_descriptor, path = tempfile.mkstemp(
        prefix=f"web-publish-{args.provider}-",
        suffix=suffix,
        dir=tmp_dir,
        text=True,
    )
    os.fchmod(file_descriptor, 0o600)
    with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as config:
        config.write(render(args.provider, token, path, args.web_port))
    print(path)


if __name__ == "__main__":
    main()
