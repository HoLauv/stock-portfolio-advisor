# stock-portfolio-advisor · 自选持仓投资价值评分与配置顾问

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.1.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org)
[![Tests](https://img.shields.io/badge/tests-49%20passed-brightgreen.svg)](#测试)
[![Deps](https://img.shields.io/badge/dependencies-stdlib%20only-orange.svg)](#安装)

> 分析 A 股自选与持仓，**按行业路由**计算价值评分与**独立的**交易环境分，输出基本面情景估值、数据缺口、受风险政策约束的配置参考，并生成可离线打开的 HTML 报告。
>
> A WorkBuddy Skill. 所有分数由脚本**确定性计算**，禁止模型心算。

**English TL;DR** — Deterministic, rule-based scoring for A-share watchlists and holdings: sector-routed value score + separate trading-environment score, scenario-based fundamental valuation, explicit data-gap reporting, constrained allocation reference, offline HTML report. Pure Python stdlib, 49 unit tests. Not investment advice.

---

## 为什么又做了一个

v1 的问题在于把"交易热度"混进了"价值判断"——资金、技术、新闻的噪音会盖过基本面信号。
v2 做的一件核心事：**把价值分和交易环境分彻底拆开**，各自独立打分、独立展示，不再合成一个"总分"糊弄过去。

| | v1 | v2.1.0 |
|---|---|---|
| 评分 | 六维合成一个总分 | **价值分（Q/G/V，按行业路由）+ 独立的交易环境分（F/T/N）** |
| 估值 | 目标价三法取中位数 | 分行业主模型 + bear/base/bull 三情景公允价值 |
| 缺失数据 | 中性兜底 | **有效覆盖率 <70% 该维度直接为 `null`**，资料不足输出 NR |
| 配置 | 固定约束 | 单票 ≤15% / 行业 ≤30% / 产业链分组 ≤30% / 现金 ≥ max(5%, 现金需求) |
| 可追溯性 | 无 | 每只股票每项指标带 `weights_version`，结果带 `model_version` |

---

## 四条设计原则

1. **不许心算** —— 分数与估值由 `scripts/score_engine.py` 调用 `scripts/value_model.py` 计算，禁止模型凭感觉估分或直接填目标价绕过公式。
2. **不许编造** —— 取不到的数据标缺失。缺失项**保留在分母里、贡献 0**，不会把"少量可得数据"放大成高分。
3. **硬风险不被缺失掩盖** —— 已知 ST / 退市 / 立案 → 强制评级 D、仓位上限 0；资料不足 → NR（暂不评级），总分 `null`。
4. **不承诺收益** —— v2 阈值尚未完成历史收益校准，README 与报告都写明这一点。

---

## 安装

```bash
git clone https://github.com/<你的用户名>/stock-portfolio-advisor.git
cd stock-portfolio-advisor
```

**零依赖**：只用 Python 标准库，Python 3.13+ 直接跑，不需要 `pip install` 任何东西。

作为 WorkBuddy 技能使用时，把整个目录放到 `~/.workbuddy/skills/` 下即可。

---

## 快速开始

仓库自带**合成数据示例**（不联网、不用真实行情），可以直接跑通整条链路：

```bash
# 1) 评分：metrics.json -> result.json
python scripts/score_engine.py \
  --input  examples/metrics.example.json \
  --output examples/result.example.json

# 2) 出报告：result.json -> HTML
python scripts/build_report.py \
  --result examples/result.example.json \
  --output examples/report.example.html

# 3) 查看输入字段模板
python scripts/score_engine.py --template
```

打开 `examples/report.example.html` 即可看到完整报告（内联 SVG，断网可看）。

---

## 使用示例

以下是**仓库示例真实跑出的结果**，不是示意：

### 输入

`examples/metrics.example.json` 是 3 只标的的指标输入（含 1 只故意留空的 `missing`）。

### 输出 · 个股

| code | 价值分 | 交易环境分 | 评级 | 动作 | 上行空间 | 仓位上限 |
|---|---|---|---|---|---|---|
| `ordinary` | 87.5 | 80.1 | A+ | 价值评分很高 | +33.3% | 15% |
| `bank` | 73.3 | 80.1 | A | 价值评分较高 | −16.7% | 12% |
| `missing` | `null` | `null` | **NR** | 暂不评级 | — | — |

第三只就是"数据不足不硬凑"的演示：**不给分、不定级、不给仓位上限**。

### 输出 · 六维与数据质量

```json
"dims": {"Q": 96.4, "G": 81.9, "V": 82.0, "F": 79.2, "T": 87.4, "N": 74.0},
"data_quality": {"Q": {"score": 96.4, "coverage": 100.0, "missing": [], "not_applicable": []}, ...}
```

每个维度都带 `coverage`（有效覆盖率）和 `missing` 清单——**分数和它的可信度一起给**。

### 输出 · 大盘与配置

```json
"market":     {"temperature": 50.0, "state": "中性"}
"allocation": {"equity_pct": 27.0, "cash_pct": 58.0, "status": "reference"}
```

配置的 `status` 是 `reference`（参考），不是指令。配套 warning 会明说：

> 仅为约束预算参考，未生成买卖订单；交易费用、最小交易单位、实际可成交性需另行核实。

---

## 评分模型

**价值分** = `(Q×wQ + G×wG + V×wV) / (wQ+wG+wV)`，权重按标的画像路由：

| profile | Q : G : V | 适用 |
|---|---|---|
| `default` | 25 : 20 : 20 | 通用盈利企业 |
| `growth` | 20 : 30 : 15 | 成长 |
| `value` | 30 : 10 : 30 | 成熟红利 |
| `cyclical` | 25 : 15 : 25 | 周期资源 |
| `bank` / `broker` / `insurance` | 30 : 10 : 25 | 分别适配（银行看不良率与资本缓冲，券商看风险覆盖率，保险看偿付能力） |

**交易环境分** = `(15F + 10T + 10N) / 35` —— 与价值分**并列展示，不混入**。

**发布门槛**：Q/G/V 均有分 + 关键财务齐全 + 有效现价 + 完整情景估值 + 风险已核查，才发布总分与评级。

**大盘温度**：均线 / 成交额 / 涨跌广度 / 破净比例 4 项，权重 30:20:20:15，缺项不输出温度。

完整口径见 [`references/scoring-model.md`](references/scoring-model.md) 与 [`references/indicator-mapping.md`](references/indicator-mapping.md)。

---

## 估值与配置

- 每次选**一种**适用的行业主模型，输出 bear / base / bull 三套公允价值。行业不适配、输入不完整、情景顺序错误 → **不出公允价值，不做技术位兜底**。
- 配置硬约束：单票 ≤15%、单一行业 ≤30%、产业链分组 ≤30%、现金 ≥ max(5%, 现金需求)。
- 结果带 `model_version` 与每只股票的 `weights_version`，跨版本/跨 profile 的快照**不直接计算分差**。

---

## 回测与校准

`scripts/backtest.py` 是一个日频、只做多、次日开盘成交的模拟器，含现金分红、拆股、成本与停牌不可成交处理。

```bash
python scripts/make_demo_data.py --folder workspace/demo --years 12 --count 12   # 合成数据
python scripts/backtest.py --dataset workspace/demo --output bt.json \
  --start 2015-01-01 --end 2024-12-31
```

⚠️ **必须说清楚**：仓库里的 49 个单元测试验证的是**公式正确性、缺失值处理、行业路由、风险判定、仓位约束与报告兼容性**，**不是历史收益回测**。
v2 的阈值**尚未完成历史收益校准**，因此本项目不宣称"更赚钱"，也不承诺目标价会兑现。

---

## 测试

```bash
cd scripts
python test_value_model.py   # 26 tests
python test_backtest.py      # 23 tests
```

共 **49 个测试全部通过**，无需联网、无需真实数据。

---

## 项目结构

```
.
├── SKILL.md                          # 技能元数据与完整工作流
├── scripts/
│   ├── score_engine.py               # 评分 CLI 入口
│   ├── value_model.py                # 估值与评分核心（确定性计算）
│   ├── build_report.py               # HTML 报告渲染（内联 SVG）
│   ├── portfolio_ledger.py           # 持仓台账与快照
│   ├── backtest.py                   # 日频回测模拟器
│   ├── build_backtest_dataset.py     # 回测数据集构建
│   ├── calibrate_weights.py          # 权重校准
│   ├── weight_registry.py            # 权重注册表（版本化）
│   ├── run_calibration.py            # 校准一键执行
│   ├── make_demo_data.py             # 合成示例数据生成
│   ├── package_skill.py              # 打包
│   └── test_*.py                     # 单元测试（49 个）
├── references/
│   ├── scoring-model.md              # 评分结构、行业路由、门槛、约束
│   ├── indicator-mapping.md          # v2 输入字段、单位、来源日期、估值公式
│   ├── data-playbook.md              # 取数命令与降级路径
│   ├── backtesting.md                # 回测数据格式与启用门槛
│   └── valuation-review-2026-09-05.md# v1 问题留档
├── config/                           # 权重、校准、回测策略配置
├── assets/                           # 报告样式与图标
└── examples/                         # 可跑通的输入 / 输出 / 报告示例
```

---

## 数据源

主通道为腾讯自选股（`westock-mcp` 连接器 + `westockdata` CLI）。连接器未连接时有降级路径，但**禁止编造自选或持仓数据**。

针对 A 股。港股 / 美股可记录清单，但**不套用** A 股行业阈值、币种与配置规则。
K 线为收盘级别，非盘中实时。

---

## 能力边界

**不做**：盘中实时盯盘 · 个股深度尽调 · 自动下单（仅模拟盘且须人工确认价格与数量）。

---

## 免责声明

本项目输出的是**评分、条件估值与配置参考**，**不构成投资建议**，不含任何收益承诺，不保证目标价兑现或回撤上限。
v2 阈值尚未完成历史收益校准。市场有风险，投资决策及其后果由使用者自行承担。

---

## License

[MIT](LICENSE)
