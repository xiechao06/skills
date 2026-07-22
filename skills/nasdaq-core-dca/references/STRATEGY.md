# 策略规则详解

## 1. 设计目标

把纳指当**核心底仓**，而不是全仓梭哈：

1. **长期持有权益底仓**（纳指 ETF / QDII 指数基金）
2. **短债蓄水池**承接工资与减投资金
3. **顶部减投 / 底部加投**，用回撤与技术指标控制节奏
4. **股比 30%–70%** 宽区间，给动态定投足够空间，减少被迫再平衡

目标中枢仍是约 **50/50**，但不再追求严格静态再平衡。

---

## 2. 状态变量

| 符号 | 含义 |
|------|------|
| \(P_t\) | 当前纳指/ETF 价格 |
| \(H_t\) | 滚动最高价（自策略起点或重置后） |
| \(\mathrm{dd}_t = (P_t - H_t)/H_t\) | 回撤（≤ 0） |
| \(L_{12m}\) | 最近 12 个月最低价 |
| \(g_{12} = (P_t - L_{12m}) / L_{12m}\) | 距 12 月低点涨幅 |
| \(\mathrm{MA}_{200}\) | 200 日均线 |
| \(\mathrm{premium} = (P_t - \mathrm{MA}_{200}) / \mathrm{MA}_{200}\) | 相对均线溢价 |
| \(E, B_{\mathrm{cash}}\) | 权益市值、短债现金 |
| \(w_E = E / (E + B_{\mathrm{cash}})\) | 当前股比 |
| \(B\) | 基准月定投金额 |

---

## 3. 策略 A：纯回撤分档

```
update H = max(H, P)
dd = (P - H) / H
gain_12m = (P - low_12m) / low_12m

if gain_12m >= 0.30:
    invest = 0.5 * B          # 高位减投；可改为 0 停投
else:
    if dd > -0.10:
        invest = 1.0 * B
    elif dd > -0.20:
        invest = 1.5 * B
    elif dd > -0.30:
        invest = 2.0 * B
    else:
        invest = 2.5 * B      # cap by available cash
```

**特点**：只依赖价格路径，不需估值数据；脚本最简单。

---

## 4. 策略 B：回撤 + MA200

```
premium = (P - MA200) / MA200
dd = (P - H) / H
gain_12m = (P - low_12m) / low_12m

if premium >= 0.15 and gain_12m >= 0.30:
    invest = 0.5 * B          # 顶部：均线上方过热 + 大涨
else:
    if dd > -0.10:
        invest = 1.0 * B
    elif dd > -0.20:
        if abs(premium) <= 0.05:
            invest = 1.5 * B  # 磨底/中枢
        else:
            invest = 1.2 * B
    elif dd > -0.30:
        invest = 2.0 * B
    else:
        invest = 2.0 * B      # 深跌谨慎上限，避免火力打光
```

**均线语义**：

- 远高于 MA200 + 大涨 → 先减投
- 回到 MA200 附近 + 有回撤 → 底部区间，加大定投
- 远低于 MA200 深跌 → 加投但设上限

---

## 5. 再平衡：30%–70% 宽区间

每月定投执行后（或月末）检查股比 \(w_E\)：

| 情况 | 动作 |
|------|------|
| \(w_E > 0.70\) | 卖出纳指 → 短债，使股比回到 **0.70**（`band`）或 **0.50**（`target`） |
| \(w_E < 0.30\) | 短债买入纳指，使股比回到 **0.30** 或 **0.50** |
| \(0.30 \le w_E \le 0.70\) | 不强制再平衡，仅执行当月定投 |

默认 `rebalance_style = band`：只把越界仓位拉回边界，最大化「顶部少买、底部多买」的空间。

---

## 6. 月度执行流程

```
1. 工资/现金流 → 全部进入短债蓄水池
2. 更新价格、H、12m low、MA200
3. 按策略 A 或 B 计算价格规则 invest（倍数 × B）
4. 读取 AI 三组指标宏观闸门（见 §9），得到 gate / max_mult / 短债地板
5. invest = min(价格规则×gate, max_mult×B, 短债余额−地板)
6. 从短债划转买入纳指
7. 检查股比是否越出区间（高压期临时收紧上限/中枢）
8. 若越界，执行再平衡
9. 记录日志：价格档位、宏观压力、金额、股比、动作
```

---

## 7. 参数调优建议

| 若你觉得… | 可调 |
|-----------|------|
| 高位仍投太多 | `top_invest_mult` 改为 0；或 `top_gain_threshold` 降到 0.25 |
| 底部加仓太猛 | 把 2.5B 改为 2.0B；深跌档与 -30% 档对齐 |
| 再平衡太少 | 收窄到 40%–60% |
| 再平衡太多 | 保持 30%–70%，或改为每季检查 |
| 想更趋势友好 | 用策略 B（MA200） |
| 想更机械 | 用策略 A（纯回撤） |

---

## 8. 风险与局限

1. **不保证跑赢静态定投**；优势主要在风险调整收益与行为纪律。
2. 回撤/均线是滞后指标，顶部可能减投偏晚，底部可能加投偏早。
3. QDII 有**额度、溢价、汇率、T+N**，实盘需单独处理。
4. 深熊中「加投 + 股比上限 70%」仍会承受较大回撤——这是权益底仓的代价。
5. 请预留应急现金，**不要把全部稳健资产都当作可投弹药**。
6. 宏观闸门依赖 `ai-bubble-indicators` 快照质量；无快照时按 **calm** 放行，不会自动吓停。

---

## 9. AI 泡沫三组指标 · 宏观闸门

纳指是**核心底仓**，不是纯 AI 主题仓。三组指标（资本覆盖 / 需求转化 / 融资压力）只调节**加仓斜率与短债地板**，不替代价格规则。

### 9.1 压力级

| pressure | 典型三组 | gate | max×B | 短债地板 | 临时中枢 | 临时股比上限 |
|----------|----------|------|-------|----------|----------|--------------|
| calm | 全绿或无快照 | 1.00 | — | 4×B | 50% | 70% |
| elevated | 1 红或 ≥2 黄 | 0.75 | 2.0 | 6×B | 45% | 70% |
| high | 2 红 | 0.50 | 1.5 | 9×B | 40% | 60% |
| systemic | 3 红 / 系统信号 | 0.25 | 0.5 | 12×B | 40% | 55% |

### 9.2 公式

```
price_mult     = 策略 A/B 给出的倍数
effective_mult = min(price_mult × gate, max_mult?) 
plan           = effective_mult × B
floor          = bond_floor_months × B

# calm / elevated：地板仅为蓄水目标（提示），不硬挡
# high / systemic：地板硬约束
if pressure in {high, systemic}:
    spendable = max(短债 − floor, 0)
else:
    spendable = 短债

actual = min(plan, spendable)
```

### 9.3 数据来源

1. CLI `--macro-snapshot PATH`
2. 环境变量 `AI_BUBBLE_SNAPSHOT`
3. `portfolio.json` 的 `macro_snapshot`
4. 自动：`~/pi_workspace/output/ai-bubble-indicators-*/snapshot.json`（最新，跳过 `*-test`）
5. `--macro-pressure elevated|high|systemic|calm` 可手动覆盖
6. `--no-macro` 关闭闸门

发薪日前建议先更新三组报告（`ai-bubble-indicators` skill），再跑 `payday`。
