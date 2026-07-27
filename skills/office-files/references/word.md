# Word（python-docx 与 OOXML）

依赖：`python-docx`，Python 中使用 `import docx`。先阅读 `../SKILL.md` 的容器路径、输出、安全和 Word 修改规则。`python-docx` 没有覆盖修订、动态目录等全部 Word 功能；需要时通过它提供的 OOXML 元素操作 WordprocessingML，不要改写整个 ZIP 包。

## 目录

- [基本原则](#基本原则)
- [遍历文档范围](#遍历文档范围)
- [读取正文和修订](#读取正文和修订)
- [直接替换文本](#直接替换文本)
- [新增内容修订](#新增内容修订)
- [处理已有修订](#处理已有修订)
- [局部和全局字体格式](#局部和全局字体格式)
- [生成标准目录](#生成标准目录)
- [局部和全局行间距](#局部和全局行间距)
- [提取图片](#提取图片)
- [创建文档](#创建文档)
- [保存和验证](#保存和验证)
- [能力边界](#能力边界)

示例中的文件名是占位符。用户指定文件时使用准确的容器路径；只有目录或批量任务才使用 `glob()`。每个完整脚本都要包含 `../SKILL.md` 要求的 PEP 723 头、输入检查、拒绝覆盖和 `main()`。

## 基本原则

1. 先检查文档结构、现有修订和目标命中数，再修改副本。
2. 区分直接编辑和修订模式。只有用户要求“修订”“审阅模式”“留痕”或 Track Changes 时才写入修订节点。
3. 不通过给 `paragraph.text` 赋值修改段落；这会删除原有 run、字符格式、超链接、书签和修订结构。
4. 文本跨 run 时建立“可见字符区间 → XML run”的映射，拆分边界 run 后处理。不要把整个段落合并到第一个 run。
5. 没有命中时失败；有多个命中且用户没有明确要求“全部”或第几个时，先询问。
6. 修改已有修订前保留其作者、时间和 ID。不自动接受、拒绝或压平修订。
7. “正文”包含主文档段落和所有层级的嵌套表格；“全文/全局/整个文档”还包含不同的首页、奇数页和偶数页页眉页脚。
8. 文本框、脚注、尾注、批注、公式及嵌入对象不在常规遍历范围内。发现或无法确认时明确报告，不声称已完成全文修改。

常用 OOXML 导入：

```python
from copy import deepcopy
from datetime import datetime, timezone

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
```

## 遍历文档范围

`document.paragraphs` 不包含表格、页眉和页脚。表格单元格内还可能嵌套表格，必须递归遍历：

```python
def iter_table_paragraphs(table):
    for row in table.rows:
        for cell in row.cells:
            yield from cell.paragraphs
            for nested_table in cell.tables:
                yield from iter_table_paragraphs(nested_table)


def iter_story_paragraphs(story):
    yield from story.paragraphs
    for table in story.tables:
        yield from iter_table_paragraphs(table)


def iter_document_stories(document, include_headers_footers: bool):
    yield "正文", document
    if not include_headers_footers:
        return

    seen_parts = set()
    for section_index, section in enumerate(document.sections, start=1):
        stories = (
            ("页眉", section.header),
            ("首页页眉", section.first_page_header),
            ("偶数页页眉", section.even_page_header),
            ("页脚", section.footer),
            ("首页页脚", section.first_page_footer),
            ("偶数页页脚", section.even_page_footer),
        )
        for label, story in stories:
            # _definition 只读取当前节显式引用的 part；不要访问空 story 的
            # paragraphs/_element，否则 python-docx 可能创建新的空页眉或页脚。
            definition = story._definition
            if definition is None:
                continue
            part_key = id(definition)
            if part_key in seen_parts:
                continue
            seen_parts.add(part_key)
            yield f"第 {section_index} 节{label}", story
```

相邻节常链接到同一个页眉或页脚定义；必须按定义对象去重，否则同一内容会被重复修改。检查标题结构时优先读取段落样式：

```python
for paragraph in iter_story_paragraphs(document):
    style_name = paragraph.style.name or ""
    if paragraph.text.strip() and (
        style_name.startswith("Heading") or style_name.startswith("标题")
    ):
        print(f"[{style_name}] {paragraph.text.strip()}")
```

## 读取正文和修订

### 三种读取结果

审阅文档至少区分以下结果：

- 当前视图：包含 `w:ins`、`w:moveTo`，排除 `w:del`、`w:moveFrom`。
- 原始视图：包含 `w:del`、`w:moveFrom`，排除 `w:ins`、`w:moveTo`。
- 修订清单：逐项输出类型、ID、作者、UTC 时间、位置和修订文本。

`paragraph.text` 和 `paragraph.runs` 可能遗漏修订包装器中的内容。使用 XML 顺序提取可见文本：

```python
CURRENT_EXCLUDED = {qn("w:del"), qn("w:moveFrom")}
ORIGINAL_EXCLUDED = {qn("w:ins"), qn("w:moveTo")}
TEXT_TAGS = {qn("w:t"), qn("w:delText")}


def has_ancestor(element, tags) -> bool:
    return any(ancestor.tag in tags for ancestor in element.iterancestors())


def paragraph_text_for_view(paragraph, view: str = "current") -> str:
    if view not in {"current", "original", "all"}:
        raise ValueError(f"未知视图：{view}")

    excluded = set()
    if view == "current":
        excluded = CURRENT_EXCLUDED
    elif view == "original":
        excluded = ORIGINAL_EXCLUDED

    pieces = []
    for element in paragraph._p.iter():
        if excluded and has_ancestor(element, excluded):
            continue
        if element.tag in TEXT_TAGS:
            pieces.append(element.text or "")
        elif element.tag == qn("w:tab"):
            pieces.append("\t")
        elif element.tag in {qn("w:br"), qn("w:cr")}:
            pieces.append("\n")
    return "".join(pieces)
```

### 修订清单

内容和格式修订使用不同节点。不要把批注 `w:commentRangeStart` 当作修订：

```python
REVISION_NAMES = {
    qn("w:ins"): "插入",
    qn("w:del"): "删除",
    qn("w:moveFrom"): "移出",
    qn("w:moveTo"): "移入",
    qn("w:rPrChange"): "字符格式",
    qn("w:pPrChange"): "段落格式",
    qn("w:tblPrChange"): "表格格式",
    qn("w:trPrChange"): "表格行格式",
    qn("w:tcPrChange"): "单元格格式",
}


def revision_text(element) -> str:
    pieces = []
    for child in element.iter():
        if child.tag in TEXT_TAGS:
            pieces.append(child.text or "")
        elif child.tag == qn("w:tab"):
            pieces.append("\t")
        elif child.tag in {qn("w:br"), qn("w:cr")}:
            pieces.append("\n")
    return "".join(pieces)


def revisions_in_paragraph(paragraph):
    for element in paragraph._p.iter():
        kind = REVISION_NAMES.get(element.tag)
        if kind is None:
            continue
        yield {
            "type": kind,
            "id": element.get(qn("w:id")),
            "author": element.get(qn("w:author")),
            "date": element.get(qn("w:date")),
            "text": revision_text(element),
        }
```

输出时为每个 story、段落和表格位置建立稳定标签，例如“正文/P12”“表格2/R3/C1/P1”“第2节首页页眉/P1”。同时输出当前视图和原始视图，避免只给出缺少上下文的修订片段。

## 直接替换文本

普通编辑优先在单个当前可见 run 内替换，以保留该 run 的格式。需要包含超链接或 `w:ins` 内的 run 时，直接遍历 XML：

```python
from docx.text.run import Run


def iter_current_runs(paragraph):
    for run_element in paragraph._p.iter(qn("w:r")):
        if has_ancestor(run_element, CURRENT_EXCLUDED):
            continue
        yield Run(run_element, paragraph)


def is_plain_text_run(run) -> bool:
    allowed = {qn("w:rPr"), qn("w:t")}
    return all(child.tag in allowed for child in run._r)


def replace_in_single_runs(paragraph, old: str, new: str) -> int:
    count = 0
    for run in iter_current_runs(paragraph):
        occurrences = run.text.count(old)
        if occurrences:
            if not is_plain_text_run(run):
                raise ValueError("目标 run 含非纯文本对象，拒绝破坏其结构")
            run.text = run.text.replace(old, new)
            count += occurrences
    return count
```

仅当目标完整位于单个纯文本 run 时使用上例。`run.text = ...` 会重建该 run 的文本、制表符和换行节点；如果 run 同时包含图片、域、脚注引用或其他非文本子节点，先失败并改用精确 XML 拆分。

目标跨 run 时：

1. 按当前视图收集每个文本节点的内容、起止字符偏移、所属 run 和父容器。
2. 在拼接文本中查找目标，确认命中数量。
3. 从最后一个命中倒序处理，避免前面的偏移失效。
4. 在命中起止位置拆分边界 run；复制原 `w:rPr`，保留前缀和后缀。
5. 只替换命中节点；不得移动或删除超链接、书签、域和既有修订包装器。

如果命中跨越不同超链接、修订包装器、书签或域边界，停止并说明无法安全自动替换，除非用户明确接受结构变化。

## 新增内容修订

### 开启修订并生成元数据

添加修订时设置 `w:trackRevisions`，并使用文档内未占用的修订 ID：

```python
REVISION_TAGS = set(REVISION_NAMES)


def enable_track_revisions(document) -> None:
    settings = document.settings.element
    if settings.find(qn("w:trackRevisions")) is None:
        settings.insert(0, OxmlElement("w:trackRevisions"))


def next_revision_id(document) -> int:
    ids = []
    for part in document.part.package.parts:
        root = getattr(part, "element", None)
        if root is None:
            continue
        for element in root.iter():
            if element.tag not in REVISION_TAGS:
                continue
            value = element.get(qn("w:id"))
            if value is not None and value.isdigit():
                ids.append(int(value))
    return max(ids, default=-1) + 1


def revision_attributes(element, revision_id: int, author: str) -> None:
    if not author.strip():
        raise ValueError("修订作者不能为空")
    timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    element.set(qn("w:id"), str(revision_id))
    element.set(qn("w:author"), author.strip())
    element.set(qn("w:date"), timestamp.isoformat().replace("+00:00", "Z"))
```

不要复用已有 ID，不要伪造用户身份。用户没有指定作者时使用清晰的代理名称，例如 `Hermes Agent`，并在交付说明中报告。

### 在单个纯文本 run 中记录替换

Word 内容替换应表现为删除旧文本和插入新文本。删除内容使用 `w:delText`，插入内容使用 `w:t`：

```python
def make_text_run(source_run_element, text: str, deleted: bool = False):
    run_element = OxmlElement("w:r")
    if source_run_element.rPr is not None:
        run_element.append(deepcopy(source_run_element.rPr))

    text_element = OxmlElement("w:delText" if deleted else "w:t")
    if text[:1].isspace() or text[-1:].isspace():
        text_element.set(XML_SPACE, "preserve")
    text_element.text = text
    run_element.append(text_element)
    return run_element


def make_revision(tag: str, run_element, revision_id: int, author: str):
    wrapper = OxmlElement(tag)
    revision_attributes(wrapper, revision_id, author)
    wrapper.append(run_element)
    return wrapper


def replace_run_text_as_revision(run, old: str, new: str, revision_id: int, author: str):
    if run.text.count(old) != 1:
        raise ValueError("目标必须在该 run 中恰好命中一次")
    allowed = {qn("w:rPr"), qn("w:t")}
    if any(child.tag not in allowed for child in run._r):
        raise ValueError("目标 run 含非纯文本对象，拒绝破坏其结构")

    prefix, suffix = run.text.split(old, 1)
    source = run._r
    parent = source.getparent()
    position = parent.index(source)
    nodes = []
    if prefix:
        nodes.append(make_text_run(source, prefix))
    if old:
        nodes.append(make_revision(
            "w:del", make_text_run(source, old, deleted=True), revision_id, author
        ))
        revision_id += 1
    if new:
        nodes.append(make_revision(
            "w:ins", make_text_run(source, new), revision_id, author
        ))
        revision_id += 1
    if suffix:
        nodes.append(make_text_run(source, suffix))

    parent.remove(source)
    for offset, node in enumerate(nodes):
        parent.insert(position + offset, node)
    return revision_id
```

调用前执行 `enable_track_revisions(document)`，初始 ID 使用 `next_revision_id(document)`。跨 run 替换仍按上一节的字符区间映射拆分边界，再把选中的旧内容放入一个或多个 `w:del`，把新内容放入 `w:ins`。不要先合并段落。

### 格式修订

字符格式留痕不是 `w:ins/w:del`。修改前复制旧 `w:rPr`，修改当前格式后把旧属性放入带作者、时间和 ID 的 `w:rPrChange/w:rPr`。段落格式同理使用 `w:pPrChange/w:pPr`。

一个属性容器中已存在 `w:rPrChange` 或 `w:pPrChange` 时，不要覆盖或嵌套新的 change；先让用户决定接受、拒绝还是保留原修订。属性修订中的子 `w:rPr`、`w:pPr` 表示变更前的属性，当前属性保留在外层：

```python
def snapshot_properties(properties, change_tag: str):
    if properties.find(qn(change_tag)) is not None:
        raise ValueError(f"已有 {change_tag}，拒绝覆盖原格式修订")
    return deepcopy(properties)


def append_property_revision(
    properties, previous_properties, change_tag: str, revision_id: int, author: str
) -> None:
    change = OxmlElement(change_tag)
    revision_attributes(change, revision_id, author)
    change.append(previous_properties)
    properties.append(change)


# 字符格式示例：先快照，再修改当前格式，最后挂入旧属性。
rpr = run._r.get_or_add_rPr()
previous_rpr = snapshot_properties(rpr, "w:rPrChange")
run.bold = True
append_property_revision(rpr, previous_rpr, "w:rPrChange", revision_id, author)
```

段落格式把 `rpr` 换成 `paragraph._p.get_or_add_pPr()`，使用 `w:pPrChange`。表格格式分别使用 `w:tblPrChange`、`w:trPrChange` 和 `w:tcPrChange`。

## 处理已有修订

只有用户明确要求时才接受或拒绝修订，并先列出将受影响的修订 ID：

| 修订 | 接受 | 拒绝 |
|---|---|---|
| `w:ins` | 移除包装器，保留内容 | 删除包装器及内容 |
| `w:del` | 删除包装器及内容 | 移除包装器，保留内容，并把 `w:delText` 改回 `w:t` |
| `w:rPrChange` / `w:pPrChange` | 删除旧属性快照 | 用快照恢复外层属性，再删除 change |
| `w:moveFrom` / `w:moveTo` | 按成对移动标记处理 | 按成对移动标记恢复 |

注意：移动修订还可能由 `moveFromRangeStart/End`、`moveToRangeStart/End` 标出范围，不能把单个包装器当成独立插入或删除。遇到移动、编号、表格结构、域或跨 part 修订时，若没有实现对应的成对校验就停止，不做部分接受/拒绝。

拒绝删除修订时还要把 `w:delInstrText` 恢复成 `w:instrText`，并保留 `xml:space`。处理完成后检查目标 ID 已按预期消失，其他修订 ID 和内容保持不变。

## 局部和全局字体格式

### 字体属性

中文字体不能只设置 `run.font.name`。同时设置 Word 的四个字体槽位：

- `w:ascii`：ASCII 字符；
- `w:hAnsi`：高 ANSI/常见西文字符；
- `w:eastAsia`：中文、日文、韩文字符；
- `w:cs`：复杂文字系统。

```python
from docx.enum.text import WD_UNDERLINE
from docx.shared import Pt, RGBColor


def set_run_fonts(run, latin: str, east_asia: str | None = None) -> None:
    east_asia = east_asia or latin
    run.font.name = latin
    rpr = run._r.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:ascii"), latin)
    rfonts.set(qn("w:hAnsi"), latin)
    rfonts.set(qn("w:eastAsia"), east_asia)
    rfonts.set(qn("w:cs"), latin)
    for theme_slot in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rfonts.attrib.pop(qn(theme_slot), None)


def apply_run_format(run) -> None:
    set_run_fonts(run, latin="Arial", east_asia="微软雅黑")
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor.from_string("1F4E79")
    run.bold = True
    run.italic = False
    run.underline = WD_UNDERLINE.SINGLE
    run.font.strike = False
    run.font.superscript = False
    run.font.subscript = False
```

只有用户指定的属性才修改。`False` 表示显式关闭，`None` 表示删除直接格式并继承样式；不能把“未指定”错误地当成 `False`。恢复自动颜色使用 `run.font.color.rgb = None`。高亮使用 `run.font.highlight_color` 和 `WD_COLOR_INDEX`，它与字体颜色不同。

### 局部修改

支持按唯一文本、第几个匹配项、段落位置、标题、样式、表格坐标或页眉页脚定位。对文本范围修改字符格式时：

1. 使用当前视图建立文本节点和字符偏移映射。
2. 确认所有命中及用户要求的匹配项。
3. 拆分命中首尾的 run，复制原 `w:rPr`。
4. 只为完全落在命中范围内的 run 设置格式。
5. 默认包含 `w:ins` 中的当前文本，排除 `w:del`；修改已删除文字需用户明确指定。

如果只对整个 run 修改，可使用 `iter_current_runs()`。不要因为目标只占 run 的一部分而格式化整个 run。

### 样式级全局修改

修改 `Normal`、`Body Text`、`Heading 1` 等样式只影响继承该属性的内容，已有直接格式仍会覆盖样式。更新样式字体时同样设置四个字体槽位：

```python
def set_style_fonts(style, latin: str, east_asia: str | None = None) -> None:
    east_asia = east_asia or latin
    style.font.name = latin
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for slot, value in (
        ("w:ascii", latin),
        ("w:hAnsi", latin),
        ("w:eastAsia", east_asia),
        ("w:cs", latin),
    ):
        rfonts.set(qn(slot), value)
    for theme_slot in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rfonts.attrib.pop(qn(theme_slot), None)
```

### 强制全文统一

用户明确要求“所有现有文字统一格式”时：

1. 修改相关样式，保证后续新增内容继承新格式。
2. 遍历所有选定 story 的当前可见 run，覆盖已有直接格式。
3. 默认不修改删除修订中的文字。
4. 分别统计正文、表格、页眉和页脚的 run 数。
5. 报告文本框、脚注、尾注、批注等未覆盖范围。

如果要求以修订模式记录字体变化，先保存旧 `w:rPr`，再按“格式修订”规则写入 `w:rPrChange`；不能只修改当前格式后声称已经留痕。

## 生成标准目录

标准目录应使用 Word 原生 TOC 域，不能把标题和猜测的页码拼成普通文本。

### 准备标题

- 目录来源段落优先使用内置 `Heading 1`～`Heading 9` 样式。
- 自定义样式只有设置正确 outline level，或 TOC 指令显式包含样式映射时才会进入目录。
- 目录标题“目录”本身不能使用会被目录收录的 Heading 样式。优先使用 `TOC Heading`；不存在时使用不带 outline level 的普通样式并单独设置外观。
- 插入前检查现有 `w:instrText`，发现已有 `TOC` 域时不要重复添加；用户要求替换时必须定位完整的 begin/separate/end 域范围。

### 插入动态 TOC 域

下面的 `paragraph` 是已经放在用户指定位置的空目录段落：

```python
def append_toc_field(paragraph, levels: str = "1-3") -> None:
    if not levels or "-" not in levels:
        raise ValueError("目录级别应类似 1-3")

    begin_run = paragraph.add_run()._r
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin.set(qn("w:dirty"), "true")
    begin_run.append(begin)

    instruction_run = paragraph.add_run()._r
    instruction = OxmlElement("w:instrText")
    instruction.set(XML_SPACE, "preserve")
    instruction.text = f' TOC \\o "{levels}" \\h \\z \\u '
    instruction_run.append(instruction)

    separate_run = paragraph.add_run()._r
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    separate_run.append(separate)

    paragraph.add_run("请在 Word/WPS 中更新目录")

    end_run = paragraph.add_run()._r
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    end_run.append(end)


def request_field_update_on_open(document) -> None:
    settings = document.settings.element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.append(update)
    update.set(qn("w:val"), "true")


def contains_toc(document) -> bool:
    for paragraph in document.element.body.iter(qn("w:p")):
        instruction = "".join(
            element.text or "" for element in paragraph.iter(qn("w:instrText"))
        )
        instruction = " ".join(instruction.split()).upper()
        if instruction == "TOC" or instruction.startswith("TOC "):
            return True
    return False
```

常用指令 `TOC \\o "1-3" \\h \\z \\u` 表示收录 1～3 级标题、生成超链接、在 Web 布局隐藏制表符和页码，并使用段落 outline level。用户指定其他级别时调整 `\\o`。

将目录标题和域插入到封面后、正文前或用户指定锚点。需要分页时显式插入分页符，不要依赖空行。插入后设置 `w:updateFields`，但必须告知用户：`python-docx` 不负责分页，也不能计算真实页码；Word/WPS 是否自动更新域取决于客户端设置，必要时打开文档后选择“更新整个目录”。没有排版引擎刷新前，占位文字不是错误，也不能声称页码已经生成。

## 局部和全局行间距

行距属于段落属性，不能只修改一个字符或 run。按文本定位时，修改命中文本所在的完整段落，并先向用户说明这一点。

### 三种行距语义

```python
from docx.enum.text import WD_LINE_SPACING
from docx.shared import Pt


def set_line_spacing(paragraph, mode: str, value: float) -> None:
    if value <= 0:
        raise ValueError("行距必须大于 0")

    paragraph_format = paragraph.paragraph_format
    if mode == "multiple":
        paragraph_format.line_spacing = float(value)
        paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    elif mode == "exact":
        paragraph_format.line_spacing = Pt(value)
        paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    elif mode == "at-least":
        paragraph_format.line_spacing = Pt(value)
        paragraph_format.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
    else:
        raise ValueError(f"未知行距模式：{mode}")


UNSET = object()


def set_paragraph_spacing(paragraph, before_pt=UNSET, after_pt=UNSET) -> None:
    if before_pt is not UNSET:
        paragraph.paragraph_format.space_before = (
            None if before_pt is None else Pt(before_pt)
        )
    if after_pt is not UNSET:
        paragraph.paragraph_format.space_after = (
            None if after_pt is None else Pt(after_pt)
        )
```

- `multiple`：多倍行距，例如 `1.0`、`1.15`、`1.5`、`2.0`；OOXML 使用 `lineRule="auto"`。
- `exact`：固定磅值，例如固定 24 磅；可能裁切过高的字符或内嵌对象。
- `at-least`：最小磅值，例如至少 18 磅；内容较高时允许增大。
- 段前、段后间距不是行距，分别设置并单独报告。
- 把属性设为 `None` 表示删除直接格式并继承样式，不等于 0 磅。

### 修改范围

- 局部：按唯一文本、段落位置、标题或表格坐标选择完整段落。
- 按样式：修改 `style.paragraph_format`，保留已有直接段落格式。
- 强制正文统一：遍历正文和嵌套表格段落，设置直接段落格式。
- 强制全文统一：额外遍历所有不同的页眉页脚。
- 如果用户只说“全文正文”，默认不要修改目录、标题、题注、页眉页脚；按样式名或 outline level 排除这些段落，并报告范围。

中文模板可能启用文档网格，`w:snapToGrid` 会影响视觉行距。只有用户要求脱离网格，或验证确认网格导致目标行距不生效时，才在段落 `w:pPr` 中写入 `w:snapToGrid w:val="0"`；不要默认关闭整个文档网格。

修订模式下修改行距时，先复制旧 `w:pPr`，再修改当前段落格式并写入 `w:pPrChange`。普通行距修改不要伪造格式修订。

## 提取图片

`.docx` 是 ZIP 包，原始图片位于 `word/media/`。提取文件不表示它们在正文中的出现顺序：

```python
from pathlib import Path
import zipfile

INPUT_PATH = Path("/opt/data/.dock/shared/input.docx")
OUTPUT_DIR = Path("/opt/data/.dock/shared/input_图片")


def extract_images():
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(INPUT_PATH)
    if OUTPUT_DIR.exists():
        raise FileExistsError(f"输出目录已存在：{OUTPUT_DIR}")

    with zipfile.ZipFile(INPUT_PATH) as archive:
        media = sorted(name for name in archive.namelist() if name.startswith("word/media/"))
        if not media:
            raise ValueError("文档中没有可提取的图片")
        OUTPUT_DIR.mkdir(parents=True)
        for name in media:
            (OUTPUT_DIR / Path(name).name).write_bytes(archive.read(name))

    if len(list(OUTPUT_DIR.iterdir())) != len(media):
        raise RuntimeError("图片提取数量校验失败")
```

## 创建文档

创建新文档时先定义标题和正文样式，再添加内容。需要目录时先为章节应用内置 Heading 样式，然后按“生成标准目录”插入 TOC 域：

```python
from pathlib import Path
import docx

OUTPUT_PATH = Path("/opt/data/.dock/shared/项目汇报.docx")


def main():
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"输出文件已存在：{OUTPUT_PATH}")

    document = docx.Document()
    document.add_heading("项目汇报", level=0)
    document.add_heading("一、项目概况", level=1)
    document.add_paragraph("这里是正文第一段。")
    document.add_heading("二、执行情况", level=1)

    table = document.add_table(rows=3, cols=2)
    table.style = "Table Grid"
    rows = [["名称", "数值"], ["事项 A", "100"], ["事项 B", "200"]]
    for row_index, row_data in enumerate(rows):
        for column_index, value in enumerate(row_data):
            table.rows[row_index].cells[column_index].text = value

    document.save(str(OUTPUT_PATH))
```

## 保存和验证

只成功执行 `document.save()` 不代表修改正确。至少执行：

1. 保存到不存在的新路径。
2. 用 `docx.Document(str(OUTPUT_PATH))` 重新打开。
3. 重新统计目标文本、段落、run、表格和标题，确认命中数与计划一致。
4. 对字体读取 `w:rFonts` 四个槽位、字号、颜色和布尔格式；分别验证样式属性与直接格式。
5. 对行距读取 `line_spacing`、`line_spacing_rule`、`space_before` 和 `space_after`。
6. 对修订检查 `word/document.xml` 及涉及的页眉页脚 part，确认目标 `w:id`、作者、时间、`w:ins/w:del` 或属性 change 存在，其他修订未变化。
7. 对目录检查完整的 begin/instrText/separate/end 域结构和 `word/settings.xml` 中的 `w:updateFields`。
8. 验证失败时删除本次新建的不完整输出；保留脚本并报告真实错误。

可以用 ZIP 做只读结构检查：

```python
import zipfile
from lxml import etree


with zipfile.ZipFile(OUTPUT_PATH) as archive:
    document_xml = etree.fromstring(archive.read("word/document.xml"))
    settings_xml = etree.fromstring(archive.read("word/settings.xml"))
```

最终报告输出完整路径、修改模式、实际范围、命中数量、修订作者、未覆盖对象，以及目录是否仍需在 Word/WPS 中更新。视觉版式只有经过 Word/WPS 或兼容排版引擎打开/渲染后才能确认；纯 XML 验证不能证明分页、换行和字体替换后的视觉效果完全正确。

## 能力边界

- `python-docx` 的高层 API 不完整呈现修订、超链接、文本框、脚注、尾注和复杂域；需要时读取 OOXML，但不要对未知结构做猜测性重写。
- 不修改 `.docm`、密码保护、损坏或依赖宏的文件。
- 跨 run 替换必须映射并拆分边界；不使用合并段落内容的降级方案。
- 对移动修订、表格结构修订、编号修订、嵌套域或跨 part 修订，只有实现并验证完整配对语义时才能自动接受或拒绝。
- 字体名称写入 DOCX 不代表运行环境或收件人电脑已安装该字体；字体替换和最终换行取决于打开文档的客户端。
- TOC 域可以由脚本创建，但真实页码和目录结果必须由 Word/WPS 等排版引擎更新。
- 行距是段落级属性；不能承诺同一段落中的局部字符使用不同的行距。
