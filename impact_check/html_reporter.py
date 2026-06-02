import html as _html
from datetime import datetime

_SEV_ORDER = ["HIGH", "MED", "LOW"]
_STATUS_LABEL = {"A": "ADDED", "M": "MODIFIED", "D": "DELETED", "R": "RENAMED"}
_STATUS_CLASS = {"A": "a", "M": "m", "D": "d", "R": "r"}


def _esc(s: str) -> str:
    return _html.escape(str(s or ""))


def _sev_badge(sev: str) -> str:
    return f'<span class="sev sev-{_esc(sev)}">{_esc(sev)}</span>'


def _sort_sev(items: list, key: str) -> list:
    return sorted(
        items,
        key=lambda x: _SEV_ORDER.index(x.get(key, "LOW")) if x.get(key, "LOW") in _SEV_ORDER else 9,
    )


def _affected_table(modules: list) -> str:
    rows = "".join(
        f"<tr><td>{_sev_badge(m.get('severity', 'LOW'))}</td>"
        f"<td class='code'>{_esc(m.get('name', ''))}</td>"
        f"<td>{_esc(m.get('reason', ''))}</td></tr>"
        for m in modules
    )
    return (
        "<table><thead><tr>"
        "<th>Mức độ</th><th>Module</th><th>Lý do</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def _tests_table(tests: list) -> str:
    def _row(t: dict) -> str:
        pri = t.get("priority", "LOW")
        return (
            f"<tr class='row-{pri.lower()}'>"
            f"<td>{_sev_badge(pri)}</td>"
            f"<td class='code type-cell'>{_esc(t.get('type', '').upper())}</td>"
            f"<td>{_esc(t.get('description', ''))}</td></tr>"
        )
    rows = "".join(_row(t) for t in tests)
    return (
        "<table><thead><tr>"
        "<th>Ưu tiên</th><th>Loại</th><th>Mô tả</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def _risks_table(risks: list) -> str:
    def _row(r: dict) -> str:
        lvl = r.get("level", "LOW")
        return (
            f"<tr class='row-{lvl.lower()}'>"
            f"<td>{_sev_badge(lvl)}</td>"
            f"<td class='code loc-cell'>{_esc(r.get('location', ''))}</td>"
            f"<td>{_esc(r.get('description', ''))}</td></tr>"
        )
    rows = "".join(_row(r) for r in risks)
    return (
        "<table><thead><tr>"
        "<th>Mức độ</th><th>Vị trí</th><th>Mô tả</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def _section(title: str, count: int, content: str, hide_if_empty: bool = False) -> str:
    if hide_if_empty and count == 0:
        return ""
    count_html = f'<span class="section-count">({count})</span>' if count > 0 else '<span class="section-count empty">(none)</span>'
    return f"""  <section>
    <h2>{title} {count_html}</h2>
    {content}
  </section>
"""


def generate_html(analysis: dict, changes, related: dict, scan_warnings: list = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = _esc(analysis.get("summary", ""))
    affected = _sort_sev(analysis.get("affected_modules", []), "severity")
    tests    = _sort_sev(analysis.get("tests_needed", []), "priority")
    risks    = _sort_sev(analysis.get("risks", []), "level")

    changed_badges = "".join(
        f'<span class="badge badge-{_STATUS_CLASS.get(f.status, "m")}">'
        f'[{_STATUS_LABEL.get(f.status, f.status)}] {_esc(f.path)}</span>'
        for f in changes.files
    )

    # Stat cards: tổng số item theo severity level (không tính LOW vào "risks")
    total_high = (
        sum(1 for m in affected if m.get("severity") == "HIGH")
        + sum(1 for r in risks if r.get("level") == "HIGH")
    )
    total_med = (
        sum(1 for m in affected if m.get("severity") == "MED")
        + sum(1 for r in risks if r.get("level") == "MED")
    )
    total_risks = len(risks)

    # Scan warnings section
    warnings_section = ""
    if scan_warnings:
        items = "".join(f"<li>{_esc(w)}</li>" for w in scan_warnings)
        warnings_section = f'  <section class="warn-section">\n    <h2>⚠ Điều kiện phân tích <span class="section-count">({len(scan_warnings)})</span></h2>\n    <ul class="warn-list">{items}</ul>\n    <p class="warn-note">Các cảnh báo trên có thể ảnh hưởng đến độ chính xác của report. Xem xét chạy lại với context đầy đủ hơn.</p>\n  </section>\n'

    # Nếu có HIGH thì highlight banner
    alert_bar = ""
    if total_high > 0:
        high_items = [r.get("location") or r.get("name", "") for r in
                      [*[m for m in affected if m.get("severity") == "HIGH"],
                       *[r for r in risks if r.get("level") == "HIGH"]]]
        items_html = "".join(f'<span class="alert-item">{_esc(p)}</span>' for p in high_items if p)
        alert_bar = f'<div class="alert-bar">⚠ {total_high} vấn đề HIGH cần xem ngay: {items_html}</div>'

    sections = (
        _section("Affected Modules", len(affected), _affected_table(affected), hide_if_empty=True)
        + _section("Risks", total_risks, _risks_table(risks), hide_if_empty=True)
        + _section("Tests Needed", len(tests), _tests_table(tests), hide_if_empty=True)
    )

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Impact Report — {_esc(changes.branch)}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}}
    .container{{max-width:1000px;margin:0 auto;padding:2rem 1.5rem}}
    header{{border-bottom:1px solid #1e293b;padding-bottom:1.5rem;margin-bottom:1rem}}
    h1{{font-size:1.25rem;font-weight:700;color:#38bdf8;margin-bottom:.5rem}}
    .meta{{color:#64748b;font-size:.8rem;line-height:1.8}}
    .meta strong{{color:#94a3b8}}
    .stats{{display:flex;gap:.75rem;margin-top:1rem;flex-wrap:wrap}}
    .stat{{background:#1e293b;border-radius:.4rem;padding:.6rem 1rem;font-size:.8rem;border:1px solid #334155;min-width:100px}}
    .stat-num{{font-size:1.4rem;font-weight:700;display:block}}
    .stat-high .stat-num{{color:#f87171}}
    .stat-med .stat-num{{color:#fbbf24}}
    .stat-neutral .stat-num{{color:#94a3b8}}
    .stat-label{{color:#64748b;font-size:.72rem}}
    .alert-bar{{background:#450a0a;border:1px solid #7f1d1d;border-radius:.4rem;padding:.65rem 1rem;margin-bottom:1rem;font-size:.82rem;color:#fca5a5;line-height:1.6}}
    .alert-item{{display:inline-block;background:#7f1d1d;border-radius:.25rem;padding:.1rem .4rem;margin:.1rem;font-family:monospace;font-size:.75rem}}
    h2{{font-size:.72rem;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:.75rem}}
    .section-count{{color:#475569;font-size:.7rem;text-transform:none;letter-spacing:0;font-weight:400}}
    .section-count.empty{{color:#334155}}
    section{{background:#1e293b;border-radius:.5rem;padding:1.25rem 1.5rem;margin-bottom:.75rem;border:1px solid #334155}}
    .summary-text{{color:#cbd5e1;line-height:1.7;font-size:.9rem}}
    .badge{{display:inline-block;padding:.15rem .45rem;border-radius:.25rem;font-size:.72rem;font-family:'Consolas',monospace;margin:.1rem .1rem .1rem 0}}
    .badge-m{{background:#422006;color:#fbbf24}}
    .badge-a{{background:#052e16;color:#4ade80}}
    .badge-d{{background:#450a0a;color:#f87171}}
    .badge-r{{background:#1e1b4b;color:#a5b4fc}}
    table{{width:100%;border-collapse:collapse;font-size:.85rem}}
    th{{text-align:left;color:#475569;font-weight:600;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;padding:.4rem .75rem;border-bottom:1px solid #334155}}
    td{{padding:.6rem .75rem;border-bottom:1px solid #0f172a;color:#cbd5e1;vertical-align:top;line-height:1.5}}
    tr:last-child td{{border-bottom:none}}
    tr:hover td{{background:#ffffff08}}
    tr.row-high td{{border-left:2px solid #f8717133}}
    tr.row-med td{{border-left:2px solid #fbbf2433}}
    tr.row-low td{{border-left:2px solid transparent}}
    .sev{{display:inline-block;font-weight:700;font-size:.7rem;padding:.15rem .4rem;border-radius:.2rem;font-family:monospace;white-space:nowrap}}
    .sev-HIGH{{background:#450a0a;color:#f87171}}
    .sev-MED{{background:#422006;color:#fbbf24}}
    .sev-LOW{{background:#052e16;color:#4ade80}}
    .code{{font-family:'Fira Code','Consolas',monospace;font-size:.78rem;color:#94a3b8}}
    .type-cell{{white-space:nowrap;width:90px}}
    .loc-cell{{width:240px;word-break:break-all}}
    footer{{text-align:center;color:#334155;font-size:.72rem;padding-top:1.5rem}}
    .warn-section{{background:#1c1a0a;border:1px solid #854d0e;border-radius:.5rem;padding:1rem 1.5rem;margin-bottom:.75rem}}
    .warn-section h2{{color:#a16207}}
    .warn-list{{list-style:none;margin:0;padding:0}}
    .warn-list li{{color:#ca8a04;font-size:.82rem;padding:.25rem 0;border-bottom:1px solid #1f1a04}}
    .warn-list li:last-child{{border-bottom:none}}
    .warn-list li::before{{content:"⚠ ";opacity:.7}}
    .warn-note{{color:#78716c;font-size:.75rem;margin-top:.6rem;font-style:italic}}
  </style>
</head>
<body>
<div class="container">
  <header>
    <h1>⚡ Impact Analysis Report</h1>
    <div class="meta">
      Branch: <strong>{_esc(changes.branch)}</strong>&nbsp;·&nbsp;
      {changed_badges}<br>
      Generated: <strong>{now}</strong>&nbsp;·&nbsp;impact-check
    </div>
    <div class="stats">
      <div class="stat stat-high">
        <span class="stat-num">{total_high}</span>
        <span class="stat-label">HIGH issues</span>
      </div>
      <div class="stat stat-med">
        <span class="stat-num">{total_med}</span>
        <span class="stat-label">MED issues</span>
      </div>
      <div class="stat stat-neutral">
        <span class="stat-num">{total_risks}</span>
        <span class="stat-label">risks total</span>
      </div>
      <div class="stat stat-neutral">
        <span class="stat-num">{len(tests)}</span>
        <span class="stat-label">tests needed</span>
      </div>
    </div>
  </header>

  {alert_bar}
{warnings_section}
  <section>
    <h2>Summary</h2>
    <p class="summary-text">{summary}</p>
  </section>

{sections}
  <footer>Generated by impact-check &nbsp;·&nbsp; {now}</footer>
</div>
</body>
</html>"""
