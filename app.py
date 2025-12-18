import os
import base64
import streamlit as st

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

def img_to_data_uri(path: str) -> str:
    """Embed local image as data URI so layout is pure HTML/CSS (no Streamlit image blocks)."""
    if not path or not os.path.exists(path):
        return ""
    ext = os.path.splitext(path)[1].lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/{ext};base64,{b64}"

crest_uri = img_to_data_uri(CREST_PATH)
flag_uri = img_to_data_uri(FLAG_PATH)

# ---------- GLOBAL DARK STYLING ----------
st.markdown(
    """
    <style>
      .stApp { background:#0e0e0f; color:#f2f2f2; }
      .block-container { padding-top:1.4rem; padding-bottom:2rem; max-width:1150px; }

      /* Card */
      .club-card{
        background:#1c1c1d;
        border:1px solid #2a2a2b;
        border-radius:20px;
        padding:24px;
      }

      /* Two-column header layout (like Swansea) */
      .header-grid{
        display:grid;
        grid-template-columns: 220px 1fr;
        gap: 26px;
        align-items: start;
      }

      /* Crest tile on the left */
      .crest-tile{
        width: 220px;
        height: 220px;
        background:#121213;
        border:1px solid #2a2a2b;
        border-radius:20px;
        display:flex;
        align-items:center;
        justify-content:center;
        overflow:hidden;
      }
      .crest-img{
        width: 180px;
        height: 180px;
        object-fit: contain;
        display:block;
      }

      /* Right side */
      .team-title{
        font-size:56px;
        font-weight:800;
        margin:0;
        line-height:1.05;
        color:#f2f2f2;
      }

      /* Rating rows */
      .ratings-col{
        display:flex;
        flex-direction:column;
        gap:16px;
        margin-top:14px;
      }

      .metric{
        display:flex;
        align-items:center;
        gap: 14px;
        flex-wrap: wrap;
      }

      /* small pill: number only */
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

      /* second row for ATT/MID/DEF */
      .triplet{
        display:flex;
        gap: 30px;
        flex-wrap: wrap;
        align-items:center;
      }

      /* League line */
      .league-row{
        display:flex;
        align-items:center;
        gap: 12px;
        margin-top: 14px;
      }

      .flag-img{
        width: 56px;
        height: 40px;
        object-fit: cover;
        border-radius: 6px;
        display:block;
      }

      /* smaller league font than title */
      .league-text{
        font-size:34px;
        font-weight:700;
        color:#d2d2d4;
        line-height:1;
      }

      /* Info on different rows */
      .info{
        margin-top: 14px;
        display:flex;
        flex-direction:column;
        gap: 6px;
        font-size:18px;
        color:#b0b0b3;
      }

      h2 { margin-top: 36px; font-size: 34px; }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------- HEADER (pure HTML so it cannot break into top/bottom) ----------
header_html = f"""
<div class="club-card">
  <div class="header-grid">

    <div class="crest-tile">
      {"<img class='crest-img' src='"+crest_uri+"'/>" if crest_uri else ""}
    </div>

    <div>
      <div class="team-title">{TEAM_NAME}</div>

      <div class="ratings-col">

        <!-- Overall row -->
        <div class="metric">
          <div class="pill" style="background:{score_color(OVERALL)}">{OVERALL}</div>
          <div class="label">Overall</div>
        </div>

        <!-- ATT / MID / DEF row -->
        <div class="triplet">
          <div class="metric">
            <div class="pill" style="background:{score_color(ATT)}">{ATT}</div>
            <div class="label">ATT</div>
          </div>

          <div class="metric">
            <div class="pill" style="background:{score_color(MID)}">{MID}</div>
            <div class="label">MID</div>
          </div>

          <div class="metric">
            <div class="pill" style="background:{score_color(DEF)}">{DEF}</div>
            <div class="label">DEF</div>
          </div>
        </div>

        <!-- Flag + League below badges -->
        <div class="league-row">
          {"<img class='flag-img' src='"+flag_uri+"'/>" if flag_uri else ""}
          <div class="league-text">{LEAGUE_TEXT}</div>
        </div>

        <!-- Info on different rows -->
        <div class="info">
          <div><b>Average Age:</b> {AVG_AGE:.2f}</div>
          <div><b>League Position:</b> {LEAGUE_POSITION}</div>
        </div>

      </div>
    </div>

  </div>
</div>
"""

st.markdown(header_html, unsafe_allow_html=True)

# ---------- PERFORMANCE ----------
st.markdown("## Performance")
if PERFORMANCE_IMAGE_PATH and os.path.exists(PERFORMANCE_IMAGE_PATH):
    st.image(PERFORMANCE_IMAGE_PATH, use_container_width=True)
else:
    st.warning(f"Performance image not found: {PERFORMANCE_IMAGE_PATH}")




