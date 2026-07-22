#!/usr/bin/env python3
"""Generate AI bubble three-group indicator report and optionally email it."""

from __future__ import annotations

import argparse
import html
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

DEFAULT_TO = "xiechao06@gmail.com"
PI_EMAIL_CONFIG = Path.home() / ".pi" / "email-config.json"
LOCAL_ENV = Path.home() / ".ai_bubble_indicators" / ".env"
# Fallbacks used on this machine when Gmail SMTP is blocked/unreliable.
FALLBACK_ENV_FILES = [
    Path.home() / ".etf_premium_monitor" / ".env",
    Path.home() / ".qdii_limits_cache" / ".env",
]

STATUS_EMOJI = {
    "green": "🟢",
    "yellow": "🟡",
    "red": "🔴",
    "unknown": "⚪",
}


def _load_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _cfg_from_env_map(env_vars: dict[str, str], base: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(base or {})
    if env_vars.get("SMTP_HOST"):
        cfg["host"] = env_vars.get("SMTP_HOST", cfg.get("host", ""))
    if env_vars.get("SMTP_PORT"):
        cfg["port"] = int(env_vars.get("SMTP_PORT", cfg.get("port", 587)))
    if env_vars.get("SMTP_USER"):
        cfg["user"] = env_vars.get("SMTP_USER", cfg.get("user", ""))
    if env_vars.get("SMTP_PASS"):
        cfg["password"] = env_vars.get("SMTP_PASS", cfg.get("password", ""))
    if env_vars.get("FROM_NAME"):
        cfg["from_name"] = env_vars.get("FROM_NAME", cfg.get("from_name", "AI Bubble Monitor"))
    if env_vars.get("NOTIFY_EMAILS"):
        # Keep recipient default as user mailbox unless explicitly overridden later.
        cfg["default_to"] = env_vars.get("NOTIFY_EMAILS", cfg.get("default_to", DEFAULT_TO))
    return cfg


def _smtp_ready(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("host") and cfg.get("user") and cfg.get("password"))


def load_smtp_config() -> dict[str, Any]:
    """Load SMTP credentials with practical fallbacks.

    Priority:
    1) process env vars (if complete)
    2) ~/.ai_bubble_indicators/.env
    3) ~/.etf_premium_monitor/.env / ~/.qdii_limits_cache/.env (known-good on this machine)
    4) ~/.pi/email-config.json (may be Gmail; can fail in some networks)
    """
    cfg: dict[str, Any] = {
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "587") or 587),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASS", ""),
        "from_name": os.environ.get("FROM_NAME", "AI Bubble Monitor"),
        # Always default report destination to the user's Gmail unless overridden.
        "default_to": DEFAULT_TO,
    }
    if os.environ.get("NOTIFY_EMAILS"):
        cfg["default_to"] = os.environ["NOTIFY_EMAILS"]
    if _smtp_ready(cfg):
        cfg["source"] = "env"
        return cfg

    local = _load_dotenv(LOCAL_ENV)
    if local:
        cfg = _cfg_from_env_map(local, cfg)
        # Skill-local config may set recipients, but keep Gmail as ultimate default if absent.
        if not cfg.get("default_to"):
            cfg["default_to"] = DEFAULT_TO
        if _smtp_ready(cfg):
            cfg["source"] = str(LOCAL_ENV)
            return cfg

    for path in FALLBACK_ENV_FILES:
        env_vars = _load_dotenv(path)
        if not env_vars:
            continue
        trial = _cfg_from_env_map(env_vars, dict(cfg))
        # Do not inherit other tools' multi-recipient lists unless user asked.
        trial["default_to"] = cfg.get("default_to") or DEFAULT_TO
        if _smtp_ready(trial):
            trial["source"] = str(path)
            trial["from_name"] = trial.get("from_name") or "AI Bubble Monitor"
            return trial

    if PI_EMAIL_CONFIG.exists():
        try:
            data = json.loads(PI_EMAIL_CONFIG.read_text(encoding="utf-8"))
            active = data.get("activeProfile") or next(iter(data.get("profiles", {})), None)
            profile = (data.get("profiles") or {}).get(active or "", {})
            smtp = profile.get("smtp") or {}
            trial = dict(cfg)
            if smtp.get("host"):
                trial["host"] = smtp.get("host", trial.get("host", ""))
                trial["port"] = int(smtp.get("port") or trial.get("port", 587))
                trial["user"] = smtp.get("user") or trial.get("user", "")
                trial["password"] = smtp.get("password") or trial.get("password", "")
            if profile.get("fromName"):
                trial["from_name"] = profile["fromName"]
            if _smtp_ready(trial):
                trial["source"] = str(PI_EMAIL_CONFIG)
                return trial
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Failed to read {PI_EMAIL_CONFIG}: {exc}", file=sys.stderr)

    cfg["source"] = "none"
    return cfg


def load_snapshot(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("snapshot must be a JSON object")
    return data


def _status_of(group: dict[str, Any] | None) -> str:
    if not group:
        return "unknown"
    s = str(group.get("status") or "unknown").lower()
    return s if s in STATUS_EMOJI else "unknown"


def _fmt_num(val: Any, digits: int = 2, suffix: str = "") -> str:
    if val is None:
        return "n/a"
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, (int, float)):
        if isinstance(val, float) and digits >= 0:
            return f"{val:.{digits}f}{suffix}"
        return f"{val}{suffix}"
    return str(val)


def _metric_line(label: str, node: Any, key: str = "value", unit: str = "") -> str:
    if node is None:
        return f"- **{label}:** n/a"
    if not isinstance(node, dict):
        return f"- **{label}:** {_fmt_num(node)}{unit}"
    val = node.get(key, node.get("value"))
    conf = node.get("confidence")
    note = node.get("method_note") or node.get("note") or ""
    extra = []
    if node.get("range_low") is not None and node.get("range_high") is not None:
        extra.append(f"range {_fmt_num(node['range_low'])}–{_fmt_num(node['range_high'])}")
    if conf:
        extra.append(f"confidence={conf}")
    if note:
        extra.append(str(note))
    tail = f" ({'; '.join(extra)})" if extra else ""
    return f"- **{label}:** {_fmt_num(val)}{unit}{tail}"


def synthesize_if_needed(snap: dict[str, Any]) -> dict[str, Any]:
    g1 = _status_of(snap.get("group1_capital_coverage"))
    g2 = _status_of(snap.get("group2_demand_conversion"))
    g3 = _status_of(snap.get("group3_financing_pressure"))
    synth = dict(snap.get("synthesis") or {})
    statuses = [g1, g2, g3]
    reds = sum(1 for s in statuses if s == "red")
    yellows = sum(1 for s in statuses if s == "yellow")

    if "systemic_signal" not in synth or synth.get("systemic_signal") is None:
        synth["systemic_signal"] = reds == 3
    if not synth.get("systemic_rule"):
        synth["systemic_rule"] = "三组同时 red → 系统性去杠杆；否则为局部/高压"
    if not synth.get("collapse_shape"):
        synth["collapse_shape"] = "layered"
    if not synth.get("pressure_level"):
        if reds == 3:
            synth["pressure_level"] = "systemic"
        elif reds >= 2:
            synth["pressure_level"] = "high"
        elif reds == 1 or yellows >= 2:
            synth["pressure_level"] = "elevated"
        elif all(s == "green" for s in statuses):
            synth["pressure_level"] = "calm"
        else:
            synth["pressure_level"] = "mixed_or_data_gap"
    snap["synthesis"] = synth
    return snap


def render_markdown(snap: dict[str, Any]) -> str:
    meta = snap.get("meta") or {}
    as_of = meta.get("as_of") or datetime.now().strftime("%Y-%m-%d")
    title = meta.get("title") or "AI泡沫三组指标监控报告"
    g1 = snap.get("group1_capital_coverage") or {}
    g2 = snap.get("group2_demand_conversion") or {}
    g3 = snap.get("group3_financing_pressure") or {}
    synth = snap.get("synthesis") or {}
    sources = snap.get("sources") or []
    gaps = snap.get("data_gaps") or []

    s1, s2, s3 = _status_of(g1), _status_of(g2), _status_of(g3)
    systemic = bool(synth.get("systemic_signal"))
    pressure = synth.get("pressure_level") or ("systemic" if systemic else "n/a")

    lines: list[str] = [
        f"# {title}",
        "",
        f"- **As of:** {as_of}",
        f"- **Framework:** {meta.get('framework', 'layered-collapse-three-groups')}",
        f"- **Author:** {meta.get('author', 'pi-agent')}",
        f"- **Systemic deleveraging signal:** {'🚨 YES' if systemic else 'No'}",
        f"- **Pressure level:** `{pressure}`",
        "",
        "## Executive dashboard",
        "",
        "| Group | Status | Focus |",
        "|-------|--------|-------|",
        f"| 1 资本覆盖 Capital coverage | {STATUS_EMOJI[s1]} `{s1}` | RCR / capex vs external AI profit |",
        f"| 2 需求转化 Demand conversion | {STATUS_EMOJI[s2]} `{s2}` | Pilot→prod / NRR / margin vs usage |",
        f"| 3 融资压力 Financing pressure | {STATUS_EMOJI[s3]} `{s3}` | Down/bridge / secondary / DSO |",
        "",
        f"**Rule:** 单组变红 = 局部压力；**三组同时 red** = 系统性去杠杆。  ",
        f"**Shape:** {synth.get('collapse_shape', 'layered')} collapse（分层塌方，而非必然巨响）。",
        "",
    ]

    if meta.get("summary"):
        lines += ["## One-line judgment", "", meta["summary"], ""]

    # Group 1
    rcr = g1.get("rcr") or {}
    lines += [
        f"## Group 1 — 资本覆盖 {STATUS_EMOJI[s1]} `{s1}`",
        "",
        _metric_line("RCR", rcr),
        _metric_line("Hyperscaler capex (USD bn)", g1.get("hyperscaler_capex_usd_bn")),
        _metric_line("AI capex share (%)", g1.get("ai_capex_share_pct"), unit="%"),
        _metric_line("Top model-lab revenue proxy (USD bn)", (g1.get("model_lab_revenue_usd_bn") or {}).get("combined_top2")),
        _metric_line("Annual revenue needed to cover new assets (USD bn)", g1.get("annual_revenue_needed_usd_bn")),
        f"- **FCF stress:** {g1.get('fcf_stress_note') or 'n/a'}",
        f"- **Notes:** {g1.get('notes') or '—'}",
        f"- **Sub-lights:** `{json.dumps(g1.get('traffic_lights') or {}, ensure_ascii=False)}`",
        "",
    ]
    ml = g1.get("model_lab_revenue_usd_bn") or {}
    if ml:
        lines += [
            "Model lab detail:",
            f"- OpenAI: {_fmt_num(ml.get('openai'))} | Anthropic: {_fmt_num(ml.get('anthropic'))} | type: {ml.get('metric_type', 'n/a')} | water_risk: {ml.get('water_risk', 'n/a')}",
            "",
        ]

    # Group 2
    lines += [
        f"## Group 2 — 需求转化 {STATUS_EMOJI[s2]} `{s2}`",
        "",
        _metric_line("Pilot → production (%)", g2.get("pilot_to_prod_pct"), unit="%"),
        _metric_line("NRR (%)", g2.get("nrr_pct"), unit="%"),
        _metric_line("Gross margin Δ (pct points)", (g2.get("gross_margin_trend") or {}).get("delta_pct_points")),
        f"- **Usage up while margin down:** {(g2.get('gross_margin_trend') or {}).get('usage_up')}",
        f"- **Notes:** {g2.get('notes') or '—'}",
        f"- **Sub-lights:** `{json.dumps(g2.get('traffic_lights') or {}, ensure_ascii=False)}`",
        "",
    ]
    surveys = g2.get("roi_surveys") or []
    if surveys:
        lines.append("ROI surveys:")
        for s in surveys:
            lines.append(f"- {s.get('org', '?')} ({s.get('as_of', '?')}): {s.get('finding', '')}")
        lines.append("")

    # Group 3
    dr = g3.get("down_round_pct") or {}
    lines += [
        f"## Group 3 — 融资压力 {STATUS_EMOJI[s3]} `{s3}`",
        "",
        _metric_line("Down round (%)", dr, unit="%"),
        f"- **Down round incl. acqui-hire (%):** {_fmt_num(dr.get('including_acquihire_pct'))}",
        _metric_line("Bridge round (%)", g3.get("bridge_round_pct"), unit="%"),
        _metric_line("Secondary discount (%)", g3.get("secondary_discount_pct"), unit="%"),
        _metric_line("Cloud DSO (days)", g3.get("cloud_dso_days")),
        f"- **Notes:** {g3.get('notes') or '—'}",
        f"- **Sub-lights:** `{json.dumps(g3.get('traffic_lights') or {}, ensure_ascii=False)}`",
        "",
    ]
    aq = g3.get("acquihire_examples") or []
    if aq:
        lines.append("Acqui-hire examples:")
        for item in aq:
            if isinstance(item, dict):
                lines.append(f"- {item.get('buyer', '?')} / {item.get('target', '?')}: {item.get('note', '')}")
            else:
                lines.append(f"- {item}")
        lines.append("")

    # Synthesis
    lines += [
        "## Synthesis",
        "",
        f"- **Systemic signal:** {'YES' if systemic else 'No'}",
        f"- **Pressure level:** {pressure}",
        f"- **Worst group:** {synth.get('worst_group') or 'n/a'}",
        f"- **Horizon:** {synth.get('horizon_note') or 'n/a'}",
        f"- **Rule:** {synth.get('systemic_rule') or 'n/a'}",
        f"- **Investment caveat:** {synth.get('investment_caveat') or '行业结构监控 ≠ 个股信号；关注流动性。'}",
        "",
    ]
    if synth.get("key_risks"):
        lines.append("### Key risks")
        lines.extend([f"- {x}" for x in synth["key_risks"]])
        lines.append("")
    if synth.get("key_offsets"):
        lines.append("### Offsetting factors")
        lines.extend([f"- {x}" for x in synth["key_offsets"]])
        lines.append("")
    if synth.get("next_checkpoints"):
        lines.append("### Next checkpoints")
        lines.extend([f"- {x}" for x in synth["next_checkpoints"]])
        lines.append("")

    if gaps:
        lines += ["## Data gaps", ""]
        lines.extend([f"- {g}" for g in gaps])
        lines.append("")

    if sources:
        lines += ["## Sources", ""]
        for i, src in enumerate(sources, 1):
            if not isinstance(src, dict):
                lines.append(f"{i}. {src}")
                continue
            title_s = src.get("title") or src.get("metric") or "source"
            url = src.get("url") or ""
            date = src.get("date") or ""
            excerpt = src.get("excerpt") or ""
            head = f"{i}. **{title_s}**"
            if date:
                head += f" ({date})"
            if url:
                head += f" — {url}"
            lines.append(head)
            if excerpt:
                lines.append(f"   > {excerpt}")
        lines.append("")

    lines += [
        "---",
        "",
        "_Generated by skill `ai-bubble-indicators`. Not investment advice._",
        "",
    ]
    return "\n".join(lines)


def _badge(status: str) -> str:
    colors = {
        "green": "#1a7f37",
        "yellow": "#9a6700",
        "red": "#cf222e",
        "unknown": "#6e7781",
    }
    labels = {
        "green": "GREEN",
        "yellow": "YELLOW",
        "red": "RED",
        "unknown": "UNKNOWN",
    }
    c = colors.get(status, colors["unknown"])
    lab = labels.get(status, status.upper())
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
        f'background:{c};color:#fff;font-size:12px;font-weight:700;'
        f'letter-spacing:.02em;">{html.escape(lab)}</span>'
    )


def _e(val: Any) -> str:
    if val is None:
        return "n/a"
    return html.escape(str(val))


def _metric_value(node: Any, key: str = "value", unit: str = "") -> str:
    if node is None:
        return "n/a"
    if not isinstance(node, dict):
        return f"{_fmt_num(node)}{unit}"
    val = node.get(key, node.get("value"))
    if val is None:
        return "n/a"
    return f"{_fmt_num(val)}{unit}"


def _metric_note(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    parts: list[str] = []
    if node.get("range_low") is not None and node.get("range_high") is not None:
        parts.append(f"range {_fmt_num(node['range_low'])}–{_fmt_num(node['range_high'])}")
    if node.get("confidence"):
        parts.append(f"confidence={node['confidence']}")
    note = node.get("method_note") or node.get("note") or ""
    if note:
        parts.append(str(note))
    return " · ".join(parts)


def _kv_row(label: str, value: str, note: str = "") -> str:
    note_html = (
        f'<div style="color:#57606a;font-size:12px;margin-top:4px;line-height:1.45;">{_e(note)}</div>'
        if note
        else ""
    )
    return (
        "<tr>"
        f'<td style="padding:10px 12px;border-bottom:1px solid #eaeef2;width:34%;'
        f'color:#57606a;vertical-align:top;">{_e(label)}</td>'
        f'<td style="padding:10px 12px;border-bottom:1px solid #eaeef2;vertical-align:top;">'
        f'<div style="font-weight:600;">{_e(value)}</div>{note_html}</td>'
        "</tr>"
    )


def _section_card(title: str, status: str, body_html: str) -> str:
    border = {
        "green": "#1a7f37",
        "yellow": "#bf8700",
        "red": "#cf222e",
        "unknown": "#afb8c1",
    }.get(status, "#afb8c1")
    return f"""
    <section style="margin:22px 0;border:1px solid #d0d7de;border-left:5px solid {border};border-radius:10px;overflow:hidden;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 16px;background:#f6f8fa;">
        <h2 style="margin:0;font-size:16px;">{title}</h2>
        {_badge(status)}
      </div>
      <div style="padding:4px 0 8px;">{body_html}</div>
    </section>
    """


def _ul(items: list[Any]) -> str:
    if not items:
        return '<p style="color:#57606a;margin:8px 16px;">—</p>'
    lis = []
    for it in items:
        lis.append(f'<li style="margin:6px 0;line-height:1.5;">{_e(it)}</li>')
    return (
        '<ul style="margin:8px 16px 12px 32px;padding:0;">' + "".join(lis) + "</ul>"
    )


def render_html(snap: dict[str, Any]) -> str:
    """Primary report format: structured HTML (email + local file)."""
    meta = snap.get("meta") or {}
    as_of = meta.get("as_of") or datetime.now().strftime("%Y-%m-%d")
    title_raw = meta.get("title") or "AI泡沫三组指标监控报告"
    title = html.escape(title_raw)
    g1 = snap.get("group1_capital_coverage") or {}
    g2 = snap.get("group2_demand_conversion") or {}
    g3 = snap.get("group3_financing_pressure") or {}
    synth = snap.get("synthesis") or {}
    sources = snap.get("sources") or []
    gaps = snap.get("data_gaps") or []

    s1, s2, s3 = _status_of(g1), _status_of(g2), _status_of(g3)
    systemic = bool(synth.get("systemic_signal"))
    pressure = str(synth.get("pressure_level") or ("systemic" if systemic else "n/a"))
    summary = str(meta.get("summary") or "")

    signal_bg = "#fff1f0" if systemic else "#f6ffed"
    signal_bd = "#ffa39e" if systemic else "#b7eb8f"
    signal_tx = "系统性去杠杆信号：YES" if systemic else "系统性去杠杆信号：No"

    # Group 1 body
    rcr = g1.get("rcr") or {}
    ml = g1.get("model_lab_revenue_usd_bn") or {}
    g1_rows = [
        _kv_row("RCR", _metric_value(rcr), _metric_note(rcr)),
        _kv_row(
            "Hyperscaler capex (USD bn)",
            _metric_value(g1.get("hyperscaler_capex_usd_bn")),
            _metric_note(g1.get("hyperscaler_capex_usd_bn")),
        ),
        _kv_row(
            "AI capex share",
            _metric_value(g1.get("ai_capex_share_pct"), unit="%"),
            _metric_note(g1.get("ai_capex_share_pct")),
        ),
        _kv_row(
            "Top labs revenue proxy (USD bn)",
            _fmt_num(ml.get("combined_top2")),
            f"OpenAI={_fmt_num(ml.get('openai'))} · Anthropic={_fmt_num(ml.get('anthropic'))} · "
            f"type={ml.get('metric_type', 'n/a')} · water_risk={ml.get('water_risk', 'n/a')}",
        ),
        _kv_row(
            "Annual revenue needed (USD bn)",
            _metric_value(g1.get("annual_revenue_needed_usd_bn")),
            _metric_note(g1.get("annual_revenue_needed_usd_bn")),
        ),
        _kv_row("FCF stress", "see note", str(g1.get("fcf_stress_note") or "n/a")),
        _kv_row("Notes", str(g1.get("notes") or "—")),
        _kv_row("Sub-lights", json.dumps(g1.get("traffic_lights") or {}, ensure_ascii=False)),
    ]
    g1_body = (
        '<table style="width:100%;border-collapse:collapse;">' + "".join(g1_rows) + "</table>"
    )

    # Group 2
    gmt = g2.get("gross_margin_trend") or {}
    g2_rows = [
        _kv_row(
            "Pilot → production",
            _metric_value(g2.get("pilot_to_prod_pct"), unit="%"),
            _metric_note(g2.get("pilot_to_prod_pct")),
        ),
        _kv_row(
            "NRR",
            _metric_value(g2.get("nrr_pct"), unit="%"),
            _metric_note(g2.get("nrr_pct")),
        ),
        _kv_row(
            "Gross margin Δ (pct pts)",
            _fmt_num(gmt.get("delta_pct_points")),
            f"direction={gmt.get('direction', 'n/a')} · usage_up={gmt.get('usage_up', 'n/a')} · "
            f"{_metric_note(gmt)}",
        ),
        _kv_row("Notes", str(g2.get("notes") or "—")),
        _kv_row("Sub-lights", json.dumps(g2.get("traffic_lights") or {}, ensure_ascii=False)),
    ]
    surveys = g2.get("roi_surveys") or []
    survey_html = ""
    if surveys:
        items = []
        for s in surveys:
            items.append(
                f"{s.get('org', '?')} ({s.get('as_of', '?')}): {s.get('finding', '')}"
            )
        survey_html = (
            '<div style="padding:4px 16px 12px;"><div style="font-weight:600;margin:8px 0 4px;">'
            "ROI surveys</div>" + _ul(items) + "</div>"
        )
    g2_body = (
        '<table style="width:100%;border-collapse:collapse;">' + "".join(g2_rows) + "</table>"
        + survey_html
    )

    # Group 3
    dr = g3.get("down_round_pct") or {}
    g3_rows = [
        _kv_row("Down round", _metric_value(dr, unit="%"), _metric_note(dr)),
        _kv_row(
            "Down round incl. acqui-hire",
            _fmt_num(dr.get("including_acquihire_pct"), suffix="%" if dr.get("including_acquihire_pct") is not None else ""),
        ),
        _kv_row(
            "Bridge round",
            _metric_value(g3.get("bridge_round_pct"), unit="%"),
            _metric_note(g3.get("bridge_round_pct")),
        ),
        _kv_row(
            "Secondary discount",
            _metric_value(g3.get("secondary_discount_pct"), unit="%"),
            _metric_note(g3.get("secondary_discount_pct")),
        ),
        _kv_row(
            "Cloud DSO (days)",
            _metric_value(g3.get("cloud_dso_days")),
            _metric_note(g3.get("cloud_dso_days")),
        ),
        _kv_row("Notes", str(g3.get("notes") or "—")),
        _kv_row("Sub-lights", json.dumps(g3.get("traffic_lights") or {}, ensure_ascii=False)),
    ]
    aq = g3.get("acquihire_examples") or []
    aq_html = ""
    if aq:
        items = []
        for item in aq:
            if isinstance(item, dict):
                items.append(
                    f"{item.get('buyer', '?')} / {item.get('target', '?')}: {item.get('note', '')}"
                )
            else:
                items.append(str(item))
        aq_html = (
            '<div style="padding:4px 16px 12px;"><div style="font-weight:600;margin:8px 0 4px;">'
            "Acqui-hire examples</div>" + _ul(items) + "</div>"
        )
    g3_body = (
        '<table style="width:100%;border-collapse:collapse;">' + "".join(g3_rows) + "</table>"
        + aq_html
    )

    # Synthesis
    synth_rows = [
        _kv_row("Systemic signal", "YES" if systemic else "No"),
        _kv_row("Pressure level", pressure),
        _kv_row("Worst group", str(synth.get("worst_group") or "n/a")),
        _kv_row("Horizon", str(synth.get("horizon_note") or "n/a")),
        _kv_row("Rule", str(synth.get("systemic_rule") or "n/a")),
        _kv_row(
            "Investment caveat",
            str(
                synth.get("investment_caveat")
                or "行业结构监控 ≠ 个股信号；关注流动性。"
            ),
        ),
    ]
    synth_extra = ""
    if synth.get("key_risks"):
        synth_extra += (
            '<div style="padding:4px 16px 0;"><div style="font-weight:600;">Key risks</div>'
            + _ul(list(synth["key_risks"]))
            + "</div>"
        )
    if synth.get("key_offsets"):
        synth_extra += (
            '<div style="padding:4px 16px 0;"><div style="font-weight:600;">Offsetting factors</div>'
            + _ul(list(synth["key_offsets"]))
            + "</div>"
        )
    if synth.get("next_checkpoints"):
        synth_extra += (
            '<div style="padding:4px 16px 12px;"><div style="font-weight:600;">Next checkpoints</div>'
            + _ul(list(synth["next_checkpoints"]))
            + "</div>"
        )
    synth_body = (
        '<table style="width:100%;border-collapse:collapse;">' + "".join(synth_rows) + "</table>"
        + synth_extra
    )

    gaps_html = ""
    if gaps:
        gaps_html = (
            '<section style="margin:22px 0;">'
            '<h2 style="font-size:16px;margin:0 0 8px;">Data gaps</h2>'
            + _ul(list(gaps))
            + "</section>"
        )

    sources_html = ""
    if sources:
        blocks = []
        for i, src in enumerate(sources, 1):
            if not isinstance(src, dict):
                blocks.append(f"<li>{_e(src)}</li>")
                continue
            t = src.get("title") or src.get("metric") or "source"
            url = src.get("url") or ""
            date = src.get("date") or ""
            excerpt = src.get("excerpt") or ""
            head = f"<strong>{_e(t)}</strong>"
            if date:
                head += f" <span style='color:#57606a;'>({_e(date)})</span>"
            if url:
                head += (
                    f' — <a href="{html.escape(url, quote=True)}" '
                    f'style="color:#0969da;word-break:break-all;">{_e(url)}</a>'
                )
            ex = (
                f'<div style="color:#57606a;font-size:12.5px;margin-top:4px;">{_e(excerpt)}</div>'
                if excerpt
                else ""
            )
            blocks.append(f'<li style="margin:10px 0;">{head}{ex}</li>')
        sources_html = (
            '<section style="margin:22px 0;">'
            '<h2 style="font-size:16px;margin:0 0 8px;">Sources</h2>'
            f'<ol style="margin:8px 16px 12px 28px;padding:0;">{ "".join(blocks)}</ol>'
            "</section>"
        )

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#eef1f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'PingFang SC','Noto Sans SC',sans-serif;color:#1f2328;">
  <div style="max-width:820px;margin:24px auto;background:#ffffff;border:1px solid #d0d7de;border-radius:14px;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,.06);">
    <div style="padding:22px 24px;background:linear-gradient(135deg,#0d1117 0%,#161b22 60%,#1f2937 100%);color:#fff;">
      <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.75;">AI Bubble Indicators · HTML Report</div>
      <h1 style="margin:10px 0 6px;font-size:24px;line-height:1.25;">{title}</h1>
      <div style="font-size:13px;opacity:.85;">As of {html.escape(as_of)} · Framework: {html.escape(str(meta.get('framework') or 'layered-collapse-three-groups'))} · Author: {html.escape(str(meta.get('author') or 'pi-agent'))}</div>
    </div>

    <div style="padding:22px 24px 8px;">
      <div style="padding:14px 16px;border-radius:10px;background:{signal_bg};border:1px solid {signal_bd};font-weight:700;margin-bottom:14px;">
        {html.escape(signal_tx)} · pressure: <code style="font-size:13px;">{html.escape(pressure)}</code>
      </div>

      {f'<p style="margin:0 0 16px;line-height:1.65;font-size:14.5px;">{html.escape(summary)}</p>' if summary else ''}

      <h2 style="font-size:15px;margin:8px 0 10px;color:#57606a;text-transform:uppercase;letter-spacing:.04em;">Executive dashboard</h2>
      <table style="width:100%;border-collapse:collapse;margin:0 0 8px;">
        <thead>
          <tr style="background:#f6f8fa;">
            <th align="left" style="padding:10px 12px;border:1px solid #d0d7de;">Group</th>
            <th align="left" style="padding:10px 12px;border:1px solid #d0d7de;">Status</th>
            <th align="left" style="padding:10px 12px;border:1px solid #d0d7de;">Focus</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style="padding:10px 12px;border:1px solid #d0d7de;">1 资本覆盖 Capital coverage</td>
            <td style="padding:10px 12px;border:1px solid #d0d7de;">{_badge(s1)}</td>
            <td style="padding:10px 12px;border:1px solid #d0d7de;color:#57606a;">RCR / capex vs external AI profit</td>
          </tr>
          <tr>
            <td style="padding:10px 12px;border:1px solid #d0d7de;">2 需求转化 Demand conversion</td>
            <td style="padding:10px 12px;border:1px solid #d0d7de;">{_badge(s2)}</td>
            <td style="padding:10px 12px;border:1px solid #d0d7de;color:#57606a;">Pilot→prod / NRR / margin vs usage</td>
          </tr>
          <tr>
            <td style="padding:10px 12px;border:1px solid #d0d7de;">3 融资压力 Financing pressure</td>
            <td style="padding:10px 12px;border:1px solid #d0d7de;">{_badge(s3)}</td>
            <td style="padding:10px 12px;border:1px solid #d0d7de;color:#57606a;">Down/bridge / secondary / DSO</td>
          </tr>
        </tbody>
      </table>
      <p style="color:#57606a;font-size:13px;line-height:1.55;margin:10px 0 0;">
        规则：单组变红 = 局部压力；<strong>三组同时 red</strong> = 系统性去杠杆。
        形态：{html.escape(str(synth.get('collapse_shape') or 'layered'))} collapse（分层塌方，而非必然巨响）。
      </p>

      {_section_card(f"Group 1 — 资本覆盖", s1, g1_body)}
      {_section_card(f"Group 2 — 需求转化", s2, g2_body)}
      {_section_card(f"Group 3 — 融资压力", s3, g3_body)}
      {_section_card("Synthesis", "red" if systemic else ("yellow" if pressure in {"elevated", "high"} else "green"), synth_body)}

      {gaps_html}
      {sources_html}

      <div style="margin:28px 0 10px;padding-top:16px;border-top:1px solid #d0d7de;color:#57606a;font-size:12px;line-height:1.5;">
        Generated by skill <code>ai-bubble-indicators</code> at {html.escape(generated)}.
        Primary format: <strong>HTML</strong>. Not investment advice.
      </div>
    </div>
  </div>
</body>
</html>
"""


def _smtp_send(msg: MIMEMultipart, to_addrs: list[str], smtp_cfg: dict[str, Any]) -> None:
    """Send via SMTP. Prefer direct socket; optional SOCKS if AI_BUBBLE_SMTP_SOCKS=1."""
    host = smtp_cfg["host"]
    port = int(smtp_cfg["port"])
    from_user = smtp_cfg["user"]
    password = smtp_cfg["password"]
    context = ssl.create_default_context()

    use_socks = os.environ.get("AI_BUBBLE_SMTP_SOCKS", "").lower() in {"1", "true", "yes"}
    proxy = os.environ.get("ALL_PROXY") or os.environ.get("all_proxy") or ""

    # Local HTTP/SOCKS proxies often break SMTP STARTTLS. Default: bypass proxy.
    saved_socket = None
    if use_socks and proxy.startswith("socks5"):
        try:
            import socks  # type: ignore
            import socket as _socket

            addr = proxy.split("://", 1)[-1]
            p_host, p_port = addr.rsplit(":", 1)
            socks.set_default_proxy(socks.SOCKS5, p_host, int(p_port))
            saved_socket = _socket.socket
            _socket.socket = socks.socksocket  # type: ignore[misc, assignment]
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] SOCKS setup failed, falling back to direct: {exc}", file=sys.stderr)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=45, context=context) as server:
                server.ehlo()
                server.login(from_user, password)
                server.sendmail(from_user, to_addrs, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=45) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(from_user, password)
                server.sendmail(from_user, to_addrs, msg.as_string())
    finally:
        if saved_socket is not None:
            import socket as _socket

            _socket.socket = saved_socket  # type: ignore[misc, assignment]


def send_email(
    *,
    to_addrs: list[str],
    subject: str,
    html_body: str,
    text_body: str,
    smtp_cfg: dict[str, Any],
) -> None:
    if not smtp_cfg.get("host") or not smtp_cfg.get("user") or not smtp_cfg.get("password"):
        raise RuntimeError(
            "SMTP not configured. Set ~/.pi/email-config.json or ~/.ai_bubble_indicators/.env"
        )

    from_user = smtp_cfg["user"]
    from_name = smtp_cfg.get("from_name") or "AI Bubble Monitor"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_user}>"
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Try configured port first, then the other common Gmail port.
    primary = int(smtp_cfg["port"])
    candidates = [primary] + [p for p in (587, 465) if p != primary]
    errors: list[str] = []
    for port in candidates:
        trial = dict(smtp_cfg)
        trial["port"] = port
        try:
            _smtp_send(msg, to_addrs, trial)
            if port != primary:
                print(f"[INFO] Sent via fallback SMTP port {port}")
            return
        except Exception as exc:  # noqa: BLE001
            errors.append(f"port {port}: {exc}")
    raise RuntimeError("; ".join(errors))


def write_outputs(
    out_dir: Path,
    snap: dict[str, Any],
    html_body: str,
    text_body: str | None = None,
    *,
    keep_markdown: bool = False,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {
        "snapshot": out_dir / "snapshot.json",
        "html": out_dir / "report.html",
        "readme": out_dir / "README.md",
    }
    paths["snapshot"].write_text(
        json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths["html"].write_text(html_body, encoding="utf-8")
    if keep_markdown and text_body is not None:
        paths["md"] = out_dir / "report.md"
        paths["md"].write_text(text_body, encoding="utf-8")
    # optional plain-text companion for mail clients / diffs
    if text_body is not None:
        paths["txt"] = out_dir / "report.txt"
        paths["txt"].write_text(text_body, encoding="utf-8")

    meta = snap.get("meta") or {}
    readme = "\n".join(
        [
            f"# {meta.get('title') or 'AI bubble indicators'}",
            "",
            f"- as_of: {meta.get('as_of')}",
            f"- generated_at: {datetime.now().isoformat(timespec='seconds')}",
            f"- systemic_signal: {(snap.get('synthesis') or {}).get('systemic_signal')}",
            f"- primary_format: HTML",
            "",
            "Files:",
            "- `snapshot.json` — structured inputs",
            "- `report.html` — **primary HTML report** (open in browser / email)",
            "- `report.txt` — plain-text fallback",
            "",
        ]
    )
    paths["readme"].write_text(readme, encoding="utf-8")
    return paths


def diff_snapshots(old_path: Path, new_path: Path) -> str:
    old = load_snapshot(old_path)
    new = load_snapshot(new_path)
    keys = [
        ("group1_capital_coverage", "status"),
        ("group2_demand_conversion", "status"),
        ("group3_financing_pressure", "status"),
        ("group1_capital_coverage", ("rcr", "value")),
        ("group2_demand_conversion", ("pilot_to_prod_pct", "value")),
        ("group2_demand_conversion", ("nrr_pct", "value")),
        ("group3_financing_pressure", ("down_round_pct", "value")),
        ("group3_financing_pressure", ("secondary_discount_pct", "value")),
    ]

    def dig(d: dict[str, Any], path: Any) -> Any:
        cur: Any = d
        if isinstance(path, tuple):
            for p in path:
                cur = (cur or {}).get(p) if isinstance(cur, dict) else None
            return cur
        return (d.get(path[0]) or {}).get(path[1]) if False else (d.get(keys_name := path))  # noqa: F841

    def get(d: dict[str, Any], group: str, field: Any) -> Any:
        g = d.get(group) or {}
        if isinstance(field, tuple):
            cur: Any = g
            for p in field:
                cur = (cur or {}).get(p) if isinstance(cur, dict) else None
            return cur
        return g.get(field)

    lines = ["# Snapshot diff", "", f"- old: `{old_path}`", f"- new: `{new_path}`", ""]
    for group, field in keys:
        ov = get(old, group, field)
        nv = get(new, group, field)
        label = field if isinstance(field, str) else ".".join(field)
        mark = "→" if ov != nv else "="
        lines.append(f"- `{group}.{label}`: {ov} {mark} {nv}")
    return "\n".join(lines) + "\n"


def parse_recipients(raw: str | None, smtp_cfg: dict[str, Any]) -> list[str]:
    text = (raw or smtp_cfg.get("default_to") or DEFAULT_TO).strip()
    return [x.strip() for x in text.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI bubble three-group report generator")
    parser.add_argument("--snapshot", type=Path, help="Path to snapshot JSON")
    parser.add_argument("--out-dir", type=Path, help="Output directory")
    parser.add_argument("--to", default=None, help=f"Comma-separated recipients (default {DEFAULT_TO})")
    parser.add_argument("--subject", default=None, help="Email subject override")
    parser.add_argument("--send", action="store_true", help="Send email after generating report")
    parser.add_argument(
        "--keep-markdown",
        action="store_true",
        help="Also write legacy report.md (primary format is HTML)",
    )
    parser.add_argument("--diff", nargs=2, metavar=("OLD", "NEW"), help="Diff two snapshots and exit")
    args = parser.parse_args(argv)

    if args.diff:
        print(diff_snapshots(Path(args.diff[0]), Path(args.diff[1])))
        return 0

    if not args.snapshot:
        parser.error("--snapshot is required unless using --diff")

    snap = synthesize_if_needed(load_snapshot(args.snapshot))
    as_of = (snap.get("meta") or {}).get("as_of") or datetime.now().strftime("%Y-%m-%d")
    out_dir = args.out_dir or Path.home() / "pi_workspace" / "output" / f"ai-bubble-indicators-{as_of}"

    # Primary: structured HTML. Plain text kept as email/multipart fallback.
    text_body = render_markdown(snap)
    html_body = render_html(snap)
    paths = write_outputs(
        out_dir,
        snap,
        html_body,
        text_body,
        keep_markdown=bool(args.keep_markdown),
    )

    print(f"[OK] Wrote {paths['html']}  (primary)")
    if "txt" in paths:
        print(f"[OK] Wrote {paths['txt']}   (plain-text fallback)")
    if "md" in paths:
        print(f"[OK] Wrote {paths['md']}    (legacy markdown)")
    print(f"[OK] Wrote {paths['snapshot']}")

    if args.send:
        smtp_cfg = load_smtp_config()
        print(f"[INFO] SMTP source: {smtp_cfg.get('source', 'unknown')} ({smtp_cfg.get('user', '')} @ {smtp_cfg.get('host', '')})")
        to_addrs = parse_recipients(args.to, smtp_cfg)
        # Ensure the user's Gmail is always included when sending "the report".
        if DEFAULT_TO not in to_addrs and (args.to is None):
            to_addrs = [DEFAULT_TO]
        g1 = _status_of(snap.get("group1_capital_coverage"))
        g2 = _status_of(snap.get("group2_demand_conversion"))
        g3 = _status_of(snap.get("group3_financing_pressure"))
        systemic = bool((snap.get("synthesis") or {}).get("systemic_signal"))
        flag = "SYSTEMIC" if systemic else "watch"
        subject = args.subject or f"[AI泡沫指标/{flag}] {as_of} · G1:{g1} G2:{g2} G3:{g3}"
        try:
            send_email(
                to_addrs=to_addrs,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                smtp_cfg=smtp_cfg,
            )
            print(f"[OK] Email sent to {', '.join(to_addrs)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] Email failed: {exc}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
