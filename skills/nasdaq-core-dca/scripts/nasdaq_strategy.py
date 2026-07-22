#!/usr/bin/env python3
"""
纳指核心底仓 · 动态定投策略引擎

上层: 目标中枢 50/50，股比容忍区间 30%–70%
中层: 月度定投强度（纯回撤分档 / 回撤+MA200）
下层: 短债蓄水池 → 按规则买入纳指

默认节奏: 发薪日每月一次；B=20000
用法见 SKILL.md
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# User config (portfolio + defaults)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_DIR = Path.home() / ".nasdaq_core_dca"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "portfolio.json"

DEFAULT_PORTFOLIO: dict[str, Any] = {
    "base_invest": 20_000,
    "monthly_income": 20_000,
    "equity_value": 0,
    "bond_value": 0,
    "equity_min": 0.30,
    "equity_max": 0.70,
    "target_equity": 0.50,
    "rebalance_style": "band",
    "mode": "ma200",
    "ticker": "QQQ",
    "top_mult": 0.5,
    "frequency": "monthly",
    # AI 泡沫三组指标宏观闸门（见 ai-bubble-indicators skill）
    "macro_gate_enabled": True,
    "macro_snapshot": None,  # 显式路径；空则自动找最新 snapshot
    "macro_pressure_override": None,  # 手动: calm/elevated/high/systemic
    "notes": "发薪日运行 payday；更新 equity_value / bond_value 为当前市值；默认真读 AI 三组指标闸门",
}

# 宏观压力 → 定投倍数上限 / 短债月数地板 / 临时股比中枢与上限
# gate 乘在「价格规则倍数」上；max_mult 是绝对封顶（×B）
MACRO_PROFILES: dict[str, dict[str, Any]] = {
    "calm": {
        "gate": 1.0,
        "max_mult": None,
        "bond_floor_months": 4.0,
        "target_equity": 0.50,
        "equity_max": 0.70,
        "label": "正常",
    },
    "elevated": {
        "gate": 0.75,
        "max_mult": 2.0,
        "bond_floor_months": 6.0,
        "target_equity": 0.45,
        "equity_max": 0.70,
        "label": "升温",
    },
    "high": {
        "gate": 0.50,
        "max_mult": 1.5,
        "bond_floor_months": 9.0,
        "target_equity": 0.40,
        "equity_max": 0.60,
        "label": "高压",
    },
    "systemic": {
        "gate": 0.25,
        "max_mult": 0.5,
        "bond_floor_months": 12.0,
        "target_equity": 0.40,
        "equity_max": 0.55,
        "label": "系统去杠杆",
    },
}

DEFAULT_BUBBLE_OUTPUT_ROOT = Path.home() / "pi_workspace" / "output"


def config_path_from_env() -> Path:
    return Path(os.environ.get("NASDAQ_CORE_DCA_CONFIG", DEFAULT_CONFIG_PATH))


def load_portfolio_config(path: Optional[Path] = None) -> dict[str, Any]:
    p = path or config_path_from_env()
    if not p.exists():
        return dict(DEFAULT_PORTFOLIO)
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    merged = dict(DEFAULT_PORTFOLIO)
    merged.update(data)
    return merged


def save_portfolio_config(cfg: dict[str, Any], path: Optional[Path] = None) -> Path:
    p = path or config_path_from_env()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return p


def _yf_close_series(ticker: str) -> pd.Series:
    """尽量稳健地拉取收盘价序列."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise SystemExit(
            "需要 yfinance: pip install yfinance pandas numpy\n"
            f"原始错误: {e}"
        ) from e

    last_err: Optional[Exception] = None
    for kwargs in (
        {"period": "2y", "auto_adjust": True, "progress": False, "threads": False},
        {
            "start": "2020-01-01",
            "auto_adjust": True,
            "progress": False,
            "threads": False,
        },
    ):
        try:
            data = yf.download(ticker, **kwargs)
            if data is None or data.empty:
                # 备用：Ticker.history
                t = yf.Ticker(ticker)
                data = t.history(period="2y", auto_adjust=True)
            if data is None or data.empty:
                continue
            if isinstance(data.columns, pd.MultiIndex):
                if "Close" in data.columns.get_level_values(0):
                    close = data["Close"]
                    if isinstance(close, pd.DataFrame):
                        close = (
                            close[ticker]
                            if ticker in close.columns
                            else close.iloc[:, 0]
                        )
                else:
                    close = data.iloc[:, 0]
            else:
                close = data["Close"] if "Close" in data.columns else data.iloc[:, 0]
            close = close.dropna().astype(float)
            if len(close) >= 200:
                return close
        except Exception as e:  # noqa: BLE001 — 网络/解析多种失败路径
            last_err = e
            continue
    msg = f"无法下载 {ticker} 行情，请检查网络；可改用 decide 手动输入价格"
    if last_err:
        msg += f"\n原始错误: {last_err}"
    raise SystemExit(msg)


def fetch_market_snapshot(ticker: str = "QQQ") -> "MarketSnapshot":
    """从 yfinance 拉取现价、滚动高点、12月低、MA200."""
    close = _yf_close_series(ticker)
    price = float(close.iloc[-1])
    rolling_high = float(close.cummax().iloc[-1])
    low_12m = float(close.tail(252).min())
    ma200 = float(close.tail(200).mean())
    dt = close.index[-1]
    date_s = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
    return MarketSnapshot(
        price=price,
        rolling_high=rolling_high,
        low_12m=low_12m,
        ma200=ma200,
        date=date_s,
    )

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class StrategyMode(str, Enum):
    DRAWDOWN = "drawdown"  # 策略 A：纯回撤分档
    MA200 = "ma200"  # 策略 B：回撤 + MA200
    BOTH = "both"  # 回测时两套都跑


class RebalanceStyle(str, Enum):
    BAND = "band"  # 越界拉回 30%/70% 边界
    TARGET = "target"  # 越界拉回 50% 中枢


@dataclass
class StrategyConfig:
    """可调策略参数（默认对齐文档 + 用户指定 30%–70% 宽区间）."""

    base_invest: float = 20_000.0  # 基准月定投 B（计划月投 2 万）
    equity_min: float = 0.30  # 股比下限
    equity_max: float = 0.70  # 股比上限
    target_equity: float = 0.50  # 目标中枢
    rebalance_style: RebalanceStyle = RebalanceStyle.BAND

    # 高位判定
    top_gain_threshold: float = 0.30  # 距 12 月低点涨幅
    top_invest_mult: float = 0.5  # 高位定投倍数（0 = 停投）
    ma_premium_threshold: float = 0.15  # P/MA200 - 1

    # 回撤分档倍数
    mult_shallow: float = 1.0  # dd > -10%
    mult_mild: float = 1.5  # -20% < dd <= -10%
    mult_deep: float = 2.0  # -30% < dd <= -20%
    mult_crash: float = 2.5  # dd <= -30%（策略 A）
    mult_crash_ma: float = 2.0  # 策略 B 深跌上限
    mult_mild_ma_near: float = 1.5  # 磨底（|premium|<=5%）
    mult_mild_ma_far: float = 1.2  # 轻度回撤但离均线远
    ma_near_band: float = 0.05  # |premium| 视为中枢

    lookback_days_12m: int = 252  # 约 12 个交易日月
    ma_window: int = 200


@dataclass
class MarketSnapshot:
    """某一决策日的市场状态."""

    price: float
    rolling_high: float
    low_12m: float
    ma200: Optional[float] = None
    date: Optional[str] = None

    @property
    def drawdown(self) -> float:
        if self.rolling_high <= 0:
            return 0.0
        return (self.price - self.rolling_high) / self.rolling_high

    @property
    def gain_from_12m_low(self) -> float:
        if self.low_12m <= 0:
            return 0.0
        return (self.price - self.low_12m) / self.low_12m

    @property
    def ma_premium(self) -> Optional[float]:
        if self.ma200 is None or self.ma200 <= 0:
            return None
        return (self.price - self.ma200) / self.ma200


@dataclass
class Portfolio:
    equity_value: float  # 纳指市值
    bond_value: float  # 短债/现金

    @property
    def total(self) -> float:
        return self.equity_value + self.bond_value

    @property
    def equity_weight(self) -> float:
        t = self.total
        return self.equity_value / t if t > 0 else 0.0

    def copy(self) -> "Portfolio":
        return Portfolio(self.equity_value, self.bond_value)


@dataclass
class MacroContext:
    """AI 三组指标宏观闸门状态."""

    enabled: bool = False
    pressure: str = "calm"  # calm / elevated / high / systemic
    gate: float = 1.0
    max_mult: Optional[float] = None
    bond_floor_months: float = 0.0
    target_equity: Optional[float] = None
    equity_max: Optional[float] = None
    label: str = "正常"
    source: str = "none"
    as_of: Optional[str] = None
    g1: str = "unknown"
    g2: str = "unknown"
    g3: str = "unknown"
    systemic_signal: bool = False
    summary: str = ""

    def profile_dict(self) -> dict[str, Any]:
        return MACRO_PROFILES.get(self.pressure, MACRO_PROFILES["calm"])


@dataclass
class Decision:
    """单次决策结果."""

    mode: str
    invest_amount: float
    invest_mult: float
    tier_label: str
    drawdown: float
    gain_12m: float
    ma_premium: Optional[float]
    equity_weight_before: float
    equity_weight_after_dca: float
    equity_weight_after_rebalance: float
    rebalance_action: str  # none / sell_equity / buy_equity
    rebalance_amount: float
    notes: list[str] = field(default_factory=list)
    # 宏观闸门审计字段
    price_mult: Optional[float] = None
    price_invest_plan: Optional[float] = None
    macro_pressure: Optional[str] = None
    macro_gate: Optional[float] = None
    bond_floor: Optional[float] = None
    bond_spendable: Optional[float] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["notes"] = " | ".join(self.notes)
        return d


def _status_str(group: Any) -> str:
    if not isinstance(group, dict):
        return "unknown"
    s = str(group.get("status") or "unknown").lower()
    return s if s in {"green", "yellow", "red", "unknown"} else "unknown"


def infer_pressure_from_snapshot(snap: dict[str, Any]) -> str:
    """从 ai-bubble snapshot 推断 pressure_level."""
    synth = snap.get("synthesis") or {}
    level = str(synth.get("pressure_level") or "").lower()
    if level in MACRO_PROFILES:
        return level
    if synth.get("systemic_signal") is True:
        return "systemic"

    g1 = _status_str(snap.get("group1_capital_coverage"))
    g2 = _status_str(snap.get("group2_demand_conversion"))
    g3 = _status_str(snap.get("group3_financing_pressure"))
    statuses = [g1, g2, g3]
    reds = sum(1 for s in statuses if s == "red")
    yellows = sum(1 for s in statuses if s == "yellow")
    if reds >= 3:
        return "systemic"
    if reds >= 2:
        return "high"
    if reds == 1 or yellows >= 2:
        return "elevated"
    if all(s == "green" for s in statuses):
        return "calm"
    return "elevated"


def find_latest_bubble_snapshot(
    root: Optional[Path] = None,
) -> Optional[Path]:
    """在 pi_workspace/output 下找最新的 ai-bubble-indicators snapshot.json."""
    root = root or Path(
        os.environ.get("AI_BUBBLE_OUTPUT_ROOT", DEFAULT_BUBBLE_OUTPUT_ROOT)
    )
    if not root.is_dir():
        return None
    candidates: list[Path] = []
    for p in root.glob("ai-bubble-indicators-*/snapshot.json"):
        # 跳过显式 test 目录
        if "-test" in p.parent.name.lower():
            continue
        candidates.append(p)
    if not candidates:
        # 兼容仅有 test 产物时
        candidates = list(root.glob("ai-bubble-indicators-*/snapshot.json"))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return candidates[0]


def load_macro_context(
    *,
    enabled: bool = True,
    snapshot_path: Optional[str | Path] = None,
    pressure_override: Optional[str] = None,
    output_root: Optional[Path] = None,
) -> MacroContext:
    """加载宏观闸门；失败时 disabled/calm，不阻断定投."""
    if not enabled:
        return MacroContext(enabled=False, pressure="calm", label="关闭")

    if pressure_override:
        p = str(pressure_override).lower()
        if p not in MACRO_PROFILES:
            raise ValueError(
                f"未知 macro pressure: {pressure_override}; "
                f"可选 {list(MACRO_PROFILES)}"
            )
        prof = MACRO_PROFILES[p]
        return MacroContext(
            enabled=True,
            pressure=p,
            gate=float(prof["gate"]),
            max_mult=prof["max_mult"],
            bond_floor_months=float(prof["bond_floor_months"]),
            target_equity=float(prof["target_equity"]),
            equity_max=float(prof["equity_max"]),
            label=str(prof["label"]),
            source=f"override:{p}",
        )

    path: Optional[Path] = None
    env_path = os.environ.get("AI_BUBBLE_SNAPSHOT")
    if snapshot_path:
        path = Path(snapshot_path).expanduser()
    elif env_path:
        path = Path(env_path).expanduser()
    else:
        path = find_latest_bubble_snapshot(output_root)

    if path is None or not path.exists():
        return MacroContext(
            enabled=True,
            pressure="calm",
            gate=1.0,
            source="missing_snapshot→calm",
            label="无快照(按正常)",
            summary="未找到 ai-bubble-indicators snapshot，宏观闸门按 calm 放行",
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return MacroContext(
            enabled=True,
            pressure="calm",
            gate=1.0,
            source=f"read_error:{path}",
            label="快照读取失败(按正常)",
            summary=str(exc),
        )

    pressure = infer_pressure_from_snapshot(data)
    prof = MACRO_PROFILES[pressure]
    meta = data.get("meta") or {}
    synth = data.get("synthesis") or {}
    return MacroContext(
        enabled=True,
        pressure=pressure,
        gate=float(prof["gate"]),
        max_mult=prof["max_mult"],
        bond_floor_months=float(prof["bond_floor_months"]),
        target_equity=float(prof["target_equity"]),
        equity_max=float(prof["equity_max"]),
        label=str(prof["label"]),
        source=str(path),
        as_of=meta.get("as_of"),
        g1=_status_str(data.get("group1_capital_coverage")),
        g2=_status_str(data.get("group2_demand_conversion")),
        g3=_status_str(data.get("group3_financing_pressure")),
        systemic_signal=bool(synth.get("systemic_signal")),
        summary=str(meta.get("summary") or ""),
    )


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def calc_invest_drawdown(snap: MarketSnapshot, cfg: StrategyConfig) -> tuple[float, float, str, list[str]]:
    """策略 A：纯回撤分档. 返回 (金额, 倍数, 档位标签, notes)."""
    notes: list[str] = []
    dd = snap.drawdown
    g = snap.gain_from_12m_low

    if g >= cfg.top_gain_threshold:
        mult = cfg.top_invest_mult
        label = "高位减投"
        notes.append(
            f"距12月低点涨幅 {g:.1%} ≥ {cfg.top_gain_threshold:.0%} → 减投"
        )
    elif dd > -0.10:
        mult = cfg.mult_shallow
        label = "常态"
        notes.append(f"回撤 {dd:.1%} > -10% → 基准定投")
    elif dd > -0.20:
        mult = cfg.mult_mild
        label = "轻度回撤加投"
        notes.append(f"回撤 {dd:.1%} 在 (-20%, -10%] → 1.5×")
    elif dd > -0.30:
        mult = cfg.mult_deep
        label = "中度回撤加投"
        notes.append(f"回撤 {dd:.1%} 在 (-30%, -20%] → 2.0×")
    else:
        mult = cfg.mult_crash
        label = "深度回撤加投"
        notes.append(f"回撤 {dd:.1%} ≤ -30% → 2.5×（受现金上限）")

    return cfg.base_invest * mult, mult, label, notes


def calc_invest_ma200(snap: MarketSnapshot, cfg: StrategyConfig) -> tuple[float, float, str, list[str]]:
    """策略 B：回撤 + MA200."""
    notes: list[str] = []
    dd = snap.drawdown
    g = snap.gain_from_12m_low
    prem = snap.ma_premium

    if prem is None:
        notes.append("MA200 缺失，回退到纯回撤规则")
        return calc_invest_drawdown(snap, cfg)

    # 顶部：均线上方过热 + 大涨
    if prem >= cfg.ma_premium_threshold and g >= cfg.top_gain_threshold:
        mult = cfg.top_invest_mult
        label = "顶部减投(MA+涨幅)"
        notes.append(
            f"MA溢价 {prem:.1%} ≥ {cfg.ma_premium_threshold:.0%} "
            f"且 12m涨幅 {g:.1%} ≥ {cfg.top_gain_threshold:.0%} → 减投"
        )
        return cfg.base_invest * mult, mult, label, notes

    if dd > -0.10:
        mult = cfg.mult_shallow
        label = "常态"
        notes.append(f"回撤 {dd:.1%} > -10% → 基准定投")
    elif dd > -0.20:
        if abs(prem) <= cfg.ma_near_band:
            mult = cfg.mult_mild_ma_near
            label = "磨底中枢加投"
            notes.append(
                f"回撤 {dd:.1%} + |MA溢价|={abs(prem):.1%}≤{cfg.ma_near_band:.0%} → 1.5×"
            )
        else:
            mult = cfg.mult_mild_ma_far
            label = "轻度回撤略加"
            notes.append(
                f"回撤 {dd:.1%} 但离均线较远 (溢价 {prem:.1%}) → 1.2×"
            )
    elif dd > -0.30:
        mult = cfg.mult_deep
        label = "中度回撤加投"
        notes.append(f"回撤 {dd:.1%} 在 (-30%, -20%] → 2.0×")
    else:
        mult = cfg.mult_crash_ma
        label = "深跌谨慎上限"
        notes.append(
            f"回撤 {dd:.1%} ≤ -30% → 2.0× 上限（避免单边下行耗尽火力）"
        )

    return cfg.base_invest * mult, mult, label, notes


def calc_invest(
    snap: MarketSnapshot, cfg: StrategyConfig, mode: StrategyMode
) -> tuple[float, float, str, list[str]]:
    if mode == StrategyMode.DRAWDOWN:
        return calc_invest_drawdown(snap, cfg)
    if mode == StrategyMode.MA200:
        return calc_invest_ma200(snap, cfg)
    raise ValueError(f"calc_invest 不支持 mode={mode}")


def apply_rebalance(
    port: Portfolio, cfg: StrategyConfig
) -> tuple[Portfolio, str, float]:
    """
    股比越出 [equity_min, equity_max] 时再平衡.
    band  : 拉回边界
    target: 拉回 target_equity
    返回 (新组合, 动作, 金额>0 表示买入权益 / 卖出权益用正数表示规模)
    """
    w = port.equity_weight
    total = port.total
    if total <= 0:
        return port, "none", 0.0

    if w > cfg.equity_max:
        target_w = (
            cfg.target_equity
            if cfg.rebalance_style == RebalanceStyle.TARGET
            else cfg.equity_max
        )
        target_eq = total * target_w
        sell = port.equity_value - target_eq
        if sell > 1e-9:
            new = Portfolio(target_eq, port.bond_value + sell)
            return new, "sell_equity", sell
        return port, "none", 0.0

    if w < cfg.equity_min:
        target_w = (
            cfg.target_equity
            if cfg.rebalance_style == RebalanceStyle.TARGET
            else cfg.equity_min
        )
        target_eq = total * target_w
        buy = target_eq - port.equity_value
        buy = min(buy, port.bond_value)  # 不能超过短债
        if buy > 1e-9:
            new = Portfolio(port.equity_value + buy, port.bond_value - buy)
            return new, "buy_equity", buy
        return port, "none", 0.0

    return port, "none", 0.0


def apply_macro_gate(
    price_amount: float,
    price_mult: float,
    label: str,
    notes: list[str],
    port: Portfolio,
    cfg: StrategyConfig,
    macro: Optional[MacroContext],
) -> tuple[float, float, str, list[str], StrategyConfig, float, float]:
    """
    把价格规则金额叠上宏观闸门。

    返回:
      gated_amount_plan, effective_mult, label, notes, cfg_for_rebalance,
      bond_floor, spendable
    """
    notes = list(notes)
    cfg_rb = StrategyConfig(**{**cfg.__dict__})
    bond_floor = 0.0
    spendable = max(port.bond_value, 0.0)

    if macro is None or not macro.enabled:
        return price_amount, price_mult, label, notes, cfg_rb, bond_floor, spendable

    # 临时收紧再平衡参数（不永久改用户配置文件）
    if macro.target_equity is not None:
        cfg_rb.target_equity = float(macro.target_equity)
    if macro.equity_max is not None:
        # 只收紧上限，不放宽用户更严的设置
        cfg_rb.equity_max = min(cfg.equity_max, float(macro.equity_max))

    gated_mult = price_mult * float(macro.gate)
    if macro.max_mult is not None:
        gated_mult = min(gated_mult, float(macro.max_mult))
    gated_amount = cfg.base_invest * gated_mult

    bond_floor = float(macro.bond_floor_months) * float(cfg.base_invest)
    # calm/elevated：地板只作蓄水目标提示，不硬挡定投（否则薄蓄水池会长期 0 投入）
    # high/systemic：地板硬约束，保弹药
    hard_floor = macro.pressure in {"high", "systemic"}
    if hard_floor:
        spendable = max(port.bond_value - bond_floor, 0.0)
    else:
        spendable = max(port.bond_value, 0.0)

    notes.append(
        f"宏观闸门 {macro.pressure}/{macro.label}: gate×{macro.gate:.2f}"
        + (f", max≤{macro.max_mult:.2f}×B" if macro.max_mult is not None else "")
        + f", 短债地板 {macro.bond_floor_months:.0f}×B={bond_floor:,.0f}"
        + ("（硬约束）" if hard_floor else "（目标提示）")
    )
    notes.append(
        f"宏观来源: {macro.source}"
        + (f" (as_of {macro.as_of})" if macro.as_of else "")
        + f" | G1={macro.g1} G2={macro.g2} G3={macro.g3}"
        + (" | SYSTEMIC" if macro.systemic_signal else "")
    )
    if abs(gated_amount - price_amount) > 1e-6:
        notes.append(
            f"价格规则 {price_amount:,.0f}（{price_mult:.2f}×）→ "
            f"宏观后计划 {gated_amount:,.0f}（{gated_mult:.2f}×）"
        )
    if (not hard_floor) and port.bond_value + 1e-6 < bond_floor:
        notes.append(
            f"短债 {port.bond_value:,.0f} 低于目标地板 {bond_floor:,.0f}，"
            f"建议优先蓄水；本月仍按闸门后金额执行（非硬挡）"
        )
    if hard_floor and spendable + 1e-6 < gated_amount:
        notes.append(
            f"短债可动用 {spendable:,.0f}（余额 {port.bond_value:,.0f} − 地板 {bond_floor:,.0f}）"
            f" < 计划 {gated_amount:,.0f}，将按可动用执行"
        )

    # 标签加上宏观后缀，便于日志扫读
    if macro.pressure != "calm":
        label = f"{label} · 宏观{macro.label}"

    return gated_amount, gated_mult, label, notes, cfg_rb, bond_floor, spendable


def make_decision(
    snap: MarketSnapshot,
    port: Portfolio,
    cfg: StrategyConfig,
    mode: StrategyMode,
    macro: Optional[MacroContext] = None,
) -> Decision:
    """完整一次月度决策：价格分档 → 宏观闸门 → 短债约束 → 再平衡."""
    price_amount, price_mult, label, notes = calc_invest(snap, cfg, mode)

    amount, mult, label, notes, cfg_rb, bond_floor, spendable = apply_macro_gate(
        price_amount, price_mult, label, notes, port, cfg, macro
    )

    # 可动用短债上限（含宏观地板）；若无宏观则 spendable=全部短债
    cash_cap = spendable if (macro and macro.enabled) else max(port.bond_value, 0.0)
    actual = min(amount, max(cash_cap, 0.0))
    if actual < amount - 1e-6:
        notes.append(f"现金/地板约束，计划 {amount:,.0f} 实际 {actual:,.0f}")

    after_dca = port.copy()
    after_dca.equity_value += actual
    after_dca.bond_value -= actual

    after_rb, rb_action, rb_amt = apply_rebalance(after_dca, cfg_rb)
    if rb_action != "none":
        notes.append(
            f"再平衡 {rb_action} {rb_amt:.0f} "
            f"(股比 {after_dca.equity_weight:.1%} → {after_rb.equity_weight:.1%}"
            f"; 上限 {cfg_rb.equity_max:.0%}/中枢 {cfg_rb.target_equity:.0%})"
        )

    return Decision(
        mode=mode.value,
        invest_amount=actual,
        invest_mult=mult,
        tier_label=label,
        drawdown=snap.drawdown,
        gain_12m=snap.gain_from_12m_low,
        ma_premium=snap.ma_premium,
        equity_weight_before=port.equity_weight,
        equity_weight_after_dca=after_dca.equity_weight,
        equity_weight_after_rebalance=after_rb.equity_weight,
        rebalance_action=rb_action,
        rebalance_amount=rb_amt,
        notes=notes,
        price_mult=price_mult,
        price_invest_plan=price_amount,
        macro_pressure=(macro.pressure if macro and macro.enabled else None),
        macro_gate=(macro.gate if macro and macro.enabled else None),
        bond_floor=bond_floor if (macro and macro.enabled) else None,
        bond_spendable=spendable if (macro and macro.enabled) else None,
    )


def resolve_macro_from_args(
    args: argparse.Namespace,
    pcfg: Optional[dict[str, Any]] = None,
) -> MacroContext:
    """统一从 CLI / portfolio.json / 环境变量解析宏观闸门."""
    pcfg = pcfg or {}
    # CLI 显式 --no-macro 优先
    if getattr(args, "no_macro", False):
        return MacroContext(enabled=False, pressure="calm", label="关闭", source="cli:--no-macro")

    enabled = getattr(args, "macro", None)
    if enabled is None:
        enabled = bool(pcfg.get("macro_gate_enabled", True))
    else:
        enabled = bool(enabled)

    override = getattr(args, "macro_pressure", None) or pcfg.get("macro_pressure_override")
    snap_path = getattr(args, "macro_snapshot", None) or pcfg.get("macro_snapshot")
    return load_macro_context(
        enabled=enabled,
        snapshot_path=snap_path,
        pressure_override=override,
    )


def print_macro_block(macro: MacroContext) -> None:
    if not macro.enabled:
        print("宏观闸门       : 关闭")
        return
    print(
        f"宏观闸门       : {macro.pressure} / {macro.label}  "
        f"(gate×{macro.gate:.2f}"
        + (f", max≤{macro.max_mult}×B" if macro.max_mult is not None else "")
        + f", 短债地板 {macro.bond_floor_months:.0f}×B)"
    )
    print(f"三组状态       : G1={macro.g1}  G2={macro.g2}  G3={macro.g3}")
    print(f"系统信号       : {'YES' if macro.systemic_signal else 'No'}")
    if macro.as_of or macro.source:
        print(f"快照           : as_of={macro.as_of or 'n/a'} | {macro.source}")
    if macro.summary:
        # 截断过长 summary
        s = macro.summary if len(macro.summary) <= 160 else macro.summary[:157] + "..."
        print(f"快照摘要       : {s}")


# ---------------------------------------------------------------------------
# CLI: decide
# ---------------------------------------------------------------------------


def cmd_decide(args: argparse.Namespace) -> int:
    cfg = StrategyConfig(
        base_invest=args.base,
        equity_min=args.equity_min,
        equity_max=args.equity_max,
        target_equity=args.target_equity,
        rebalance_style=RebalanceStyle(args.rebalance_style),
        top_invest_mult=args.top_mult,
    )
    mode = StrategyMode(args.mode)
    if mode == StrategyMode.BOTH:
        print("decide 模式请选择 drawdown 或 ma200", file=sys.stderr)
        return 2

    snap = MarketSnapshot(
        price=args.price,
        rolling_high=args.high,
        low_12m=args.low_12m,
        ma200=args.ma200,
        date=datetime.now().strftime("%Y-%m-%d"),
    )
    port = Portfolio(equity_value=args.equity, bond_value=args.bond)
    macro = resolve_macro_from_args(args)
    decision = make_decision(snap, port, cfg, mode, macro=macro)

    # 打印可读报告
    print("=" * 60)
    print("纳指定投决策报告")
    print("=" * 60)
    print(f"日期           : {snap.date}")
    print(f"策略模式       : {decision.mode}")
    print(f"现价 / 滚动高点: {snap.price:.2f} / {snap.rolling_high:.2f}")
    print(f"回撤           : {decision.drawdown:.2%}")
    print(f"距12月低点涨幅 : {decision.gain_12m:.2%}")
    if decision.ma_premium is not None:
        print(f"MA200 溢价     : {decision.ma_premium:.2%}")
    print("-" * 60)
    print_macro_block(macro)
    print("-" * 60)
    print(f"当前组合       : 权益 {port.equity_value:,.0f} + 短债 {port.bond_value:,.0f}")
    print(f"当前股比       : {port.equity_weight:.1%}")
    print(f"容忍区间       : {cfg.equity_min:.0%} – {cfg.equity_max:.0%}")
    print("-" * 60)
    if decision.price_mult is not None and decision.price_invest_plan is not None:
        print(
            f"价格档位       : {decision.price_mult:.2f}×B → 计划 {decision.price_invest_plan:,.0f} 元"
        )
    print(f"档位(含宏观)   : {decision.tier_label}  ({decision.invest_mult:.2f}×B)")
    if decision.bond_floor is not None:
        print(
            f"短债地板/可动用: {decision.bond_floor:,.0f} / {decision.bond_spendable or 0:,.0f} 元"
        )
    print(f"本月应投纳指   : {decision.invest_amount:,.0f} 元")
    print(f"定投后股比     : {decision.equity_weight_after_dca:.1%}")
    if decision.rebalance_action != "none":
        act = "卖出纳指→短债" if decision.rebalance_action == "sell_equity" else "短债→买入纳指"
        print(f"再平衡         : {act} {decision.rebalance_amount:,.0f} 元")
        print(f"再平衡后股比   : {decision.equity_weight_after_rebalance:.1%}")
    else:
        print("再平衡         : 无需（股比在区间内）")
    print("-" * 60)
    for n in decision.notes:
        print(f"  · {n}")
    print("=" * 60)

    # 操作清单
    print("\n【本月操作清单】")
    steps = []
    if args.monthly_income > 0:
        steps.append(f"1. 工资/现金流 {args.monthly_income:,.0f} 元 → 全部进入短债蓄水池")
        i = 2
    else:
        i = 1
    if decision.invest_amount > 0:
        steps.append(f"{i}. 从短债划转 {decision.invest_amount:,.0f} 元 申购纳指基金")
        i += 1
    else:
        steps.append(f"{i}. 本月暂停/零定投，短债继续蓄水")
        i += 1
    if decision.rebalance_action == "sell_equity":
        steps.append(f"{i}. 赎回纳指 {decision.rebalance_amount:,.0f} 元 → 转入短债（股比压回上限）")
    elif decision.rebalance_action == "buy_equity":
        steps.append(f"{i}. 额外从短债买入纳指 {decision.rebalance_amount:,.0f} 元（股比拉回下限）")
    else:
        steps.append(f"{i}. 无需再平衡")
    for s in steps:
        print(s)

    if args.export:
        path = Path(args.export)
        path.parent.mkdir(parents=True, exist_ok=True)
        row = decision.to_dict()
        row.update(
            {
                "date": snap.date,
                "price": snap.price,
                "rolling_high": snap.rolling_high,
                "low_12m": snap.low_12m,
                "ma200": snap.ma200,
                "equity": port.equity_value,
                "bond": port.bond_value,
            }
        )
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            w.writeheader()
            w.writerow(row)
        print(f"\n已导出: {path}")

    return 0


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------


def _month_ends(prices: pd.Series) -> pd.DatetimeIndex:
    """每月最后一个交易日."""
    df = prices.to_frame("p")
    df["ym"] = df.index.to_period("M")
    # 每月最后一行
    idx = df.groupby("ym").tail(1).index
    return pd.DatetimeIndex(idx)


def prepare_price_frame(close: pd.Series, cfg: StrategyConfig) -> pd.DataFrame:
    """从日线收盘价构造决策所需字段."""
    close = close.dropna().sort_index()
    df = pd.DataFrame({"price": close})
    df["rolling_high"] = df["price"].cummax()
    df["low_12m"] = df["price"].rolling(cfg.lookback_days_12m, min_periods=20).min()
    df["ma200"] = df["price"].rolling(cfg.ma_window, min_periods=cfg.ma_window).mean()
    return df


def run_backtest(
    close: pd.Series,
    cfg: StrategyConfig,
    mode: StrategyMode,
    initial_equity: float,
    initial_bond: float,
    monthly_income: float,
    ticker: str = "QQQ",
) -> pd.DataFrame:
    """
    月度回测:
      - 每月末: 收入进短债 → 按规则定投 → 再平衡
      - 权益市值随价格比例变动
    """
    if mode == StrategyMode.BOTH:
        raise ValueError("run_backtest 单次只跑一种 mode")

    df = prepare_price_frame(close, cfg)
    month_ends = _month_ends(df["price"])
    # 等 MA200 就绪后再开始
    ready = df["ma200"].first_valid_index()
    if ready is None:
        raise RuntimeError("价格序列太短，无法计算 MA200")
    month_ends = month_ends[month_ends >= ready]

    port = Portfolio(initial_equity, initial_bond)
    last_price = float(df.loc[month_ends[0], "price"])
    records = []

    for dt in month_ends:
        row = df.loc[dt]
        px = float(row["price"])
        # 权益随价格变动
        if last_price > 0:
            port.equity_value *= px / last_price
        last_price = px

        # 月度收入进短债
        if monthly_income > 0:
            port.bond_value += monthly_income

        snap = MarketSnapshot(
            price=px,
            rolling_high=float(row["rolling_high"]),
            low_12m=float(row["low_12m"]) if pd.notna(row["low_12m"]) else px,
            ma200=float(row["ma200"]) if pd.notna(row["ma200"]) else None,
            date=dt.strftime("%Y-%m-%d"),
        )
        decision = make_decision(snap, port, cfg, mode)

        # 执行定投
        invest = decision.invest_amount
        port.equity_value += invest
        port.bond_value -= invest

        # 执行再平衡
        port, rb_action, rb_amt = apply_rebalance(port, cfg)

        records.append(
            {
                "date": dt,
                "price": px,
                "drawdown": snap.drawdown,
                "gain_12m": snap.gain_from_12m_low,
                "ma_premium": snap.ma_premium,
                "tier": decision.tier_label,
                "mult": decision.invest_mult,
                "invest": invest,
                "rebalance_action": rb_action,
                "rebalance_amount": rb_amt,
                "equity": port.equity_value,
                "bond": port.bond_value,
                "total": port.total,
                "equity_weight": port.equity_weight,
                "mode": mode.value,
                "ticker": ticker,
            }
        )

    return pd.DataFrame(records).set_index("date")


def summarize_backtest(bt: pd.DataFrame, label: str) -> dict:
    if bt.empty:
        return {"label": label, "error": "empty"}
    total0 = float(bt["total"].iloc[0])
    total1 = float(bt["total"].iloc[-1])
    years = max((bt.index[-1] - bt.index[0]).days / 365.25, 1e-9)
    cagr = (total1 / total0) ** (1 / years) - 1 if total0 > 0 else float("nan")
    # 月度收益近似
    rets = bt["total"].pct_change().dropna()
    vol = float(rets.std() * np.sqrt(12)) if len(rets) > 1 else float("nan")
    # 最大回撤
    peak = bt["total"].cummax()
    dd = (bt["total"] - peak) / peak
    max_dd = float(dd.min())
    avg_w = float(bt["equity_weight"].mean())
    min_w = float(bt["equity_weight"].min())
    max_w = float(bt["equity_weight"].max())
    n_rb = int((bt["rebalance_action"] != "none").sum())
    total_invest = float(bt["invest"].sum())

    return {
        "label": label,
        "start": str(bt.index[0].date()),
        "end": str(bt.index[-1].date()),
        "years": round(years, 2),
        "final_total": round(total1, 0),
        "cagr": cagr,
        "ann_vol": vol,
        "max_drawdown": max_dd,
        "avg_equity_weight": avg_w,
        "min_equity_weight": min_w,
        "max_equity_weight": max_w,
        "rebalance_count": n_rb,
        "total_dca_invested": round(total_invest, 0),
        "n_months": len(bt),
    }


def print_summary(s: dict) -> None:
    print(f"\n── {s['label']} ──")
    if "error" in s:
        print(s["error"])
        return
    print(f"区间       : {s['start']} → {s['end']}  ({s['years']} 年, {s['n_months']} 个月)")
    print(f"期末总资产 : {s['final_total']:,.0f}")
    print(f"年化收益   : {s['cagr']:.2%}")
    print(f"年化波动   : {s['ann_vol']:.2%}")
    print(f"最大回撤   : {s['max_drawdown']:.2%}")
    print(
        f"股比 均/低/高: {s['avg_equity_weight']:.1%} / "
        f"{s['min_equity_weight']:.1%} / {s['max_equity_weight']:.1%}"
    )
    print(f"再平衡次数 : {s['rebalance_count']}")
    print(f"累计定投   : {s['total_dca_invested']:,.0f}")


def _buy_and_hold_benchmark(
    close: pd.Series,
    initial_equity: float,
    initial_bond: float,
    monthly_income: float,
    month_ends: pd.DatetimeIndex,
) -> pd.DataFrame:
    """基准: 50/50 起始，每月收入全买纳指，不做再平衡/动态倍数."""
    port_eq = initial_equity
    port_bd = initial_bond
    last_px = float(close.loc[month_ends[0]])
    rows = []
    for dt in month_ends:
        px = float(close.loc[dt])
        port_eq *= px / last_px
        last_px = px
        if monthly_income > 0:
            # 收入一半进股一半进债（静态）
            port_eq += monthly_income * 0.5
            port_bd += monthly_income * 0.5
        total = port_eq + port_bd
        rows.append(
            {
                "date": dt,
                "total": total,
                "equity": port_eq,
                "bond": port_bd,
                "equity_weight": port_eq / total if total else 0,
                "invest": monthly_income * 0.5,
                "rebalance_action": "none",
            }
        )
    return pd.DataFrame(rows).set_index("date")


def cmd_backtest(args: argparse.Namespace) -> int:
    try:
        import yfinance as yf
    except ImportError:
        print("请先安装: pip install yfinance pandas numpy", file=sys.stderr)
        return 1

    cfg = StrategyConfig(
        base_invest=args.base,
        equity_min=args.equity_min,
        equity_max=args.equity_max,
        target_equity=args.target_equity,
        rebalance_style=RebalanceStyle(args.rebalance_style),
        top_invest_mult=args.top_mult,
    )

    print(f"下载 {args.ticker} {args.start} → {args.end or 'today'} ...")
    data = yf.download(
        args.ticker,
        start=args.start,
        end=args.end,
        auto_adjust=True,
        progress=False,
    )
    if data.empty:
        print("无数据，请检查 ticker/日期", file=sys.stderr)
        return 1

    # yfinance 多级列兼容
    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"][args.ticker] if args.ticker in data["Close"].columns else data["Close"].iloc[:, 0]
    else:
        close = data["Close"]
    close = close.dropna().astype(float)

    modes: list[StrategyMode]
    if args.mode == "both":
        modes = [StrategyMode.DRAWDOWN, StrategyMode.MA200]
    else:
        modes = [StrategyMode(args.mode)]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    for mode in modes:
        print(f"\n运行回测 mode={mode.value} ...")
        bt = run_backtest(
            close=close,
            cfg=cfg,
            mode=mode,
            initial_equity=args.initial_equity,
            initial_bond=args.initial_bond,
            monthly_income=args.monthly_income,
            ticker=args.ticker,
        )
        s = summarize_backtest(bt, f"策略-{mode.value}")
        print_summary(s)
        summaries.append(s)
        csv_path = out_dir / f"backtest_{args.ticker}_{mode.value}.csv"
        bt.to_csv(csv_path)
        print(f"明细已保存: {csv_path}")

    # 基准
    df_prep = prepare_price_frame(close, cfg)
    ready = df_prep["ma200"].first_valid_index()
    month_ends = _month_ends(close)
    month_ends = month_ends[month_ends >= ready]
    bench = _buy_and_hold_benchmark(
        close,
        args.initial_equity,
        args.initial_bond,
        args.monthly_income,
        month_ends,
    )
    # 对齐字段以便 summarize
    if "drawdown" not in bench.columns:
        bench["drawdown"] = np.nan
        bench["gain_12m"] = np.nan
        bench["ma_premium"] = np.nan
        bench["tier"] = "static_50_50"
        bench["mult"] = 0.5
        bench["rebalance_amount"] = 0.0
        bench["price"] = close.reindex(bench.index).values
        bench["mode"] = "benchmark"
        bench["ticker"] = args.ticker
    sb = summarize_backtest(bench, "基准-静态50/50月投")
    print_summary(sb)
    bench.to_csv(out_dir / f"backtest_{args.ticker}_benchmark.csv")

    # 对比表
    print("\n" + "=" * 60)
    print("对比摘要")
    print("=" * 60)
    all_s = summaries + [sb]
    try:
        from tabulate import tabulate

        table = [
            [
                x["label"],
                f"{x['cagr']:.2%}",
                f"{x['max_drawdown']:.2%}",
                f"{x['ann_vol']:.2%}",
                f"{x['avg_equity_weight']:.1%}",
                x["rebalance_count"],
                f"{x['final_total']:,.0f}",
            ]
            for x in all_s
        ]
        print(
            tabulate(
                table,
                headers=["策略", "年化", "最大回撤", "波动", "平均股比", "再平衡次数", "期末"],
                tablefmt="simple",
            )
        )
    except ImportError:
        for x in all_s:
            print(
                f"{x['label']}: CAGR={x['cagr']:.2%} MDD={x['max_drawdown']:.2%} "
                f"终值={x['final_total']:,.0f}"
            )

    print(
        f"\n参数: B={cfg.base_invest:.0f}, 股比区间="
        f"[{cfg.equity_min:.0%},{cfg.equity_max:.0%}], "
        f"再平衡={cfg.rebalance_style.value}, 月收入={args.monthly_income:.0f}"
    )
    print("注意: 回测未计入 QDII 溢价、申赎费、汇率与限购。")
    return 0


# ---------------------------------------------------------------------------
# Demo (offline synthetic) — 无网时自检
# ---------------------------------------------------------------------------


def cmd_demo(_: argparse.Namespace) -> int:
    """用合成价格序列演示决策链路."""
    rng = np.random.default_rng(42)
    n = 800
    # 随机游走 + 一段深跌
    rets = rng.normal(0.0004, 0.012, n)
    rets[500:580] = rng.normal(-0.004, 0.02, 80)  # 熊市段
    price = 100 * np.cumprod(1 + rets)
    idx = pd.bdate_range("2018-01-01", periods=n)
    close = pd.Series(price, index=idx, name="close")

    cfg = StrategyConfig(base_invest=20_000, equity_min=0.30, equity_max=0.70)
    for mode in (StrategyMode.DRAWDOWN, StrategyMode.MA200):
        bt = run_backtest(
            close,
            cfg,
            mode,
            initial_equity=100_000,
            initial_bond=100_000,
            monthly_income=20_000,
            ticker="SYN",
        )
        print_summary(summarize_backtest(bt, f"demo-{mode.value}"))
        print(bt[["price", "drawdown", "tier", "invest", "equity_weight", "total"]].tail(8))
        print()
    return 0


def cmd_init_config(args: argparse.Namespace) -> int:
    """初始化 ~/.nasdaq_core_dca/portfolio.json"""
    path = Path(args.config) if args.config else config_path_from_env()
    if path.exists() and not args.force:
        print(f"配置已存在: {path}")
        print("如需覆盖请加 --force")
        return 1
    cfg = dict(DEFAULT_PORTFOLIO)
    if args.equity is not None:
        cfg["equity_value"] = args.equity
    if args.bond is not None:
        cfg["bond_value"] = args.bond
    if args.base is not None:
        cfg["base_invest"] = args.base
        cfg["monthly_income"] = args.base
    if args.mode:
        cfg["mode"] = args.mode
    saved = save_portfolio_config(cfg, path)
    print(f"已写入配置: {saved}")
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    print("\n请编辑 equity_value / bond_value 为当前持仓市值后，发薪日运行:")
    print(f"  python {Path(__file__).name} payday")
    return 0


def cmd_show_config(args: argparse.Namespace) -> int:
    path = Path(args.config) if args.config else config_path_from_env()
    cfg = load_portfolio_config(path)
    print(f"配置文件: {path} {'(存在)' if path.exists() else '(使用默认，尚未 init)'}")
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    return 0


def cmd_set_holdings(args: argparse.Namespace) -> int:
    """更新持仓市值."""
    path = Path(args.config) if args.config else config_path_from_env()
    cfg = load_portfolio_config(path)
    if args.equity is not None:
        cfg["equity_value"] = args.equity
    if args.bond is not None:
        cfg["bond_value"] = args.bond
    if args.base is not None:
        cfg["base_invest"] = args.base
    if args.income is not None:
        cfg["monthly_income"] = args.income
    saved = save_portfolio_config(cfg, path)
    print(f"已更新: {saved}")
    print(
        f"权益 {cfg['equity_value']:,.0f} | 短债 {cfg['bond_value']:,.0f} | "
        f"B={cfg['base_invest']:,.0f}"
    )
    return 0


def cmd_payday(args: argparse.Namespace) -> int:
    """
    发薪日一键决策:
      1) 读 portfolio.json 持仓
      2) 自动拉 QQQ 行情算回撤/MA200
      3) 输出本月操作清单
    """
    path = Path(args.config) if args.config else config_path_from_env()
    pcfg = load_portfolio_config(path)

    equity = args.equity if args.equity is not None else float(pcfg["equity_value"])
    bond = args.bond if args.bond is not None else float(pcfg["bond_value"])
    base = args.base if args.base is not None else float(pcfg["base_invest"])
    income = (
        args.monthly_income
        if args.monthly_income is not None
        else float(pcfg.get("monthly_income", base))
    )
    mode_s = args.mode or pcfg.get("mode", "ma200")
    ticker = args.ticker or pcfg.get("ticker", "QQQ")

    if equity <= 0 and bond <= 0 and not args.allow_empty:
        print(
            "持仓为 0。请先设置市值:\n"
            f"  python {Path(__file__).name} set-holdings --equity <纳指市值> --bond <短债余额>\n"
            "或 payday --equity ... --bond ...",
            file=sys.stderr,
        )
        return 2

    # 工资先进入短债（决策时用含工资后的短债）
    bond_after_income = bond + income

    print(f"拉取 {ticker} 行情...")
    snap = fetch_market_snapshot(ticker)
    print(
        f"行情日 {snap.date}: P={snap.price:.2f} H={snap.rolling_high:.2f} "
        f"L12={snap.low_12m:.2f} MA200={snap.ma200:.2f}"
    )

    cfg = StrategyConfig(
        base_invest=base,
        equity_min=float(pcfg.get("equity_min", 0.30)),
        equity_max=float(pcfg.get("equity_max", 0.70)),
        target_equity=float(pcfg.get("target_equity", 0.50)),
        rebalance_style=RebalanceStyle(pcfg.get("rebalance_style", "band")),
        top_invest_mult=float(
            args.top_mult if args.top_mult is not None else pcfg.get("top_mult", 0.5)
        ),
    )
    # CLI 覆盖区间
    if args.equity_min is not None:
        cfg.equity_min = args.equity_min
    if args.equity_max is not None:
        cfg.equity_max = args.equity_max

    mode = StrategyMode(mode_s)
    port = Portfolio(equity_value=equity, bond_value=bond_after_income)
    macro = resolve_macro_from_args(args, pcfg)
    decision = make_decision(snap, port, cfg, mode, macro=macro)

    print("=" * 60)
    print("发薪日 · 纳指定投决策")
    print("=" * 60)
    print(f"配置文件       : {path}")
    print(f"标的 / 策略     : {ticker} / {mode.value}")
    print(f"行情日         : {snap.date}")
    print(f"现价 / 滚动高点: {snap.price:.2f} / {snap.rolling_high:.2f}")
    print(f"回撤           : {decision.drawdown:.2%}")
    print(f"距12月低点涨幅 : {decision.gain_12m:.2%}")
    if decision.ma_premium is not None:
        print(f"MA200 溢价     : {decision.ma_premium:.2%}")
    print("-" * 60)
    print_macro_block(macro)
    print("-" * 60)
    print(f"发薪前持仓     : 权益 {equity:,.0f} + 短债 {bond:,.0f}")
    print(f"本月工资入池   : {income:,.0f} → 短债变为 {bond_after_income:,.0f}")
    print(f"当前股比(含工资): {port.equity_weight:.1%}")
    print(f"容忍区间       : {cfg.equity_min:.0%} – {cfg.equity_max:.0%}")
    print(f"基准月投 B     : {base:,.0f}")
    print("-" * 60)
    if decision.price_mult is not None and decision.price_invest_plan is not None:
        print(
            f"价格档位       : {decision.price_mult:.2f}×B → 计划 {decision.price_invest_plan:,.0f} 元"
        )
    print(f"档位(含宏观)   : {decision.tier_label}  ({decision.invest_mult:.2f}×B)")
    if decision.bond_floor is not None:
        print(
            f"短债地板/可动用: {decision.bond_floor:,.0f} / {decision.bond_spendable or 0:,.0f} 元"
        )
    print(f"本月应投纳指   : {decision.invest_amount:,.0f} 元")
    print(f"定投后股比     : {decision.equity_weight_after_dca:.1%}")
    if decision.rebalance_action != "none":
        act = (
            "卖出纳指→短债"
            if decision.rebalance_action == "sell_equity"
            else "短债→买入纳指"
        )
        print(f"再平衡         : {act} {decision.rebalance_amount:,.0f} 元")
        print(f"再平衡后股比   : {decision.equity_weight_after_rebalance:.1%}")
    else:
        print("再平衡         : 无需（股比在区间内）")
    print("-" * 60)
    for n in decision.notes:
        print(f"  · {n}")
    print("=" * 60)

    print("\n【本月操作清单】")
    print(f"1. 工资/现金流 {income:,.0f} 元 → 全部进入短债蓄水池")
    if decision.invest_amount > 0:
        print(f"2. 从短债划转 {decision.invest_amount:,.0f} 元 申购纳指基金")
    else:
        print("2. 本月暂停/零定投，短债继续蓄水")
    if decision.rebalance_action == "sell_equity":
        print(
            f"3. 赎回纳指 {decision.rebalance_amount:,.0f} 元 → 转入短债（股比压回上限）"
        )
    elif decision.rebalance_action == "buy_equity":
        print(
            f"3. 额外从短债买入纳指 {decision.rebalance_amount:,.0f} 元（股比拉回下限）"
        )
    else:
        print("3. 无需再平衡")
    print(
        "4. 操作完成后更新持仓:\n"
        f"   python {Path(__file__).name} set-holdings "
        f"--equity <新市值> --bond <新短债余额>"
    )

    if args.export:
        out = Path(args.export)
        out.parent.mkdir(parents=True, exist_ok=True)
        row = decision.to_dict()
        row.update(
            {
                "date": snap.date,
                "ticker": ticker,
                "price": snap.price,
                "rolling_high": snap.rolling_high,
                "low_12m": snap.low_12m,
                "ma200": snap.ma200,
                "equity_before": equity,
                "bond_before": bond,
                "income": income,
                "bond_after_income": bond_after_income,
            }
        )
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            w.writeheader()
            w.writerow(row)
        print(f"\n已导出: {out}")

    # 可选：写决策日志
    if args.log:
        log_dir = path.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"payday_{datetime.now().strftime('%Y%m%d')}.json"
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "ticker": ticker,
            "snapshot": {
                "date": snap.date,
                "price": snap.price,
                "rolling_high": snap.rolling_high,
                "low_12m": snap.low_12m,
                "ma200": snap.ma200,
            },
            "portfolio": {
                "equity": equity,
                "bond": bond,
                "income": income,
            },
            "macro": asdict(macro),
            "decision": decision.to_dict(),
        }
        with log_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"决策日志: {log_path}")

    return 0


def cmd_market(args: argparse.Namespace) -> int:
    """只查看当前市场状态（不决策）."""
    ticker = args.ticker or "QQQ"
    snap = fetch_market_snapshot(ticker)
    print(f"{ticker} @ {snap.date}")
    print(f"  现价       : {snap.price:.2f}")
    print(f"  滚动最高   : {snap.rolling_high:.2f}")
    print(f"  回撤       : {snap.drawdown:.2%}")
    print(f"  12月最低   : {snap.low_12m:.2f}")
    print(f"  12月涨幅   : {snap.gain_from_12m_low:.2%}")
    print(f"  MA200      : {snap.ma200:.2f}")
    if snap.ma_premium is not None:
        print(f"  MA200溢价  : {snap.ma_premium:.2%}")
    return 0


def cmd_macro_status(args: argparse.Namespace) -> int:
    """只查看宏观闸门（不拉行情、不定投）."""
    path = Path(args.config) if getattr(args, "config", None) else config_path_from_env()
    pcfg = load_portfolio_config(path)
    macro = resolve_macro_from_args(args, pcfg)
    print("=" * 60)
    print("AI 泡沫三组指标 · 宏观闸门")
    print("=" * 60)
    print_macro_block(macro)
    if macro.enabled and macro.pressure in MACRO_PROFILES:
        prof = MACRO_PROFILES[macro.pressure]
        print("-" * 60)
        print("生效参数:")
        print(f"  gate              : ×{prof['gate']}")
        print(f"  max_mult          : {prof['max_mult']}")
        print(f"  bond_floor_months : {prof['bond_floor_months']}")
        print(f"  target_equity     : {prof['target_equity']:.0%}")
        print(f"  equity_max        : {prof['equity_max']:.0%}")
        print(
            "公式: 实际投入 = min(价格倍数×gate×B, max_mult×B, 短债−地板×B)"
        )
    print("=" * 60)
    return 0


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="纳指核心底仓动态定投策略（回撤分档 / MA200 + 股比30%–70%）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # shared portfolio / band args
    def add_band_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--base", type=float, default=20_000, help="基准月定投 B（默认 2 万）")
        sp.add_argument("--equity-min", type=float, default=0.30, help="股比下限")
        sp.add_argument("--equity-max", type=float, default=0.70, help="股比上限")
        sp.add_argument("--target-equity", type=float, default=0.50, help="目标中枢")
        sp.add_argument(
            "--rebalance-style",
            choices=["band", "target"],
            default="band",
            help="越界时拉回边界或中枢",
        )
        sp.add_argument(
            "--top-mult",
            type=float,
            default=0.5,
            help="高位定投倍数（0=停投）",
        )

    def add_macro_args(sp: argparse.ArgumentParser) -> None:
        g = sp.add_mutually_exclusive_group()
        g.add_argument(
            "--macro",
            dest="macro",
            action="store_true",
            default=None,
            help="强制开启 AI 三组指标宏观闸门",
        )
        g.add_argument(
            "--no-macro",
            dest="no_macro",
            action="store_true",
            help="关闭宏观闸门（仅价格规则）",
        )
        sp.add_argument(
            "--macro-pressure",
            choices=list(MACRO_PROFILES.keys()),
            default=None,
            help="手动指定压力级（覆盖 snapshot）",
        )
        sp.add_argument(
            "--macro-snapshot",
            default=None,
            help="ai-bubble-indicators 的 snapshot.json 路径",
        )

    # init-config
    ic = sub.add_parser("init-config", help="初始化 ~/.nasdaq_core_dca/portfolio.json")
    ic.add_argument("--config", default=None, help="配置路径")
    ic.add_argument("--equity", type=float, default=None)
    ic.add_argument("--bond", type=float, default=None)
    ic.add_argument("--base", type=float, default=20_000)
    ic.add_argument("--mode", choices=["drawdown", "ma200"], default="ma200")
    ic.add_argument("--force", action="store_true")
    ic.set_defaults(func=cmd_init_config)

    # show-config
    sc = sub.add_parser("show-config", help="查看持仓配置")
    sc.add_argument("--config", default=None)
    sc.set_defaults(func=cmd_show_config)

    # set-holdings
    sh = sub.add_parser("set-holdings", help="更新纳指/短债市值")
    sh.add_argument("--config", default=None)
    sh.add_argument("--equity", type=float, default=None, help="纳指市值")
    sh.add_argument("--bond", type=float, default=None, help="短债余额")
    sh.add_argument("--base", type=float, default=None, help="基准月投 B")
    sh.add_argument("--income", type=float, default=None, help="月工资/现金流")
    sh.set_defaults(func=cmd_set_holdings)

    # payday — 发薪日主入口
    pd_ = sub.add_parser("payday", help="发薪日一键决策（自动拉行情）")
    pd_.add_argument("--config", default=None, help="portfolio.json 路径")
    pd_.add_argument("--equity", type=float, default=None, help="覆盖配置中的纳指市值")
    pd_.add_argument("--bond", type=float, default=None, help="覆盖配置中的短债（发薪前）")
    pd_.add_argument("--base", type=float, default=None, help="覆盖基准月投 B")
    pd_.add_argument("--monthly-income", type=float, default=None, help="本月工资")
    pd_.add_argument("--mode", choices=["drawdown", "ma200"], default=None)
    pd_.add_argument("--ticker", default=None, help="默认 QQQ")
    pd_.add_argument("--equity-min", type=float, default=None)
    pd_.add_argument("--equity-max", type=float, default=None)
    pd_.add_argument("--top-mult", type=float, default=None)
    pd_.add_argument("--export", type=str, default=None)
    pd_.add_argument("--log", action="store_true", help="写入 ~/.nasdaq_core_dca/logs/")
    pd_.add_argument(
        "--allow-empty",
        action="store_true",
        help="允许持仓为 0（首次建仓）",
    )
    add_macro_args(pd_)
    pd_.set_defaults(func=cmd_payday)

    # market
    mk = sub.add_parser("market", help="只查看 QQQ 回撤/MA200 状态")
    mk.add_argument("--ticker", default="QQQ")
    mk.set_defaults(func=cmd_market)

    # decide
    d = sub.add_parser("decide", help="手动输入价格与持仓做决策")
    d.add_argument("--price", type=float, required=True, help="当前价格/净值")
    d.add_argument("--high", type=float, required=True, help="滚动最高价")
    d.add_argument("--low-12m", type=float, required=True, help="近12个月最低价")
    d.add_argument("--ma200", type=float, default=None, help="200日均线（ma200模式需要）")
    d.add_argument("--equity", type=float, required=True, help="当前纳指市值")
    d.add_argument("--bond", type=float, required=True, help="当前短债/现金")
    d.add_argument(
        "--mode",
        choices=["drawdown", "ma200"],
        default="ma200",
        help="定投规则",
    )
    d.add_argument("--monthly-income", type=float, default=0, help="本月新进现金流（展示用）")
    d.add_argument("--export", type=str, default=None, help="导出 CSV 路径")
    add_band_args(d)
    add_macro_args(d)
    d.set_defaults(func=cmd_decide)

    # macro-status — 只看闸门
    ms = sub.add_parser("macro-status", help="查看 AI 三组指标宏观闸门状态")
    ms.add_argument("--config", default=None)
    add_macro_args(ms)
    ms.set_defaults(func=cmd_macro_status)

    # backtest
    b = sub.add_parser("backtest", help="用历史行情回测")
    b.add_argument("--ticker", default="QQQ", help="标的代码")
    b.add_argument("--start", default="2010-01-01")
    b.add_argument("--end", default=None)
    b.add_argument(
        "--mode",
        choices=["drawdown", "ma200", "both"],
        default="both",
    )
    b.add_argument("--initial-equity", type=float, default=200_000)
    b.add_argument("--initial-bond", type=float, default=200_000)
    b.add_argument(
        "--monthly-income",
        type=float,
        default=20_000,
        help="每月流入蓄水池金额（默认与 B 同为 2 万）",
    )
    b.add_argument("--out-dir", default="out", help="回测结果目录")
    add_band_args(b)
    b.set_defaults(func=cmd_backtest)

    # demo
    m = sub.add_parser("demo", help="离线合成数据自检")
    m.set_defaults(func=cmd_demo)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
