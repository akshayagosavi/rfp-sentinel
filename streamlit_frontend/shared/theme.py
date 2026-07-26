"""
Shared visual theme + render helpers for RFP Sentinel Streamlit dashboards.
Import and call `inject_theme()` once at the top of every page, then use the
render_* helpers so every dashboard looks identical without copy-pasting CSS.
"""
import html

import streamlit as st

NAVY = "#0B2545"
SAFFRON = "#FF9933"
GREEN = "#138808"
PRESENT = "#1B7A3D"
MISSING = "#a3311a"
SEV_COLORS = {"high": "#a3311a", "medium": "#8a6300", "low": "#3a5c8a"}


def inject_theme():
    st.markdown(f"""
    <style>
        .stApp {{ background:#F6F3EB; }}
        div.block-container {{ padding-top:1.2rem; max-width:960px; }}
        .tricolor {{
            height:6px; width:100%;
            background:linear-gradient(to right,{SAFFRON} 0 33.3%, #fff 33.3% 66.6%, {GREEN} 66.6% 100%);
            margin:-1rem -1rem 1.2rem -1rem; width:calc(100% + 2rem);
        }}
        .letterhead {{
            background:{NAVY}; color:#f2efe4; padding:20px 26px;
            border-bottom:3px solid {SAFFRON}; border-radius:4px;
            display:flex; align-items:center; gap:16px; margin-bottom:1.4rem;
        }}
        .letterhead .seal {{
            width:48px; height:48px; border-radius:50%; border:2px solid {SAFFRON};
            display:flex; align-items:center; justify-content:center;
            font-family:Georgia,serif; font-weight:700; font-size:18px; color:{SAFFRON}; flex:none;
        }}
        .letterhead h1 {{ font-family:Georgia,serif; font-size:1.4rem; margin:0; color:#f2efe4; }}
        .letterhead p {{ margin:2px 0 0; font-size:.8rem; color:#c9d2e0; }}
        .role-badge {{
            margin-left:auto; font-size:.7rem; text-transform:uppercase; letter-spacing:.5px;
            border:1px solid {SAFFRON}; color:{SAFFRON}; padding:4px 10px; border-radius:12px;
        }}
        .issue-box {{
            border:1px solid #e4ddc9; border-left:5px solid #5b5f56; background:#fffdf7;
            border-radius:4px; padding:12px 14px; margin-bottom:10px;
        }}
        .issue-box.present {{ border-left-color:{PRESENT}; }}
        .issue-box.missing {{ border-left-color:{MISSING}; }}
        .issue-top {{ display:flex; justify-content:space-between; align-items:center; gap:10px; }}
        .issue-label {{ font-weight:600; font-size:.92rem; color:#20241f; }}
        .chip {{ font-size:.68rem; font-weight:700; text-transform:uppercase; letter-spacing:.4px; padding:3px 9px; border-radius:12px; }}
        .chip.present {{ background:#e9f4ec; color:{PRESENT}; }}
        .chip.missing {{ background:#fbeae5; color:{MISSING}; }}
        .issue-meta {{ font-size:.76rem; color:#5b5f56; margin-top:5px; }}
        .snippet {{ font-size:.8rem; font-style:italic; color:#5b5f56; margin-top:6px; border-left:2px solid #e4ddc9; padding-left:8px; }}
        .stamp-wrap {{ display:flex; align-items:center; gap:18px; margin-bottom:1rem; }}
        .stamp {{
            width:74px; height:74px; border-radius:50%; border:3px solid {NAVY}; flex:none;
            display:flex; flex-direction:column; align-items:center; justify-content:center;
            font-family:Georgia,serif; color:{NAVY}; transform:rotate(-6deg);
        }}
        .stamp .pct {{ font-size:1.2rem; font-weight:700; line-height:1; }}
        .stamp .lbl {{ font-size:.5rem; letter-spacing:.5px; text-transform:uppercase; margin-top:2px; }}
        .disclaimer {{
            font-size:.75rem; color:#5b5f56; background:#f0ecdd; border:1px dashed #cfc6a6;
            border-radius:4px; padding:8px 12px; margin-top:1rem;
        }}
        [data-testid="stSidebarNav"] li a span {{ font-size:.92rem; }}
    </style>
    <div class="tricolor"></div>
    """, unsafe_allow_html=True)


def render_letterhead(subtitle: str, role: str | None = None):
    role_html = f'<span class="role-badge">{html.escape(role)}</span>' if role else ""
    st.markdown(f"""
    <div class="letterhead">
        <div class="seal">RS</div>
        <div>
            <h1>RFP Sentinel</h1>
            <p>{html.escape(subtitle)}</p>
        </div>
        {role_html}
    </div>
    """, unsafe_allow_html=True)


def render_stamp(present: int, total: int, meta_html: str):
    pct = round((present / total) * 100) if total else 0
    st.markdown(f"""
    <div class="stamp-wrap">
        <div class="stamp"><div class="pct">{pct}%</div><div class="lbl">Compliant</div></div>
        <div style="font-size:.85rem;color:#5b5f56;">{meta_html}<br><b>{present}</b> of <b>{total}</b> checks passed.</div>
    </div>
    """, unsafe_allow_html=True)


def render_issue(issue: dict):
    sev = issue.get("severity", "low")
    sev_color = SEV_COLORS.get(sev, "#5b5f56")
    snippet_html = ""
    if issue.get("matched_snippet"):
        page = f" — p.{issue['page_number']}" if issue.get("page_number") else ""
        snippet_html = f'<div class="snippet">"{html.escape(issue["matched_snippet"])}"{page}</div>'
    st.markdown(f"""
    <div class="issue-box {issue['status']}">
        <div class="issue-top">
            <span class="issue-label">{html.escape(issue['label'])}</span>
            <span class="chip {issue['status']}">{issue['status']}</span>
        </div>
        <div class="issue-meta">
            Severity: <span style="color:{sev_color};font-weight:700;">{sev}</span>
            &nbsp;·&nbsp; Norm ref: {html.escape(issue['norm'])}
        </div>
        {snippet_html}
    </div>
    """, unsafe_allow_html=True)


def render_results(issues: list[dict], meta_html: str):
    present = sum(1 for i in issues if i["status"] == "present")
    render_stamp(present, len(issues), meta_html)
    for issue in issues:
        render_issue(issue)


def render_disclaimer(text: str):
    st.markdown(f'<div class="disclaimer">{html.escape(text)}</div>', unsafe_allow_html=True)
