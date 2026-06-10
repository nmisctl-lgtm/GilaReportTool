# 🌊 Gila River Basin Pipeline - Dev Journal

> **核心目标:** 替代旧版 Fortran 引擎，基于 1964 最高法院法令，自动化计算农作物消耗性灌溉需求 (CIR)。

---

## 📍 当前状态 (You Are Here)
* **版本:** v0.1.0-alpha
* **最近完成:** 成功完成 Phase 1 跨机器迁移验证 (作物参数 + 气候 ETL + 核心物理引擎)。
* **当前堵塞/待办:** 
  * !!! **Corp Survey data clean up**!!!
  * 准备启动 Phase 2 (`regional_aggregator.py`) 的开发。

---

## 📝 开发日志 (Log)

### [2026-06-10] Phase 1 净室重构与跨设备迁移
* **✅ Done:** * 重构了 `etl_climate.py`，加入了 `all_touched=True` 解决小多边形气候提取为空的问题。
  * 修复了 GDB 读取时的 EPSG:26913 到 4326 的坐标系转换问题。
  * 引入 `uv` 和 `git`，成功在新机器上实现一键环境复原并跑通集成测试。
* **➡️ Next:** * 开始编写 `regional_aggregator.py`。需要把 `etl_crop_survey.py` 里的面积，乘以核心引擎输出的单亩 CIR。

### [YYYY-MM-DD] 模板日期
* **✅ Done:** (今天解决了什么具体问题？)
* **➡️ Next:** (下次打开电脑第一行代码应该写什么？)
* **💡 想法/发现:** (选填：例如“发现某个 API 更好用”，或“数据源有个坑需要注意”)

---

## 🛠️ 常用开发命令速查
* **同步环境:** `uv sync`
* **添加依赖:** `uv add <package_name>`
* **运行集成测试:** `python test_phase1.py`
* **激活venv:**
  * PowerShell `venv\Scripts\Activate.ps1` 
  * macOS/Linux `source venv/bin/activate`