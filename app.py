import os
import re
import base64
import unicodedata
import textwrap
import pandas as pd
import numpy as np
import streamlit as st
import streamlit.components.v1 as components

# =========================
# CONFIG
# =========================
CSV_PATH = "Chinaall.csv"
TEAM_NAME = "Chengdu Rongcheng"

CREST_PATH = "images/chengdu_rongcheng_f.c.svg.png"
FLAG_PATH = "images/china.png"
PERFORMANCE_IMAGE_PATH = "images/chengugraph.png"

# Header manual inputs
OVERALL = 88
ATT_HDR = 66
MID_HDR = 77
DEF_HDR = 79
LEAGUE_TEXT = "Super League"
AVG_AGE = 24.32
LEAGUE_POSITION = 2

DEFAULT_AVATAR = "https://i.redd.it/43axcjdu59nd1.jpeg"

# =========================
# COLOR SCALE
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

def _pro_rating_color(v: float) -> str:
    try:
        v = float(v)
    except Exception:
        v = 0.0
    for thr, col in COLORS:
        if v >= thr:
            return col
    return COLORS[-1][1]

def _pro_show99(x) -> int:
    try:
        return max(0, min(99, int(float(x))))
    except Exception:
        return 0

def _fmt2(n: int) -> str:
    try:
        return f"{int(n):02d}"
    except Exception:
        return "00"

# =========================
# POSITION CHIP COLORS
# =========================
_POS_COLORS = {
    "CF":"#6EA8FF","LWF":"#6EA8FF","LW":"#6EA8FF","LAMF":"#6EA8FF","RW":"#6EA8FF","RWF":"#6EA8FF","RAMF":"#6EA8FF",
    "AMF":"#7FE28A","LCMF":"#5FD37A","RCMF":"#5FD37A","RDMF":"#31B56B","LDMF":"#31B56B","DMF":"#31B56B","CMF":"#5FD37A",
    "LWB":"#FFD34D","RWB":"#FFD34D","LB":"#FF9A3C","RB":"#FF9A3C","RCB":"#D1763A","CB":"#D1763A","LCB":"#D1763A",
    "GK":"#B8A1FF",
}
def _pro_chip_color(p: str) -> str:
    return _POS_COLORS.get(str(p).strip().upper(), "#2d3550")

# =========================
# FLAGS (Twemoji)
# =========================
TWEMOJI_SPECIAL = {
    "eng":"1f3f4-e0067-e0062-e0065-e006e-e0067-e007f",
    "sct":"1f3f4-e0067-e0062-e0073-e0063-e0074-e007f",
    "wls":"1f3f4-e0067-e0062-e0077-e006c-e0073-e007f",
}

COUNTRY_TO_CC = {
    "china":"cn",
    "england":"eng","scotland":"sct","wales":"wls",
    "united kingdom":"gb","great britain":"gb",
    "brazil":"br","argentina":"ar","uruguay":"uy",
    "spain":"es","france":"fr","germany":"de","italy":"it","portugal":"pt",
    "netherlands":"nl","belgium":"be","sweden":"se","norway":"no","denmark":"dk","poland":"pl",
    "japan":"jp","south korea":"kr","korea":"kr",
    "united states":"us","usa":"us","canada":"ca","australia":"au",
    "israel":"il",
}

def _norm(s: str) -> str:
    if not s:
        return ""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii").strip().lower()

def _cc_to_twemoji(cc: str):
    if not cc or len(cc) != 2:
        return None
    a, b = cc.upper()
    cp1 = 0x1F1E6 + (ord(a) - ord("A"))
    cp2 = 0x1F1E6 + (ord(b) - ord("A"))
    return f"{cp1:04x}-{cp2:04x}"

def _flag_html(country_name: str) -> str:
    if not country_name:
        return "<span class='chip'>—</span>"
    n = _norm(country_name)
    cc = COUNTRY_TO_CC.get(n, "")
    if not cc:
        return "<span class='chip'>—</span>"

    if cc in TWEMOJI_SPECIAL:
        code = TWEMOJI_SPECIAL[cc]
        src = f"https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/svg/{code}.svg"
        return f"<span class='flagchip'><img src='{src}' alt='{country_name}'></span>"

    code = _cc_to_twemoji(cc) if len(cc) == 2 else None
    if code:
        src = f"https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/svg/{code}.svg"
        return f"<span class='flagchip'><img src='{src}' alt='{country_name}'></span>"

    return f"<span class='chip'>{cc.upper()}</span>"

# --- SAFE foot extractor ---
def _get_foot(row) -> str:
    for col in ("Foot","Preferred foot","Preferred Foot"):
        if col in row.index:
            val = row[col]
            try:
                if pd.isna(val):
                    continue
            except Exception:
                pass
            s = str(val).strip()
            if s and s.lower() not in {"nan","none","null"}:
                return s
    return ""

# =========================
# ROLES (weights)
# =========================
CB_ROLES = {
    "Ball Playing CB": {"Passes per 90":2,"Accurate passes, %":2,"Forward passes per 90":2,"Accurate forward passes, %":2,
                        "Progressive passes per 90":2,"Progressive runs per 90":1.5,"Dribbles per 90":1.5,"Accurate long passes, %":1,
                        "Passes to final third per 90":1.5},
    "Wide CB": {"Defensive duels per 90":1.5,"Defensive duels won, %":2,"Dribbles per 90":2,"Forward passes per 90":1,
                "Progressive passes per 90":1,"Progressive runs per 90":2},
    "Box Defender": {"Aerial duels per 90":1,"Aerial duels won, %":3,"PAdj Interceptions":2,"Shots blocked per 90":1,"Defensive duels won, %":4},
}

FB_ROLES = {
    "Build Up FB": {"Passes per 90":2,"Accurate passes, %":1.5,"Forward passes per 90":2,"Accurate forward passes, %":2,
                    "Progressive passes per 90":2.5,"Progressive runs per 90":2,"Dribbles per 90":2,"Passes to final third per 90":2,"xA per 90":1},
    "Attacking FB": {"Crosses per 90":2,"Dribbles per 90":3.5,"Accelerations per 90":1,"Successful dribbles, %":1,"Touches in box per 90":2,
                     "Progressive runs per 90":3,"Passes to penalty area per 90":2,"xA per 90":3},
    "Defensive FB": {"Aerial duels per 90":1,"Aerial duels won, %":1.5,"Defensive duels per 90":2,"PAdj Interceptions":3,"Shots blocked per 90":1,"Defensive duels won, %":3.5},
}

CM_ROLES = {
    "Deep Playmaker": {"Passes per 90":1,"Accurate passes, %":1,"Forward passes per 90":2,"Accurate forward passes, %":1.5,
                       "Progressive passes per 90":3,"Passes to final third per 90":2.5,"Accurate long passes, %":1},
    "Advanced Playmaker": {"Deep completions per 90":1.5,"Smart passes per 90":2,"xA per 90":4,"Passes to penalty area per 90":2},
    "Defensive Midfielder": {"Defensive duels per 90":4,"Defensive duels won, %":4,"PAdj Interceptions":3,"Aerial duels per 90":0.5,"Aerial duels won, %":1},
    "Goal Threat": {"Non-penalty goals per 90":3,"xG per 90":3,"Shots per 90":1.5,"Touches in box per 90":2},
    "Ball-Carrying": {"Dribbles per 90":4,"Successful dribbles, %":2,"Progressive runs per 90":3,"Accelerations per 90":3},
}

ATT_ROLES = {
    "Playmaker": {"Passes per 90":2,"xA per 90":3,"Key passes per 90":1,"Deep completions per 90":1.5,"Smart passes per 90":1.5,"Passes to penalty area per 90":2},
    "Goal Threat": {"xG per 90":3,"Non-penalty goals per 90":3,"Shots per 90":2,"Touches in box per 90":2},
    "Ball Carrier": {"Dribbles per 90":4,"Successful dribbles, %":2,"Progressive runs per 90":3,"Accelerations per 90":3},
}

CF_ROLES = {
    "Target Man CF": {"Aerial duels per 90":3,"Aerial duels won, %":5},
    "Goal Threat CF": {"Non-penalty goals per 90":3,"Shots per 90":1.5,"xG per 90":3,"Touches in box per 90":1,"Shots on target, %":0.5},
    "Link-Up CF": {"Passes per 90":2,"Passes to penalty area per 90":1.5,"Deep completions per 90":1,"Smart passes per 90":1.5,"Accurate passes, %":1.5,
                   "Key passes per 90":1,"Dribbles per 90":2,"Successful dribbles, %":1,"Progressive runs per 90":2,"xA per 90":3},
}

GK_ROLES = {
    "Shot Stopper GK": {"Prevented goals per 90":3, "Save rate, %":1},
    "Ball Playing GK": {"Passes per 90":1, "Accurate passes, %":3, "Accurate long passes, %":2},
    "Sweeper GK": {"Exits per 90":1},
}

LOWER_BETTER = {"Conceded goals per 90"}  # invert percentiles for these

# =========================
# HELPERS
# =========================
ATT_VALID_PRIMARY = ("RW", "LW", "LWF", "RWF", "AMF", "LAMF", "RAMF")

def add_primary_position(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["Primary Position"] = out["Position"].astype(str).str.split(",").str[0].str.strip().str.upper()
    return out

def pos_group(primary_pos: str) -> str:
    p = str(primary_pos).strip().upper()
    if p.startswith("GK"):
        return "GK"
    if p.startswith(("LCB","RCB","CB")):
        return "CB"
    if p.startswith(("RB","RWB","LB","LWB")):
        return "FB"
    if p.startswith(("LCMF","RCMF","LDMF","RDMF","DMF","CMF")):
        return "CM"
    if p in set(ATT_VALID_PRIMARY):
        return "ATT"
    if p.startswith("CF"):
        return "CF"
    return "OTHER"

def detect_minutes_col(df: pd.DataFrame) -> str:
    for c in ["Minutes played","Minutes Played","Minutes","mins","minutes","Min"]:
        if c in df.columns:
            return c
    return "Minutes played"

def metrics_used_by_roles() -> set:
    rolesets = [CB_ROLES, FB_ROLES, CM_ROLES, ATT_ROLES, CF_ROLES, GK_ROLES]
    s = set()
    for rs in rolesets:
        for _, wmap in rs.items():
            s |= set(wmap.keys())
    return s

def add_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    used = metrics_used_by_roles()
    out = df.copy()

    for m in used:
        if m in out.columns:
            out[m] = pd.to_numeric(out[m], errors="coerce")

    for m in used:
        if m not in out.columns:
            continue

        pct = out.groupby("PosGroup")[m].transform(lambda s: s.rank(pct=True) * 100)

        if m in LOWER_BETTER:
            pct = 100 - pct

        out[f"{m} Percentile"] = pct.fillna(0)

    return out

def weighted_role_score(row: pd.Series, weights: dict) -> int:
    num, den = 0.0, 0.0
    for metric, w in weights.items():
        col = f"{metric} Percentile"
        v = row.get(col, 0)
        try:
            v = float(v)
        except Exception:
            v = 0.0
        if pd.isna(v):
            v = 0.0
        num += w * v
        den += w
    return _pro_show99((num / den) if den > 0 else 0.0)

def compute_role_scores_for_row(row: pd.Series) -> dict:
    g = row.get("PosGroup", "OTHER")
    if g == "GK":
        return {k: weighted_role_score(row, w) for k, w in GK_ROLES.items()}
    if g == "CB":
        return {k: weighted_role_score(row, w) for k, w in CB_ROLES.items()}
    if g == "FB":
        return {k: weighted_role_score(row, w) for k, w in FB_ROLES.items()}
    if g == "CM":
        roles = {k: weighted_role_score(row, w) for k, w in CM_ROLES.items()}
        return dict(sorted(roles.items(), key=lambda x: x[1], reverse=True)[:3])
    if g == "ATT":
        return {k: weighted_role_score(row, w) for k, w in ATT_ROLES.items()}
    if g == "CF":
        return {k: weighted_role_score(row, w) for k, w in CF_ROLES.items()}
    return {}

def img_to_data_uri(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    ext = os.path.splitext(path)[1].lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/{ext};base64,{b64}"

def _age_text(row: pd.Series) -> str:
    if "Age" in row.index:
        try:
            a = int(float(row["Age"]))
            return f"{a}y.o." if a > 0 else "—"
        except Exception:
            return "—"
    return "—"

def _contract_year(row: pd.Series) -> str:
    for c in ("Contract expires", "Contract Expires", "Contract", "Contract expiry"):
        if c in row.index:
            cy = pd.to_datetime(row.get(c), errors="coerce")
            return f"{int(cy.year)}" if pd.notna(cy) else "—"
    return "—"

def _positions_html(pos: str) -> str:
    raw = (pos or "").strip().upper()
    tokens = [t for t in re.split(r"[,\s/;]+", raw) if t]
    seen, ordered = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return "".join(f"<span class='postext' style='color:{_pro_chip_color(t)}'>{t}</span>" for t in ordered)

def metric_sections_for_group(g: str):
    g = (g or "").strip().upper()

    # ========== GOALKEEPER ==========
    if g == "GK":
        return {
            "GOALKEEPING": [
                ("Exits", "Exits per 90"),
                ("Goals Prevented", "Prevented goals per 90"),
                ("Goals Conceded", "Conceded goals per 90"),   # LOWER IS BETTER (inverted via LOWER_BETTER)
                ("Save Rate", "Save rate, %"),
                ("Shots Against", "Shots against per 90"),
                ("xG Against", "xG against per 90"),
            ],
            "POSSESSION": [
                ("Passes", "Passes per 90"),
                ("Passing Accuracy %", "Accurate passes, %"),
                ("Long Passes", "Long passes per 90"),
                ("Long Passing %", "Accurate long passes, %"),
            ],
        }

    # ========== CENTER BACKS ==========
    if g == "CB":
        return {
            "ATTACKING": [
                ("Goals: Non-Penalty", "Non-penalty goals per 90"),
                ("xG", "xG per 90"),
                ("Offensive Duels", "Offensive duels per 90"),
                ("Offensive Duel Success %", "Offensive duels won, %"),
                ("Progressive Runs", "Progressive runs per 90"),
            ],
            "DEFENSIVE": [
                ("Aerial Duels", "Aerial duels per 90"),
                ("Aerial Duel Success %", "Aerial duels won, %"),
                ("Defensive Duels", "Defensive duels per 90"),
                ("Defensive Duel Success %", "Defensive duels won, %"),
                ("PAdj Interceptions", "PAdj Interceptions"),
                ("Shots Blocked", "Shots blocked per 90"),
                ("Successful Defensive Actions", "Successful defensive actions per 90"),
            ],
            "POSSESSION": [
                ("Accelerations", "Accelerations per 90"),
                ("Dribbles", "Dribbles per 90"),
                ("Dribbling Success %", "Successful dribbles, %"),
                ("Forward Passes", "Forward passes per 90"),
                ("Forward Passing Accuracy %", "Accurate forward passes, %"),
                ("Long Passes", "Long passes per 90"),
                ("Long Passing Success %", "Accurate long passes, %"),
                ("Passes", "Passes per 90"),
                ("Passing Accuracy %", "Accurate passes, %"),
                ("Passes to Final 3rd", "Passes to final third per 90"),
                ("Passes to Final 3rd Success %", "Accurate passes to final third, %"),
                ("Progessive Passes", "Progressive passes per 90"),
                ("Progessive Passing Success %", "Accurate progressive passes, %"),
            ],
        }

    # ========== STRIKER (CF) ==========
    if g == "CF":
        return {
            "ATTACKING": [
                ("Crosses", "Crosses per 90"),
                ("Crossing Accuracy %", "Accurate crosses, %"),
                ("Goals: Non-Penalty", "Non-penalty goals per 90"),
                ("xG", "xG per 90"),
                ("Conversion Rate %", "Goal conversion, %"),
                ("Header Goals", "Head goals per 90"),
                ("Expected Assists", "xA per 90"),
                ("Offensive Duels", "Offensive duels per 90"),
                ("Offensive Duel Success %", "Offensive duels won, %"),
                ("Progressive Runs", "Progressive runs per 90"),
                ("Shots", "Shots per 90"),
                ("Shooting Accuracy %", "Shots on target, %"),
                ("Touches in Opposition Box", "Touches in box per 90"),
            ],
            "DEFENSIVE": [
                ("Aerial Duels", "Aerial duels per 90"),
                ("Aerial Duel Success %", "Aerial duels won, %"),
                ("Defensive Duels", "Defensive duels per 90"),
                ("Defensive Duel Success %", "Defensive duels won, %"),
                ("PAdj. Interceptions", "PAdj Interceptions"),
                ("Successful Def. Actions", "Successful defensive actions per 90"),
            ],
            "POSSESSION": [
                ("Deep Completions", "Deep completions per 90"),
                ("Dribbles", "Dribbles per 90"),
                ("Dribbling Success %", "Successful dribbles, %"),
                ("Key Passes", "Key passes per 90"),
                ("Passes", "Passes per 90"),
                ("Passing Accuracy %", "Accurate passes, %"),
                ("Passes to Penalty Area", "Passes to penalty area per 90"),
                ("Passes to Penalty Area %", "Accurate passes to penalty area, %"),
                ("Smart Passes", "Smart passes per 90"),
            ],
        }

    # ========== FULLBACKS + CENTRAL MIDFIELD + ATTACKERS (same) ==========
    # Covers FB / CM / ATT plus any fallback (OTHER)
    return {
        "ATTACKING": [
            ("Crosses", "Crosses per 90"),
            ("Crossing %", "Accurate crosses, %"),
            ("Goals: Non-Penalty", "Non-penalty goals per 90"),
            ("xG", "xG per 90"),
            ("Expected Assists", "xA per 90"),
            ("Offensive Duels", "Offensive duels per 90"),
            ("Offensive Duel %", "Offensive duels won, %"),
            ("Shots", "Shots per 90"),
            ("Shooting %", "Shots on target, %"),
            ("Touches in box", "Touches in box per 90"),
        ],
        "DEFENSIVE": [
            ("Aerial Duels", "Aerial duels per 90"),
            ("Aerial Win %", "Aerial duels won, %"),
            ("Defensive Duels", "Defensive duels per 90"),
            ("Defensive Duel %", "Defensive duels won, %"),
            ("PAdj Interceptions", "PAdj Interceptions"),
            ("Shots blocked", "Shots blocked per 90"),
            ("Succ. def acts", "Successful defensive actions per 90"),
        ],
        "POSSESSION": [
            ("Accelerations", "Accelerations per 90"),
            ("Deep completions", "Deep completions per 90"),
            ("Dribbles", "Dribbles per 90"),
            ("Dribbling %", "Successful dribbles, %"),
            ("Forward Passes", "Forward passes per 90"),
            ("Forward Pass %", "Accurate forward passes, %"),
            ("Key passes", "Key passes per 90"),
            ("Long Passes", "Long passes per 90"),
            ("Long Pass %", "Accurate long passes, %"),
            ("Passes", "Passes per 90"),
            ("Passing %", "Accurate passes, %"),
            ("Passes to F3rd", "Passes to final third per 90"),
            ("Passes F3rd %", "Accurate passes to final third, %"),
            ("Passes Pen-Area", "Passes to penalty area per 90"),
            ("Pass Pen-Area %", "Accurate passes to penalty area, %"),
            ("Progessive Passes", "Progressive passes per 90"),
            ("Prog Pass %", "Accurate progressive passes, %"),
            ("Progressive Runs", "Progressive runs per 90"),
            ("Smart Passes", "Smart passes per 90"),
        ],
    }


    # slim per group
    if g == "CB":
        return {"DEFENSIVE": DEF, "POSSESSION": POS}
    if g == "FB":
        return {"ATTACKING": ATT, "DEFENSIVE": DEF, "POSSESSION": POS}
    if g == "CM":
        return {"ATTACKING": ATT, "DEFENSIVE": DEF, "POSSESSION": POS}
    if g == "ATT":
        return {"ATTACKING": ATT, "POSSESSION": POS}
    if g == "CF":
        return {"ATTACKING": ATT, "POSSESSION": POS, "DEFENSIVE": DEF}

    return {"POSSESSION": POS}

def metric_badge_html(row: pd.Series, metric: str):
    col = f"{metric} Percentile"
    val = row.get(col, 0)
    try:
        val = float(val)
    except Exception:
        val = 0.0
    p = _pro_show99(val)
    return f"<div class='m-badge' style='background:{_pro_rating_color(p)}'>{_fmt2(p)}</div>"

# =========================
# STREAMLIT SETUP
# =========================
st.set_page_config(page_title="Club View", layout="wide", initial_sidebar_state="collapsed")

# Pro-layout font smoothing / numeric style (back to original vibe)
st.markdown("""
<style>
html, body, .block-container *{
  -webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;
  text-rendering:optimizeLegibility;
  font-feature-settings:"liga","kern","tnum";
  font-variant-numeric:tabular-nums;
}
.stApp { background:#0e0e0f; color:#f2f2f2; }
.block-container { padding-top:1.3rem; padding-bottom:2rem; max-width:1150px; }
header, footer { visibility:hidden; }

.section-title{
  font-size: 40px;
  font-weight: 900;
  letter-spacing: 1px;
  margin-top: 26px;
  margin-bottom: 12px;
  color: #f2f2f2;
}

/* PRO CARD */
.pro-wrap{ display:flex; justify-content:center; }
.pro-card{
  position:relative; width:min(720px,98%);
  display:grid; grid-template-columns:96px 1fr 64px;
  gap:12px; align-items:start;
  background:#141823; border:1px solid rgba(255,255,255,.06); border-radius:20px;
  padding:16px; margin-bottom:12px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.03), 0 6px 24px rgba(0,0,0,.35);
}
.pro-avatar{ width:96px; height:96px; border-radius:12px; border:1px solid #2a3145; overflow:hidden; background:#0b0d12; }
.pro-avatar img{ width:100%; height:100%; object-fit:cover; image-rendering:auto; transform:translateZ(0); }

.flagchip{ display:inline-flex; align-items:center; gap:6px; background:transparent; border:none; padding:0; height:auto;}
.flagchip img{ width:26px; height:18px; border-radius:2px; display:block; }

.chip{ background:transparent; color:#a6a6a6; border:none; padding:0; border-radius:0; font-size:15px; line-height:18px; opacity:.92; }
.row{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:2px 0; }
.leftrow1{ margin-top:6px; } .leftrow-foot{ margin-top:2px; } .leftrow-contract{ margin-top:10px; }

.pill{ padding:2px 6px; min-width:36px; border-radius:6px; font-weight:700; font-size:18px; line-height:1; color:#0b0d12; text-align:center; display:inline-block; box-shadow:none; }

.name{ font-weight:800; font-size:22px; color:#e8ecff; margin-bottom:6px; letter-spacing:.2px; line-height:1.15; }
.sub{ color:#a8b3cf; font-size:15px; opacity:.9; }

.posrow{ margin-top:13.5px; }
.postext{ font-weight:600; font-size:14.5px; letter-spacing:.2px; margin-right:11px; }

.rank{ position:absolute; top:10.5px; right:14px; color:#b7bfe1; font-weight:800; font-size:18px; text-align:right; pointer-events:none; }

.teamline{ color:#dbe3ff; font-size:14px; font-weight:600; margin-top:6.5px; letter-spacing:.05px; opacity:.95; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

/* Individual metrics (card dropdown) */
.m-sec{ background:#121621; border:1px solid #242b3b; border-radius:16px; padding:10px 12px; }
.m-title{ color:#e8ecff; font-weight:800; letter-spacing:.02em; margin:4px 0 10px 0; }
.m-row{ display:flex; justify-content:space-between; align-items:center; padding:8px 8px; border-radius:10px; }
.m-label{ color:#c9d3f2; font-size:15.5px; letter-spacing:.1px; flex:1 1 auto; }
.m-badge{ flex:0 0 auto; min-width:44px; text-align:center; padding:2px 10px; border-radius:8px; font-weight:700; font-size:18.5px; color:#0b0d12; border:1px solid rgba(0,0,0,.15); box-shadow:none; }
.metrics-grid{ display:grid; grid-template-columns:1fr; gap:12px; }
@media (min-width: 720px){ .metrics-grid{ grid-template-columns:repeat(3,1fr);} }
</style>
""", unsafe_allow_html=True)

# =========================
# LOAD CSV
# =========================
if not os.path.exists(CSV_PATH):
    st.error(f"CSV not found at: {CSV_PATH}. Upload it to your repo root.")
    st.stop()

df_all = pd.read_csv(CSV_PATH)

need_cols = {"Team", "Player", "Position"}
if not need_cols.issubset(set(df_all.columns)):
    st.error(f"CSV must include at least: {', '.join(sorted(list(need_cols)))}")
    st.stop()

mins_col = detect_minutes_col(df_all)
df_all[mins_col] = pd.to_numeric(df_all[mins_col], errors="coerce").fillna(0)

df_all = add_primary_position(df_all)
df_all["PosGroup"] = df_all["Primary Position"].apply(pos_group)

# =========================
# HEADER (single iframe OK)
# =========================
crest_uri = img_to_data_uri(CREST_PATH)
flag_uri = img_to_data_uri(FLAG_PATH)

header_html = f"""
<!doctype html>
<html><head><meta charset="utf-8">
<style>
body{{margin:0;background:transparent;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;}}
.club-card{{background:#1c1c1d;border:1px solid #2a2a2b;border-radius:20px;padding:24px;}}
.header-grid{{display:grid;grid-template-columns:260px 1fr;gap:26px;align-items:start;}}
.crest-tile{{width:260px;height:220px;background:#121213;border:1px solid #2a2a2b;border-radius:20px;display:flex;align-items:center;justify-content:center;overflow:hidden;}}
.crest-img{{width:200px;height:200px;object-fit:contain;}}
.left-league{{display:flex;align-items:center;gap:12px;padding-left:6px;}}
.flag-img{{width:56px;height:40px;object-fit:cover;border-radius:6px;}}
.team-title{{font-size:54px;font-weight:850;margin:0;line-height:1.05;color:#f2f2f2;}}
.ratings-col{{display:flex;flex-direction:column;gap:12px;margin-top:12px;}}
.metric{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}}
.pill{{width:56px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:900;color:#111;border:1px solid rgba(0,0,0,.35);}}
.label{{font-size:34px;font-weight:700;color:#9ea0a6;line-height:1;}}
.triplet{{display:flex;gap:26px;flex-wrap:wrap;align-items:center;}}
.info{{margin-top:10px;display:flex;flex-direction:column;gap:6px;font-size:18px;color:#b0b0b3;}}
</style></head>
<body>
<div class="club-card">
  <div class="header-grid">
    <div>
      <div class="crest-tile">{f"<img class='crest-img' src='{crest_uri}' />" if crest_uri else ""}</div>
      <div class="left-league">
        {f"<img class='flag-img' src='{flag_uri}' />" if flag_uri else ""}
        <div style="font-size:28px;font-weight:700;color:#d2d2d4;line-height:1;">{LEAGUE_TEXT}</div>
      </div>
    </div>
    <div>
      <div class="team-title">{TEAM_NAME}</div>
      <div class="ratings-col">
        <div class="metric">
          <div class="pill" style="background:{_pro_rating_color(OVERALL)}">{OVERALL}</div>
          <div class="label">Overall</div>
        </div>
        <div class="triplet">
          <div class="metric">
            <div class="pill" style="background:{_pro_rating_color(ATT_HDR)}">{ATT_HDR}</div>
            <div class="label">ATT</div>
          </div>
          <div class="metric">
            <div class="pill" style="background:{_pro_rating_color(MID_HDR)}">{MID_HDR}</div>
            <div class="label">MID</div>
          </div>
          <div class="metric">
            <div class="pill" style="background:{_pro_rating_color(DEF_HDR)}">{DEF_HDR}</div>
            <div class="label">DEF</div>
          </div>
        </div>
        <div class="info">
          <div><b>Average Age:</b> {AVG_AGE:.2f}</div>
          <div><b>League Position:</b> {LEAGUE_POSITION}</div>
        </div>
      </div>
    </div>
  </div>
</div>
</body></html>
"""
components.html(header_html, height=360)

# =========================
# PERFORMANCE
# =========================
st.markdown('<div class="section-title">PERFORMANCE</div>', unsafe_allow_html=True)
if PERFORMANCE_IMAGE_PATH and os.path.exists(PERFORMANCE_IMAGE_PATH):
    st.image(PERFORMANCE_IMAGE_PATH, use_container_width=True)
else:
    st.warning(f"Performance image not found: {PERFORMANCE_IMAGE_PATH}")

# =========================
# SQUAD + FILTERS (UNDER SQUAD)
# =========================
st.markdown('<div class="section-title" style="margin-top:30px;">SQUAD</div>', unsafe_allow_html=True)

# ---- Controls must be here (under Squad title) ----
c1, c2 = st.columns([1.2, 1.0])

max_mins = int(max(5000, float(df_all[mins_col].max() if len(df_all) else 5000)))

with c1:
    minutes_range = st.slider(
        "Minutes (affects role scores / percentiles)",
        min_value=0,
        max_value=max_mins,
        value=(500, min(5000, max_mins)),
        step=50
    )

with c2:
    age_range = st.slider(
        "Age (display only)",
        min_value=16,
        max_value=45,
        value=(16, 45),
        step=1
    )

# ---- Pool = minutes range (affects percentiles/roles) ----
pool = df_all[(df_all[mins_col] >= minutes_range[0]) & (df_all[mins_col] <= minutes_range[1])].copy()
if pool.empty:
    st.info("No players exist inside this minutes range. Widen the slider.")
    st.stop()

pool = add_percentiles(pool)

# ---- Team from pool ----
df_team = pool[pool["Team"].astype(str).str.strip() == TEAM_NAME].copy()
if df_team.empty:
    st.info(f"No players found for Team='{TEAM_NAME}' inside this minutes range.")
    st.stop()

# role scores
df_team["RoleScores"] = df_team.apply(compute_role_scores_for_row, axis=1)

# display age filter (does not change pool)
df_view = df_team.copy()
if "Age" in df_view.columns:
    df_view["Age_num"] = pd.to_numeric(df_view["Age"], errors="coerce")
    df_view = df_view[(df_view["Age_num"] >= age_range[0]) & (df_view["Age_num"] <= age_range[1])].copy()

# sort by minutes DESC
df_view = df_view.sort_values(mins_col, ascending=False).reset_index(drop=True)

if df_view.empty:
    st.info("No players match the Age display filter.")
    st.stop()

# =========================
# RENDER CARDS (with per-card metrics dropdown)
# =========================
for i, row in df_view.iterrows():
    player = str(row.get("Player", "—"))
    league = str(row.get("League", ""))
    pos = str(row.get("Position", ""))
    birth = str(row.get("Birth country", "")) if "Birth country" in df_view.columns else ""
    foot = _get_foot(row) or "—"
    age_txt = _age_text(row)
    contract_txt = _contract_year(row)
    mins = int(row.get(mins_col, 0) or 0)

    roles = row.get("RoleScores", {})
    if not isinstance(roles, dict):
        roles = {}
    roles_sorted = sorted(roles.items(), key=lambda x: x[1], reverse=True)

    pills_html = "".join(
        f"<div class='row' style='align-items:center;'>"
        f"<span class='pill' style='background:{_pro_rating_color(v)}'>{_fmt2(v)}</span>"
        f"<span class='sub'>{k}</span>"
        f"</div>"
        for k, v in roles_sorted
    ) if roles_sorted else "<div class='row'><span class='chip'>No role scores</span></div>"

    flag = _flag_html(birth)
    pos_html = _positions_html(pos)

    card_html = f"""
    <div class='pro-wrap'>
      <div class='pro-card'>
        <div>
          <div class='pro-avatar'>
            <img src="{DEFAULT_AVATAR}" alt="{player}" loading="lazy" />
          </div>
          <div class='row leftrow1'>{flag}<span class='chip'>{age_txt}</span><span class='chip'>{mins} mins</span></div>
          <div class='row leftrow-foot'><span class='chip'>{foot}</span></div>
          <div class='row leftrow-contract'><span class='chip'>{contract_txt}</span></div>
        </div>

        <div>
          <div class='name'>{player}</div>
          {pills_html}
          <div class='row posrow'>{pos_html}</div>
          <div class='teamline'>{TEAM_NAME} · {league}</div>
        </div>

        <div class='rank'>#{_fmt2(i+1)}</div>
      </div>
    </div>
    """
    st.markdown(" ".join(card_html.split()), unsafe_allow_html=True)

    # --- Individual player metrics dropdown (FROM CARD) ---
    exp_key = f"ind_metrics_{i}_{player}_{mins}"
with st.expander("Individual Metrics", expanded=False):

    def pct_of(met: str) -> float:
        col = f"{met} Percentile"
        v = row.get(col, 0)
        try:
            return float(np.nan_to_num(v, nan=0.0))
        except Exception:
            return 0.0

    def raw_of(met: str) -> str:
        if met not in row.index:
            return "—"
        v = row.get(met, np.nan)
        try:
            v = float(v)
        except Exception:
            return str(v) if v is not None else "—"
        if np.isnan(v):
            return "—"
        # formatting: % columns cleaner
        if "%" in met:
            return f"{v:.0f}%"
        return f"{v:.2f}"

    g = str(row.get("PosGroup", "OTHER")).strip().upper()
    sections = metric_sections_for_group(g)

    def _sec_html(title, pairs):
        rows_html = []
        for lab, met in pairs:
            if met not in row.index:
                continue

            p = _pro_show99(pct_of(met))
            badge = f"<div class='m-badge' style='background:{_pro_rating_color(p)}'>{_fmt2(p)}</div>"
            raw = raw_of(met)

            rows_html.append(
                f"<div class='m-row'>"
                f"<div class='m-label'>{lab} <span style='opacity:.65'>({raw})</span></div>"
                f"{badge}"
                f"</div>"
            )

        if not rows_html:
            rows_html = [f"<div class='m-row'><div class='m-label'>No metrics found for this section.</div><div></div></div>"]

        return f"<div class='m-sec'><div class='m-title'>{title}</div>{''.join(rows_html)}</div>"

    sec_blocks = [_sec_html(title, pairs) for title, pairs in sections.items()]
    st.markdown("<div class='metrics-grid'>" + "".join(sec_blocks) + "</div>", unsafe_allow_html=True)
    st.caption(f"Percentiles are within minutes pool {minutes_range[0]}–{minutes_range[1]} (by PosGroup).")














