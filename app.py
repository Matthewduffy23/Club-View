import os
import re
import json
import base64
import unicodedata
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

# =========================
# CONFIG (edit in code only)
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

# Photo auto-match (FotMob squad page)
FOTMOB_SQUAD_URL = "https://www.fotmob.com/teams/737052/squad/chengdu-rongcheng-fc"

# Hidden admin photo overrides (NOT shown to normal users)
# - stored locally on the server as JSON (Streamlit Cloud keeps it in the repo workspace)
PHOTO_OVERRIDES_PATH = Path("data/player_photos_overrides.json")
PHOTO_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)

# Optional: protect editor with a password in .streamlit/secrets.toml:
# ADMIN_PASS="yourpassword"
ADMIN_PASS = st.secrets.get("ADMIN_PASS", "")

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
        return max(0, min(99, int(round(float(x)))))
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
    "china pr":"cn",            # ✅ required by you
    "pr china":"cn",
    "people's republic of china":"cn",
    "england":"eng","scotland":"sct","wales":"wls",
    "united kingdom":"gb","great britain":"gb",
    "brazil":"br","argentina":"ar","spain":"es","france":"fr","germany":"de","italy":"it","portugal":"pt",
    "netherlands":"nl","belgium":"be","sweden":"se","norway":"no","denmark":"dk","poland":"pl","japan":"jp","south korea":"kr",
    "israel":"il","croatia":"hr","serbia":"rs","australia":"au","new zealand":"nz","united states":"us","usa":"us",
}

def _norm(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode("ascii")
    return s.strip().lower()

def _norm_series(sr: pd.Series) -> pd.Series:
    return sr.astype(str).map(_norm)

def _cc_to_twemoji(cc: str):
    if not cc or len(cc) != 2:
        return None
    a,b = cc.upper()
    cp1 = 0x1F1E6 + (ord(a)-ord("A"))
    cp2 = 0x1F1E6 + (ord(b)-ord("A"))
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
    else:
        code = _cc_to_twemoji(cc) if len(cc) == 2 else None

    if code:
        src = f"https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/svg/{code}.svg"
        return f"<span class='flagchip'><img src='{src}' alt='{country_name}'></span>"
    return f"<span class='chip'>{cc.upper()}</span>"

# =========================
# SAFE FOOT EXTRACTOR
# =========================
def _get_foot(row: pd.Series) -> str:
    for col in ("Foot","Preferred foot","Preferred Foot"):
        if col in row.index:
            v = row.get(col)
            if pd.isna(v):
                continue
            s = str(v).strip()
            if s and s.lower() not in {"nan","none","null"}:
                return s
    return ""

# =========================
# ROLE DEFINITIONS
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

# Lower is better -> invert percentile (your requirement)
LOWER_BETTER = {"Conceded goals per 90"}

def pos_group_from_primary(primary_pos: str) -> str:
    p = str(primary_pos).strip().upper()
    if p.startswith("GK"):
        return "GK"
    if p.startswith(("LCB","RCB","CB")):
        return "CB"
    if p.startswith(("RB","RWB","LB","LWB")):
        return "FB"
    if p.startswith(("LCMF","RCMF","LDMF","RDMF","DMF","CMF")):
        return "CM"
    if p in {"RW","RWF","RAMF","LW","LWF","LAMF","AMF"}:
        return "ATT"
    if p.startswith("CF"):
        return "CF"
    return "OTHER"

def weighted_role_score(row: pd.Series, weights: dict[str, float]) -> int:
    num, den = 0.0, 0.0
    for metric, w in weights.items():
        col = f"{metric} Percentile"
        v = row.get(col, np.nan)
        try:
            v = float(v)
        except Exception:
            v = np.nan
        if pd.isna(v):
            continue
        num += w * v
        den += w
    score_0_100 = (num / den) if den > 0 else 0.0
    return _pro_show99(score_0_100)

def compute_role_scores_for_row(row: pd.Series) -> dict[str, int]:
    g = row.get("PosGroup","OTHER")
    if g == "GK":
        return {k: weighted_role_score(row, w) for k,w in GK_ROLES.items()}
    if g == "CB":
        return {k: weighted_role_score(row, w) for k,w in CB_ROLES.items()}
    if g == "FB":
        return {k: weighted_role_score(row, w) for k,w in FB_ROLES.items()}
    if g == "CM":
        roles = {k: weighted_role_score(row, w) for k,w in CM_ROLES.items()}
        return dict(sorted(roles.items(), key=lambda x:x[1], reverse=True)[:3])  # top 3 only
    if g == "ATT":
        return {k: weighted_role_score(row, w) for k,w in ATT_ROLES.items()}
    if g == "CF":
        return {k: weighted_role_score(row, w) for k,w in CF_ROLES.items()}
    return {}

def detect_minutes_col(df: pd.DataFrame) -> str:
    for c in ["Minutes played","Minutes Played","Minutes","mins","minutes","Min"]:
        if c in df.columns:
            return c
    return "Minutes played"

def img_to_data_uri(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    ext = os.path.splitext(path)[1].lower().replace(".","")
    if ext == "jpg":
        ext = "jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/{ext};base64,{b64}"

# =========================
# Individual metrics (by position group) — ONLY show metrics that exist + have a percentile
# =========================
GK_GOALKEEPING = [
    ("Exits", "Exits per 90"),
    ("Goals Prevented", "Prevented goals per 90"),
    ("Goals Conceded", "Conceded goals per 90"),  # lower is better -> inverted percentile
    ("Save Rate", "Save rate, %"),
    ("Shots Against", "Shots against per 90"),
    ("xG Against", "xG against per 90"),
]
GK_POSSESSION = [
    ("Passes", "Passes per 90"),
    ("Passing Accuracy %", "Accurate passes, %"),
    ("Long Passes", "Long passes per 90"),
    ("Long Passing %", "Accurate long passes, %"),
]

CB_ATTACKING = [
    ("Goals: Non-Penalty", "Non-penalty goals per 90"),
    ("xG", "xG per 90"),
    ("Offensive Duels", "Offensive duels per 90"),
    ("Offensive Duel Success %", "Offensive duels won, %"),
    ("Progressive Runs", "Progressive runs per 90"),
]
CB_DEFENSIVE = [
    ("Aerial Duels", "Aerial duels per 90"),
    ("Aerial Duel Success %", "Aerial duels won, %"),
    ("Defensive Duels", "Defensive duels per 90"),
    ("Defensive Duel Success %", "Defensive duels won, %"),
    ("PAdj Interceptions", "PAdj Interceptions"),
    ("Shots Blocked", "Shots blocked per 90"),
    ("Successful Defensive Actions", "Successful defensive actions per 90"),
]
CB_POSSESSION = [
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
]

GEN_ATTACKING = [
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
]
GEN_DEFENSIVE = [
    ("Aerial Duels", "Aerial duels per 90"),
    ("Aerial Win %", "Aerial duels won, %"),
    ("Defensive Duels", "Defensive duels per 90"),
    ("Defensive Duel %", "Defensive duels won, %"),
    ("PAdj Interceptions", "PAdj Interceptions"),
    ("Shots blocked", "Shots blocked per 90"),
    ("Succ. def acts", "Successful defensive actions per 90"),
]
GEN_POSSESSION = [
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
]

CF_ATTACKING = [
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
]
CF_DEFENSIVE = [
    ("Aerial Duels", "Aerial duels per 90"),
    ("Aerial Duel Success %", "Aerial duels won, %"),
    ("Defensive Duels", "Defensive duels per 90"),
    ("Defensive Duel Success %", "Defensive duels won, %"),
    ("PAdj. Interceptions", "PAdj Interceptions"),
    ("Successful Def. Actions", "Successful defensive actions per 90"),
]
CF_POSSESSION = [
    ("Deep Completions", "Deep completions per 90"),
    ("Dribbles", "Dribbles per 90"),
    ("Dribbling Success %", "Successful dribbles, %"),
    ("Key Passes", "Key passes per 90"),
    ("Passes", "Passes per 90"),
    ("Passing Accuracy %", "Accurate passes, %"),
    ("Passes to Penalty Area", "Passes to penalty area per 90"),
    ("Passes to Penalty Area %", "Accurate passes to penalty area, %"),
    ("Smart Passes", "Smart passes per 90"),
]

def metrics_used_by_roles() -> set[str]:
    rolesets = [CB_ROLES, FB_ROLES, CM_ROLES, ATT_ROLES, CF_ROLES, GK_ROLES]
    s = set()
    for rs in rolesets:
        for _, wmap in rs.items():
            s |= set(wmap.keys())
    return s

def metrics_used_by_individual_sections() -> set[str]:
    all_lists = [
        GK_GOALKEEPING, GK_POSSESSION,
        CB_ATTACKING, CB_DEFENSIVE, CB_POSSESSION,
        GEN_ATTACKING, GEN_DEFENSIVE, GEN_POSSESSION,
        CF_ATTACKING, CF_DEFENSIVE, CF_POSSESSION,
    ]
    s = set()
    for lst in all_lists:
        for _, met in lst:
            s.add(met)
    return s

# =========================
# Percentiles: computed on POOL (minutes slider) and merged to display rows
# =========================
def add_percentiles_on_pool(df_pool: pd.DataFrame, used_metrics: set[str]) -> pd.DataFrame:
    out = df_pool.copy()
    for m in used_metrics:
        if m in out.columns:
            out[m] = pd.to_numeric(out[m], errors="coerce")

    # rank within PosGroup
    for m in used_metrics:
        if m not in out.columns:
            continue
        pct = out.groupby("PosGroup")[m].transform(lambda s: s.rank(pct=True) * 100.0)
        if m in LOWER_BETTER:
            pct = 100.0 - pct
        out[f"{m} Percentile"] = pct
    return out

# =========================
# FotMob photo map (surname match)
# =========================
@st.cache_data(ttl=60*60*6)
def fetch_fotmob_photo_map(url: str) -> dict[str, str]:
    """
    Returns mapping of normalized player name/surname -> FotMob image URL.
    Best-effort: parse playerimages/<id>.png references found in HTML.
    """
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
        html = r.text
    except Exception:
        return {}

    # Find player image IDs
    ids = sorted(set(re.findall(r"playerimages/(\d+)\.png", html)))
    # Also try to capture names near those ids (best effort)
    # Many pages embed JSON with "name":"..." — grab those too.
    names = re.findall(r'"name"\s*:\s*"([^"]+)"', html)

    # If names list exists, map surname -> one of the ids in order (best-effort).
    # If not, still allow id-based images via overrides.
    photo_map: dict[str, str] = {}
    base = "https://images.fotmob.com/image_resources/playerimages/{}.png"

    if names and ids:
        n = min(len(names), len(ids))
        for i in range(n):
            nm = names[i]
            pid = ids[i]
            full = _norm(nm)
            sur = _norm(nm.split()[-1]) if nm.strip() else ""
            if full:
                photo_map[full] = base.format(pid)
            if sur:
                # surname key (used for matching your request)
                photo_map[sur] = base.format(pid)

    # Fallback: if we couldn't align names, at least store the ids (won't be used unless you override)
    for pid in ids[:500]:
        photo_map[f"id:{pid}"] = base.format(pid)

    return photo_map

def load_photo_overrides() -> dict:
    if PHOTO_OVERRIDES_PATH.exists():
        try:
            return json.loads(PHOTO_OVERRIDES_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_photo_overrides(d: dict) -> None:
    PHOTO_OVERRIDES_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

def get_player_photo(player_name: str, fotmob_map: dict[str,str], overrides: dict) -> str:
    """
    Priority:
      1) overrides exact full-name key
      2) overrides surname key
      3) fotmob surname match
      4) default avatar
    """
    full = _norm(player_name)
    sur = _norm(player_name.split()[-1]) if player_name else ""
    if full and full in overrides:
        return overrides[full]
    if sur and sur in overrides:
        return overrides[sur]
    if sur and sur in fotmob_map:
        return fotmob_map[sur]
    if full and full in fotmob_map:
        return fotmob_map[full]
    return DEFAULT_AVATAR

# =========================
# STREAMLIT SETUP (restore font smoothing like your old pro layout)
# =========================
st.set_page_config(page_title="Club View", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
html, body, .block-container *{
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; text-rendering:optimizeLegibility;
  font-feature-settings:"liga","kern","tnum"; font-variant-numeric:tabular-nums;
}
.stApp { background:#0e0e0f; color:#f2f2f2; }
.block-container { padding-top:1.1rem; padding-bottom:2rem; max-width:1150px; }
header, footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

# =========================
# LOAD CSV
# =========================
if not os.path.exists(CSV_PATH):
    st.error(f"CSV not found at: {CSV_PATH}. Upload it to your repo root.")
    st.stop()

df_all = pd.read_csv(CSV_PATH)

req_cols = {"Team","Player","Position"}
missing = [c for c in req_cols if c not in df_all.columns]
if missing:
    st.error(f"CSV missing required columns: {missing}")
    st.stop()

mins_col = detect_minutes_col(df_all)
df_all[mins_col] = pd.to_numeric(df_all[mins_col], errors="coerce").fillna(0)

# Primary Position (your attacker fix)
df_all["Position"] = df_all["Position"].astype(str)
df_all["Primary Position"] = df_all["Position"].astype(str).str.split(",").str[0].str.strip()
df_all["PosGroup"] = df_all["Primary Position"].apply(pos_group_from_primary)

# =========================
# HEADER (compact / mobile-friendly)
# =========================
crest_uri = img_to_data_uri(CREST_PATH)
flag_uri = img_to_data_uri(FLAG_PATH)

st.markdown("""
<style>
.club-card{
  background:#1c1c1d; border:1px solid #2a2a2b; border-radius:18px;
  padding:14px 14px;
}
.header-grid{
  display:grid;
  grid-template-columns: 120px 1fr;
  gap: 14px;
  align-items:center;
}
.crest-tile{
  width:120px; height:98px;
  background:#121213; border:1px solid #2a2a2b; border-radius:16px;
  display:flex; align-items:center; justify-content:center; overflow:hidden;
}
.crest-img{ width:84px; height:84px; object-fit:contain; }
.left-league{ display:flex; align-items:center; gap:10px; margin-top:8px; }
.flag-img{ width:42px; height:30px; object-fit:cover; border-radius:6px; }
.league-text{ font-size:20px; font-weight:750; color:#d2d2d4; line-height:1; }

.team-title{
  font-size: clamp(26px, 5.7vw, 44px);
  font-weight: 900; line-height:1.05; margin:0; color:#f2f2f2;
}
.pill{
  width:48px; height:36px; border-radius:12px;
  display:flex; align-items:center; justify-content:center;
  font-size:20px; font-weight:900; color:#111;
  border:1px solid rgba(0,0,0,.35);
}
.label{ font-size:22px; font-weight:800; color:#9ea0a6; }
.triplet{ display:flex; gap:16px; flex-wrap:wrap; align-items:center; margin-top:10px; }
.metric{ display:flex; align-items:center; gap:10px; }
.info{ margin-top:10px; display:flex; flex-direction:column; gap:4px; font-size:14px; color:#b0b0b3; }

@media (min-width: 820px){
  .header-grid{ grid-template-columns: 160px 1fr; }
  .crest-tile{ width:160px; height:120px; }
  .crest-img{ width:105px; height:105px; }
  .league-text{ font-size:24px; }
  .pill{ width:56px; height:42px; font-size:24px; }
  .label{ font-size:28px; }
}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="club-card">
  <div class="header-grid">
    <div>
      <div class="crest-tile">
        {f"<img class='crest-img' src='{crest_uri}' />" if crest_uri else ""}
      </div>
      <div class="left-league">
        {f"<img class='flag-img' src='{flag_uri}' />" if flag_uri else ""}
        <div class="league-text">{LEAGUE_TEXT}</div>
      </div>
    </div>
    <div>
      <div class="team-title">{TEAM_NAME}</div>

      <div class="metric" style="margin-top:10px;">
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
""", unsafe_allow_html=True)

# =========================
# PERFORMANCE
# =========================
st.markdown("""
<style>
.section-title{
  font-size: clamp(26px, 6vw, 40px);
  font-weight: 900; letter-spacing: 1px;
  margin-top: 22px; margin-bottom: 12px; color: #f2f2f2;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="section-title">PERFORMANCE</div>', unsafe_allow_html=True)
if PERFORMANCE_IMAGE_PATH and os.path.exists(PERFORMANCE_IMAGE_PATH):
    st.image(PERFORMANCE_IMAGE_PATH, use_container_width=True)
else:
    st.warning(f"Performance image not found: {PERFORMANCE_IMAGE_PATH}")

# =========================
# SQUAD + CONTROLS (UNDER SQUAD TITLE as you demanded)
# =========================
st.markdown('<div class="section-title" style="margin-top:24px;">SQUAD</div>', unsafe_allow_html=True)

# Controls row under SQUAD
c1, c2, c3 = st.columns([2.2, 2.0, 1.5])
with c1:
    pool_min, pool_max = st.slider(
        "Minutes (pool + display)",
        min_value=0, max_value=int(max(5000, df_all[mins_col].max() if len(df_all) else 5000)),
        value=(500, 5000), step=10
    )
with c2:
    age_min, age_max = st.slider(
        "Age (display only)",
        min_value=16, max_value=45,
        value=(16, 45), step=1
    )
with c3:
    visa_only = st.checkbox("Visa players (exclude China PR)", value=False)

# =========================
# Build POOL (minutes affects calculation)
# =========================
df_pool = df_all[(df_all[mins_col] >= pool_min) & (df_all[mins_col] <= pool_max)].copy()

# used metrics for BOTH role scores + individual dropdowns (so we don't get fake 00s)
USED_METRICS = metrics_used_by_roles() | metrics_used_by_individual_sections()

# ensure missing columns don't explode
for m in USED_METRICS:
    if m in df_pool.columns:
        df_pool[m] = pd.to_numeric(df_pool[m], errors="coerce")

# percentiles on pool
df_pool = add_percentiles_on_pool(df_pool, USED_METRICS)

# =========================
# Build DISPLAY df for TEAM (minutes filter affects display too)
# =========================
df_team = df_all[df_all["Team"].astype(str).str.strip() == TEAM_NAME].copy()
if df_team.empty:
    st.info(f"No players found for Team = '{TEAM_NAME}'.")
    st.stop()

df_team[mins_col] = pd.to_numeric(df_team[mins_col], errors="coerce").fillna(0)
df_disp = df_team[(df_team[mins_col] >= pool_min) & (df_team[mins_col] <= pool_max)].copy()

# display-only age filter
if "Age" in df_disp.columns:
    age_num = pd.to_numeric(df_disp["Age"], errors="coerce")
    df_disp = df_disp[(age_num >= age_min) & (age_num <= age_max)].copy()

# visa toggle (exclude China PR in display only)
if visa_only and "Birth country" in df_disp.columns:
    bc = _norm_series(df_disp["Birth country"])
    df_disp = df_disp[bc.ne("china pr")].copy()

# sort by minutes desc
df_disp = df_disp.sort_values(mins_col, ascending=False).reset_index(drop=True)

if df_disp.empty:
    st.info("No players match the current filters.")
    st.stop()

# =========================
# Merge percentiles from pool onto display rows
# (Key = Player + Team + League + Minutes played + Position)
# =========================
def make_key(df: pd.DataFrame) -> pd.Series:
    league = df["League"] if "League" in df.columns else ""
    return (
        df["Player"].astype(str).fillna("") + "||" +
        df["Team"].astype(str).fillna("") + "||" +
        league.astype(str).fillna("") + "||" +
        df[mins_col].astype(str).fillna("") + "||" +
        df["Position"].astype(str).fillna("")
    )

df_pool_keyed = df_pool.copy()
df_disp_keyed = df_disp.copy()
df_pool_keyed["_k"] = make_key(df_pool_keyed)
df_disp_keyed["_k"] = make_key(df_disp_keyed)

pct_cols = [c for c in df_pool_keyed.columns if c.endswith(" Percentile")]
pool_pct = df_pool_keyed[["_k","PosGroup"] + pct_cols].drop_duplicates("_k", keep="first")

df_disp_keyed = df_disp_keyed.merge(pool_pct, on="_k", how="left", suffixes=("", ""))

# fill missing percentiles with NaN (so we can hide metrics without calculation)
# (don’t force to 0; 0 was making it look like "00" when actually missing)
for c in pct_cols:
    if c in df_disp_keyed.columns:
        df_disp_keyed[c] = pd.to_numeric(df_disp_keyed[c], errors="coerce")

# role scores from percentiles
df_disp_keyed["RoleScores"] = df_disp_keyed.apply(compute_role_scores_for_row, axis=1)

# =========================
# Pro card CSS + badge mini (use SAME crest as header)
# =========================
st.markdown("""
<style>
:root { --card:#141823; --soft:#1e2533; }

.pro-wrap{ display:flex; justify-content:center; }
.pro-card{
  position:relative; width:min(720px,98%);
  display:grid; grid-template-columns:96px 1fr 64px;
  gap:12px; align-items:start;
  background:var(--card); border:1px solid rgba(255,255,255,.06);
  border-radius:20px; padding:16px; margin-bottom:14px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.03), 0 6px 24px rgba(0,0,0,.35);
}
.pro-avatar{ width:96px; height:96px; border-radius:12px; border:1px solid #2a3145; overflow:hidden; background:#0b0d12; }
.pro-avatar img{ width:100%; height:100%; object-fit:cover; }

.flagchip{ display:inline-flex; align-items:center; gap:6px; background:transparent; border:none; padding:0; height:auto;}
.flagchip img{ width:26px; height:18px; border-radius:2px; display:block; }

.chip{ background:transparent; color:#a6a6a6; border:none; padding:0; border-radius:0; font-size:15px; line-height:18px; opacity:.92; }
.row{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:2px 0; }
.leftrow1{ margin-top:6px; } .leftrow-foot{ margin-top:2px; } .leftrow-contract{ margin-top:10px; }

.pillscore{ padding:2px 6px; min-width:36px; border-radius:6px; font-weight:900; font-size:18px; line-height:1; color:#0b0d12; text-align:center; display:inline-block; }
.name{ font-weight:950; font-size:22px; color:#e8ecff; margin-bottom:6px; letter-spacing:.2px; line-height:1.15; }
.sub{ color:#a8b3cf; font-size:15px; opacity:.9; }

.posrow{ margin-top:12px; }
.postext{ font-weight:800; font-size:14.5px; letter-spacing:.2px; margin-right:10px; }

.rank{ position:absolute; top:10px; right:14px; color:#b7bfe1; font-weight:900; font-size:18px; }

.teamline{ color:#dbe3ff; font-size:14px; font-weight:700; margin-top:6px; letter-spacing:.05px; opacity:.95; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.teamline-wrap{ display:flex; align-items:center; gap:8px; }
.badge-mini{ width:16px; height:16px; border-radius:3px; object-fit:contain; display:inline-block; }

.m-sec{ background:#121621; border:1px solid #242b3b; border-radius:16px; padding:10px 12px; }
.m-title{ color:#e8ecff; font-weight:900; letter-spacing:.02em; margin:4px 0 10px 0; }
.m-row{ display:flex; justify-content:space-between; align-items:center; padding:8px 8px; border-radius:10px; }
.m-label{ color:#c9d3f2; font-size:15.5px; letter-spacing:.1px; flex:1 1 auto; }
.m-badge{ flex:0 0 auto; min-width:44px; text-align:center; padding:2px 10px; border-radius:8px; font-weight:900; font-size:18px; color:#0b0d12; border:1px solid rgba(0,0,0,.15); }
.metrics-grid{ display:grid; grid-template-columns:1fr; gap:12px; }
@media (min-width: 720px){ .metrics-grid{ grid-template-columns:repeat(3,1fr);} }
</style>
""", unsafe_allow_html=True)

def _contract_year(row: pd.Series) -> str:
    for c in ("Contract expires","Contract Expires","Contract","Contract expiry"):
        if c in row.index:
            cy = pd.to_datetime(row.get(c), errors="coerce")
            return f"{int(cy.year)}" if pd.notna(cy) else "—"
    return "—"

def _age_text(row: pd.Series) -> str:
    if "Age" in row.index:
        a = pd.to_numeric(row.get("Age"), errors="coerce")
        try:
            a = int(a) if not pd.isna(a) else 0
        except Exception:
            a = 0
        return f"{a}y.o." if a > 0 else "—"
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

def pct_of(row: pd.Series, metric: str) -> float | None:
    col = f"{metric} Percentile"
    if col not in row.index:
        return None
    v = row.get(col)
    if v is None or pd.isna(v):
        return None
    try:
        return float(v)
    except Exception:
        return None

def build_metrics_sections(row: pd.Series) -> list[tuple[str, list[tuple[str, str]]]]:
    g = row.get("PosGroup","OTHER")
    if g == "GK":
        return [
            ("GOALKEEPING", GK_GOALKEEPING),
            ("POSSESSION", GK_POSSESSION),
        ]
    if g == "CB":
        return [
            ("ATTACKING", CB_ATTACKING),
            ("DEFENSIVE", CB_DEFENSIVE),
            ("POSSESSION", CB_POSSESSION),
        ]
    if g == "CF":
        return [
            ("ATTACKING", CF_ATTACKING),
            ("DEFENSIVE", CF_DEFENSIVE),
            ("POSSESSION", CF_POSSESSION),
        ]
    # FB, CM, ATT all use the same blocks you specified
    if g in {"FB","CM","ATT"}:
        return [
            ("ATTACKING", GEN_ATTACKING),
            ("DEFENSIVE", GEN_DEFENSIVE),
            ("POSSESSION", GEN_POSSESSION),
        ]
    return []

def section_html(title: str, pairs: list[tuple[str,str]], row: pd.Series) -> str:
    rows = []
    # ✅ don’t display metrics with no calculation
    for lab, met in pairs:
        p = pct_of(row, met)
        if p is None:
            continue
        pp = _pro_show99(p)
        rows.append(
            f"<div class='m-row'>"
            f"<div class='m-label'>{lab}</div>"
            f"<div class='m-badge' style='background:{_pro_rating_color(pp)}'>{_fmt2(pp)}</div>"
            f"</div>"
        )
    if not rows:
        return ""  # hide whole section if nothing calculable
    return f"<div class='m-sec'><div class='m-title'>{title}</div>{''.join(rows)}</div>"

# =========================
# Photos (FotMob + hidden overrides)
# =========================
fotmob_map = fetch_fotmob_photo_map(FOTMOB_SQUAD_URL)
photo_overrides = load_photo_overrides()

# Optional hidden editor (only if password set + correct)
with st.sidebar:
    st.caption("Admin")
    if ADMIN_PASS:
        pw = st.text_input("Admin password", type="password")
        is_admin = (pw == ADMIN_PASS)
    else:
        is_admin = False

    if is_admin:
        st.write("Hidden player photo overrides (saved server-side)")
        st.write("Key can be full name or surname (normalized). Value must be an image URL.")
        key_in = st.text_input("Player key (full name or surname)")
        url_in = st.text_input("Image URL")
        colA, colB = st.columns(2)
        with colA:
            if st.button("Save override"):
                k = _norm(key_in)
                if k and (url_in.startswith("http://") or url_in.startswith("https://")):
                    photo_overrides[k] = url_in.strip()
                    save_photo_overrides(photo_overrides)
                    st.success("Saved.")
                else:
                    st.error("Provide a valid key + http(s) URL.")
        with colB:
            if st.button("Delete override"):
                k = _norm(key_in)
                if k in photo_overrides:
                    photo_overrides.pop(k, None)
                    save_photo_overrides(photo_overrides)
                    st.success("Deleted.")

# =========================
# RENDER CARDS
# - Uses st.markdown (NOT components.html) so HTML never prints as text
# - Badge icon uses SAME crest as top
# =========================
badge_mini_html = f"<img class='badge-mini' src='{crest_uri}' alt=''>" if crest_uri else ""

for i, row in df_disp_keyed.iterrows():
    player = str(row.get("Player","—"))
    league = str(row.get("League",""))
    pos = str(row.get("Position",""))
    birth = str(row.get("Birth country","")) if "Birth country" in df_disp_keyed.columns else ""
    foot = _get_foot(row) or "—"
    age_txt = _age_text(row)
    contract_txt = _contract_year(row)
    mins = int(row.get(mins_col, 0) or 0)

    # photo
    avatar_url = get_player_photo(player, fotmob_map, photo_overrides)

    # roles
    roles = row.get("RoleScores", {})
    if not isinstance(roles, dict):
        roles = {}
    roles_sorted = sorted(roles.items(), key=lambda x: x[1], reverse=True)

    pills_html = "".join(
        f"<div class='row' style='align-items:center;'>"
        f"<span class='pillscore' style='background:{_pro_rating_color(v)}'>{_fmt2(v)}</span>"
        f"<span class='sub'>{k}</span>"
        f"</div>"
        for k, v in roles_sorted
    ) if roles_sorted else "<div class='row'><span class='sub'>No role scores</span></div>"

    flag = _flag_html(birth)
    pos_html = _positions_html(pos)

    st.markdown(f"""
    <div class='pro-wrap'>
      <div class='pro-card'>
        <div>
          <div class='pro-avatar'>
            <img src="{avatar_url}" alt="{player}" loading="lazy" />
          </div>
          <div class='row leftrow1'>{flag}<span class='chip'>{age_txt}</span><span class='chip'>{mins} mins</span></div>
          <div class='row leftrow-foot'><span class='chip'>{foot}</span></div>
          <div class='row leftrow-contract'><span class='chip'>{contract_txt}</span></div>
        </div>

        <div>
          <div class='name'>{player}</div>
          {pills_html}
          <div class='row posrow'>{pos_html}</div>
          <div class='teamline teamline-wrap'>{badge_mini_html}<span>{TEAM_NAME} · {league}</span></div>
        </div>

        <div class='rank'>#{_fmt2(i+1)}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Individual metrics dropdown (per position group)
    with st.expander("Individual Metrics", expanded=False):
        sections = build_metrics_sections(row)
        blocks = []
        for title, pairs in sections:
            h = section_html(title, pairs, row)
            if h:
                blocks.append(h)
        if not blocks:
            st.info("No calculable percentile metrics found for this player under current pool.")
        else:
            st.markdown("<div class='metrics-grid'>" + "".join(blocks) + "</div>", unsafe_allow_html=True)



















