import html
import json
import os

import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
FONT_URL = os.environ.get(
    "FONT_URL",
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500,600;700;800&display=swap",
)

SAMPLES = {
    "— write my own —": "",
    "Routine: hypertension + diabetes": "67-year-old male with hypertension and type 2 diabetes. Started on metformin 500 mg twice daily. Follow up in 3 months.",
    "Negation: nothing to extract": "No history of diabetes. Not on metformin.",
    "Dose probe: 2000 mg metformin": "Patient on metformin 2000 mg daily for diabetes. Follow up in 6 months.",
    "Healthy check-up": "30-year-old male. No chronic conditions. Annual physical exam.",
}

REASONS = {
    "rag_verification_failed": "A medication dose could not be confirmed against FDA label text.",
    "low_confidence_field": "At least one extracted item has low confidence.",
    "negation_mismatch": "The note says something is absent (e.g. 'no diabetes') but it was extracted.",
    "malformed_dose": "A dose was not in a recognisable format.",
    "model_requested_review": "The model itself asked for a human to check this note.",
}

st.set_page_config(page_title="Clinical Note Extractor", page_icon="🩺", layout="wide")
CSS = """
<style>
@import url('%s');
:root{
  --c1:#B2EBF2; --c2:#80DEEA; --c3:#4DD0E1; --c4:#26C6DA; --c5:#00BCD4;
  --ink:#06323B; --muted:#3F6B74; --line:#B2EBF2; --card:#FFFFFF;
  --warn-bg:#FFE7B3; --warn-ink:#5C3B00; --warn-line:#F0A92E;
}
html, body, [class*="css"], .stMarkdown { font-family:'Inter', system-ui, sans-serif; color:var(--ink); }
.block-container { padding-top:1.4rem; max-width:1200px; }
#MainMenu, footer { visibility:hidden; }
.hero { background:linear-gradient(120deg,var(--c5) 0%,var(--c4) 40%,var(--c2) 100%);
        border-radius:20px; padding:30px 34px; margin-bottom:18px; box-shadow:0 8px 24px rgba(0,188,212,.25); }
.hero-title { font-size:2.1rem; font-weight:800; color:var(--ink); letter-spacing:-0.5px; }
.hero-sub { font-size:1.08rem; color:var(--ink); margin:6px 0 16px 0; max-width:720px; }
.chip { display:inline-block; background:rgba(255,255,255,.85); color:var(--ink); border-radius:999px;
        padding:5px 13px; margin:0 8px 6px 0; font-size:.85rem; font-weight:600; }
.steps { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:22px; }
.step { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px; }
.step-num { display:inline-block; width:26px; height:26px; line-height:26px; text-align:center; border-radius:50%;
            background:var(--c5); color:var(--ink); font-weight:800; font-size:.85rem; margin-bottom:6px; }
.step-title { font-weight:700; } .step-text { font-size:.85rem; color:var(--muted); }
.section-title { font-size:1.15rem; font-weight:700; margin:0 0 8px 0; }
.card { background:var(--card); border:1px solid var(--line); border-left:6px solid var(--c4);
       border-radius:14px; padding:14px 18px; margin-bottom:12px; box-shadow:0 2px 10px rgba(6,50,59,.05); }
.card-title { font-weight:700; margin-bottom:6px; }
.row { padding:6px 0; border-top:1px dashed var(--line); } .row:first-of-type { border-top:none; }
.muted { color:var(--muted); font-size:.9rem; }
.pill { display:inline-block; background:#E3F8FB; border:1px solid var(--c2); border-radius:8px;
       padding:1px 8px; margin-left:6px; font-size:.82rem; }
.badge { display:inline-block; border-radius:999px; padding:2px 10px; margin-left:8px; font-size:.75rem; font-weight:700; }
.badge-high   { background:var(--c5); color:var(--ink); }
.badge-medium { background:var(--c2); color:var(--ink); }
.badge-low    { background:var(--warn-bg); color:var(--warn-ink); border:1px solid var(--warn-line); }
.banner { border-radius:14px; padding:14px 18px; margin-bottom:14px; font-weight:600; }
.banner-ok   { background:var(--c1); border:1px solid var(--c3); color:var(--ink); }
.review-banner { background:var(--warn-bg); border:1px solid var(--warn-line); color:var(--warn-ink); }
.banner small { display:block; font-weight:500; margin-top:3px; }
.tiles { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:12px; }
.tile { background:var(--card); border:1px solid var(--line); border-radius:14px; text-align:center; padding:10px 0; }
.tile-num { font-size:1.7rem; font-weight:800; color:var(--ink); } .tile-label { font-size:.8rem; color:var(--muted); }
.empty { border:2px dashed var(--c3); background:#fff; border-radius:16px; padding:46px 20px; text-align:center; color:var(--muted); }
.empty-icon { font-size:2.4rem; }
button[data-testid="stBaseButton-primary"], .stButton button[kind="primary"] {
  background:var(--c5); color:var(--ink); border:none; font-weight:700; border-radius:12px; padding:.55rem 1.2rem; }
button[data-testid="stBaseButton-primary"]:hover, .stButton button[kind="primary"]:hover { background:var(--c4); color:var(--ink); }
[data-testid="stDownloadButton"] button { border:1.5px solid var(--c4); color:var(--ink); border-radius:12px; font-weight:600; }
textarea { border-radius:12px !important; }
section[data-testid="stSidebar"] { background:linear-gradient(180deg,var(--c1) 0%,#F4FCFD 70%); }
.legend-row { margin:5px 0; font-size:.88rem; }
@media (max-width:800px){ .steps{grid-template-columns:repeat(2,1fr);} }
</style>
""".replace("%s", FONT_URL)
st.markdown(CSS, unsafe_allow_html=True)


def e(text) -> str:
    return html.escape(str(text))


def badge(level: str) -> str:
    level = level if level in ("high", "medium", "low") else "medium"
    dots = {"high": "●●●", "medium": "●●○", "low": "●○○"}[level]
    return f'<span class="badge badge-{level}">{dots} {level}</span>'


def card(title: str, body: str) -> None:
    st.markdown(
        f'<div class="card"><div class="card-title">{title}</div>{body}</div>',
        unsafe_allow_html=True,
    )


def rag_label(med: dict) -> str:
    if med.get("rag_verified") is True:
        return '<span class="pill">✅ dose matches FDA label</span>'
    if med.get("rag_verified") is False:
        return '<span class="pill">⚠ dose not confirmed</span>'
    return '<span class="pill">— no dose to check</span>'


def api_status():
    try:
        r = requests.get(f"{API_BASE}/health", timeout=2)
        return True, r.json().get("mode", "unknown")
    except requests.RequestException:
        return False, ""


def load_sample() -> None:
    st.session_state.note = SAMPLES[st.session_state.sample]


def show_result(result: dict) -> None:
    if result.get("transport_error"):
        st.error(
            f"Could not reach the API at {API_BASE}. Is it running?  ({result['transport_error']})"
        )
        return
    if not result.get("ok"):
        st.error(f"Extraction failed: {result.get('error')}")
        return

    data = result["data"]
    if result["needs_human_review"]:
        why = REASONS.get(
            data.get("abstention_reason"), "The system was not confident enough."
        )
        st.markdown(
            f'<div class="banner review-banner">⚠ Needs human review<small>{e(why)}</small></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="banner banner-ok">✅ Checks passed — auto-accepted'
            "<small>Still a demo: always have a clinician confirm real data.</small></div>",
            unsafe_allow_html=True,
        )

    dx, meds, fus = data["diagnoses"], data["medications"], data["follow_ups"]
    st.markdown(
        f'<div class="tiles"><div class="tile"><div class="tile-num">{len(dx)}</div><div class="tile-label">Diagnoses</div></div>'
        f'<div class="tile"><div class="tile-num">{len(meds)}</div><div class="tile-label">Medications</div></div>'
        f'<div class="tile"><div class="tile-num">{len(fus)}</div><div class="tile-label">Follow-ups</div></div></div>',
        unsafe_allow_html=True,
    )

    age, sex = data.get("patient_age"), data.get("patient_sex")
    card(
        "👤 Patient",
        f'Age: <b>{age if age is not None else "not stated"}</b> &nbsp;·&nbsp; Sex: <b>{e(sex or "not stated")}</b>',
    )

    rows = "".join(
        f'<div class="row">{e(d["description"])}{badge(d["confidence"])}</div>'
        for d in dx
    )
    card("🩺 Diagnoses", rows or '<span class="muted">None found</span>')

    rows = ""
    for m in meds:
        details = " · ".join(
            e(x) for x in (m.get("dose"), m.get("frequency"), m.get("route")) if x
        )
        rows += (
            f'<div class="row"><b>{e(m["name"])}</b> {details}{badge(m["confidence"])}'
            f'<div style="margin-top:4px">{rag_label(m)}</div></div>'
        )
    card("💊 Medications", rows or '<span class="muted">None found</span>')

    rows = "".join(
        f'<div class="row">{e(f["action"])}{" — " + e(f["timeframe"]) if f.get("timeframe") else ""}{badge(f["confidence"])}</div>'
        for f in fus
    )
    card("📅 Follow-ups", rows or '<span class="muted">None found</span>')

    st.download_button(
        "⬇ Download JSON",
        json.dumps(data, indent=2),
        "extraction.json",
        "application/json",
    )
    with st.expander("Raw JSON"):
        st.json(data)


online, mode = api_status()

with st.sidebar:
    st.markdown("### 🩺 Clinical Note Extractor")
    st.markdown(
        f"**API:** {'🟢 online' if online else '🔴 offline'}"
        + (f"  \n**Mode:** {mode}" if online else "")
    )
    st.markdown("---")
    st.markdown("**How to read the badges**")
    st.markdown(
        f'<div class="legend-row">{badge("high")} sure</div>'
        f'<div class="legend-row">{badge("medium")} fairly sure</div>'
        f'<div class="legend-row">{badge("low")} please check</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**Privacy**")
    st.caption(
        "Names, SSNs, phone numbers and MRNs are removed on this machine before any AI model sees the note. "
        "The audit log stores only a hash, never the note."
    )
    st.caption(
        "⚠ Use **synthetic notes only**. Free AI-model tiers may use prompts to improve their products."
    )

st.markdown(
    """
<div class="hero">
  <div class="hero-title">🩺 Clinical Note Extractor</div>
  <div class="hero-sub">Turn messy clinical notes into structured data — and know when <b>not</b> to trust it.</div>
  <span class="chip">De-identified first</span><span class="chip"> Doses checked against FDA labels</span>
  <span class="chip">Asks a human when unsure</span><span class="chip">Synthetic data only · Not for clinical use</span>
</div>
<div class="steps">
  <div class="step"><div class="step-num">1</div><div class="step-title">Protect</div><div class="step-text">Personal identifiers are removed first.</div></div>
  <div class="step"><div class="step-num">2</div><div class="step-title">Extract</div><div class="step-text">AI reads the note into diagnoses, medications and follow-ups.</div></div>
  <div class="step"><div class="step-num">3</div><div class="step-title">Verify</div><div class="step-text">Each dose is checked against the official FDA label.</div></div>
  <div class="step"><div class="step-num">4</div><div class="step-title">Decide</div><div class="step-text">Confident → accept. Unsure → send to a human.</div></div>
</div>
""",
    unsafe_allow_html=True,
)

left, right = st.columns([1, 1.15], gap="large")

with left:
    st.markdown(
        '<div class="section-title">1 · Paste a clinical note</div>',
        unsafe_allow_html=True,
    )
    st.selectbox(
        "Try a sample note", list(SAMPLES), key="sample", on_change=load_sample
    )
    note = st.text_area(
        "Clinical note (synthetic only)",
        key="note",
        height=230,
        placeholder="e.g. 67-year-old male with hypertension. Metformin 500 mg twice daily. Follow up in 3 months.",
    )
    clicked = st.button(
        "Extract", type="primary", use_container_width=True, disabled=not online
    )
    if not online:
        st.warning(
            "The API is offline. Start it first (see the README), then refresh this page."
        )

if clicked:
    if not note.strip():
        st.session_state.result = None
        with left:
            st.warning("Please enter a note first.")
    else:
        with right, st.spinner("Reading the note…"):
            try:
                resp = requests.post(
                    f"{API_BASE}/extract", json={"note": note}, timeout=120
                )
                resp.raise_for_status()
                st.session_state.result = resp.json()
            except requests.RequestException as err:
                st.session_state.result = {"transport_error": str(err)}

with right:
    st.markdown(
        '<div class="section-title">2 · Structured result</div>', unsafe_allow_html=True
    )
    if st.session_state.get("result"):
        show_result(st.session_state.result)
    else:
        st.markdown(
            '<div class="empty"><div class="empty-icon">📝</div>'
            "<b>Your results will appear here</b><br>Pick a sample or paste a note, then press <b>Extract</b>.</div>",
            unsafe_allow_html=True,
        )

st.caption(
    "Synthetic data only · De-identified before extraction · Not for clinical use"
)
