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

def load_img(path):
    return Image.open(path) if os.path.exists(path) else None

# ---------- GLOBAL DARK STYLING ----------
st.markdown(
    """
    <style>
    .stApp {
        background: #0e0e0f;
        color: #f2f2f2;
    }

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    /* Header card */
    .club-card {
        background: #1c1c1d;
        border-radius: 20px;
        padding: 26px;
        border: 1px solid #2a2a2b;
    }

    /* Crest tile (big) */
    .crest-box {
        width: 200px;
        height: 200px;
        background: #121213;
        border-radius: 20px;
        border: 1px solid #2a2a2b;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    /* Team title */
    .team-title {
        font-size: 64px;
        font-weight: 800;
        margin: 0;
        line-height: 1.05;
    }

    /* Rating row */
    .ratings {
        display: flex;
        gap: 28px;
        margin-top: 14px;
        flex-wrap: wrap;
    }

    .rating {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .pill {
        min-width: 56px;
        height: 44px;
        border-radius: 12px;
        font-size: 26px;
        font-weight: 900;
        color: #111;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .rating-label {
        font-size: 34px;
        font-weight: 700;
        color: #9ea0a6;
    }

    /* League line */
    .league {
        display: flex;
        align-items: center;
        gap: 14px;
        margin-top: 16px;
    }

    .league-text {
        font-size: 32px;
        font-weight: 600;
        color: #cfcfd2;
    }

    /* Info row */
    .info {
        margin-top: 14px;
        font-size: 18px;
        color: #b0b0b3;
    }

    h2 {
        font-size: 34px;
        margin-top: 40px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

crest = load_img(CREST_PATH)
flag = load_img(FLAG_PATH)
perf = load_img(PERFORMANCE_IMAGE_PATH)

# ---------- HEADER ----------
st.markdown('<div class="club-card">', unsafe_allow_html=True)
c1, c2 = st.columns([1.4, 6], vertical_alignment="center")

with c1:
    st.markdown('<div class="crest-box">', unsafe_allow_html=True)
    if crest:
        st.image(crest, width=150)
    st.markdown('</div>', unsafe_allow_html=True)

with c2:
    st.markdown(f'<p class="team-title">{TEAM_NAME}</p>', unsafe_allow_html=True)

    def rating(value, label):
        return f"""
        <div class="rating">
            <div class="pill" style="background:{score_color(value)}">{value}</div>
            <div class="rating-label">{label}</div>
        </div>
        """

    st.markdown(
        f"""
        <div class="ratings">
            {rating(OVERALL, "Overall")}
            {rating(ATT, "ATT")}
            {rating(MID, "MID")}
            {rating(DEF, "DEF")}
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<div class="league">', unsafe_allow_html=True)
    if flag:
        st.image(flag, width=56)
    st.markdown(f'<div class="league-text">{LEAGUE_TEXT}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="info"><b>Average Age:</b> {AVG_AGE:.2f} &nbsp;&nbsp; <b>League Position:</b> {LEAGUE_POSITION}</div>',
        unsafe_allow_html=True
    )

st.markdown('</div>', unsafe_allow_html=True)

# ---------- PERFORMANCE ----------
st.markdown("## Performance")
if perf:
    st.image(perf, use_container_width=True)

