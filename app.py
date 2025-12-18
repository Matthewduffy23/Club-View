import os
import re
import base64
import unicodedata
import textwrap
from typing import Dict, List, Tuple, Optional

import pandas as pd
import numpy as np
import requests
import streamlit as st

# =========================
# CONFIG (edit in code only)
# =========================
CSV_PATH = "Chinaall.csv"
TEAM_NAME = "Chengdu Rongcheng"

CREST_PATH = "images/chengdu_rongcheng_f.c.svg.png"   # adjust if filename differs
FLAG_PATH = "images/china.png"                        # adjust if filename differs
PERFORMANCE_IMAGE_PATH = "images/chengugraph.png"     # your image

# Header manual inputs
OVERALL = 88
ATT_HDR = 66
MID_HDR = 77
DEF_HDR = 79
LEAGUE_TEXT = "Super League"
AVG_AGE = 24.32
LEAGUE_POSITION = 2

DEFAULT_AVATAR = "https://i.redd.it/43axcjdu59nd1.jpeg"

# Optional hidden local override file (NOT shown in UI)
# columns: Player, ImageURL   (Player should match your CSV Player string)
PLAYER_IMAGE_OVERRIDES_CSV = "player_images.csv"

# FotMob team squad page (used as fallback to auto-map pictures)
FOTMOB_SQUAD_URL = "https://www.fotmob.com/teams/737052/squad/chengdu-rongcheng-fc"


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
# NORMALIZATION
# =========================
def _norm_str(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()

def _norm_series(sr: pd.Series) -> pd.Series:
    # safe vectorized normalizer for visa toggle, etc.
    s = sr.astype(str).fillna("")
    s = s.map(_norm_str)
    return s


# =========================
# FLAGS (Twemoji)
# =========================
TWEMOJI_SPECIAL = {
    "eng":"1f3f4-e0067-e0062-e0065-e006e-e0067-e007f",
    "sct":"1f3f4-e0067-e0062-e0073-e0063-e0074-e007f",
    "wls":"1f3f4-e0067-e0062-e0077-e006c-e0073-e007f",
}
COUNTRY_TO_CC = {
    # IMPORTANT: China PR
    "china pr":"cn",
    "china":"cn",

    "england":"eng","scotland":"sct","wales":"wls",
    "united kingdom":"gb","great britain":"gb",

    "brazil":"br","argentina":"ar","spain":"es","france":"fr","germany":"de","italy":"it","portugal":"pt",
    "netherlands":"nl","belgium":"be","sweden":"se","norway":"no","denmark":"dk","poland":"pl","japan":"jp","south korea":"kr",
    "israel":"il","netherlands":"nl",
}

def _cc_to_twemoji(cc: str) -> Optional[str]:
    if not cc or len(cc) != 2:
        return None
    a, b = cc.upper()
    if not ("A" <= a <= "Z" and "A" <= b <= "Z"):
        return None
    cp1 = 0x1F1E6 + (ord(a) - ord("A"))
    cp2 = 0x1F1E6 + (ord(b) - ord("A"))
    return f"{cp1:04x}-{cp2:04x}"

def _flag_html(country_name: str) -> str:
    if not country_name or str(country_name).strip() == "" or str(country_name).lower() == "nan":
        return "<span class='chip'>—</span>"

    n = _norm_str(country_name)
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
    for col in ("Foot", "Preferred foot", "Preferred Foot"):
        if col in row.index:
            v = row.get(col)
            if pd.isna(v):
                continue
            s = str(v).strip()
            if s and s.lower() not in {"nan", "none", "null"}:
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

# LOWER is better -> invert percentile
LOWER_BETTER = {"Conceded goals per 90"}


# =========================
# POSITION GROUPING (Primary Position aware)
# =========================
VALID_ATTACK_POS = ('RW', 'LW', 'LWF', 'RWF', 'AMF', 'LAMF', 'RAMF')

def _primary_position(pos: str) -> str:
    # Primary Position = first token before comma
    s = str(pos or "").strip()
    if not s:
        return ""
    return s.split(",")[0].strip().upper()

def pos_group(primary_pos: str) -> str:
    p = str(primary_pos).strip().upper()
    if p.startswith("GK"):
        return "GK"
    if p.startswith(("LCB", "RCB", "CB")):
        return "CB"
    if p.startswith(("RB","RWB","LB","LWB")):
        return "FB"
    if p.startswith(("LCMF","RCMF","LDMF","RDMF","DMF","CMF")):
        return "CM"
    if p in set(VALID_ATTACK_POS):
        return "ATT"
    if p.startswith("CF"):
        return "CF"
    return "OTHER"


# =========================
# PERCENTILES + ROLE SCORES
# =========================
def metrics_used_by_roles() -> set:
    rolesets = [CB_ROLES, FB_ROLES, CM_ROLES, ATT_ROLES, CF_ROLES, GK_ROLES]
    s = set()
    for rs in rolesets:
        for _, wmap in rs.items():
            s |= set(wmap.keys())
    return s

USED_METRICS = metrics_used_by_roles()

def add_percentiles(pool_df: pd.DataFrame) -> pd.DataFrame:
    out = pool_df.copy()

    # ensure numeric
    for m in USED_METRICS:
        if m in out.columns:
            out[m] = pd.to_numeric(out[m], errors="coerce")

    for m in USED_METRICS:
        if m not in out.columns:
            continue

        # within position group
        pct = out.groupby("PosGroup")[m].transform(lambda s: s.rank(pct=True, method="average") * 100.0)

        if m in LOWER_BETTER:
            pct = 100.0 - pct

        out[f"{m} Percentile"] = pct.fillna(0.0)

    return out

def weighted_role_score(row: pd.Series, weights: Dict[str, float]) -> int:
    num, den = 0.0, 0.0
    for metric, w in weights.items():
        col = f"{metric} Percentile"
        if col not in row.index:
            continue
        v = row.get(col, 0.0)
        try:
            v = float(v)
        except Exception:
            v = 0.0
        if pd.isna(v):
            v = 0.0
        num += w * v
        den += w
    score_0_100 = (num / den) if den > 0 else 0.0
    return _pro_show99(score_0_100)

def compute_role_scores_for_row(row: pd.Series) -> Dict[str, int]:
    g = row.get("PosGroup","OTHER")
    if g == "GK":
        return {k: weighted_role_score(row, w) for k,w in GK_ROLES.items()}
    if g == "CB":
        return {k: weighted_role_score(row, w) for k,w in CB_ROLES.items()}
    if g == "FB":
        return {k: weighted_role_score(row, w) for k,w in FB_ROLES.items()}
    if g == "CM":
        roles = {k: weighted_role_score(row, w) for k,w in CM_ROLES.items()}
        return dict(sorted(roles.items(), key=lambda x:x[1], reverse=True)[:3])
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


# =========================
# IMAGES
# =========================
def img_to_data_uri(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    ext = os.path.splitext(path)[1].lower().replace(".","")
    if ext == "jpg":
        ext = "jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/{ext};base64,{b64}"

@st.cache_data(show_spinner=False, ttl=60*60)
def load_player_overrides_csv(path: str) -> Dict[str, str]:
    if not path or not os.path.exists(path):
        return {}
    try:
        o = pd.read_csv(path)
        if "Player" not in o.columns or "ImageURL" not in o.columns:
            return {}
        m = {}
        for _, r in o.iterrows():
            p = _norm_str(r.get("Player",""))
            u = str(r.get("ImageURL","")).strip()
            if p and u:
                m[p] = u
        return m
    except Exception:
        return {}

@st.cache_data(show_spinner=False, ttl=60*60)
def fotmob_name_to_image_map(url: str) -> Dict[str, str]:
    """
    Best-effort: parse FotMob squad page and extract player names + image IDs.
    We map by normalized surname (last token) AND normalized full name.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        }
        html = requests.get(url, headers=headers, timeout=15).text
    except Exception:
        return {}

    # Try to find "playerId":123 and "name":"Felipe" pairs in embedded JSON.
    # This regex is resilient enough for the current FotMob page structure.
    # We'll capture small windows around playerId and name.
    pairs = []
    for m in re.finditer(r'"playerId"\s*:\s*(\d+).*?"name"\s*:\s*"([^"]+)"', html, re.DOTALL):
        pid = m.group(1)
        name = m.group(2)
        if pid and name:
            pairs.append((name, pid))

    # If that failed, try inverse order
    if not pairs:
        for m in re.finditer(r'"name"\s*:\s*"([^"]+)".*?"playerId"\s*:\s*(\d+)', html, re.DOTALL):
            name = m.group(1)
            pid = m.group(2)
            if pid and name:
                pairs.append((name, pid))

    out: Dict[str, str] = {}
    for name, pid in pairs:
        img = f"https://images.fotmob.com/image_resources/playerimages/{pid}.png"
        nfull = _norm_str(name)
        if nfull:
            out[nfull] = img
            # surname key
            parts = nfull.split()
            if parts:
                out[parts[-1]] = img
    return out

def resolve_player_avatar(player_name: str, overrides: Dict[str, str], fotmob_map: Dict[str, str]) -> str:
    p = _norm_str(player_name)
    if p in overrides:
        return overrides[p]
    if p in fotmob_map:
        return fotmob_map[p]
    # surname match
    parts = p.split()
    if parts and parts[-1] in fotmob_map:
        return fotmob_map[parts[-1]]
    return DEFAULT_AVATAR


# =========================
# METRICS DROPDOWN DEFINITIONS (per PosGroup)
# - Only show metrics that exist and have a valid percentile column
# =========================
def metric_blocks_for_group(posgroup: str) -> List[Tuple[str, List[Tuple[str, str]]]]:
    # returns list of (section_title, [(label, metric_colname)])
    if posgroup == "GK":
        return [
            ("GOALKEEPING", [
                ("Exits", "Exits per 90"),
                ("Goals Prevented", "Prevented goals per 90"),
                ("Goals Conceded", "Conceded goals per 90"),  # lower better is already handled in percentile calc
                ("Save Rate", "Save rate, %"),
                ("Shots Against", "Shots against per 90"),
                ("xG Against", "xG against per 90"),
            ]),
            ("POSSESSION", [
                ("Passes", "Passes per 90"),
                ("Passing Accuracy %", "Accurate passes, %"),
                ("Long Passes", "Long passes per 90"),
                ("Long Passing %", "Accurate long passes, %"),
            ]),
        ]

    if posgroup == "CB":
        return [
            ("ATTACKING", [
                ("Goals: Non-Penalty", "Non-penalty goals per 90"),
                ("xG", "xG per 90"),
                ("Offensive Duels", "Offensive duels per 90"),
                ("Offensive Duel Success %", "Offensive duels won, %"),
                ("Progressive Runs", "Progressive runs per 90"),
            ]),
            ("DEFENSIVE", [
                ("Aerial Duels", "Aerial duels per 90"),
                ("Aerial Duel Success %", "Aerial duels won, %"),
                ("Defensive Duels", "Defensive duels per 90"),
                ("Defensive Duel Success %", "Defensive duels won, %"),
                ("PAdj Interceptions", "PAdj Interceptions"),
                ("Shots Blocked", "Shots blocked per 90"),
                ("Successful Defensive Actions", "Successful defensive actions per 90"),
            ]),
            ("POSSESSION", [
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
            ]),
        ]

    if posgroup in {"FB", "CM", "ATT"}:
        return [
            ("ATTACKING", [
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
            ]),
            ("DEFENSIVE", [
                ("Aerial Duels", "Aerial duels per 90"),
                ("Aerial Win %", "Aerial duels won, %"),
                ("Defensive Duels", "Defensive duels per 90"),
                ("Defensive Duel %", "Defensive duels won, %"),
                ("PAdj Interceptions", "PAdj Interceptions"),
                ("Shots blocked", "Shots blocked per 90"),
                ("Succ. def acts", "Successful defensive actions per 90"),
            ]),
            ("POSSESSION", [
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
            ]),
        ]

    if posgroup == "CF":
        return [
            ("ATTACKING", [
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
            ]),
            ("DEFENSIVE", [
                ("Aerial Duels", "Aerial duels per 90"),
                ("Aerial Duel Success %", "Aerial duels won, %"),
                ("Defensive Duels", "Defensive duels per 90"),
                ("Defensive Duel Success %", "Defensive duels won, %"),
                ("PAdj. Interceptions", "PAdj Interceptions"),
                ("Successful Def. Actions", "Successful defensive actions per 90"),
            ]),
            ("POSSESSION", [
                ("Deep Completions", "Deep completions per 90"),
                ("Dribbles", "Dribbles per 90"),
                ("Dribbling Success %", "Successful dribbles, %"),
                ("Key Passes", "Key passes per 90"),
                ("Passes", "Passes per 90"),
                ("Passing Accuracy %", "Accurate passes, %"),
                ("Passes to Penalty Area", "Passes to penalty area per 90"),
                ("Passes to Penalty Area %", "Accurate passes to penalty area, %"),
                ("Smart Passes", "Smart passes per 90"),
            ]),
        ]

    return []


def render_metrics_expander(row: pd.Series, posgroup: str):
    # Only show metrics that exist + have percentile computed (and not all-zero missing)
    blocks = metric_blocks_for_group(posgroup)

    def pct_of(metric: str) -> Optional[float]:
        col = f"{metric} Percentile"
        if col not in row.index:
            return None
        v = row.get(col, None)
        if v is None or pd.isna(v):
            return None
        try:
            return float(v)
        except Exception:
            return None

    def val_of(metric: str) -> Optional[float]:
        if metric not in row.index:
            return None
        v = row.get(metric, None)
        if v is None or pd.isna(v):
            return None
        try:
            return float(v)
        except Exception:
            return None

    def sec_html(title: str, pairs: List[Tuple[str, str]]) -> str:
        rows = []
        for lab, met in pairs:
            p = pct_of(met)
            raw = val_of(met)

            # "Don't display metrics with no calculation"
            # -> show only if percentile exists AND (raw exists OR percentile > 0)
            if p is None:
                continue
            if raw is None and float(p) == 0.0:
                continue

            p99 = _pro_show99(p)
            rows.append(
                f"<div class='m-row'>"
                f"<div class='m-label'>{lab}</div>"
                f"<div class='m-badge' style='background:{_pro_rating_color(p99)}'>{_fmt2(p99)}</div>"
                f"</div>"
            )
        if not rows:
            return ""
        return f"<div class='m-sec'><div class='m-title'>{title}</div>{''.join(rows)}</div>"

    sections_html = []
    for title, pairs in blocks:
        h = sec_html(title, pairs)
        if h:
            sections_html.append(h)

    if not sections_html:
        st.info("No individual metrics available for this player (missing columns in your CSV).")
        return

    st.markdown(
        "<div class='metrics-grid'>" + "".join(sections_html) + "</div>",
        unsafe_allow_html=True
    )


# =========================
# STREAMLIT SETUP
# =========================
st.set_page_config(page_title="Club View", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
/* Global typography like your Pro Layout */
html, body, .block-container *{
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; text-rendering:optimizeLegibility;
  font-feature-settings:"liga","kern","tnum"; font-variant-numeric:tabular-nums;
}

.stApp { background:#0e0e0f; color:#f2f2f2; }
.block-container { padding-top:1.1rem; padding-bottom:2rem; max-width:1150px; }
header, footer { visibility:hidden; }

.section-title{
  font-size:40px;font-weight:900;letter-spacing:1px;
  margin-top:26px;margin-bottom:12px;color:#f2f2f2;
}
@media (max-width: 640px){
  .section-title{ font-size:34px; margin-top:18px; }
}

/* Card CSS */
.pro-wrap{ display:flex; justify-content:center; }
.pro-card{
  position:relative; width:min(720px,98%); display:grid; grid-template-columns:96px 1fr 64px;
  gap:12px; align-items:start;
  background:#141823; border:1px solid rgba(255,255,255,.06); border-radius:20px;
  padding:16px; margin-bottom:12px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.03), 0 6px 24px rgba(0,0,0,.35);
}
@media (max-width: 640px){
  .pro-card{ width:min(560px,98%); grid-template-columns:86px 1fr 52px; padding:14px; border-radius:18px; }
}

.pro-avatar{ width:96px; height:96px; border-radius:12px; border:1px solid #2a3145; overflow:hidden; background:#0b0d12; }
.pro-avatar img{ width:100%; height:100%; object-fit:cover; image-rendering:auto; transform:translateZ(0); }
@media (max-width: 640px){
  .pro-avatar{ width:86px; height:86px; }
}

.flagchip{ display:inline-flex; align-items:center; gap:6px; background:transparent; border:none; padding:0; height:auto;}
.flagchip img{ width:26px; height:18px; border-radius:2px; display:block; }

.chip{ color:#a6a6a6; font-size:15px; line-height:18px; opacity:.92; }
.row{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:2px 0; }
.leftrow1{ margin-top:6px; } .leftrow-foot{ margin-top:2px; } .leftrow-contract{ margin-top:10px; }

.pill{ padding:2px 6px; min-width:36px; border-radius:6px; font-weight:900; font-size:18px; line-height:1; color:#0b0d12; text-align:center; display:inline-block; box-shadow:none; }
.name{ font-weight:950; font-size:22px; color:#e8ecff; margin-bottom:6px; letter-spacing:.2px; line-height:1.15; }
.postext{ font-weight:800; font-size:14.5px; letter-spacing:.2px; margin-right:10px; }
.rank{ position:absolute; top:10px; right:14px; color:#b7bfe1; font-weight:900; font-size:18px; }
.teamline{ color:#dbe3ff; font-size:14px; font-weight:700; margin-top:6px; letter-spacing:.05px; opacity:.95; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.teamline-wrap{ display:flex; align-items:center; gap:8px; }
.badge-mini{ width:16px; height:16px; border-radius:50%; object-fit:cover; border:1px solid rgba(255,255,255,.18); }

/* Individual metrics */
.m-sec{ background:#121621; border:1px solid #242b3b; border-radius:16px; padding:10px 12px; }
.m-title{ color:#e8ecff; font-weight:900; letter-spacing:.02em; margin:4px 0 10px 0; }
.m-row{ display:flex; justify-content:space-between; align-items:center; padding:8px 8px; border-radius:10px; }
.m-label{ color:#c9d3f2; font-size:15.5px; letter-spacing:.1px; flex:1 1 auto; }
.m-badge{ flex:0 0 auto; min-width:44px; text-align:center; padding:2px 10px; border-radius:8px; font-weight:900; font-size:18.5px; color:#0b0d12; border:1px solid rgba(0,0,0,.15); box-shadow:none; }
.metrics-grid{ display:grid; grid-template-columns:1fr; gap:12px; }
@media (min-width: 720px){ .metrics-grid{ grid-template-columns:repeat(3,1fr);} }

/* Compact header */
.hdr-wrap{ display:flex; justify-content:center; }
.hdr-card{
  width:min(720px,98%);
  background:#1c1c1d;border:1px solid #2a2a2b;border-radius:20px;padding:16px;
}
.hdr-grid{ display:grid; grid-template-columns:120px 1fr; gap:14px; align-items:center; }
.hdr-crestbox{
  width:120px;height:120px;background:#121213;border:1px solid #2a2a2b;border-radius:18px;
  display:flex;align-items:center;justify-content:center;overflow:hidden;
}
.hdr-crestbox img{ width:96px;height:96px;object-fit:contain; }
.hdr-team{ font-size:38px;font-weight:900;line-height:1.05;color:#f2f2f2; margin-bottom:6px;}
.hdr-subrow{ display:flex; align-items:center; gap:10px; margin-top:6px; color:#c9c9cc; font-weight:800; }
.hdr-subrow img{ width:46px;height:32px;object-fit:cover;border-radius:6px; }

.hdr-metrics{ display:flex; gap:14px; flex-wrap:wrap; margin-top:8px; align-items:center; }
.hdr-metric{ display:flex; align-items:center; gap:10px; }
.hdr-pill{
  width:46px;height:34px;border-radius:10px;display:flex;align-items:center;justify-content:center;
  font-size:18px;font-weight:950;color:#111;border:1px solid rgba(0,0,0,.35);
}
.hdr-label{ font-size:20px;font-weight:900;color:#9ea0a6; letter-spacing:.02em; }

.hdr-info{ margin-top:8px; color:#b0b0b3; font-size:14px; font-weight:700; display:flex; gap:16px; flex-wrap:wrap; }
@media (max-width: 640px){
  .hdr-grid{ grid-template-columns:92px 1fr; gap:12px; }
  .hdr-crestbox{ width:92px;height:92px;border-radius:16px;}
  .hdr-crestbox img{ width:74px;height:74px; }
  .hdr-team{ font-size:30px; }
  .hdr-label{ font-size:18px; }
  .hdr-pill{ width:44px;height:32px; font-size:17px; }
  .hdr-subrow img{ width:40px;height:28px; }
}
</style>
""", unsafe_allow_html=True)


# =========================
# LOAD CSV
# =========================
if not os.path.exists(CSV_PATH):
    st.error(f"CSV not found at: {CSV_PATH}. Upload it to your repo root.")
    st.stop()

df_all = pd.read_csv(CSV_PATH)

if "Team" not in df_all.columns or "Player" not in df_all.columns:
    st.error("CSV must include at least 'Team' and 'Player'.")
    st.stop()

# Minutes column
mins_col = detect_minutes_col(df_all)
df_all[mins_col] = pd.to_numeric(df_all.get(mins_col, 0), errors="coerce").fillna(0)

# Primary Position + PosGroup
df_all["Position"] = df_all.get("Position", "").astype(str)
df_all["Primary Position"] = df_all["Position"].astype(str).str.split(",").str[0].str.strip().str.upper()
df_all["PosGroup"] = df_all["Primary Position"].apply(pos_group)

# Stable row id for joining pool->display
df_all["_rowid"] = df_all.index.astype(int)


# =========================
# HEADER (compact, no iframe)
# =========================
crest_uri = img_to_data_uri(CREST_PATH)
flag_uri = img_to_data_uri(FLAG_PATH)

header_html = f"""
<div class="hdr-wrap">
  <div class="hdr-card">
    <div class="hdr-grid">
      <div>
        <div class="hdr-crestbox">
          {f"<img src='{crest_uri}' alt='crest' />" if crest_uri else ""}
        </div>
        <div class="hdr-subrow">
          {f"<img src='{flag_uri}' alt='flag' />" if flag_uri else ""}
          <div style="font-size:20px;font-weight:900;line-height:1;">{LEAGUE_TEXT}</div>
        </div>
      </div>

      <div>
        <div class="hdr-team">{TEAM_NAME}</div>

        <div class="hdr-metrics">
          <div class="hdr-metric">
            <div class="hdr-pill" style="background:{_pro_rating_color(OVERALL)}">{OVERALL}</div>
            <div class="hdr-label">Overall</div>
          </div>
          <div class="hdr-metric">
            <div class="hdr-pill" style="background:{_pro_rating_color(ATT_HDR)}">{ATT_HDR}</div>
            <div class="hdr-label">ATT</div>
          </div>
          <div class="hdr-metric">
            <div class="hdr-pill" style="background:{_pro_rating_color(MID_HDR)}">{MID_HDR}</div>
            <div class="hdr-label">MID</div>
          </div>
          <div class="hdr-metric">
            <div class="hdr-pill" style="background:{_pro_rating_color(DEF_HDR)}">{DEF_HDR}</div>
            <div class="hdr-label">DEF</div>
          </div>
        </div>

        <div class="hdr-info">
          <div><b>Average Age:</b> {AVG_AGE:.2f}</div>
          <div><b>League Position:</b> {LEAGUE_POSITION}</div>
        </div>
      </div>
    </div>
  </div>
</div>
"""
st.markdown(header_html, unsafe_allow_html=True)


# =========================
# PERFORMANCE
# =========================
st.markdown('<div class="section-title">PERFORMANCE</div>', unsafe_allow_html=True)

if PERFORMANCE_IMAGE_PATH and os.path.exists(PERFORMANCE_IMAGE_PATH):
    st.image(PERFORMANCE_IMAGE_PATH, use_container_width=True)
else:
    st.warning(f"Performance image not found: {PERFORMANCE_IMAGE_PATH}")


# =========================
# PLAYERS (filters live here)  ✅ moved as requested
# =========================
st.markdown('<div class="section-title">PLAYERS</div>', unsafe_allow_html=True)

# Defaults
min_pool_default, max_pool_default = 500, 5000
age_min_default, age_max_default = 16, 45

max_mins = int(max(5000, df_all[mins_col].max() if len(df_all) else 5000))

cA, cB, cC = st.columns([2.2, 2.2, 1.6])
with cA:
    pool_minutes = st.slider(
        "Minutes (pool + display)",
        min_value=0,
        max_value=max_mins,
        value=(min_pool_default, min(max_pool_default, max_mins)),
        step=10,
        key="minutes_pool",
    )
with cB:
    age_range = st.slider(
        "Age (display only)",
        min_value=16,
        max_value=45,
        value=(age_min_default, age_max_default),
        step=1,
        key="age_display",
    )
with cC:
    visa_only = st.checkbox("Visa players (exclude China PR)", value=False, key="visa_only")

pool_min, pool_max = pool_minutes
age_min, age_max = age_range


# =========================
# Build POOL -> compute percentiles -> role scores
# (pool affects calculations; age + visa are display-only)
# =========================
pool_df = df_all[(df_all[mins_col] >= pool_min) & (df_all[mins_col] <= pool_max)].copy()
pool_df = add_percentiles(pool_df)

# compute role scores on POOL
pool_df["RoleScores"] = pool_df.apply(compute_role_scores_for_row, axis=1)

# Join pool-calculated columns back to df_all by _rowid (safe, no suffix conflicts)
# Keep only the derived columns we need
derived_cols = (
    [f"{m} Percentile" for m in USED_METRICS if f"{m} Percentile" in pool_df.columns]
    + ["RoleScores"]
)
pool_keep = pool_df[["_rowid"] + derived_cols].copy()
df_joined = df_all.merge(pool_keep, on="_rowid", how="left")

# =========================
# DISPLAY set: Team filter + age display + visa display + minutes display
# =========================
df_disp = df_joined[df_joined["Team"].astype(str).str.strip() == TEAM_NAME].copy()
if df_disp.empty:
    st.info(f"No players found for Team = '{TEAM_NAME}'.")
    st.stop()

# display minutes filter uses same slider (pool + display)
df_disp = df_disp[(df_disp[mins_col] >= pool_min) & (df_disp[mins_col] <= pool_max)].copy()

# age display only (does not affect pool)
if "Age" in df_disp.columns:
    df_disp["Age_num"] = pd.to_numeric(df_disp["Age"], errors="coerce")
    df_disp = df_disp[(df_disp["Age_num"].fillna(0) >= age_min) & (df_disp["Age_num"].fillna(0) <= age_max)].copy()

# visa toggle: exclude China PR from DISPLAY only
if visa_only and "Birth country" in df_disp.columns:
    bc_norm = _norm_series(df_disp["Birth country"])
    df_disp = df_disp[bc_norm.ne("china pr")].copy()

# Sort by minutes desc
df_disp = df_disp.sort_values(mins_col, ascending=False).reset_index(drop=True)

if df_disp.empty:
    st.info("No players match the selected display filters.")
    st.stop()


# =========================
# Player images (hidden overrides + FotMob fallback)
# =========================
overrides_map = load_player_overrides_csv(PLAYER_IMAGE_OVERRIDES_CSV)
fotmob_map = fotmob_name_to_image_map(FOTMOB_SQUAD_URL)

# Badge icon (same as top crest) ✅ use same badge everywhere
badge_uri = crest_uri  # same image as team crest on top
badge_html = f"<img class='badge-mini' src='{badge_uri}' alt='' />" if badge_uri else ""


# =========================
# Helpers for rendering
# =========================
def _age_text(row: pd.Series) -> str:
    if "Age" in row.index:
        try:
            a = int(float(row.get("Age", 0)))
            return f"{a}y.o." if a > 0 else "—"
        except Exception:
            return "—"
    return "—"

def _contract_year(row: pd.Series) -> str:
    c = "Contract expires"
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


# =========================
# RENDER PLAYER CARDS
# =========================
for i, row in df_disp.iterrows():
    player = str(row.get("Player","—"))
    league = str(row.get("League",""))
    pos = str(row.get("Position",""))
    birth = str(row.get("Birth country","")) if "Birth country" in df_disp.columns else ""
    foot = _get_foot(row) or "—"
    age_txt = _age_text(row)
    contract_txt = _contract_year(row)
    mins = int(row.get(mins_col, 0) or 0)

    flag = _flag_html(birth)
    pos_html = _positions_html(pos)

    avatar_url = resolve_player_avatar(player, overrides_map, fotmob_map)

    roles = row.get("RoleScores", {})
    if not isinstance(roles, dict):
        roles = {}
    roles_sorted = sorted(roles.items(), key=lambda x: x[1], reverse=True)

    pills_html = "".join(
        f"<div class='row' style='align-items:center;'>"
        f"<span class='pill' style='background:{_pro_rating_color(v)}'>{_fmt2(v)}</span>"
        f"<span class='chip'>{k}</span>"
        f"</div>"
        for k, v in roles_sorted
    ) if roles_sorted else "<div class='row'><span class='chip'>No role scores</span></div>"

    # ✅ no league label on card (as requested)
    teamline_html = f"<div class='teamline teamline-wrap'>{badge_html}<span>{TEAM_NAME}</span></div>"

    card_html = f"""
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
          <div class='row' style='margin-top:10px;'>{pos_html}</div>
          {teamline_html}
        </div>

        <div class='rank'>#{_fmt2(i+1)}</div>
      </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

    # Individual metrics dropdown (per position group)
    with st.expander("Individual Metrics", expanded=False):
        render_metrics_expander(row, str(row.get("PosGroup","OTHER")))





















