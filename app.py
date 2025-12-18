# app.py — Club View (FULL A→Z)

import os
import re
import json
import base64
import unicodedata
import textwrap
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Optional (FotMob scrape)
try:
    import requests
except Exception:
    requests = None

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

# FotMob team squad page (your working source)
FOTMOB_TEAM_SQUAD_URL = "https://www.fotmob.com/teams/737052/squad/chengdu-rongcheng-fc"

# Optional hidden override mapping file (not shown in UI)
# If present, it overrides fotmob mapping.
# Format: {"felipe":"https://images.fotmob.com/image_resources/playerimages/123.png", "letschert":"..."}
PLAYER_PHOTO_JSON = "assets/player_photos.json"

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
# Safe normalizer (SCALAR ONLY)
# =========================
def _norm_str(s) -> str:
    if s is None:
        return ""
    s = str(s)
    if not s.strip():
        return ""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").strip().lower()

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
    "israel":"il","austria":"at","netherlands":"nl",
}

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
# Role definitions
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

# LOWER is better (invert percentile)
LOWER_BETTER = {"Conceded goals per 90"}  # per your instruction

# =========================
# Positions / groups (Primary Position)
# =========================
ATT_PRIMARY = {"RW", "LW", "LWF", "RWF", "AMF", "LAMF", "RAMF"}

def pos_group(primary_pos: str) -> str:
    p = str(primary_pos).strip().upper()
    if p.startswith("GK"):
        return "GK"
    if p in {"LCB","RCB","CB"}:
        return "CB"
    if p in {"RB","RWB","LB","LWB"}:
        return "FB"
    if p in {"LCMF","RCMF","LDMF","RDMF","DMF","CMF"}:
        return "CM"
    if p in ATT_PRIMARY:
        return "ATT"
    if p.startswith("CF"):
        return "CF"
    return "OTHER"

# =========================
# Utility
# =========================
def detect_minutes_col(df: pd.DataFrame) -> str:
    for c in ["Minutes played","Minutes Played","Minutes","mins","minutes","Min"]:
        if c in df.columns:
            return c
    return "Minutes played"

def img_to_data_uri(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    ext = os.path.splitext(path)[1].lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/{ext};base64,{b64}"

def render_html(html: str):
    """
    Critical: Strip left indentation on EVERY line so Streamlit doesn't treat it as a Markdown code block.
    """
    if html is None:
        return
    s = textwrap.dedent(str(html))
    s = "\n".join([ln.lstrip() for ln in s.splitlines()]).strip()
    st.markdown(s, unsafe_allow_html=True)

# =========================
# Percentiles (roles + expanders)
# =========================
def metrics_used_by_roles() -> set:
    rolesets = [CB_ROLES, FB_ROLES, CM_ROLES, ATT_ROLES, CF_ROLES, GK_ROLES]
    s = set()
    for rs in rolesets:
        for _, wmap in rs.items():
            s |= set(wmap.keys())
    return s

METRICS_FOR_EXPANDERS = {
    # GK
    "Exits per 90","Prevented goals per 90","Conceded goals per 90","Save rate, %","Shots against per 90","xG against per 90",
    "Long passes per 90",

    # General lists
    "Non-penalty goals per 90","xG per 90","xA per 90","Shots per 90","Shots on target, %","Goal conversion, %",
    "Head goals per 90","Touches in box per 90",
    "Crosses per 90","Accurate crosses, %",
    "Offensive duels per 90","Offensive duels won, %",
    "Aerial duels per 90","Aerial duels won, %",
    "Defensive duels per 90","Defensive duels won, %",
    "PAdj Interceptions","Shots blocked per 90","Successful defensive actions per 90",
    "Accelerations per 90","Dribbles per 90","Successful dribbles, %","Progressive runs per 90",
    "Deep completions per 90","Smart passes per 90","Key passes per 90",
    "Forward passes per 90","Accurate forward passes, %",
    "Passes per 90","Accurate passes, %",
    "Passes to final third per 90","Accurate passes to final third, %",
    "Passes to penalty area per 90","Accurate passes to penalty area, %",
    "Progressive passes per 90","Accurate progressive passes, %",
    "Accurate long passes, %",
}
METRICS_FOR_PCTS = metrics_used_by_roles() | METRICS_FOR_EXPANDERS

def add_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # numeric coercion
    for m in METRICS_FOR_PCTS:
        if m in out.columns:
            out[m] = pd.to_numeric(out[m], errors="coerce")

    # compute within PosGroup
    for m in METRICS_FOR_PCTS:
        if m not in out.columns:
            continue
        pct = out.groupby("PosGroup")[m].transform(lambda s: s.rank(pct=True) * 100)
        if m in LOWER_BETTER:
            pct = 100 - pct
        out[f"{m} Percentile"] = pct

    return out

# =========================
# Role score calc
# =========================
def weighted_role_score(row: pd.Series, weights: Dict[str, float]) -> int:
    num, den = 0.0, 0.0
    for metric, w in weights.items():
        col = f"{metric} Percentile"
        if col not in row.index:
            continue
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

def compute_role_scores_for_row(row: pd.Series) -> Dict[str, int]:
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

# =========================
# Individual Metrics sections (YOUR exact label+order)
# Show ONLY metrics that exist + have percentile
# =========================
def _metric_present(row: pd.Series, met: str) -> bool:
    if met not in row.index:
        return False
    v = row.get(met, np.nan)
    return pd.notna(v)

def _pct_of(row: pd.Series, met: str) -> float:
    col = f"{met} Percentile"
    if col not in row.index:
        return np.nan
    v = row.get(col, np.nan)
    try:
        return float(v)
    except Exception:
        return np.nan

def _val_str(row: pd.Series, met: str) -> str:
    if met not in row.index:
        return ""
    v = row.get(met, np.nan)
    if pd.isna(v):
        return ""
    try:
        fv = float(v)
        if np.isfinite(fv):
            if float(fv).is_integer():
                return str(int(fv))
            return f"{fv:.2f}"
    except Exception:
        pass
    s = str(v).strip()
    return s

def _build_sections_for_posgroup(pg: str):
    if pg == "GK":
        GOALKEEPING = [
            ("Exits", "Exits per 90"),
            ("Goals Prevented", "Prevented goals per 90"),
            ("Goals Conceded", "Conceded goals per 90"),
            ("Save Rate", "Save rate, %"),
            ("Shots Against", "Shots against per 90"),
            ("xG Against", "xG against per 90"),
        ]
        POSSESSION = [
            ("Passes", "Passes per 90"),
            ("Passing Accuracy %", "Accurate passes, %"),
            ("Long Passes", "Long passes per 90"),
            ("Long Passing %", "Accurate long passes, %"),
        ]
        return [("GOALKEEPING", GOALKEEPING), ("POSSESSION", POSSESSION)]

    if pg == "CB":
        ATTACKING = [
            ("Goals: Non-Penalty", "Non-penalty goals per 90"),
            ("xG", "xG per 90"),
            ("Offensive Duels", "Offensive duels per 90"),
            ("Offensive Duel Success %", "Offensive duels won, %"),
            ("Progressive Runs", "Progressive runs per 90"),
        ]
        DEFENSIVE = [
            ("Aerial Duels", "Aerial duels per 90"),
            ("Aerial Duel Success %", "Aerial duels won, %"),
            ("Defensive Duels", "Defensive duels per 90"),
            ("Defensive Duel Success %", "Defensive duels won, %"),
            ("PAdj Interceptions", "PAdj Interceptions"),
            ("Shots Blocked", "Shots blocked per 90"),
            ("Successful Defensive Actions", "Successful defensive actions per 90"),
        ]
        POSSESSION = [
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
        return [("ATTACKING", ATTACKING), ("DEFENSIVE", DEFENSIVE), ("POSSESSION", POSSESSION)]

    if pg in {"FB", "CM", "ATT"}:
        ATTACKING = [
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
        DEFENSIVE = [
            ("Aerial Duels", "Aerial duels per 90"),
            ("Aerial Win %", "Aerial duels won, %"),
            ("Defensive Duels", "Defensive duels per 90"),
            ("Defensive Duel %", "Defensive duels won, %"),
            ("PAdj Interceptions", "PAdj Interceptions"),
            ("Shots blocked", "Shots blocked per 90"),
            ("Succ. def acts", "Successful defensive actions per 90"),
        ]
        POSSESSION = [
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
        return [("ATTACKING", ATTACKING), ("DEFENSIVE", DEFENSIVE), ("POSSESSION", POSSESSION)]

    if pg == "CF":
        ATTACKING = [
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
        DEFENSIVE = [
            ("Aerial Duels", "Aerial duels per 90"),
            ("Aerial Duel Success %", "Aerial duels won, %"),
            ("Defensive Duels", "Defensive duels per 90"),
            ("Defensive Duel Success %", "Defensive duels won, %"),
            ("PAdj. Interceptions", "PAdj Interceptions"),
            ("Successful Def. Actions", "Successful defensive actions per 90"),
        ]
        POSSESSION = [
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
        return [("ATTACKING", ATTACKING), ("DEFENSIVE", DEFENSIVE), ("POSSESSION", POSSESSION)]

    return []

def _sec_html(title: str, rows: List[Tuple[str, str]], row: pd.Series) -> str:
    pieces = []
    for lab, met in rows:
        if not _metric_present(row, met):
            continue
        p = _pct_of(row, met)
        if pd.isna(p):
            continue
        p99 = _pro_show99(p)
        val = _val_str(row, met)
        val_html = f"<span class='m-val'>{val}</span>" if val != "" else ""
        pieces.append(
            "<div class='m-row'>"
            f"<div class='m-label'>{lab}{val_html}</div>"
            f"<div class='m-badge' style='background:{_pro_rating_color(p99)}'>{_fmt2(p99)}</div>"
            "</div>"
        )
    if not pieces:
        return ""
    return f"<div class='m-sec'><div class='m-title'>{title}</div>{''.join(pieces)}</div>"

# =========================
# FotMob surname matching (hidden; no UI)
# =========================
def _load_json_photo_map() -> Dict[str, str]:
    if not os.path.exists(PLAYER_PHOTO_JSON):
        return {}
    try:
        with open(PLAYER_PHOTO_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {_norm_str(k): str(v).strip() for k, v in data.items() if str(v).strip()}
    except Exception:
        pass
    return {}

@st.cache_data(ttl=24*3600, show_spinner=False)
def _fotmob_photo_map() -> Dict[str, str]:
    """
    Scrape FotMob team squad page and extract player IDs + names.
    Returns mapping for:
      - full name
      - surname
      - "t. surname"
    -> https://images.fotmob.com/image_resources/playerimages/{id}.png
    """
    if requests is None:
        return {}

    try:
        r = requests.get(
            FOTMOB_TEAM_SQUAD_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if r.status_code != 200:
            return {}
        html = r.text

        # Common patterns in FotMob markup / embedded JSON
        # We try several regexes to be resilient.
        pairs = []

        # Pattern A: "id":12345,"name":"Player Name"
        for m in re.finditer(r'"id"\s*:\s*(\d+)\s*,\s*"name"\s*:\s*"([^"]+)"', html):
            pid = m.group(1)
            name = m.group(2)
            if name and pid:
                pairs.append((name, pid))

        # Pattern B: "playerId":12345,"name":"Player Name"
        for m in re.finditer(r'"playerId"\s*:\s*(\d+)\s*,\s*"name"\s*:\s*"([^"]+)"', html):
            pid = m.group(1)
            name = m.group(2)
            if name and pid:
                pairs.append((name, pid))

        # De-dupe
        seen = set()
        out = {}
        for name, pid in pairs:
            key = (_norm_str(name), str(pid))
            if key in seen:
                continue
            seen.add(key)

            url = f"https://images.fotmob.com/image_resources/playerimages/{pid}.png"

            full = _norm_str(name)
            if full:
                out[full] = url

            parts = re.split(r"\s+", name.strip())
            if parts:
                surname = _norm_str(parts[-1])
                if surname:
                    out.setdefault(surname, url)

                if len(parts) >= 2:
                    init_surname = _norm_str(f"{parts[0][0]}. {parts[-1]}")
                    if init_surname:
                        out.setdefault(init_surname, url)

        return out
    except Exception:
        return {}

PHOTO_OVERRIDES = _load_json_photo_map()
PHOTO_FOTMOB = _fotmob_photo_map()

def _pick_photo(player_name: str) -> str:
    """
    Priority:
      1) assets/player_photos.json (hidden override)
      2) FotMob scrape map
      3) default avatar
    """
    p = str(player_name or "").strip()
    if not p:
        return DEFAULT_AVATAR

    full = _norm_str(p)

    # overrides first
    if full in PHOTO_OVERRIDES:
        return PHOTO_OVERRIDES[full]
    if full in PHOTO_FOTMOB:
        return PHOTO_FOTMOB[full]

    parts = re.split(r"\s+", p.strip())
    if parts:
        surname = _norm_str(parts[-1])
        if surname in PHOTO_OVERRIDES:
            return PHOTO_OVERRIDES[surname]
        if surname in PHOTO_FOTMOB:
            return PHOTO_FOTMOB[surname]

        if len(parts) >= 2:
            init_surname = _norm_str(f"{parts[0][0]}. {parts[-1]}")
            if init_surname in PHOTO_OVERRIDES:
                return PHOTO_OVERRIDES[init_surname]
            if init_surname in PHOTO_FOTMOB:
                return PHOTO_FOTMOB[init_surname]

    return DEFAULT_AVATAR

# =========================
# STREAMLIT SETUP + CSS
# =========================
st.set_page_config(page_title="Club View", layout="wide", initial_sidebar_state="collapsed")

st.markdown(textwrap.dedent("""
<style>
html, body, .block-container *{
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; text-rendering:optimizeLegibility;
  font-feature-settings:"liga","kern","tnum"; font-variant-numeric:tabular-nums;
}
.stApp { background:#0e0e0f; color:#f2f2f2; }
.block-container { padding-top:1.05rem; padding-bottom:2rem; max-width:980px; }
header, footer { visibility:hidden; }

/* ===== Compact Header ===== */
.club-card{
  background:#1c1c1d; border:1px solid #2a2a2b; border-radius:18px; padding:16px;
}
.header-grid{ display:grid; grid-template-columns: 170px 1fr; gap: 16px; align-items:start; }
.crest-tile{
  width:170px; height:130px; background:#121213; border:1px solid #2a2a2b;
  border-radius:16px; display:flex; align-items:center; justify-content:center; overflow:hidden;
}
.crest-img{ width:100px; height:100px; object-fit: contain; display:block; }
.left-league{ display:flex; align-items:center; gap:10px; padding-left:4px; margin-top:8px; }
.flag-img{ width:42px; height:30px; object-fit:cover; border-radius:6px; display:block; }
.league-text{ font-size:18px; font-weight:800; color:#d2d2d4; line-height:1; }

.team-title{ font-size:34px; font-weight:900; margin:0; line-height:1.05; color:#f2f2f2; }
.ratings-col{ display:flex; flex-direction:column; gap:10px; margin-top:10px; }
.metric{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.pillhdr{
  width:42px; height:32px; border-radius:10px; display:flex; align-items:center; justify-content:center;
  font-size:17px; font-weight:900; color:#111; border:1px solid rgba(0,0,0,.35);
}
.hlabel{ font-size:19px; font-weight:800; color:#9ea0a6; line-height:1; }
.triplet{ display:flex; gap:16px; flex-wrap:wrap; align-items:center; }
.info{ margin-top:6px; display:flex; flex-direction:column; gap:4px; font-size:14px; color:#b0b0b3; }

@media (max-width: 720px){
  .block-container{ max-width: 650px; padding-top:.8rem; }
  .header-grid{ grid-template-columns: 1fr; }
  .crest-tile{ width:100%; height:110px; }
  .crest-img{ width:88px; height:88px; }
  .team-title{ font-size:28px; }
  .pillhdr{ width:40px; height:30px; font-size:16px; }
  .hlabel{ font-size:18px; }
}

/* ===== Titles ===== */
.section-title{
  font-size:40px; font-weight:900; letter-spacing:1px;
  margin-top:22px; margin-bottom:10px; color:#f2f2f2;
}
@media (max-width: 720px){
  .section-title{ font-size:34px; }
}

/* ===== Pro Cards ===== */
:root { --card:#141823; }
.pro-wrap{ display:flex; justify-content:center; }
.pro-card{
  position:relative; width:min(720px,98%);
  display:grid; grid-template-columns:96px 1fr 64px; gap:12px; align-items:start;
  background:var(--card); border:1px solid rgba(255,255,255,.06); border-radius:20px;
  padding:16px; margin-bottom:12px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.03), 0 6px 24px rgba(0,0,0,.35);
}
.pro-avatar{ width:96px; height:96px; border-radius:12px; border:1px solid #2a3145; overflow:hidden; background:#0b0d12; }
.pro-avatar img{ width:100%; height:100%; object-fit:cover; }

.flagchip{ display:inline-flex; align-items:center; gap:6px; background:transparent; border:none; padding:0; height:auto;}
.flagchip img{ width:26px; height:18px; border-radius:2px; display:block; }

.chip{ background:transparent; color:#a6a6a6; border:none; padding:0; border-radius:0; font-size:15px; line-height:18px; opacity:.92; }
.row{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:2px 0; }
.leftrow1{ margin-top:6px; } .leftrow-foot{ margin-top:2px; } .leftrow-contract{ margin-top:6px; }

.pill{ padding:2px 6px; min-width:36px; border-radius:6px; font-weight:900; font-size:18px; line-height:1; color:#0b0d12; text-align:center; }
.name{ font-weight:950; font-size:22px; color:#e8ecff; margin-bottom:6px; letter-spacing:.2px; line-height:1.15; }
.postext{ font-weight:800; font-size:14.5px; letter-spacing:.2px; margin-right:10px; }
.posrow{ margin-top:10px; }
.rank{ position:absolute; top:10px; right:14px; color:#b7bfe1; font-weight:900; font-size:18px; }
.teamline{ color:#dbe3ff; font-size:14px; font-weight:700; margin-top:6px; letter-spacing:.05px; opacity:.95; }
.teamline-wrap{ display:flex; align-items:center; gap:8px; }
.badge-mini{ width:14px; height:14px; border-radius:4px; display:block; }

@media (max-width: 720px){
  .pro-card{ grid-template-columns:86px 1fr 54px; padding:14px; border-radius:18px; }
  .pro-avatar{ width:86px; height:86px; }
  .name{ font-size:20px; }
}

/* ===== Individual Metrics ===== */
.m-sec{ background:#121621; border:1px solid #242b3b; border-radius:16px; padding:10px 12px; }
.m-title{ color:#e8ecff; font-weight:900; letter-spacing:.02em; margin:4px 0 10px 0; }
.m-row{ display:flex; justify-content:space-between; align-items:center; padding:8px 8px; border-radius:10px; }
.m-label{ color:#c9d3f2; font-size:15px; letter-spacing:.1px; flex:1 1 auto; }
.m-badge{ flex:0 0 auto; min-width:44px; text-align:center; padding:2px 10px; border-radius:8px; font-weight:900; font-size:18px; color:#0b0d12; border:1px solid rgba(0,0,0,.15); }
.m-val{ color:#9fb0d9; font-size:13px; margin-left:10px; white-space:nowrap; }
.metrics-grid{ display:grid; grid-template-columns:1fr; gap:12px; }
@media (min-width: 720px){ .metrics-grid{ grid-template-columns:repeat(3,1fr);} }
</style>
""").strip(), unsafe_allow_html=True)

# =========================
# LOAD CSV
# =========================
if not os.path.exists(CSV_PATH):
    st.error(f"CSV not found at: {CSV_PATH}. Upload it to your repo root.")
    st.stop()

df_all = pd.read_csv(CSV_PATH)

for need in ("Team", "Player", "Position"):
    if need not in df_all.columns:
        st.error(f"CSV must include '{need}'.")
        st.stop()

df_all["Position"] = df_all["Position"].astype(str)
df_all["Primary Position"] = df_all["Position"].astype(str).str.split(",").str[0].str.strip().str.upper()
df_all["PosGroup"] = df_all["Primary Position"].apply(pos_group)

mins_col = detect_minutes_col(df_all)
df_all[mins_col] = pd.to_numeric(df_all[mins_col], errors="coerce").fillna(0)

df_team_all = df_all[df_all["Team"].astype(str).str.strip() == TEAM_NAME].copy()
if df_team_all.empty:
    st.info(f"No players found for Team = '{TEAM_NAME}'.")
    st.stop()

# =========================
# HEADER (single iframe is ok)
# =========================
crest_uri = img_to_data_uri(CREST_PATH)
flag_uri = img_to_data_uri(FLAG_PATH)

header_html = f"""
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

      <div class="ratings-col">
        <div class="metric">
          <div class="pillhdr" style="background:{_pro_rating_color(OVERALL)}">{OVERALL}</div>
          <div class="hlabel">Overall</div>
        </div>

        <div class="triplet">
          <div class="metric">
            <div class="pillhdr" style="background:{_pro_rating_color(ATT_HDR)}">{ATT_HDR}</div>
            <div class="hlabel">ATT</div>
          </div>
          <div class="metric">
            <div class="pillhdr" style="background:{_pro_rating_color(MID_HDR)}">{MID_HDR}</div>
            <div class="hlabel">MID</div>
          </div>
          <div class="metric">
            <div class="pillhdr" style="background:{_pro_rating_color(DEF_HDR)}">{DEF_HDR}</div>
            <div class="hlabel">DEF</div>
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
"""
components.html(textwrap.dedent(header_html).strip(), height=265)

# =========================
# PERFORMANCE
# =========================
st.markdown('<div class="section-title">PERFORMANCE</div>', unsafe_allow_html=True)
if PERFORMANCE_IMAGE_PATH and os.path.exists(PERFORMANCE_IMAGE_PATH):
    st.image(PERFORMANCE_IMAGE_PATH, use_container_width=True)
else:
    st.warning(f"Performance image not found: {PERFORMANCE_IMAGE_PATH}")

# =========================
# SQUAD
# =========================
st.markdown('<div class="section-title" style="margin-top:24px;">SQUAD</div>', unsafe_allow_html=True)

# Controls UNDER SQUAD (as requested)
c1, c2, c3 = st.columns([2.2, 2.0, 1.4])
with c1:
    minutes_range = st.slider(
        "Minutes (pool + display)",
        min_value=0,
        max_value=int(max(5000, df_team_all[mins_col].max() if len(df_team_all) else 5000)),
        value=(500, 5000),
        step=10,
        key="minutes_range"
    )
with c2:
    age_range = st.slider(
        "Age (display only)",
        min_value=16,
        max_value=45,
        value=(16, 45),
        step=1,
        key="age_range"
    )
with c3:
    visa_only = st.checkbox("Visa players (exclude China PR)", value=False, key="visa_only")

# Pool filter by minutes (affects percentiles + role scores)
min_m, max_m = minutes_range
df_pool = df_team_all[(df_team_all[mins_col] >= min_m) & (df_team_all[mins_col] <= max_m)].copy()

if df_pool.empty:
    st.info(f"No players in pool for {TEAM_NAME} with {mins_col} between {min_m} and {max_m}.")
    st.stop()

# Compute percentiles on pool
df_pool = add_percentiles(df_pool)
df_pool["RoleScores"] = df_pool.apply(compute_role_scores_for_row, axis=1)

# Display filter: age + visa (DOES NOT affect pool calcs)
df_disp = df_pool.copy()

if "Age" in df_disp.columns:
    df_disp["Age_num"] = pd.to_numeric(df_disp["Age"], errors="coerce")
    a0, a1 = age_range
    df_disp = df_disp[(df_disp["Age_num"].fillna(-1) >= a0) & (df_disp["Age_num"].fillna(999) <= a1)].copy()

if visa_only and "Birth country" in df_disp.columns:
    # IMPORTANT: no _norm() on Series; do scalar ops
    df_disp = df_disp[df_disp["Birth country"].astype(str).str.strip().str.lower().ne("china pr")].copy()

# sort by minutes desc
df_disp = df_disp.sort_values(mins_col, ascending=False).reset_index(drop=True)

if df_disp.empty:
    st.info("No players match display filters (age/visa) within current minutes pool.")
    st.stop()

# =========================
# Card helpers
# =========================
def _age_text(row: pd.Series) -> str:
    if "Age_num" in row.index and pd.notna(row.get("Age_num")):
        try:
            a = int(row.get("Age_num"))
            return f"{a}y.o." if a > 0 else "—"
        except Exception:
            return "—"
    if "Age" in row.index:
        try:
            a = int(float(row.get("Age")))
            return f"{a}y.o." if a > 0 else "—"
        except Exception:
            return "—"
    return "—"

def _contract_year(row: pd.Series) -> str:
    for c in ("Contract expires","Contract Expires","Contract","Contract expiry"):
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

badge_mini_html = f"<img class='badge-mini' src='{crest_uri}' alt='badge' />" if crest_uri else ""

# =========================
# Render cards
# =========================
for i, row in df_disp.iterrows():
    player = str(row.get("Player", "—"))
    league = str(row.get("League", ""))
    pos_full = str(row.get("Position", ""))
    birth = str(row.get("Birth country", "")) if "Birth country" in df_disp.columns else ""
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
        f"<span class='chip'>{k}</span>"
        f"</div>"
        for k, v in roles_sorted
    ) if roles_sorted else "<div class='row'><span class='chip'>No role scores</span></div>"

    flag = _flag_html(birth)
    pos_html = _positions_html(pos_full)
    photo_url = _pick_photo(player)

    card_html = f"""
    <div class='pro-wrap'>
      <div class='pro-card'>
        <div>
          <div class='pro-avatar'>
            <img src="{photo_url}" alt="{player}" loading="lazy" />
          </div>
          <div class='row leftrow1'>
            {flag}
            <span class='chip'>{age_txt}</span>
            <span class='chip'>{mins} mins</span>
          </div>
          <div class='row leftrow-foot'><span class='chip'>{foot}</span></div>
          <div class='row leftrow-contract'><span class='chip'>{contract_txt}</span></div>
        </div>

        <div>
          <div class='name'>{player}</div>
          {pills_html}
          <div class='row posrow'>{pos_html}</div>
          <div class='teamline teamline-wrap'>
            {badge_mini_html}
            <span>{TEAM_NAME} · {league}</span>
          </div>
        </div>

        <div class='rank'>#{_fmt2(i+1)}</div>
      </div>
    </div>
    """
    render_html(card_html)

    # Individual Metrics expander (position-specific, hide missing metrics)
    sections = _build_sections_for_posgroup(str(row.get("PosGroup", "OTHER")))
    if sections:
        with st.expander("Individual Metrics", expanded=False):
            sec_htmls = []
            for title, rowspec in sections:
                chunk = _sec_html(title, rowspec, row)
                if chunk:
                    sec_htmls.append(chunk)

            if not sec_htmls:
                st.info("No individual metrics available for this player (missing columns / percentiles).")
            else:
                render_html("<div class='metrics-grid'>" + "".join(sec_htmls) + "</div>")



















