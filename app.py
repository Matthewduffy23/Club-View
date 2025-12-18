import os
import streamlit as st
from PIL import Image

st.set_page_config(page_title="Club View", layout="wide")

# =========================
# EDIT THESE VALUES ONLY
# =========================
TEAM_NAME = "Chengdu Rongcheng"
LEAGUE_TEXT = "Super League"

OVERALL = 88
ATT = 66
MID = 77
DEF = 79

AVG_AGE = 24.32
LEAGUE_POSITION = 2

CREST_PATH = "images/chengdu_rongcheng_f.c.svg.png"
FLAG_PATH = "images/china.png"
PERFORMANCE_IMAGE_PATH = "images/chengugraph.png"
# =========================

COLORS = [
    (85, "#2E6114"),
    (75, "#5C9E2E"),
    (66, "#7FBC41"),
    (54, "#A7D763"),
    (44, "#F6D645"),
    (25, "#D77A2E"),
    (0,  "#C63733"),
]

def score_color(score: int) -> str:
    for threshold, color in COLORS:
        if score >= threshold:
            return color
    return COLORS[-1][1]

def load_img(path: str):
    return Image.open(path) if path and os.path.exists(path) else None

crest = load_img(CREST_PATH)
flag = load_img(FLAG_PATH)
perf = load_img(PERFORMANCE_IMAGE_PATH)

# --- Dark theme + Swansea-like card layout ---
st.markdown(
    """
    <style>
      .stApp { background:#0e0e0f; color:#f2f2f2; }
      .block-container { padding-top:1.4rem; padding-bottom:2rem; max-width:1100px; }

      .club-card{
        background:#1c1c1d;
        border:1px solid #2a2a2b;
        border-radius:20px;
        padding:22px;
      }

      .grid{
        display:grid;
        grid-template-columns: 240px 1fr;
        gap: 22px;
        align-items: stretch; /* makes crest tile full height */
      }

      .crest-tile{
        background:#121213;
        border:1px solid #2a2a2b;
        border-radius:20px;
        height: 100%;
        min-height: 230px; /* baseline height */
        display:flex;
        align-items:center;
        justify-content:center;
        padding:18px;
      }

      .right{
        display:flex;
        flex-direction:column;
        justify-content:flex-start;
        gap: 14px;
        padding-top: 6px;
      }

      .team-title{
        font-size:56px;
        font-weight:800;
        margin:0;
        line-height:1.05;
        letter-spacing:.2px;
      }

      .metric-row{
        display:flex;
        align-items:center;
        gap: 14px;
        flex-wrap: wrap;
      }

      .pill{
        width:60px;
        height:46px;
        border-radius:12px;
        display:flex;
        align-items:center;
        justify-content:center;
        font-size:28px;
        font-weight:900;
        color:#111;
        border:1px solid rgba(0,0,0,.35);
        box-shadow: 0 1px 0 rgba(255,255,255,0.06) inset;
      }

      .label{
        font-size:40px;
        font-weight:700;
        color:#9ea0a6;
        line-height:1;
      }

      .league-row{
        display:flex;
        align-items:center;
        gap: 12px;
        margin-top: 2px;
      }

      .league-text{
        font-size:32px;   /* smaller like Swansea */
        font-weight:650;
        color:#d2d2d4;
        line-height:1;
      }

      .info-row{
        font-size:18px;
        color:#b0b0b3;
        margin-top: 2px;
      }

      h2 { margin-top: 36px; font-size: 34px; }
    </style>
    """,
    unsafe_allow_html=True
)

def metric(value: int, text: str) -> str:
    return f"""
      <div class="metric-row">
        <div class="pill" style="background:{score_color(value)}">{value}</div>
        <div class="label">{text}</div>
      </div>
    """

# ---------------- Header Card ----------------
st.markdown('<div class="club-card">', unsafe_allow_html=True)
st.markdown('<div class="grid">', unsafe_allow_html=True)

# Left crest tile
st.markdown('<div class="crest-tile">', unsafe_allow_html=True)
if crest:
    st.image(crest, width=170)
st.markdown('</div>', unsafe_allow_html=True)

# Right content (stacked like Swansea)
st.markdown('<div class="right">', unsafe_allow_html=True)

st.markdown(f'<div class="team-title">{TEAM_NAME}</div>', unsafe_allow_html=True)

# Overall ABOVE the other three
st.markdown(metric(OVERALL, "Overall"), unsafe_allow_html=True)

# ATT / MID / DEF row
st.markdown(
    f"""
    <div class="metric-row" style="gap:26px;">
      <div style="display:flex; align-items:center; gap:14px;">
        <div class="pill" style="background:{score_color(ATT)}">{ATT}</div>
        <div class="label">ATT</div>
      </div>

      <div style="display:flex; align-items:center; gap:14px;">
        <div class="pill" style="background:{score_color(MID)}">{MID}</div>
        <div class="label">MID</div>
      </div>

      <div style="display:flex; align-items:center; gap:14px;">
        <div class="pill" style="background:{score_color(DEF)}">{DEF}</div>
        <div class="label">DEF</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# Flag & League BELOW the badge rows
st.markdown('<div class="league-row">', unsafe_allow_html=True)
if flag:
    st.image(flag, width=56)
st.markdown(f'<div class="league-text">{LEAGUE_TEXT}</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Info on different rows
st.markdown(f'<div class="info-row"><b>Average Age:</b> {AVG_AGE:.2f}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="info-row"><b>League Position:</b> {LEAGUE_POSITION}</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)  # right
st.markdown('</div>', unsafe_allow_html=True)  # grid
st.markdown('</div>', unsafe_allow_html=True)  # club-card

# ---------------- Performance ----------------
st.markdown("## Performance")
if perf:
    st.image(perf, use_container_width=True)
else:
    st.warning(f"Performance image not found: {PERFORMANCE_IMAGE_PATH}")



