# How the 2024 report is produced / 2024 年报告如何产生

This is a plain-language map of the calculation.  It describes the verified
2024 baseline; 2025 will use the same calculation stages after its new input
formats have passed quality checks.

下图使用日常语言说明已经核对的 2024 基线。2025 年会复用相同的计算阶段，
但必须先完成新输入格式的质量检查。

```mermaid
flowchart TD
    A[Raw crop survey<br/>原始作物调查：地块、作物、面积、供水方式] --> E[Input quality checks<br/>输入质量检查：缺失、重复、不合理数值、未知代码]
    B[Raw weather data<br/>原始气象：温度、降水、日照、蒸发] --> E
    C[Raw diversion records<br/>原始引水记录：每天每条水渠的流量] --> E
    D[Non-agricultural records<br/>非农记录：牲畜、蓄水池、城市/工业、湖泊] --> E

    E --> F[Crop water need (CIR)<br/>作物灌溉需水量：根据天气和作物参数估计每英亩需要多少水]
    E --> G[Monthly diversion ledger<br/>月度引水账：流量换算、渠道精确匹配、覆盖率检查]
    E --> H[Non-agricultural use<br/>非农耗水：牲畜、stock tank 蒸发、城市/工业/生活、湖泊]

    F --> I[Required water and shortage<br/>理论需水量与缺水：作物/水面蒸发需求减去实际计量引水]
    G --> I
    I --> J[Area consumptive use<br/>区域实际耗水：将缺水比例应用于地表水；地下水按已供给处理]

    J --> K[Table I: irrigated acreage<br/>表 I：灌溉面积]
    J --> L[Table II: annual consumptive use<br/>表 II：年度耗水量]
    H --> L
    G --> M[Table IV: annual diversions<br/>表 IV：年度引水量]
    L --> N[Table III: ten-year history<br/>表 III：本年表 II 加此前九年历史]
    K --> O[Report review and PDF<br/>审阅关键中间结果后生成 PDF 报告]
    L --> O
    M --> O
    N --> O
```

## What the words mean / 术语解释

| Term | Plain-language meaning | 中文解释 |
| --- | --- | --- |
| Acre-foot (AF) | Water needed to cover one acre of land one foot deep; about 326,000 US gallons. | 英亩英尺：一英亩土地铺一英尺深水的体积，约 32.6 万美制加仑。 |
| Consumptive use (CU) | Water that is used up by plants, animals, evaporation, or people and is not immediately returned to the stream. | 耗水量：被作物、动物、蒸发或人使用而没有立即回到河流的水。 |
| Consumptive irrigation requirement (CIR) | The amount of irrigation water a crop needs after useful rainfall is considered. | 作物灌溉需水量：考虑有效降水后，作物仍需要通过灌溉补充的水。 |
| Diversion | Water taken from a river, ditch, well, or reservoir for use. | 引水量：从河流、水渠、水井或水库取出的水。 |
| Metered | Measured by an instrument, rather than guessed. | 已计量：由仪表测得，而不是估算。 |
| Shortage | The part of calculated water need that measured supply did not meet. | 缺水量：理论需水量中没有被实测供水满足的部分。 |
| QA/QC | Quality assurance and quality control: checks that make data trustworthy before calculation. | 质量保证/质量控制：在计算前检查数据是否可信。 |
| Stock tank | A small livestock watering pond or tank; its water-surface evaporation is counted. | 牲畜饮水池/槽；其水面蒸发需要计入耗水。 |

## The four key tables / 四张关键表

| Table | Question answered | Input to the next step |
| --- | --- | --- |
| I — Acreage Survey | How many irrigated acres are in each area? / 每个区域有多少灌溉面积？ | Area CU calculation / 区域耗水计算 |
| II — Annual Consumptive Use | How much water was actually consumed this year? / 本年实际耗用了多少水？ | Table III and final report / 表 III 与最终报告 |
| III — Ten-year CU | How does this year compare with the preceding nine years? / 本年与前九年相比如何？ | Final report trend section / 报告趋势部分 |
| IV — Diversions | How much water was diverted, and how complete is the record? / 引了多少水，记录是否完整？ | Shortage calculation and QA/QC / 缺水计算与质量控制 |
