# 从表格数据生成静态图表图片

用于从 `.xlsx`、CSV 或 TSV 数据生成 PNG 等静态图表图片。先阅读 `excel-common.md` 和 `excel-read.md`，不修改来源文件。

## 数据与图表

1. 先确认工作表、表头、字段类型、单位、日期粒度、空值和重复值，再执行聚合。
2. 根据数据关系选择图表：类别比较用柱状图，时间趋势用折线图，构成关系只在类别较少且总量语义明确时使用饼图。
3. 标题、轴标签、刻度、图例、注释和单位沿用用户语言。中文不得因字体问题翻译成英文、删除或改写。
4. 金额、百分比、计数和日期使用与数据语义一致的格式；不要把相关性写成因果关系，也不要补造缺失数据。
5. 默认输出 PNG；用户未指定尺寸时使用适合聊天查看的横向画布和不低于 150 DPI，避免标签重叠或被裁切。

## 强制中文字体流程

Matplotlib 自带的 DejaVu Sans 不完整覆盖中文，不能把它作为中文图表字体。使用技能自带的 `scripts/cjk_font.py`：

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib", "pandas", "openpyxl", "pillow"]
# ///

import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

PROFILE_HOME = Path(os.environ.get("HERMES_DOCK_PROFILE_HOME", "/opt/data"))
SKILL_SCRIPTS = PROFILE_HOME / "skills" / "office-files" / "scripts"
if not SKILL_SCRIPTS.is_dir():
    raise FileNotFoundError(f"找不到 office-files 技能脚本目录：{SKILL_SCRIPTS}")
sys.path.insert(0, str(SKILL_SCRIPTS))

from cjk_font import configure_matplotlib, save_png_verified

chart_text = "".join([
    "销售合同分析",
    "合同类型",
    "合同数量",
    "签约金额趋势",
    "年月",
    "签约金额（元）",
    # 加入所有动态类别、刻度文本、图例和注释
])
font_properties = configure_matplotlib(chart_text)

import matplotlib.pyplot as plt
```

- 必须在导入 `matplotlib.pyplot` 前选择 `Agg` 后端并调用 `configure_matplotlib()`。
- `chart_text` 必须包含实际会出现在图片中的所有动态中文、符号和单位，不能只用示例文字验证。
- 字体解析器优先使用容器已有且覆盖全部 `chart_text` 的字体；没有时下载并校验固定版本的 Noto Sans CJK SC，缓存到 `/opt/data/.dock/office-files-fonts/`，供后续离线复用。
- `configure_matplotlib()` 会注册字体、设置全局字体族并关闭 Unicode 负号替换。创建标题、轴标签、图例和注释时显式传入返回的 `font_properties`；Seaborn 或样式表会重置 `rcParams` 时，在设置主题后再次调用它。
- 字体下载、哈希校验或字符覆盖检查失败时直接失败并报告缺失字符。不要用英文、拼音、空标签、乱码或方框字继续交付。

## 渲染与验证

明确为文字对象指定字体，并用 `save_png_verified()` 保存：

```python
figure, axes = plt.subplots(figsize=(10, 6))
axes.set_title("销售合同签约金额趋势", fontproperties=font_properties)
axes.set_xlabel("年月", fontproperties=font_properties)
axes.set_ylabel("签约金额（万元）", fontproperties=font_properties)
axes.legend(prop=font_properties)
axes.annotate("最高金额", xy=(2, 160), fontproperties=font_properties)

save_png_verified(
    figure,
    OUTPUT_PATH,
    font_properties=font_properties,
    dpi=180,
)
plt.close(figure)
```

`save_png_verified()` 会把图中已有和自动生成的 `Text` 对象绑定到已校验的字体文件，在同目录临时 PNG 上执行 `canvas.draw()`、布局、保存、缺字告警检查和 Pillow 验证，全部通过后才原子发布到最终路径。它会兼容 `Glyph ... missing from font` 和 `Glyph ... missing from current font` 等告警文案；失败时删除本次临时文件，不留下最终错误图片。不要在调用它之前执行 `canvas.draw()`、`tight_layout()` 或其他会触发文本绘制的操作；布局交给 `bbox_inches="tight"`，确有额外布局需要时扩展该函数的受控绘制范围。

保存后：

1. 使用当前环境可用的图片查看工具实际打开每张图片，检查中文标题、刻度、图例和注释是否可读，是否存在方框、乱码、重叠、裁切或过小文字。
2. 图像查看工具不可用时，明确说明只完成字符覆盖、缺字告警和 PNG 结构验证，不能声称已经完成视觉检查。
3. 视觉检查失败时删除本次生成的错误图片后再修复重跑，不把它作为交付物。
4. 输出路径已存在时失败，不覆盖旧图；成功后报告每张图片的完整路径、图表含义、数据范围和验证结果。

仅仅成功执行 `savefig()`、文件能打开或没有抛出异常，都不足以证明中文正常显示。
