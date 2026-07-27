# Excel 和 CSV（openpyxl / pandas）

先阅读 `../SKILL.md` 的容器路径、输出和安全规则。

- 使用 `openpyxl` 精确读取或修改普通单元格、样式和公式。
- 使用 `pandas` 分析表格数据、创建新的结果表以及转换 CSV/XLSX。
- 不使用 pandas 覆盖原工作簿；它不会保留原有样式、公式和高级对象。

## 目录

- [检查工作簿](#检查工作簿)
- [修改单元格](#修改单元格)
- [写入公式](#写入公式)
- [创建工作簿](#创建工作簿)
- [使用 pandas 分析](#使用-pandas-分析)
- [XLSX 转 CSV](#xlsx-转-csv)
- [CSV 转 XLSX](#csv-转-xlsx)
- [能力边界](#能力边界)

示例中的输入文件名只是占位符。用户指定了文件时，使用其在容器内的准确路径；只有批量任务才使用 `glob()`。

## 检查工作簿

读取展示值时使用 `data_only=True`。如果 Excel 没有保存过公式缓存，公式单元格可能返回 `None`；需要检查公式本身时改用 `data_only=False`。

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["openpyxl"]
# ///
from pathlib import Path
import openpyxl

INPUT_PATH = Path("/opt/data/.dock/shared/input.xlsx")
MAX_ROWS = 20


def value_to_text(value) -> str:
    return "" if value is None else str(value)


def main():
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(INPUT_PATH)

    workbook = openpyxl.load_workbook(INPUT_PATH, data_only=True, read_only=True)
    try:
        print(f"文件：{INPUT_PATH}")
        print(f"工作表：{workbook.sheetnames}")
        for worksheet in workbook.worksheets:
            print(f"\n=== {worksheet.title} ===")
            for row_index, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
                print(f"R{row_index}: " + " | ".join(value_to_text(value) for value in row))
                if row_index >= MAX_ROWS:
                    print(f"... 仅显示前 {MAX_ROWS} 行")
                    break
    finally:
        workbook.close()


if __name__ == "__main__":
    main()
```

超大工作簿必须保持 `read_only=True` 并限制输出行数。不要为了统计行数而把所有行加载到列表。

## 修改单元格

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["openpyxl"]
# ///
from pathlib import Path
import openpyxl

INPUT_PATH = Path("/opt/data/.dock/shared/input.xlsx")
OUTPUT_PATH = Path("/opt/data/.dock/shared/input_修改版.xlsx")
SHEET_NAME = "Sheet1"


def main():
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(INPUT_PATH)
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"输出文件已存在：{OUTPUT_PATH}")

    workbook = openpyxl.load_workbook(INPUT_PATH)
    if SHEET_NAME not in workbook.sheetnames:
        workbook.close()
        raise KeyError(f"工作表不存在：{SHEET_NAME}")

    worksheet = workbook[SHEET_NAME]
    worksheet["A1"] = "新内容"
    workbook.save(OUTPUT_PATH)
    workbook.close()

    validated = openpyxl.load_workbook(OUTPUT_PATH, data_only=False, read_only=True)
    try:
        if validated[SHEET_NAME]["A1"].value != "新内容":
            raise RuntimeError("输出工作簿内容校验失败")
    finally:
        validated.close()
    print(f"已创建：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

## 写入公式

`openpyxl` 只写公式，不计算结果。公式函数使用英文名和逗号分隔参数；用户需要用 Excel 或其他兼容程序打开并保存，才能刷新公式缓存。

```python
worksheet["C1"] = "=A1+B1"
worksheet["D1"] = "=SUM(A1:A10)"
```

保存后使用 `data_only=False` 重新打开并确认公式字符串存在，不要声称已经计算出最新结果。

## 创建工作簿

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["openpyxl"]
# ///
from pathlib import Path
import openpyxl
from openpyxl.styles import Alignment, Font

OUTPUT_PATH = Path("/opt/data/.dock/shared/数据表.xlsx")


def main():
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"输出文件已存在：{OUTPUT_PATH}")

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "数据表"

    rows = [["名称", "数值", "备注"], ["事项 A", 100, "说明 A"], ["事项 B", 200, "说明 B"]]
    for row_index, row_data in enumerate(rows, start=1):
        for column_index, value in enumerate(row_data, start=1):
            cell = worksheet.cell(row=row_index, column=column_index, value=value)
            if row_index == 1:
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center")

    workbook.create_sheet("说明")["A1"] = "这里是说明页。"
    workbook.save(OUTPUT_PATH)
    workbook.close()

    validated = openpyxl.load_workbook(OUTPUT_PATH, read_only=True)
    try:
        if validated.sheetnames != ["数据表", "说明"]:
            raise RuntimeError("输出工作簿结构校验失败")
    finally:
        validated.close()
    print(f"已创建：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

## 使用 pandas 分析

只把分析结果写入新文件，不用 pandas 覆盖来源工作簿。

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas", "openpyxl"]
# ///
from pathlib import Path
import pandas as pd

INPUT_PATH = Path("/opt/data/.dock/shared/input.xlsx")
OUTPUT_PATH = Path("/opt/data/.dock/shared/input_分析结果.xlsx")


def main():
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(INPUT_PATH)
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"输出文件已存在：{OUTPUT_PATH}")

    dataframe = pd.read_excel(INPUT_PATH, sheet_name=0)
    numeric_summary = dataframe.describe()
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="原始数据", index=False)
        numeric_summary.to_excel(writer, sheet_name="数值统计")

    sheets = pd.ExcelFile(OUTPUT_PATH).sheet_names
    if sheets != ["原始数据", "数值统计"]:
        raise RuntimeError("分析结果工作表校验失败")
    print(f"已输出：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

如果没有数值列，先根据用户目标选择需要分析的列，不要机械调用 `describe()` 并生成无意义结果。

## XLSX 转 CSV

每个工作表输出一个 UTF-8 BOM CSV，方便用户用中文 Excel 直接打开。写入前一次性检查所有目标文件，避免只完成部分转换。

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas", "openpyxl"]
# ///
from pathlib import Path
import pandas as pd

INPUT_PATH = Path("/opt/data/.dock/shared/input.xlsx")
OUTPUT_DIR = Path("/opt/data/.dock/shared")


def main():
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(INPUT_PATH)

    sheets = pd.read_excel(INPUT_PATH, sheet_name=None)
    outputs = {name: OUTPUT_DIR / f"{INPUT_PATH.stem}__{name}.csv" for name in sheets}
    existing = [path for path in outputs.values() if path.exists()]
    if existing:
        raise FileExistsError(f"输出文件已存在：{existing}")

    for name, dataframe in sheets.items():
        output_path = outputs[name]
        dataframe.to_csv(output_path, index=False, encoding="utf-8-sig")
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError(f"CSV 输出校验失败：{output_path}")
        print(f"已导出：{output_path}（{len(dataframe)} 行）")


if __name__ == "__main__":
    main()
```

## CSV 转 XLSX

先确认 CSV 编码。中国大陆常见文件通常是 `utf-8-sig` 或 `gb18030`；不要静默轮流猜测。读取失败时报告编码错误，再根据用户信息明确修改 `CSV_ENCODING`。

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas", "openpyxl"]
# ///
from pathlib import Path
import openpyxl
import pandas as pd

INPUT_PATH = Path("/opt/data/.dock/shared/input.csv")
OUTPUT_PATH = Path("/opt/data/.dock/shared/input.xlsx")
CSV_ENCODING = "utf-8-sig"


def main():
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(INPUT_PATH)
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"输出文件已存在：{OUTPUT_PATH}")

    dataframe = pd.read_csv(INPUT_PATH, encoding=CSV_ENCODING)
    dataframe.to_excel(OUTPUT_PATH, index=False, engine="openpyxl")

    validated = openpyxl.load_workbook(OUTPUT_PATH, read_only=True)
    try:
        if validated.active.max_row != len(dataframe) + 1:
            raise RuntimeError("CSV 转 XLSX 行数校验失败")
    finally:
        validated.close()
    print(f"已输出：{OUTPUT_PATH}（{len(dataframe)} 行）")


if __name__ == "__main__":
    main()
```

## 能力边界

- `data_only=True` 返回上次由 Excel 保存的公式缓存，不会自行计算公式。
- `openpyxl` 不能保证保留所有 shapes、外部链接、嵌入对象和其他高级 Excel 功能。
- `read_only=True` 适合大文件读取，但不能修改，图表和图片等功能也不可用。
- pandas 适合数据分析和新结果文件，不适合需要保留原格式的工作簿修改。
- 不修改 `.xlsm`、密码保护或依赖复杂高级功能的工作簿。
