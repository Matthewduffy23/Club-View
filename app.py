import os
import streamlit as st
from PIL import Image

st.set_page_config(page_title="Club View", layout="wide")

# --- paths to your preloaded images (as per your repo) ---
DEFAULT_CREST = "images/chengdu_rongcheng_f.c.svg.png"
DEFAULT_FLAG = "images/china.png"
DEFAULT_PERF = "images/chengugraph.png"

def pill(label: str, value: int) -> str:
    # Yellow stat pill like your screenshot
    return f"""
    <span style="
        display:inline-flex; align-items:center; gap:10px;
        padding:8px 12px; border-radius:12px;
        background:#F3C845; color:#111;
        border:1px solid #D3AE2E;
        font-weight:800; font-size:20px; line-height:1;
        margin-right:10px;
    ">
      <span style="font-size:20px;">{value}</span>
      <span style="opacity:.85; font-weight:700; font-size:16px;">{label}</span>
    </span>
    """

def safe_image(path: str):
    if path and os.path.exists(path):
        return Image.open(path)
    return None

def render_top_card(
    team_name: str,
    overall: int,
    att: int,
    pos: int,
    deff: int,
    league_text: str,
    avg_age: float,
    league_position: int,
    crest_path: str,
    flag_path: str,
):
    st.markdown(
        """
        <style>
          .topcard{
            background:#222;
            border:1px solid #2f2f2f;
            border-radius:18px;
            padding:18px;
          }
          .title{
            color:#fff;
            font-size:42px;
            font-weight:900;
            margin:0;
          }
          .muted{ color:#b9b9b9; }
        </style>
        """,
        unsafe_allow_html=True
    )

    crest = safe_image(crest_path)
    flag = safe_image(flag_path)

    st.markdown('<div class="topcard">', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 5], vertical_alignment="center")

    with c1:
        if crest:
            st.image(crest, width=120)

    with c2:
        st.markdown(f'<p class="title">{team_name}</p>', unsafe_allow_html=True)

        st.markdown(
            pill("Overall", overall) + pill("ATT", att) + pill("POS", pos) + pill("DEF", deff),
            unsafe_allow_html=True
        )

        cflag, ctext = st.columns([1, 10], vertical_alignment="center")
        with cflag:
            if flag:
                st.image(flag, width=44)
        with ctext:
            st.markdown(
                f'<span class="muted" style="font-size:24px;">{league_text}</span>',
                unsafe_allow_html=True
            )

        st.markdown(
            f"""
            <div class="muted" style="font-size:18px; margin-top:10px;">
              <b>Average Age:</b> {avg_age:.2f}
              &nbsp;&nbsp;&nbsp; <b>League Position:</b> {league_position}
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("</div>", unsafe_allow_html=True)


# ---------------- Sidebar: manual inputs ----------------
st.sidebar.header("Club Header Inputs")

team_name = st.sidebar.text_input("Team name", "Chengdu Rongcheng")
league_text = st.sidebar.text_input("League text", "Super League")

colA, colB = st.sidebar.columns(2)
with colA:
    overall = st.number_input("Overall", 0, 99, 88)
    att = st.number_input("ATT", 0, 99, 66)
with colB:
    pos = st.number_input("POS", 0, 99, 77)
    deff = st.number_input("DEF", 0, 99, 79)

avg_age = st.sidebar.number_input("Average Age", 0.0, 60.0, 24.32, step=0.01, format="%.2f")
league_position = st.sidebar.number_input("League Position", 1, 50, 2)

# Optional: let you override image filepaths later (still manual, but no uploads)
st.sidebar.subheader("Image paths (optional)")
crest_path = st.sidebar.text_input("Crest image path", DEFAULT_CREST)
flag_path = st.sidebar.text_input("Flag image path", DEFAULT_FLAG)
performance_path = st.sidebar.text_input("Performance chart image path", DEFAULT_PERF)

# ---------------- Main page ----------------
render_top_card(
    team_name=team_name,
    overall=int(overall),
    att=int(att),
    pos=int(pos),
    deff=int(deff),
    league_text=league_text,
    avg_age=float(avg_age),
    league_position=int(league_position),
    crest_path=crest_path,
    flag_path=flag_path,
)

st.write("")
st.subheader("Performance")
perf_img = safe_image(performance_path)
if perf_img:
    st.image(perf_img, use_container_width=True)
else:
    st.warning(f"Performance image not found at: {performance_path}")
