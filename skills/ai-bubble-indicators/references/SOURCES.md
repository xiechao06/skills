# 数据源清单

调研时优先用权威、可复核来源。下列为起点，非穷尽。

## Group 1 — 资本覆盖

| 数据 | 来源 |
|------|------|
| Hyperscaler capex | 公司 10-K/10-Q、earnings release、IR deck（MSFT, AMZN, GOOGL, META, ORCL） |
| Capex guidance | 最近一季财报电话会 |
| FCF | 现金流量表 |
| 模型公司收入/ARR | OpenAI / Anthropic 等媒体引用的公司披露、可靠二手（FT, The Information, Bloomberg） |
| GPU 寿命/折旧讨论 | 公司会计政策、卖方研究（Goldman 等） |
| 电力/长协 | 公司能源公告、核能/SMR 协议新闻 |

**注意：** ARR/run-rate 常含水（合同额、月×12、承诺未确认）。报告中必须标注口径。

## Group 2 — 需求转化

| 数据 | 来源 |
|------|------|
| 企业 AI 采用/试点转生产 | Deloitte State of AI、Gartner、McKinsey Global Survey |
| ROI 体感 | IBM CEO Study、BCG 企业调研、Morgan Stanley 等卖方摘要 |
| NRR | 上市 AI/应用软件公司财报 KPI；私募基准（Carta, PitchBook） |
| 用量与毛利 | 云与模型公司财报分部、毛利率注释 |
| 预算纪律案例 | 企业砍预算/设 AI 消费档位的可信新闻 |

## Group 3 — 融资压力

| 数据 | 来源 |
|------|------|
| Down round / bridge | Carta State of Private Markets、PitchBook、Crunchbase 汇总 |
| Acqui-hire | 公司公告与靠谱科技媒体拆解（对价结构） |
| Secondary 折价 | Forge、EquityZen、Hiive 等成交报道/指数 |
| 应收 DSO | 云厂商季报应收与收入推算，或直接披露 |
| VC 流向 AI 占比 | PitchBook / CB Insights 季度报告 |

## 搜索关键词（中英）

```
hyperscaler capex guidance 2026
AI capital expenditure free cash flow
OpenAI Anthropic ARR revenue loss
Deloitte enterprise AI deployment production
net revenue retention AI software
Carta down rounds AI
private market secondary discount OpenAI
cloud DSO accounts receivable AWS Azure GCP
AI bubble ROI survey McKinsey BCG
```

## 引用规范

snapshot `sources[]` 每项建议：

```json
{
  "metric": "msft_capex_fy_guidance",
  "title": "Microsoft FY26 capex commentary",
  "url": "https://...",
  "date": "2026-xx-xx",
  "excerpt": "一句话原意"
}
```
