# Project map / 项目结构说明

The project keeps the implementation flat for now so that the tested 2024
baseline remains stable.  The filename prefix and this map define each
module's role; new 2025 production work should follow these seams rather than
create a second calculation path.

项目目前保持扁平目录，以避免破坏已经通过 2024 回归测试的基线。文件名前缀和
本说明定义模块职责；2025 的新功能应沿用这些分界点，不应再建立第二套计算路径。

| Module family | Purpose / 用途 | 2025 status |
| --- | --- | --- |
| `fortran_parity`, `legacy_dat`, `cir_runner`, `cir_bridge` | Verified crop-water-need engine; parses legacy evidence only where needed. / 已核对的作物需水计算与旧资料读取。 | Production calculation foundation / 生产计算基础 |
| `diversion_ingest`, `diversion_mapping`, `diversion_ledger` | Daily-flow QA, exact source-to-ditch mapping, and monthly required-water/shortage ledger. / 日流量 QA、精确映射、月度需求和缺水账。 | Production calculation foundation / 生产计算基础 |
| `area_consumptive_use`, `annual_summary`, `non_agricultural_use` | Area CU, Table II aggregation, and non-agricultural CU. / 区域耗水、Table II 汇总、非农耗水。 | Production calculation foundation / 生产计算基础 |
| `report_preview`, `main.py` | Small user-facing interface; currently runs the read-only 2024 Table II preview. / 简单用户入口；目前运行只读 2024 Table II 预览。 | Extend after 2025 adapters are approved / 2025 适配器确认后扩展 |
| `legacy_*`, `legacy_2024_*` | Read-only adapters used only to prove 2024 agreement. / 只读旧资料适配器，只用于证明 2024 一致性。 | Do not use as 2025 input parsers / 不作为 2025 解析器 |
| `etl_*` | Earlier input-extraction experiments. / 早期输入提取试验。 | Review before production use / 投产前需审查 |
| `core_blaney_criddle`, `regional_aggregator`, `archive_scripts` | Historical/prototype reference. / 历史或原型参考。 | Not production path / 非生产路径 |

## Naming rules / 命名规则

- Use complete units in names: `_af` or `_acft` for acre-feet, `_ft` for feet,
  `_in` for inches, `_acres` for area, and `_cfs` for cubic feet per second.
  / 在变量名中写明单位。
- Use `*_by_stream`, `*_by_area`, or `*_by_ditch` for dictionaries, rather than
  an unexplained plural. / 字典必须说明按流域、区域或水渠索引。
- Keep raw input, calculated output, and policy decisions separate.  A policy
  such as `shortage_assessed` must never be guessed from a blank cell or zero.
  / 原始输入、计算结果与政策判断必须分开；不能由空值或零值猜测政策。
- Keep legacy spreadsheet-cell references inside `legacy_*` adapters. / 旧
  工作簿单元格引用只能存在于 `legacy_*` 适配器中。
