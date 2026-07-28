# Word 原生自动目录

用于创建或检查 Word 原生可更新目录。先阅读 `../SKILL.md` 和 `word-common.md`；创建新文档时同时读取 `word-layout.md`，编辑现有文档时同时读取 `word.md`。

## 强制规则

- 用户要求“目录、自动目录、可更新目录、目录页”时，默认生成 Word 原生 `TOC` 域。禁止用普通段落、制表符、点线和猜测页码模拟目录；只有用户明确要求静态文本目录时才生成普通文本。
- 使用技能自带的 `scripts/word_toc.py`，不要临时重写复杂域。
- 已有原生 TOC 时不重复插入。已有静态文本目录时不要静默删除或替换；先确认替换范围。
- 目录标题（如“目录”）不能使用会被目录收录的 Heading 样式。
- `python-docx` 不能分页或计算真实页码。没有 Word/WPS 等排版引擎刷新时，只能承诺已创建原生可更新目录，不能声称页码已生成。

## 标题和插入位置

- 目录来源优先使用内置 `Heading 1`～`Heading 9`。
- 自定义标题样式必须设置正确的 outline level；一级对应 `0`、二级对应 `1`，依次类推。
- 将目录标题和空域段落放在封面后、正文前或用户指定锚点，需要换页时使用分页符；添加完整正文和所有标题后才调用 helper。

## 使用 helper

每个任务脚本仍需包含 PEP 723 依赖、输入检查、拒绝覆盖和 `main()`。通过当前 profile 路径导入：

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["python-docx>=1.2.0"]
# ///

import os
import sys
from pathlib import Path

import docx

PROFILE_HOME = Path(os.environ.get("HERMES_DOCK_PROFILE_HOME", "/opt/data"))
SKILL_SCRIPTS = PROFILE_HOME / "skills" / "office-files" / "scripts"
if not SKILL_SCRIPTS.is_dir():
    raise FileNotFoundError(f"找不到 office-files 技能脚本目录：{SKILL_SCRIPTS}")
sys.path.insert(0, str(SKILL_SCRIPTS))

from word_toc import (
    append_native_toc,
    configure_toc_title,
    validate_native_toc,
)
```

创建新文档时保留目录段落引用，完成正文后再填充原生域：

```python
document = docx.Document()
document.add_heading("项目报告", level=0)

toc_title = document.add_paragraph("目录")
configure_toc_title(document, toc_title)
toc_paragraph = document.add_paragraph()
document.add_page_break()

document.add_heading("一、项目概况", level=1)
document.add_paragraph("正文内容。")
document.add_heading("二、执行情况", level=1)
document.add_heading("2.1 当前进度", level=2)
document.add_paragraph("正文内容。")

append_native_toc(
    document,
    toc_paragraph,
    title_paragraph=toc_title,
    levels=(1, 3),
)
document.save(str(OUTPUT_PATH))

result = validate_native_toc(
    OUTPUT_PATH,
    toc_title="目录",
    levels=(1, 3),
    expected_count=1,
)
```

`append_native_toc()` 会：

- 强制校验紧邻 TOC 的目录标题段落，拒绝会被目录收录的标题或域段落；
- 拒绝非空域段落、无可收录正文标题和已有 TOC；
- 写入完整的 begin/instrText/separate/end 复杂域；
- 使用 `TOC \o "1-3" \h \z \u`；
- 设置 `w:dirty="true"` 和 `w:updateFields="true"`；
- 把“请在 Word/WPS 中更新整个目录”写在域结果区。该文字位于 separate/end 之间，是原生域的当前结果，不是手工目录。

## 验证和交付

保存后必须调用 `validate_native_toc()`。它会重新打开 DOCX 并检查：

- TOC 数量和指定目录级别；
- begin/instrText/separate/end 完整配对；
- dirty 和 updateFields 更新标记；
- 至少有一个可收录标题；
- 目录标题没有落入收录级别，且与调用方传入的标题文本一致。

验证失败时删除本次新建的不完整输出，保留任务脚本并报告真实错误。不要仅凭 `paragraph.text`、文件能打开或看到占位文字判断目录类型。

交付时说明已创建 Word 原生自动目录、是否经过排版引擎更新；未更新时提示用户在 Word/WPS 中选择“更新整个目录”，并明确未经排版引擎时没有验证真实页码、分页和最终目录视觉效果。
