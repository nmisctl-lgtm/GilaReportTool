# Gila Report Tool / Gila 报告工具

This project rebuilds the Gila–San Francisco consumptive-use report so that
reviewed raw data can be quality-checked, calculated transparently, displayed
as key intermediate tables, and eventually rendered as a PDF report.

本项目重建 Gila–San Francisco 耗水量报告：经过审阅的原始数据先进行 QA/QC，
再通过透明计算形成关键中间表，最后生成 PDF 报告。

## Start here / 从这里开始

- [2024 report flow](docs/2024_report_flow.md) — plain-language visual data flow
  and glossary / 面向非专业读者的数据流图与术语表。
- [Project map](docs/architecture.md) — which scripts are production, legacy,
  or prototypes / 哪些脚本是生产、旧资料适配器或原型。
- [2024 data flow](docs/2024_data_flow.md) — equations and audit trail /
  公式与审计数据流。

## Current verified command / 当前已核对命令

```bash
uv run python main.py validate-2024
```

It performs a read-only 2024 Table II preview and prints the four calculated
stream-system annual-use totals. It does not alter the workbook.

该命令只读计算并显示 2024 Table II 四个流域的年度耗水总量，不会修改工作簿。

## Status / 当前状态

- 2024 crop-water requirement, diversion ledger, area CU, non-agricultural CU,
  and Table II totals have regression tests.
- 2025 diversion input parsing and QA/QC are the next implementation stage.
- Existing `legacy_*` modules are evidence adapters only; they are not 2025
  input parsers.
