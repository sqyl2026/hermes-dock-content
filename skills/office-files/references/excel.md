# Excel 与 CSV 任务路由

先阅读 `../SKILL.md` 和 `excel-common.md`，再按任务加载对应参考。使用 `openpyxl` 处理普通 `.xlsx`，使用 pandas 分析表格数据；不要用 pandas 覆盖来源工作簿。

## 路由

| 任务 | 额外参考 | 主要方法 |
|---|---|---|
| 读取、汇总、数据质量检查 | `excel-read.md` | 只读结构检查、`openpyxl`、pandas |
| 从表格数据生成静态图表图片 | `excel-read.md`、`excel-chart.md` | pandas 聚合、Matplotlib 渲染、中文字体与 PNG 验证 |
| 创建新的 XLSX | `excel-create.md` | `openpyxl.Workbook()` |
| 修改现有 XLSX | `excel-edit.md` | 按任务检查相关结构，选择最小写入路径并验证 |
| 写入、检查或修复公式 | `excel-formulas.md` | 公式字符串、静态验证、可用时对副本动态重算 |
| CSV/TSV/XLSX 转换 | `excel-conversion.md` | pandas 或流式 `csv`/`openpyxl` |

一个请求包含多个阶段时，按“检查结构 → 读取或修改 → 静态验证 → 报告未验证范围”执行。读取任务不创建无意义的输出文件；用户明确要求结果文件时才写入。

## 工具选择

- 精确读取或修改普通单元格、公式、基础样式、表格和数据验证：`openpyxl`。
- 数据清洗、聚合、透视和新分析结果文件：pandas。
- 不使用 pandas 修改现有工作簿。
- 只有高层库无法完成明确、局部且可验证的任务时才查看 OOXML；不要为普通编辑重写整个 ZIP 包。

## 核心边界

- `data_only=True` 只读取 Excel 上次保存的公式缓存；不能计算公式，也不能据此判断公式正确。
- 绝不把以 `data_only=True` 加载的工作簿保存回文件。
- `openpyxl` 的行列插入和删除不会自动维护所有公式、表格、图表和命名区域依赖；结构修改前读取 `excel-edit.md`。
- 不修改 `.xlsm`，不绕过密码保护；数字签名或未知扩展可能受影响时说明风险，并验证与任务相关的对象。
- 静态验证通过只表示没有发现工具能够识别的结构错误，不证明公式业务逻辑或运行结果正确。
- 不刷新外部连接、外部工作簿、DDE、WEBSERVICE 或其他联网数据源。
