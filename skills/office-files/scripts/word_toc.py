"""Create and validate native Word TOC fields."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["python-docx>=1.2.0"]
# ///

from __future__ import annotations

import math
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from lxml import etree

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
TRUE_VALUES = {"1", "on", "true"}


@dataclass(frozen=True)
class NativeTocValidation:
    instructions: tuple[str, ...]
    field_kinds: tuple[str, ...]
    heading_count: int
    update_on_open: bool


@dataclass(frozen=True)
class _ComplexField:
    instruction: str
    has_separator: bool
    dirty: bool


@dataclass
class _OpenField:
    instruction_parts: list[str] = field(default_factory=list)
    has_separator: bool = False
    dirty: bool = False


@dataclass(frozen=True)
class _SimpleField:
    instruction: str
    has_result: bool


def _is_on(value: str | None) -> bool:
    return value is None or value.lower() in TRUE_VALUES


def _is_in_textbox(element) -> bool:
    return any(
        ancestor.tag == qn("w:txbxContent")
        for ancestor in element.iterancestors()
    )


def _normalize_instruction(value: str) -> str:
    return " ".join(value.split())


def _is_toc_instruction(value: str) -> bool:
    return (
        re.match(
            r"^TOC(?:\s|$)",
            _normalize_instruction(value),
            re.IGNORECASE,
        )
        is not None
    )


def _validate_levels(levels: tuple[int, int]) -> tuple[int, int]:
    if (
        not isinstance(levels, tuple)
        or len(levels) != 2
        or any(type(level) is not int for level in levels)
    ):
        raise ValueError("目录级别必须是两个整数，例如 (1, 3)")
    start, end = levels
    if not 1 <= start <= end <= 9:
        raise ValueError("目录级别必须满足 1 <= 起始级别 <= 结束级别 <= 9")
    return start, end


def _parse_complex_fields(root) -> tuple[list[_ComplexField], list[_OpenField], int]:
    completed: list[_ComplexField] = []
    stack: list[_OpenField] = []
    unmatched_ends = 0

    for element in root.iter():
        if _is_in_textbox(element):
            continue
        if element.tag == qn("w:fldChar"):
            field_type = element.get(qn("w:fldCharType"))
            if field_type == "begin":
                dirty_value = element.get(qn("w:dirty"))
                stack.append(
                    _OpenField(
                        dirty=dirty_value is not None and _is_on(dirty_value)
                    )
                )
            elif field_type == "separate" and stack:
                stack[-1].has_separator = True
            elif field_type == "end":
                if not stack:
                    unmatched_ends += 1
                    continue
                current = stack.pop()
                completed.append(
                    _ComplexField(
                        instruction=_normalize_instruction(
                            "".join(current.instruction_parts)
                        ),
                        has_separator=current.has_separator,
                        dirty=current.dirty,
                    )
                )
        elif (
            element.tag == qn("w:instrText")
            and stack
            and not stack[-1].has_separator
        ):
            stack[-1].instruction_parts.append(element.text or "")

    return completed, stack, unmatched_ends


def _toc_fields(root) -> tuple[list[_ComplexField], list[_OpenField], int]:
    completed, open_fields, unmatched_ends = _parse_complex_fields(root)
    toc_fields = [
        complex_field
        for complex_field in completed
        if _is_toc_instruction(complex_field.instruction)
    ]
    open_toc_fields = [
        open_field
        for open_field in open_fields
        if _is_toc_instruction("".join(open_field.instruction_parts))
    ]
    return toc_fields, open_toc_fields, unmatched_ends


def _simple_toc_fields(root) -> tuple[_SimpleField, ...]:
    return tuple(
        _SimpleField(
            instruction=_normalize_instruction(element.get(qn("w:instr")) or ""),
            has_result=any(
                bool((text.text or "").strip())
                for text in element.iter(qn("w:t"))
                if not _is_in_textbox(text)
            ),
        )
        for element in root.iter(qn("w:fldSimple"))
        if not _is_in_textbox(element)
        and _is_toc_instruction(element.get(qn("w:instr")) or "")
    )


def _simple_toc_instructions(root) -> tuple[str, ...]:
    return tuple(field.instruction for field in _simple_toc_fields(root))


def _outline_level_from_properties(properties) -> int | None:
    if properties is None:
        return None
    outline = properties.find(qn("w:outlineLvl"))
    if outline is None:
        return None
    value = outline.get(qn("w:val"))
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"无效的 outline level：{value}") from error


def paragraph_outline_level(paragraph: Paragraph) -> int | None:
    direct = _outline_level_from_properties(paragraph._p.find(qn("w:pPr")))
    if direct is not None:
        return direct

    style = paragraph.style
    seen_style_ids: set[str] = set()
    while style is not None and style.style_id not in seen_style_ids:
        seen_style_ids.add(style.style_id)
        style_level = _outline_level_from_properties(style.element.find(qn("w:pPr")))
        if style_level is not None:
            return style_level
        match = re.fullmatch(r"Heading([1-9])", style.style_id, re.IGNORECASE)
        if match:
            return int(match.group(1)) - 1
        style = style.base_style
    return None


def _is_textbox_paragraph(element) -> bool:
    return _is_in_textbox(element)


def _body_paragraph_elements(body) -> list:
    return [
        element
        for element in body.iter(qn("w:p"))
        if not _is_textbox_paragraph(element)
    ]


def _body_paragraphs(document) -> list[Paragraph]:
    return [
        Paragraph(element, document)
        for element in _body_paragraph_elements(document.element.body)
    ]


def count_toc_headings(document, levels: tuple[int, int] = (1, 3)) -> int:
    start, end = _validate_levels(levels)
    minimum = start - 1
    maximum = end - 1
    return sum(
        1
        for paragraph in _body_paragraphs(document)
        if (level := paragraph_outline_level(paragraph)) is not None
        and minimum <= level <= maximum
        and bool(paragraph.text.strip())
    )


def configure_toc_title(document, paragraph: Paragraph) -> str:
    """Apply a non-collected style to the visible TOC title."""
    if paragraph.part is not document.part:
        raise ValueError("目录标题段落不属于当前文档")
    if not paragraph.text.strip():
        raise ValueError("目录标题不能为空")

    toc_style = next(
        (
            style
            for style in document.styles
            if style.style_id == "TOCHeading" or style.name == "TOC Heading"
        ),
        document.styles["Normal"],
    )
    paragraph.style = toc_style
    properties = paragraph._p.get_or_add_pPr()
    outline = properties.get_or_add_outlineLvl()
    outline.set(qn("w:val"), "9")
    return toc_style.name


def find_native_toc_instructions(document) -> tuple[str, ...]:
    completed, open_fields, _ = _toc_fields(document.element.body)
    instructions = [complex_field.instruction for complex_field in completed]
    instructions.extend(
        _normalize_instruction("".join(open_field.instruction_parts))
        for open_field in open_fields
    )
    instructions.extend(_simple_toc_instructions(document.element.body))
    return tuple(instructions)


def request_field_update_on_open(document) -> None:
    settings = document.settings.element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.insert_element_before(
            update,
            "w:hdrShapeDefaults",
            "w:footnotePr",
            "w:endnotePr",
            "w:compat",
            "w:docVars",
            "w:rsids",
            "m:mathPr",
            "w:attachedSchema",
            "w:themeFontLang",
            "w:clrSchemeMapping",
            "w:doNotIncludeSubdocsInStats",
            "w:doNotAutoCompressPictures",
            "w:forceUpgrade",
            "w:captions",
            "w:readModeInkLockDown",
            "w:smartTagType",
            "sl:schemaLibrary",
            "w:shapeDefaults",
            "w:doNotEmbedSmartTags",
            "w:decimalSymbol",
            "w:listSeparator",
        )
    update.set(qn("w:val"), "true")


def _validate_field_kind(field_kind: str) -> str:
    if field_kind not in {"simple", "complex"}:
        raise ValueError("field_kind 必须是 simple 或 complex")
    return field_kind


def _validate_placeholder_format(font_name: str, size_pt: float) -> int:
    if not font_name.strip():
        raise ValueError("目录占位文字字体不能为空")
    if (
        isinstance(size_pt, bool)
        or not isinstance(size_pt, (int, float))
        or not math.isfinite(size_pt)
        or size_pt <= 0
    ):
        raise ValueError("目录占位文字字号必须是正数")
    half_points = round(size_pt * 2)
    if half_points < 1:
        raise ValueError("目录占位文字字号必须至少为 0.5pt")
    return half_points


def _run_properties(font_name: str, half_points: int) -> object:
    properties = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    for slot in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(slot), font_name)
    properties.append(fonts)

    size = OxmlElement("w:sz")
    size.set(qn("w:val"), str(half_points))
    properties.append(size)
    complex_size = OxmlElement("w:szCs")
    complex_size.set(qn("w:val"), str(half_points))
    properties.append(complex_size)
    return properties


def _run_with_child(child) -> object:
    run = OxmlElement("w:r")
    run.append(child)
    return run


def _formatted_run_with_child(
    child,
    *,
    font_name: str,
    half_points: int,
) -> object:
    run = OxmlElement("w:r")
    run.append(_run_properties(font_name, half_points))
    run.append(child)
    return run


def append_native_toc(
    document,
    paragraph: Paragraph,
    *,
    title_paragraph: Paragraph,
    levels: tuple[int, int] = (1, 3),
    field_kind: str = "simple",
    placeholder: str = "请在 Word/WPS 中更新整个目录",
    placeholder_font: str = "宋体",
    placeholder_size_pt: float = 12,
) -> str:
    """Append a simple or complex native TOC field to an empty paragraph."""
    start, end = _validate_levels(levels)
    field_kind = _validate_field_kind(field_kind)
    half_points = _validate_placeholder_format(
        placeholder_font,
        placeholder_size_pt,
    )
    if paragraph.part is not document.part:
        raise ValueError("目录域段落不属于当前文档")
    if title_paragraph.part is not document.part:
        raise ValueError("目录标题段落不属于当前文档")
    if not title_paragraph.text.strip():
        raise ValueError("目录标题不能为空")
    if title_paragraph._p.getnext() is not paragraph._p:
        raise ValueError("目录标题必须紧邻目录域段落")
    if not placeholder.strip():
        raise ValueError("目录域结果占位文字不能为空")
    if any(child.tag != qn("w:pPr") for child in paragraph._p):
        raise ValueError("目录域必须写入一个空段落")
    field_level = paragraph_outline_level(paragraph)
    if field_level is not None and start - 1 <= field_level <= end - 1:
        raise ValueError("目录域段落使用了会被目录收录的 outline level")
    title_level = paragraph_outline_level(title_paragraph)
    if title_level is not None and start - 1 <= title_level <= end - 1:
        raise ValueError("目录标题使用了会被目录收录的 outline level")

    existing = find_native_toc_instructions(document)
    if existing:
        raise ValueError(f"文档已存在原生 TOC 域：{'；'.join(existing)}")

    heading_count = count_toc_headings(document, levels)
    if heading_count == 0:
        raise ValueError(
            f"文档中没有可收录的 {start}～{end} 级标题，拒绝创建空目录"
        )

    instruction_text = f'TOC \\o "{start}-{end}" \\h \\z \\u'

    result = OxmlElement("w:t")
    result.set(XML_SPACE, "preserve")
    result.text = placeholder

    request_field_update_on_open(document)
    if field_kind == "simple":
        simple = OxmlElement("w:fldSimple")
        simple.set(qn("w:instr"), f" {instruction_text} ")
        simple.set(qn("w:dirty"), "true")
        simple.append(
            _formatted_run_with_child(
                result,
                font_name=placeholder_font,
                half_points=half_points,
            )
        )
        paragraph._p.append(simple)
    else:
        begin = OxmlElement("w:fldChar")
        begin.set(qn("w:fldCharType"), "begin")
        begin.set(qn("w:dirty"), "true")

        instruction = OxmlElement("w:instrText")
        instruction.set(XML_SPACE, "preserve")
        instruction.text = f" {instruction_text} "

        separate = OxmlElement("w:fldChar")
        separate.set(qn("w:fldCharType"), "separate")

        end_field = OxmlElement("w:fldChar")
        end_field.set(qn("w:fldCharType"), "end")
        for child in (begin, instruction, separate):
            paragraph._p.append(_run_with_child(child))
        paragraph._p.append(
            _formatted_run_with_child(
                result,
                font_name=placeholder_font,
                half_points=half_points,
            )
        )
        paragraph._p.append(_run_with_child(end_field))
    return instruction_text


def _settings_request_update(settings_root) -> bool:
    update = settings_root.find(qn("w:updateFields"))
    return update is not None and _is_on(update.get(qn("w:val")))


def _instruction_has_switch(instruction: str, switch: str) -> bool:
    normalized = _normalize_instruction(instruction).upper()
    return (
        re.search(
            rf"(?<!\S){re.escape(switch.upper())}(?:\s|$)",
            normalized,
        )
        is not None
    )


def _instruction_switch_arguments(
    instruction: str,
    switch: str,
) -> tuple[str, ...]:
    normalized = _normalize_instruction(instruction).upper()
    return tuple(
        re.findall(
            rf"(?<!\S){re.escape(switch.upper())}\s+\"([^\"]+)\"(?=\s|$)",
            normalized,
        )
    )


def _validate_toc_instruction(
    instruction: str,
    *,
    start: int,
    end: int,
) -> None:
    expected_level_argument = f"{start}-{end}"
    level_arguments = _instruction_switch_arguments(instruction, "\\O")
    if level_arguments != (expected_level_argument,):
        raise ValueError(
            f"TOC 目录级别错误：期望 {expected_level_argument}，实际 {instruction}"
        )
    missing_switches = [
        switch
        for switch in ("\\H", "\\Z", "\\U")
        if not _instruction_has_switch(instruction, switch)
    ]
    if missing_switches:
        raise ValueError("TOC 缺少开关：" + "、".join(missing_switches))


def _toc_start_paragraph_indices(document_root) -> tuple[int, ...]:
    body = document_root.find(qn("w:body"))
    if body is None:
        raise ValueError("word/document.xml 缺少 w:body")
    indices: list[int] = []
    for index, paragraph in enumerate(_body_paragraph_elements(body)):
        instruction = _normalize_instruction(
            "".join(
                element.text or ""
                for element in paragraph.iter(qn("w:instrText"))
                if not _is_in_textbox(element)
            )
        )
        simple_toc = any(
            not _is_in_textbox(element)
            and _is_toc_instruction(element.get(qn("w:instr")) or "")
            for element in paragraph.iter(qn("w:fldSimple"))
        )
        if _is_toc_instruction(instruction) or simple_toc:
            indices.append(index)
    return tuple(indices)


def validate_native_toc(
    path: str | Path,
    *,
    toc_title: str,
    levels: tuple[int, int] = (1, 3),
    expected_count: int = 1,
    field_kind: str | None = None,
) -> NativeTocValidation:
    """Validate simple or complex native TOC fields in a saved DOCX."""
    start, end = _validate_levels(levels)
    if type(expected_count) is not int or expected_count < 1:
        raise ValueError("expected_count 必须是大于等于 1 的整数")
    if not toc_title.strip():
        raise ValueError("toc_title 不能为空")
    if field_kind is not None:
        field_kind = _validate_field_kind(field_kind)

    document_path = Path(path)
    if not document_path.is_file():
        raise FileNotFoundError(document_path)
    if document_path.suffix.lower() != ".docx":
        raise ValueError(f"输入必须是 .docx：{document_path}")

    with zipfile.ZipFile(document_path) as archive:
        names = set(archive.namelist())
        required_parts = {"word/document.xml", "word/settings.xml"}
        missing_parts = required_parts - names
        if missing_parts:
            raise ValueError(
                "DOCX 缺少目录验证所需部件：" + "、".join(sorted(missing_parts))
            )
        document_root = etree.fromstring(archive.read("word/document.xml"))
        settings_root = etree.fromstring(archive.read("word/settings.xml"))

    toc_fields, open_toc_fields, unmatched_ends = _toc_fields(document_root)
    simple_toc_fields = _simple_toc_fields(document_root)
    if open_toc_fields or unmatched_ends:
        raise ValueError(
            "DOCX 存在未完整配对的复杂域："
            f"未结束 TOC={len(open_toc_fields)}，无起点 end={unmatched_ends}"
        )
    total_count = len(toc_fields) + len(simple_toc_fields)
    if total_count != expected_count:
        raise ValueError(
            f"原生 TOC 数量错误：期望 {expected_count}，实际 {total_count}"
        )
    field_kinds = ("complex",) * len(toc_fields) + ("simple",) * len(simple_toc_fields)
    if field_kind is not None and set(field_kinds) != {field_kind}:
        raise ValueError(
            f"TOC 域类型错误：期望 {field_kind}，实际 {'、'.join(field_kinds)}"
        )

    for toc_field in toc_fields:
        _validate_toc_instruction(
            toc_field.instruction,
            start=start,
            end=end,
        )
        if not toc_field.has_separator:
            raise ValueError("TOC 缺少 separate 域节点")
        if not toc_field.dirty:
            raise ValueError("TOC begin 未设置 w:dirty=true")
    for toc_field in simple_toc_fields:
        _validate_toc_instruction(
            toc_field.instruction,
            start=start,
            end=end,
        )
        if not toc_field.has_result:
            raise ValueError("w:fldSimple TOC 缺少可见结果文字")

    update_on_open = _settings_request_update(settings_root)
    if not update_on_open:
        raise ValueError("word/settings.xml 未设置 w:updateFields=true")

    reopened = docx.Document(str(document_path))
    heading_count = count_toc_headings(reopened, levels)
    if heading_count == 0:
        raise ValueError(f"文档中没有可收录的 {start}～{end} 级标题")

    toc_start_indices = _toc_start_paragraph_indices(document_root)
    if len(toc_start_indices) != expected_count:
        raise ValueError(
            "无法唯一定位 TOC 起始段落："
            f"期望 {expected_count}，实际 {len(toc_start_indices)}"
        )
    paragraphs = _body_paragraphs(reopened)
    minimum = start - 1
    maximum = end - 1
    for toc_index in toc_start_indices:
        if toc_index == 0:
            raise ValueError("TOC 前缺少目录标题段落")
        title_paragraph = paragraphs[toc_index - 1]
        if title_paragraph.text.strip() != toc_title:
            raise ValueError(
                f"TOC 前的标题错误：期望 {toc_title}，"
                f"实际 {title_paragraph.text.strip()}"
            )
        level = paragraph_outline_level(title_paragraph)
        if level is not None and minimum <= level <= maximum:
            raise ValueError("目录标题使用了会被目录收录的 outline level")

    return NativeTocValidation(
        instructions=(
            tuple(toc_field.instruction for toc_field in toc_fields)
            + tuple(toc_field.instruction for toc_field in simple_toc_fields)
        ),
        field_kinds=field_kinds,
        heading_count=heading_count,
        update_on_open=update_on_open,
    )
