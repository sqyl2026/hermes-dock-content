"""Resolve and configure a Simplified Chinese font for Matplotlib charts."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib", "pillow"]
# ///

from __future__ import annotations

import hashlib
import http.client
import os
import tempfile
import urllib.error
import urllib.request
import warnings
from pathlib import Path

import matplotlib
from matplotlib import font_manager
from matplotlib.ft2font import FT2Font
from matplotlib.text import Text
from PIL import Image

FONT_NAME = "NotoSansCJKsc-Regular.otf"
FONT_SHA256 = "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
FONT_CACHE_DIR = Path("/opt/data/.dock/office-files-fonts")
FONT_SOURCE = (
    "https://raw.githubusercontent.com/notofonts/noto-cjk/"
    "Sans2.004/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
)
FONT_URLS = (
    "https://gh-proxy.com/" + FONT_SOURCE,
    "https://ghfast.top/" + FONT_SOURCE,
    FONT_SOURCE,
)
MAX_FONT_BYTES = 24 * 1024 * 1024


def _required_codepoints(text: str) -> set[int]:
    return {ord(character) for character in text if not character.isspace()}


def _font_codepoints(path: Path) -> set[int]:
    return set(FT2Font(str(path)).get_charmap())


def _missing_characters(path: Path, text: str) -> list[str]:
    missing = _required_codepoints(text) - _font_codepoints(path)
    return [chr(codepoint) for codepoint in sorted(missing)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _system_font_candidates() -> list[Path]:
    preferred_tokens = (
        "notosanscjksc",
        "notosanssc",
        "sourcehansanssc",
        "sourcehansanscn",
        "wenquanyi",
        "droidsansfallback",
        "simhei",
        "yahei",
        "hiraginosansgb",
        "stheiti",
        "simsun",
    )
    ranked_paths: list[tuple[int, str, Path]] = []
    for path in {Path(path) for path in font_manager.findSystemFonts()}:
        try:
            family_name = FT2Font(str(path)).family_name
        except (OSError, RuntimeError):
            continue
        identity = path.name + family_name
        normalized = "".join(
            character for character in identity.lower() if character.isalnum()
        )
        rank = next(
            (index for index, token in enumerate(preferred_tokens) if token in normalized),
            None,
        )
        if rank is not None:
            ranked_paths.append((rank, str(path), path))
    return [path for _, _, path in sorted(ranked_paths)]


def _download_font(destination: Path) -> None:
    errors: list[str] = []
    destination.parent.mkdir(parents=True, exist_ok=True)

    for url in FONT_URLS:
        temporary_path: Path | None = None
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Hermes-Dock-office-files/1"},
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=destination.parent,
                    prefix=FONT_NAME + ".",
                    suffix=".part",
                    delete=False,
                ) as temporary_file:
                    temporary_path = Path(temporary_file.name)
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_FONT_BYTES:
                            raise RuntimeError(f"字体文件超过 {MAX_FONT_BYTES} 字节限制")
                        temporary_file.write(chunk)

            actual_sha256 = _sha256(temporary_path)
            if actual_sha256 != FONT_SHA256:
                raise RuntimeError(
                    f"字体 SHA-256 不匹配：期望 {FONT_SHA256}，实际 {actual_sha256}"
                )
            os.replace(temporary_path, destination)
            return
        except (
            OSError,
            RuntimeError,
            http.client.HTTPException,
            urllib.error.URLError,
        ) as error:
            errors.append(f"{url}: {error}")
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    raise RuntimeError("无法下载并校验中文字体：" + "；".join(errors))


def resolve_cjk_font(text: str) -> Path:
    """Return a font path that covers every non-whitespace character in text."""
    if not text.strip():
        raise ValueError("必须提供图表中实际使用的文字以检查字体覆盖")

    for candidate in _system_font_candidates():
        try:
            if not _missing_characters(candidate, text):
                return candidate
        except (OSError, RuntimeError):
            continue

    cached_font = FONT_CACHE_DIR / FONT_NAME
    if cached_font.exists():
        actual_sha256 = _sha256(cached_font)
        if actual_sha256 != FONT_SHA256:
            raise RuntimeError(
                f"缓存字体校验失败：{cached_font}，"
                f"期望 {FONT_SHA256}，实际 {actual_sha256}"
            )
        missing = _missing_characters(cached_font, text)
        if missing:
            raise RuntimeError(f"缓存中文字体缺少字符：{''.join(missing)}")
        return cached_font

    _download_font(cached_font)
    missing = _missing_characters(cached_font, text)
    if missing:
        raise RuntimeError(f"下载的中文字体缺少字符：{''.join(missing)}")
    return cached_font


def configure_matplotlib(text: str) -> font_manager.FontProperties:
    """Configure Matplotlib and return explicit properties for chart text."""
    font_path = resolve_cjk_font(text)
    font_manager.fontManager.addfont(str(font_path))
    properties = font_manager.FontProperties(fname=str(font_path))
    matplotlib.rcParams["font.family"] = [properties.get_name()]
    matplotlib.rcParams["axes.unicode_minus"] = False
    return properties


def _is_missing_glyph_warning(message: object) -> bool:
    normalized = str(message).lower()
    return all(token in normalized for token in ("glyph", "missing", "font"))


def _bind_font_file(figure: matplotlib.figure.Figure, font_path: str) -> None:
    for text in figure.findobj(match=Text):
        properties = text.get_fontproperties().copy()
        properties.set_file(font_path)
        text.set_fontproperties(properties)


def _verify_png(path: Path) -> None:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if image.format != "PNG" or image.width < 1 or image.height < 1:
            raise RuntimeError(f"PNG 结构或尺寸无效：{path}")
        extrema = image.convert("RGB").getextrema()
        if all(minimum == maximum for minimum, maximum in extrema):
            raise RuntimeError(f"PNG 画面为空或只有单一颜色：{path}")


def save_png_verified(
    figure: matplotlib.figure.Figure,
    output_path: str | Path,
    *,
    font_properties: font_manager.FontProperties,
    dpi: int = 180,
) -> Path:
    """Render, validate, and atomically publish a PNG without missing glyphs."""
    destination = Path(output_path)
    if destination.suffix.lower() != ".png":
        raise ValueError(f"输出必须使用 .png 扩展名：{destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"输出目录不存在：{destination.parent}")
    if destination.exists():
        raise FileExistsError(f"输出文件已存在：{destination}")

    font_path = font_properties.get_file()
    if not font_path:
        raise ValueError("font_properties 必须绑定到已校验的字体文件")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=destination.stem + ".",
            suffix=".tmp.png",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        _bind_font_file(figure, font_path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            figure.canvas.draw()
            figure.savefig(
                temporary_path,
                dpi=dpi,
                bbox_inches="tight",
                facecolor="white",
            )
        missing_glyph_warnings = [
            str(item.message) for item in caught if _is_missing_glyph_warning(item.message)
        ]
        if missing_glyph_warnings:
            raise RuntimeError("图表字体缺字：" + "；".join(missing_glyph_warnings))

        _verify_png(temporary_path)
        temporary_path.chmod(0o644)
        os.link(temporary_path, destination)
        return destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
