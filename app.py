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
MID = 77   # (use MID like your example)
DEF = 79

AVG_AGE = 24.32
LEAGUE_POSITION = 2

CREST_PATH = "images/chengdu_rongcheng_f.c.svg.png"
FLAG_PATH = "images/china.png"

PERFORMANCE_IMAGE_PATH = "images/chengugraph.png"
# =========================

COLORS = [
    (85, "#2E6114"),  # Deep green
    (75, "#5C9E2E"),  # Green+
    (66, "#7FBC41"),  # Green
    (54, "#A7D763"),  # Green-
    (44, "#F6D645"),  # Bright yellow
    (25, "#D77A2E"),  # Orange
    (0,  "#C63733"),  # Red
]

def score_color(score: int) -> str:
    for threshold, hex_color in COLORS:
        if score >= threshold:
            return hex_color
    return COLORS[-1][1]

def safe_image(path: str):
    if path and os.path.exists(path):
        return Image.open(path)
    return None

# ---- Global dark styling ----
st.markdown(
    """
    <style>
      /* Main background + padding */
      .stApp {
        background: #0f0f10;
        color: #eaeaea;
      }

      /* Tighten top padding a bit */
      .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
      }

      /* Header card */
      .club-card {
        background: #1f1f20;
        border: 1px solid #2a2a2b;
        border-radius: 18px;
        padding: 18px 18px;
      }

      /* Crest tile on left */
      .crest-tile {
        width: 150px;
        height: 150px;
        border-radius: 18px;
        background: #161617;
        border: 1px solid #2a2a2b;
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .title {
        font-size: 52px;
        font-weight: 800;
        margin: 0;
        color: #f2f2f2;
        letter-spacing: 0.2px;
      }

      /* Rating row */
      .rating-row {
        display: flex;
        align-items: center;
        gap: 18px;
        flex-wrap: wrap;
        margin-top: 8px;
      }

      /* Each metric group: [pill] [label] */
      .metric {
        display: inline-flex;
        align-items: center;
        gap: 10px;
      }

      .metric-label {
        font-size: 36px;
        font-weight: 700;
        color: #a8a8aa;
        line-height: 1;
      }

      /* Pill: number only */
      .pill {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 54px;
        height: 44px;
        padding: 0 14px;
        border-radius: 12px;
        font-weight: 900;
        font-size: 26px;
        color: #101010;
        border: 1px solid rgba(0,0,0,0.35);
        box-shadow: 0 1px 0 rgba(255,255,255,0.06) inset;
      }

      /* League line */
      .league-line {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 14px;
      }

      .league-text {
        font-size: 42px;
        font-weight: 700;
        color: #d9d9db;
      }

      /* Info line under league */
      .info-line {
        margin-top: 14px;
        font-size: 18px;
        color: #b0b0b3;
      }

      /* Section headings */
      h2, h3 {
        color: #f2f2f2 !important;
      }

      /* Make images look nice on dark */
      img {
        image-rendering: auto;
      }
    </style>
    """,
    unsafe_allow_html=True
)

crest = safe_image(CREST_PATH)
flag = safe_image(FLAG_PATH)
perf = safe_image(PERFORMANCE_IMAGE_PATH)

# ---- Header card layout ----
st.markdown('<div class="club-card">', unsafe_allow_html=True)
left, right = st.columns([1.2, 6], vertical_alignment="center")

with left:
    st.markdown('<div class="crest-tile">', unsafe_allow_html=True)
    if crest:
        st.image(crest, width=118)
    st.markdown('</div>', unsafe_allow_html=True)

with right:
    st.markdown(f'<p class="title">{TEAM_NAME}</p>', unsafe_allow_html=True)

    def metric_html(value: int, label: str) -> str:
        bg = score_color(value)
        return f"""
        <div class="metric">
          <div class="pill" style="background:{bg};">{value}</div>
          <div class="metric-label">{label}</div>
        </div>
        """

    ratings_html = f"""
      <div class="rating-row">
        {metric_html(OVERALL, "Overall")}
        {metric_html(ATT, "ATT")}
        {metric_html(MID, "MID")}
        {metric_html(DEF, "DEF")}
      </div>
    """
    st.markdown(ratings_html, unsafe_allow_html=True)

    # League line with flag
    st.markdown('<div class="league-line">', unsafe_allow_html=True)
    if flag:
        # render via st.image to preserve correct sizing
        fcol, tcol = st.columns([0.7, 10], vertical_alignment="center")
        with fcol:
            st.image(flag, width=56)
        with tcol:
            st.markdown(f'<div class="league-text">{LEAGUE_TEXT}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="league-text">{LEAGUE_TEXT}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="info-line"><b>Average Age:</b> {AVG_AGE:.2f} &nbsp;&nbsp;&nbsp; <b>League Position:</b> {LEAGUE_POSITION}</div>',
        unsafe_allow_html=True
    )

st.markdown('</div>', unsafe_allow_html=True)

# ---- Performance section ----
st.write("")
st.markdown("## Performance")

if perf:
    st.image(perf, use_container_width=True)
else:
    st.warning(f"Performance image not found: {PERFORMANCE_IMAGE_PATH}")

