# Excel 与 CSV 读取分析

用于读取、汇总、清洗、数据质量检查和回答数据问题。先阅读 `excel-common.md`，不修改来源文件。

## 读取工作簿

先按任务确认工作表、隐藏内容、公式和相关高级对象。需要同时观察公式与缓存值时分别打开：

```python
formula_book = openpyxl.load_workbook(INPUT_PATH, data_only=False, read_only=True)
value_book = openpyxl.load_workbook(INPUT_PATH, data_only=True, read_only=True)
```

两者都只读并在 `finally` 中关闭。缓存值为 `None` 不等于零，可能只是文件从未由 Excel/WPS 保存计算结果。绝不保存 `data_only=True` 工作簿。

限制输出行数，不把整个工作表打印到对话。报告工作表名称、有效范围、公式数量、隐藏工作表和只读分析未覆盖的高级对象。

## pandas 分析

先判断表头：

| 情况 | pandas 参数 |
|---|---|
| 第一行是表头 | `header=0` |
| 第三行是表头 | `header=2` |
| 两行合并表头 | `header=[0, 1]` |
| 没有表头 | `header=None` |

表头位置不明确时先查看前若干行，不自动把第一行当作字段名。将 pandas 行号转换为 Excel 行号时计入 0/1 基准和表头行数，并在报告中使用工作表名加 Excel 坐标。

执行分析时：

- 聚合直接基于已确认的数据列，不重新推导来源值。
- 合并表使用 `validate="1:1"`、`"m:1"` 等约束表达预期关系。
- 混合类型使用 `pd.to_numeric(..., errors="coerce")` 时报告无法转换的原始行。
- 检查空值、重复、唯一键、异常日期、无穷值和不合理范围。
- 不把相关性写成因果关系，不给出数据无法支持的业务结论。

## 大文件

- 大 XLSX 使用 `openpyxl(..., read_only=True)` 流式遍历。
- 大 CSV/TSV 使用 `pandas.read_csv(..., chunksize=...)`。
- 只需要部分列时使用 `usecols`。
- 不为了统计行数执行 `list(worksheet.rows)`。
- XLSX 没有真正的 pandas 分块读取；内存不足时改用 openpyxl 流式聚合。

## 数值展示

展示格式和存储类型分开：

- 货币和小数按用户要求显示小数位；
- 百分比显示为百分数，但计算仍使用原始小数；
- 计数显示为整数；
- 年份不加千位分隔；
- 只在文本报告中使用 `f"{value:.2f}"`，写入 XLSX 时保持数值并使用 `number_format`。

少量结果直接回复；长结果写入新的 CSV/XLSX/JSON。用户没有要求文件时不要制造结果工作簿。
