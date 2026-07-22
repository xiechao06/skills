---
name: ai-bubble-indicators
description: |
  Generate an AI bubble / systemic-deleveraging monitoring report across three
  indicator groups (capital coverage RCR, demand conversion, financing pressure),
  then email it. Use when user asks for AI泡沫指标报告, RCR/NRR/降价融资监控,
  分层塌方信号, AI bubble dashboard, or wants the three-group collapse checklist
  emailed (default xiechao06@gmail.com).
---

# ai-bubble-indicators — AI 泡沫三组指标报告

基于「分层塌方」框架，生成并邮件发送三组监控指标报告：

1. **资本覆盖** — RCR（外部 AI 毛利能否养活 capex 资产）
2. **需求转化** — 试点转生产、NRR、调用量 vs 毛利率
3. **融资压力** — down round / bridge / 老股折价 / 云厂商应收账期

**系统信号规则：** 单组变红 = 局部压力；**三组同时恶化** = 系统性去杠杆。

默认收件人：`xiechao06@gmail.com`  
详细定义见 [references/INDICATORS.md](references/INDICATORS.md)  
数据源见 [references/SOURCES.md](references/SOURCES.md)

---

## Agent 工作流（每次运行）

### 0. 路径

```bash
# 仓库 canonical 路径（~/workspace/skills）
SKILL_DIR="$HOME/workspace/skills/skills/ai-bubble-indicators"
# pi 侧通常是软链：~/.pi/agent/skills/ai-bubble-indicators -> 上述路径
# SKILL_DIR="$HOME/.pi/agent/skills/ai-bubble-indicators"

PY="$SKILL_DIR/.venv/bin/python"
SCRIPT="$SKILL_DIR/scripts/generate_and_send.py"
OUT_ROOT="$HOME/pi_workspace/output"

# 首次：
if [ ! -x "$PY" ]; then
  python3 -m venv "$SKILL_DIR/.venv"
  "$SKILL_DIR/.venv/bin/pip" install -r "$SKILL_DIR/requirements.txt"
fi
```

### 1. 调研并填写快照 JSON

用 `web_search` / `fetch_content` 收集最新公开数据，**不要编造数字**。  
查不到就填 `null`，并在 `notes` 写明缺口。

快照路径（推荐）：

```bash
DATE=$(date +%Y-%m-%d)
OUT_DIR="$OUT_ROOT/ai-bubble-indicators-$DATE"
mkdir -p "$OUT_DIR"
SNAP="$OUT_DIR/snapshot.json"
```

从模板复制后编辑：

```bash
cp "$SKILL_DIR/templates/snapshot.example.json" "$SNAP"
```

字段说明见模板与 [references/INDICATORS.md](references/INDICATORS.md)。  
至少尽量填齐：

| 组 | 必填优先 |
|----|----------|
| G1 资本覆盖 | hyperscaler 2025/2026 capex、头部模型 ARR/收入、自估 RCR 或区间 |
| G2 需求转化 | 试点→生产转化率、AI NRR（或代理指标）、毛利率趋势 |
| G3 融资压力 | down round %、bridge %、secondary 折价、应收 DSO 变化 |
| 综合 | 每组 `status`: `green` / `yellow` / `red` / `unknown` |

`status` 判定阈值（默认）：

| 指标 | yellow | red |
|------|--------|-----|
| RCR | < 0.7 | < 0.5 且 capex 仍高增 |
| 试点转生产 | < 25% | < 15% |
| NRR | < 100% | < 80%（或持续 20–40% 区） |
| 毛利率 | 下行 >3pct | 下行 >5pct 且与用量背离 |
| Down round | > 20% | > 30% |
| Bridge 占比 | > 35% | > 50% |
| 老股折价 | > 15% | > 25% |
| 应收账期 | 明显拉长 | 显著拉长 + 其他融资红灯 |

综合：

- `systemic_signal = true` **仅当** 三组 `status` 均为 `red`（或至少两组 `red` 且第三组 `yellow` 且你有强证据）
- 否则写清「局部压力在哪一组」

### 2. 生成报告 + 发邮件

```bash
"$PY" "$SCRIPT" \
  --snapshot "$SNAP" \
  --out-dir "$OUT_DIR" \
  --to xiechao06@gmail.com \
  --send
```

只生成不发送：

```bash
"$PY" "$SCRIPT" --snapshot "$SNAP" --out-dir "$OUT_DIR"
```

指定主题/附加说明：

```bash
"$PY" "$SCRIPT" \
  --snapshot "$SNAP" \
  --out-dir "$OUT_DIR" \
  --to xiechao06@gmail.com \
  --subject "AI泡沫三组指标周报 $(date +%Y-%m-%d)" \
  --send
```

### 3. 向用户回报

1. 展示报告路径：`$OUT_DIR/report.html`（**主格式**；浏览器打开）
2. 用 5–10 行摘要说明：三组颜色、是否系统信号、最大风险、数据缺口
3. 确认邮件是否发送成功（脚本 stdout 含 `[OK] Email sent`；邮件正文为 HTML）

---

## 快速触发语

用户说以下任一，即运行本 skill 全流程：

- 「跑一下 AI 泡沫指标报告」
- 「三组指标发我邮箱」
- 「AI bubble indicators report」
- 「分层塌方监控」

若用户只说「发邮箱」未给地址 → 默认 `xiechao06@gmail.com`。

---

## 邮件配置

**收件人默认：`xiechao06@gmail.com`**（与发件 SMTP 账号可以不同）。

SMTP 凭证查找顺序：

1. 环境变量 `SMTP_*`
2. `~/.ai_bubble_indicators/.env`（本 skill 专用，推荐）
3. `~/.etf_premium_monitor/.env` / `~/.qdii_limits_cache/.env`（本机已验证可用的回退）
4. `~/.pi/email-config.json`

专用配置示例：

```bash
mkdir -p ~/.ai_bubble_indicators
cat > ~/.ai_bubble_indicators/.env << 'EOF'
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USER=your_smtp_user@qq.com
SMTP_PASS=your_smtp_auth_code
NOTIFY_EMAILS=xiechao06@gmail.com
FROM_NAME=AI Bubble Monitor
EOF
```

> 注：部分网络下 Gmail SMTP（`smtp.gmail.com`）会 `Connection unexpectedly closed`；可用 QQ/其他 SMTP 发到 Gmail 收件箱。

---

## 产出物约定

```
~/pi_workspace/output/ai-bubble-indicators-YYYY-MM-DD/
├── snapshot.json      # 结构化输入（可版本对比）
├── report.html        # **主报告（结构化 HTML，邮件同款）**
├── report.txt         # 纯文本回退（multipart/alternative）
└── README.md          # 本次运行说明
```

可选：`--keep-markdown` 额外写出旧版 `report.md`。

历史快照可 diff：

```bash
"$PY" "$SCRIPT" --diff "$OUT_ROOT/ai-bubble-indicators-OLD/snapshot.json" "$SNAP"
```

---

## 研究纪律（必须遵守）

1. **禁止编造**：无来源数字一律 `null` + notes
2. **标注来源**：每条关键数字在 snapshot 的 `sources[]` 留 URL 或报告名
3. **口径透明**：ARR vs 确认收入、含股权激励与否、capex 是否含租赁，写在 notes
4. **区分环内/环外**：RCR 分子尽量剔「投资后再买云/GPU」的回流
5. **结论克制**：默认叙事是「分层压力」，不是「AI 技术死亡」
6. **股价 ≠ 行业**：报告结尾提醒流动性与股价可脱节

---

## Project structure

```
ai-bubble-indicators/
├── SKILL.md
├── requirements.txt
├── references/
│   ├── INDICATORS.md
│   └── SOURCES.md
├── templates/
│   └── snapshot.example.json
└── scripts/
    └── generate_and_send.py
```
