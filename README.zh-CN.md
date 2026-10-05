# Asphalt PDF Plan Takeoff（沥青图纸 PDF 算量）

**从图纸 PDF 中提取并校验铺装工程量** —— 输出面积、厚度、吨数、订购吨数与车次，用于沥青工程估算，每个数值都带置信度与证据，并由确定性计算引擎得出最终数量。

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CLI](https://img.shields.io/badge/CLI-command--line-blue)](#使用)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6)](https://www.microsoft.com/windows)

**[English](./README.md)** | 简体中文

---

## 解决什么问题

人工从市政/铺装图纸 PDF 里做工程量计算又慢又容易出错——估算师要手描区域、抄比例注记、再把数字重新敲进表格。本工具把**沥青与路面项目的图纸 PDF 算量**自动化：自动分类图纸页、解析文本、比例注记与矢量图形，输出带置信度和证据的可测量铺装区域。

比例不明、尺寸冲突、标签不确定的内容绝不靠猜——全部进入**复核队列**交给估算师。校验后的数量再交给 [AsphaltCosts.com](https://asphaltcosts.com/) 引擎换算吨数、订购吨数与车次。

## 核心功能

- **图纸 PDF 算量** ——市政 / 铺装 / 场地平面 PDF → 铺装面积分区
- **图纸页分类与矢量解析** ——文本、比例注记与图形矢量
- **证据化数值** ——每条数量携带来源页码、区域、方法、置信度与状态
- **绝不静默猜测** ——比例不明 / 尺寸冲突 → 复核队列
- **引擎对接** ——面积 → 压实体积 → 吨数 → 订购吨数 → 车次（AsphaltCosts 引擎或其本地镜像）
- **可审计输出** ——JSON / CSV / Markdown + 计算记录

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python -m scripts.s02_pdf_plan_takeoff --project ./project --input ./fixtures/pdf
```

加 `--help` 查看全部选项。本工具家族统一 CLI 约定：`--project <路径> --input <路径> --output <路径> --format json|csv|md|xlsx|pdf --config <路径> --verbose --dry-run`。

## 输出

- `takeoff.json` / `takeoff.csv` ——校验后的面积记录（area_id、图纸页、来源、数量、单位、厚度、方法、置信度、状态）
- `review_queue.json` ——比例不明 / 低置信度 / 尺寸冲突项
- `summary.md` ——图纸摘要与引擎计算记录

## 工作原理

- **标准生命周期** ——`发现 → 摄取 → 提取 → 归一化 → 校验 → 计算 → 输出 → 审计`
- **证据状态机** ——每条数量按 `提取 → 归一化 → 已校验 → 已验证` 推进；允许停在更早状态
- **确定性计算** ——吨数、压实体积、覆盖面积、车次与材料成本来自 AsphaltCosts 网页引擎，绝不在本工具中重写公式

## 质量保证

- 每条记录做确定性 schema 校验；
- 黄金样例 fixtures 与精确期望值（`tests/`）；
- 复核队列：低置信度、比例不明与冲突进入 `review_queue.json` / 摘要——绝不静默修正；
- 审计日志：每次运行将 `run_id`、耗时、输入哈希、引擎版本与输出写入 `<project>/audit/`。

## 测试

```bash
python -m pytest -q
```

## 安全与隐私

本地文件默认留在本地。API 密钥存放在环境变量（`ASPHALTCOSTS_API_KEY`、`ADI_AI_API_KEY`）——绝不写入源码。派生文件写入 `working/` 或 `output/`；来源文件永不修改。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。属 [Asphalt Desktop Intelligence](https://github.com/anleeylee/asphalt-desktop-intelligence) 工具集的一部分。

## 计算引擎

[**AsphaltCosts.com**](https://asphaltcosts.com/) 是确定性计算层：面积 → 压实体积 → 净吨数 → 订购吨数（损耗只计一次）→ 车次 → 材料成本，内置有出处的规划默认值（FHWA 密度 145 lb/ft³，损耗率与车容量可编辑）。本工具把测量并校验后的输入喂给该引擎（或其带标签的本地镜像 `asphaltcosts-web-engine/1.0-mirror`），绝不重写公式。
