---
name: nasdaq-core-dca
description: |
  纳指核心底仓动态定投决策：发薪日根据回撤分档 / MA200 计算本月应投金额，
  股比容忍 30%–70%，短债蓄水池管理。默认基准月投 2 万元。
  Use when: 用户提到纳指定投、发薪日定投、回撤加仓、纳指底仓、payday DCA、
  纳指再平衡、QQQ 定投策略、短债蓄水池，或要跑本月纳指该投多少。
---

# nasdaq-core-dca — 纳指核心底仓动态定投

发薪日运行一次：自动拉 QQQ 行情 → 按回撤/MA200 分档 → 输出本月操作清单。

## 策略摘要

| 层级 | 规则 |
|------|------|
| 上层 | 中枢 50/50，股比 **30%–70%**；越界才再平衡 |
| 中层 A `drawdown` | 纯回撤分档：高位 0.5B / 常态 1B / 轻 1.5B / 中 2B / 深 2.5B |
| 中层 B `ma200`（默认） | 回撤 + MA200 趋势过滤；深跌上限 2B |
| **宏观闸门** | 读取 `ai-bubble-indicators` 三组快照，调节 gate / 短债地板 / 临时股比 |
| 下层 | 工资先进短债，再按档位划转买纳指 |
| **B** | **默认 20,000 元**（用户计划月投） |

详细规则见 [references/STRATEGY.md](references/STRATEGY.md) §9。

## Agent 工作流

### 0. 路径与依赖（每次会话先解析）

```bash
SKILL_DIR="$HOME/workspace/skills/skills/nasdaq-core-dca"
# 若从 ~/.pi/agent/skills 软链：
# SKILL_DIR="$HOME/.pi/agent/skills/nasdaq-core-dca"
PY="$SKILL_DIR/.venv/bin/python"
SCRIPT="$SKILL_DIR/scripts/nasdaq_strategy.py"

# 首次或依赖缺失时：
if [ ! -x "$PY" ]; then
  python3 -m venv "$SKILL_DIR/.venv"
  "$SKILL_DIR/.venv/bin/pip" install -r "$SKILL_DIR/requirements.txt"
fi
```

后续命令一律用 `"$PY" "$SCRIPT" ...`。

### 1. 首次使用：初始化配置

```bash
"$PY" "$SCRIPT" init-config \
  --equity <当前纳指市值> \
  --bond <当前短债余额> \
  --base 20000 \
  --mode ma200
```

配置写入 `~/.nasdaq_core_dca/portfolio.json`。

### 2. 发薪日（主路径）

用户说「发薪了」「本月纳指投多少」「跑一下定投」时：

1. **确认/更新持仓**（若用户给了新市值）：
   ```bash
   "$PY" "$SCRIPT" set-holdings --equity <纳指市值> --bond <短债余额>
   ```
2. **（建议）先更新 AI 三组指标报告**，确保 `~/pi_workspace/output/ai-bubble-indicators-*/snapshot.json` 较新。
3. **跑发薪日决策**（自动拉 QQQ + 宏观闸门）：
   ```bash
   "$PY" "$SCRIPT" payday --log
   ```
   若用户当场报了市值：
   ```bash
   "$PY" "$SCRIPT" payday --equity 120000 --bond 80000 --monthly-income 20000 --log
   ```
   常用宏观开关：
   ```bash
   "$PY" "$SCRIPT" macro-status
   "$PY" "$SCRIPT" payday --no-macro          # 仅价格规则
   "$PY" "$SCRIPT" payday --macro-pressure high
   "$PY" "$SCRIPT" payday --macro-snapshot ~/pi_workspace/output/ai-bubble-indicators-2026-07-22/snapshot.json
   ```
4. **把「本月操作清单」原样展示给用户**（价格档位、宏观压力、应投、是否再平衡）。
5. 提醒：操作完成后用 `set-holdings` 更新市值。

### 3. 仅看市场状态

```bash
"$PY" "$SCRIPT" market
"$PY" "$SCRIPT" market --ticker QQQ
```

### 4. 手动决策（无网 / 自备价格）

```bash
"$PY" "$SCRIPT" decide \
  --price <P> --high <H> --low-12m <L> --ma200 <MA> \
  --equity <E> --bond <B> --mode ma200 --monthly-income 20000
```

### 5. 回测（可选）

```bash
"$PY" "$SCRIPT" backtest --ticker QQQ --start 2010-01-01 --mode both \
  --base 20000 --monthly-income 20000 --out-dir /tmp/nasdaq-bt
```

### 6. 离线自检

```bash
"$PY" "$SCRIPT" demo
```

## 档位金额表（B = 2 万）

| 状态 | 倍数 | 本月投纳指 |
|------|------|------------|
| 高位减投 | 0.5× | **1 万** |
| 常态 | 1.0× | **2 万** |
| 轻度回撤 | 1.5× | **3 万** |
| 中度回撤 | 2.0× | **4 万** |
| 深度回撤 | 2.0–2.5× | **4–5 万**（受短债余额上限） |

## 何时触发

- 发薪日 / 月度定投决策
- 「纳指这个月投多少」「要不要加仓」
- 回撤分档、MA200、股比 30–70 再平衡
- 短债蓄水池怎么划转
- AI 泡沫 / 三组指标 / 塌方信号下纳指怎么投
- 「宏观闸门」「macro-status」
- 想回测 QQQ 动态定投 vs 静态 50/50

## 配置文件

路径：`~/.nasdaq_core_dca/portfolio.json`（可用环境变量 `NASDAQ_CORE_DCA_CONFIG` 覆盖）

```json
{
  "base_invest": 20000,
  "monthly_income": 20000,
  "equity_value": 120000,
  "bond_value": 100000,
  "equity_min": 0.30,
  "equity_max": 0.70,
  "mode": "ma200",
  "ticker": "QQQ"
}
```

## 注意

- **不构成投资建议**；未计入 QDII 溢价、申赎费、汇率、限购。
- 行情默认用 **QQQ** 作纳指标的；国内 QDII 净值节奏可能略有差异。
- 深跌加投依赖短债弹药，提醒用户短债池宜常备 2–3 个月加投额度。
- 脚本是**发薪日决策器**，不是日频交易系统；默认每月跑一次。

## 文件结构

```
nasdaq-core-dca/
├── SKILL.md
├── requirements.txt
├── references/
│   └── STRATEGY.md
└── scripts/
    └── nasdaq_strategy.py
```
