# app.py — Club View (A–Z, fixed)
# ------------------------------------------------------------
# Key fixes included:
# 1) NO components.html for repeating cards (prevents HTML printing in iframes)
# 2) Compact responsive header (fits mobile, no overflow)
# 3) Proper attacker loading via Primary Position (split first token)
# 4) Minutes slider affects POOL (percentiles + role scores). Age slider is DISPLAY only.
# 5) “Visa players” toggle excludes Birth country == "China PR" from DISPLAY only
# 6) No more _norm(series) bug (Visa toggle crash fixed)
# 7) Individual Metrics: position-specific lists; only show metrics that exist & actually compute
# 8) Goalkeeper: Conceded goals per 90 is LOWER = BETTER (percentiles inverted)
# 9) China flag: maps "China PR" -> CN
# 10) FotMob surname/photo match (cached) + optional hidden local JSON overrides (no UI shown)
# ------------------------------------------------------------

import os
import re
import json
import base64
import unicodedata
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

CREST_PATH = "images/chengdu_rongcheng_f.c.svg.png"   # adjust if needed
FLAG_PATH  = "images/china.png"                       # optional (header flag)
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

# Optional hidden local override file (NOT exposed in UI)
# Format:
# {
#   "felipe": "https://....png",
#   "liu dianzuo": "https://....png"
# }
PLAYER_PHOTO_OVERRIDES_JSON = "player_photos.json"

# FotMob team page for auto photo map (cached)
FOTMOB_TEAM_URL = "https://www.fotmob.com/teams/737052/squad/chengdu-rongcheng-fc"

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
# NORMALIZATION
# =========================
def _norm_one(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()

def _norm_series(sr: pd.Series) -> pd.Series:
    return sr.astype(str).fillna("").map(_norm_one)

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
    "china pr":"cn",  # IMPORTANT
    "england":"eng","scotland":"sct","wales":"wls",
    "united kingdom":"gb","great britain":"gb",
    "brazil":"br","argentina":"ar","spain":"es","france":"fr","germany":"de","italy":"it","portugal":"pt",
    "netherlands":"nl","belgium":"be","sweden":"se","norway":"no","denmark":"dk","poland":"pl","japan":"jp","south korea":"kr",
    "israel":"il",
}

def _cc_to_twemoji(cc: str) -> Optional[str]:
    if not cc or len(cc) != 2:
        return None
    a, b = cc.upper()
    cp1 = 0x1F1E6 + (ord(a) - ord("A"))
    cp2 = 0x1F1E6 + (ord(b) - ord("A"))
    return f"{cp1:04x}-{cp2:04x}"

def _flag_html(country_name: str) -> str:
    if not country_name:
        return "<span class='chip'>—</span>"
    n = _norm_one(country_name)
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

# LOWER is better -> invert percentile
LOWER_BETTER = {
    "Conceded goals per 90",  # IMPORTANT for GK
}

# =========================
# POSITION GROUPING (uses Primary Position)
# =========================
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
    if p in {"RW","RWF","RAMF","LW","LWF","LAMF","AMF"}:
        return "ATT"
    if p.startswith("CF"):
        return "CF"
    return "OTHER"

def weighted_role_score(row: pd.Series, weights: Dict[str, float]) -> int:
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

# =========================
# UTILITIES
# =========================
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

def _positions_html(pos: str) -> str:
    raw = (pos or "").strip().upper()
    tokens = [t for t in re.split(r"[,\s/;]+", raw) if t]
    seen, ordered = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return "".join(f"<span class='postext' style='color:{_pro_chip_color(t)}'>{t}</span>" for t in ordered)

def _age_text(row: pd.Series) -> str:
    if "Age" in row.index:
        try:
            a = int(float(row["Age"]))
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

# =========================
# Percentiles computed from POOL (minutes slider affects POOL)
# - per PosGroup when group has enough samples; fallback to global pool ranking
# =========================
def metrics_used_by_roles() -> set:
    rolesets = [CB_ROLES, FB_ROLES, CM_ROLES, ATT_ROLES, CF_ROLES, GK_ROLES]
    s = set()
    for rs in rolesets:
        for _, wmap in rs.items():
            s |= set(wmap.keys())
    return s

def add_pool_percentiles(df_all: pd.DataFrame, pool_mask: pd.Series, min_group: int = 5) -> pd.DataFrame:
    used = metrics_used_by_roles()
    out = df_all.copy()

    for m in used:
        if m in out.columns:
            out[m] = pd.to_numeric(out[m], errors="coerce")

    pool = out.loc[pool_mask].copy()
    if pool.empty:
        for m in used:
            out[f"{m} Percentile"] = 0.0
        return out

    pool["__gcount"] = pool.groupby("PosGroup")["PosGroup"].transform("size")

    for m in used:
        if m not in pool.columns:
            out[f"{m} Percentile"] = 0.0
            continue

        global_pct = pool[m].rank(pct=True) * 100.0
        group_pct = pool.groupby("PosGroup")[m].transform(lambda s: s.rank(pct=True) * 100.0)

        use_group = pool["__gcount"] >= min_group
        pct = global_pct.where(~use_group, group_pct)

        if m in LOWER_BETTER:
            pct = 100.0 - pct

        out[f"{m} Percentile"] = 0.0
        out.loc[pool_mask, f"{m} Percentile"] = pct.fillna(0.0).values

    return out

# =========================
# FotMob photo scraping (cached)
# =========================
@st.cache_data(show_spinner=False, ttl=60*60*12)
def fotmob_photo_map(team_url: str) -> Dict[str, str]:
    """
    Returns mapping from normalized full name -> image url (best-effort).
    This is intentionally conservative; if parsing fails, returns {}.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        html = requests.get(team_url, headers=headers, timeout=20).text

        ids = re.findall(r'"id"\s*:\s*(\d+)\s*,\s*"name"\s*:\s*"([^"]+)"', html)
        if not ids:
            ids = re.findall(r'"playerId"\s*:\s*(\d+).*?"name"\s*:\s*"([^"]+)"', html, flags=re.S)

        out = {}
        for pid, name in ids:
            nm = _norm_one(name)
            if not nm:
                continue
            out[nm] = f"https://images.fotmob.com/image_resources/playerimages/{pid}.png"
        return out
    except Exception:
        return {}

def load_local_photo_overrides(path: str) -> Dict[str, str]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return { _norm_one(k): str(v).strip() for k,v in obj.items() if str(v).strip() }
        return {}
    except Exception:
        return {}

def resolve_player_photo(player_name: str,
                         team_photo_map: Dict[str, str],
                         local_overrides: Dict[str, str]) -> str:
    """
    Priority:
    1) local overrides by full name
    2) fotmob by full name
    3) fotmob by surname match
    4) default avatar
    """
    n_full = _norm_one(player_name)
    if n_full in local_overrides:
        return local_overrides[n_full]

    if n_full in team_photo_map:
        return team_photo_map[n_full]

    parts = [p for p in n_full.split() if p]
    surname = parts[-1] if parts else ""
    if surname:
        for k, v in team_photo_map.items():
            kp = [p for p in k.split() if p]
            if kp and kp[-1] == surname:
                return v

    return DEFAULT_AVATAR

# =========================
# INDIVIDUAL METRICS LISTS (your exact order + labels)
# =========================
METRICS_BY_GROUP = {
    "GK": {
        "GOALKEEPING": [
            ("Exits", "Exits per 90"),
            ("Goals Prevented", "Prevented goals per 90"),
            ("Goals Conceded", "Conceded goals per 90"),
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
    },
    "CB": {
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
    },
    "FB": {
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
    },
    "CM": {
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
    },
    "ATT": {
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
    },
    "CF": {  # STRIKER
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
    },
}

def _available_metric_pairs(df: pd.DataFrame, pairs: List[Tuple[str,str]]) -> List[Tuple[str,str]]:
    out = []
    for lab, met in pairs:
        if met in df.columns and f"{met} Percentile" in df.columns:
            out.append((lab, met))
    return out

def _metric_pct(row: pd.Series, met: str) -> float:
    col = f"{met} Percentile"
    v = row.get(col, np.nan)
    try:
        v = float(v)
    except Exception:
        v = np.nan
    if pd.isna(v):
        return np.nan
    return v

def _metric_val(row: pd.Series, met: str) -> float:
    v = row.get(met, np.nan)
    try:
        v = float(v)
    except Exception:
        v = np.nan
    return v

# =========================
# STREAMLIT SETUP
# =========================
st.set_page_config(page_title="Club View", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
html, body, .stApp, .block-container *{
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; text-rendering:optimizeLegibility;
  font-feature-settings:"liga","kern","tnum"; font-variant-numeric:tabular-nums;
}
.stApp { background:#0e0e0f; color:#f2f2f2; }
.block-container { padding-top:1rem; padding-bottom:2rem; max-width:1000px; }
header, footer { visibility:hidden; }

.section-title{
  font-size:40px;font-weight:900;letter-spacing:1px;
  margin-top:26px;margin-bottom:12px;color:#f2f2f2;
}
@media (max-width: 600px){
  .section-title{ font-size:34px; }
}

.pro-wrap{ display:flex; justify-content:center; }
.pro-card{
  position:relative; width:min(720px,98%); display:grid; grid-template-columns:96px 1fr 64px;
  gap:12px; align-items:start;
  background:#141823; border:1px solid rgba(255,255,255,.06); border-radius:20px;
  padding:16px; margin-bottom:12px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.03), 0 6px 24px rgba(0,0,0,.35);
}
@media (max-width: 600px){
  .pro-card{ grid-template-columns:84px 1fr 52px; padding:14px; }
}

.pro-avatar{ width:96px; height:96px; border-radius:12px; border:1px solid #2a3145; overflow:hidden; background:#0b0d12; }
@media (max-width: 600px){
  .pro-avatar{ width:84px; height:84px; }
}
.pro-avatar img{ width:100%; height:100%; object-fit:cover; }

.flagchip{ display:inline-flex; align-items:center; }
.flagchip img{ width:26px; height:18px; border-radius:2px; display:block; }
.chip{ color:#a6a6a6; font-size:15px; line-height:18px; opacity:.92; }
.row{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:2px 0; }
.leftrow1{ margin-top:6px; } .leftrow-foot{ margin-top:2px; } .leftrow-contract{ margin-top:6px; }

.pill{ padding:2px 6px; min-width:36px; border-radius:6px; font-weight:900; font-size:18px; line-height:1; color:#0b0d12; text-align:center; }
.name{ font-weight:950; font-size:22px; color:#e8ecff; margin-bottom:6px; letter-spacing:.2px; line-height:1.15; }
.postext{ font-weight:800; font-size:14.5px; letter-spacing:.2px; margin-right:10px; }
.rank{ position:absolute; top:10px; right:14px; color:#b7bfe1; font-weight:900; font-size:18px; }
.teamline{ color:#dbe3ff; font-size:14px; font-weight:700; margin-top:6px; letter-spacing:.05px; opacity:.95; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.teamline-wrap{ display:flex; align-items:center; gap:8px; }
.badge-mini{ width:18px; height:18px; border-radius:4px; display:inline-block; object-fit:contain; }

.m-sec{ background:#121621; border:1px solid #242b3b; border-radius:16px; padding:10px 12px; }
.m-title{ color:#e8ecff; font-weight:800; letter-spacing:.02em; margin:4px 0 10px 0; }
.m-row{ display:flex; justify-content:space-between; align-items:center; padding:8px 8px; border-radius:10px; }
.m-label{ color:#c9d3f2; font-size:15.5px; letter-spacing:.1px; flex:1 1 auto; }
.m-right{ display:flex; align-items:center; gap:10px; flex:0 0 auto; }
.m-val{ color:#a8b3cf; font-size:13px; opacity:.9; min-width:54px; text-align:right; }
.m-badge{ min-width:44px; text-align:center; padding:2px 10px; border-radius:8px; font-weight:800; font-size:18px; color:#0b0d12; border:1px solid rgba(0,0,0,.15); }
.metrics-grid{ display:grid; grid-template-columns:1fr; gap:12px; }
@media (min-width: 820px){ .metrics-grid{ grid-template-columns:repeat(3,1fr);} }

.header-shell{
  background:#1c1c1d;border:1px solid #2a2a2b;border-radius:18px;padding:16px;
}
.header-grid{
  display:grid; grid-template-columns:140px 1fr; gap:14px; align-items:center;
}
@media (max-width: 600px){
  .header-grid{ grid-template-columns:110px 1fr; }
}
.crest-box{
  width:140px; height:120px; background:#121213; border:1px solid #2a2a2b; border-radius:16px;
  display:flex; align-items:center; justify-content:center; overflow:hidden;
}
@media (max-width: 600px){
  .crest-box{ width:110px; height:96px; }
}
.crest-box img{ width:92%; height:92%; object-fit:contain; }

.header-title{ font-size:40px; font-weight:900; line-height:1.05; margin:0; }
@media (max-width: 600px){ .header-title{ font-size:28px; } }

.header-subrow{ display:flex; align-items:center; gap:10px; margin-top:8px; color:#d2d2d4; }
.header-subrow img{ width:44px; height:32px; object-fit:cover; border-radius:6px; }
@media (max-width: 600px){ .header-subrow img{ width:36px; height:26px; } }

.header-metrics{ display:flex; flex-wrap:wrap; gap:10px; margin-top:10px; align-items:center; }
.h-metric{ display:flex; align-items:center; gap:8px; }
.h-pill{
  width:48px; height:36px; border-radius:12px; display:flex; align-items:center; justify-content:center;
  font-size:20px; font-weight:900; color:#111; border:1px solid rgba(0,0,0,.35);
}
@media (max-width: 600px){
  .h-pill{ width:44px; height:34px; font-size:18px; border-radius:11px; }
}
.h-label{ font-size:20px; font-weight:800; color:#9ea0a6; }
@media (max-width: 600px){ .h-label{ font-size:18px; } }

.header-info{ margin-top:10px; display:flex; flex-direction:column; gap:4px; font-size:14px; color:#b0b0b3; }
</style>
""", unsafe_allow_html=True)

# =========================
# LOAD DATA
# =========================
if not os.path.exists(CSV_PATH):
    st.error(f"CSV not found at: {CSV_PATH}. Upload it to your repo root.")
    st.stop()

df_all = pd.read_csv(CSV_PATH)

if "Team" not in df_all.columns or "Player" not in df_all.columns:
    st.error("CSV must include at least 'Team' and 'Player'.")
    st.stop()

df_all = df_all.reset_index(drop=True)
df_all["RowID"] = df_all.index.astype(int)

df_all["Position"] = df_all.get("Position", "").astype(str)
df_all["Primary Position"] = df_all["Position"].astype(str).str.split(",").str[0].str.strip()
df_all["PosGroup"] = df_all["Primary Position"].apply(pos_group)

mins_col = detect_minutes_col(df_all)
df_all[mins_col] = pd.to_numeric(df_all[mins_col], errors="coerce").fillna(0)

# =========================
# HEADER (compact + responsive, NOT too wide)
# =========================
crest_uri = img_to_data_uri(CREST_PATH)
flag_uri  = img_to_data_uri(FLAG_PATH)

header_html = (
f"<div class='header-shell'>"
f"  <div class='header-grid'>"
f"    <div>"
f"      <div class='crest-box'>{('<img src=\"'+crest_uri+'\" />') if crest_uri else ''}</div>"
f"      <div class='header-subrow'>"
f"        {('<img src=\"'+flag_uri+'\" />') if flag_uri else ''}"
f"        <div style='font-size:18px;font-weight:800;line-height:1;'>{LEAGUE_TEXT}</div>"
f"      </div>"
f"    </div>"
f"    <div>"
f"      <div class='header-title'>{TEAM_NAME}</div>"
f"      <div class='header-metrics'>"
f"        <div class='h-metric'><div class='h-pill' style='background:{_pro_rating_color(OVERALL)};'>{OVERALL}</div><div class='h-label'>Overall</div></div>"
f"        <div class='h-metric'><div class='h-pill' style='background:{_pro_rating_color(ATT_HDR)};'>{ATT_HDR}</div><div class='h-label'>ATT</div></div>"
f"        <div class='h-metric'><div class='h-pill' style='background:{_pro_rating_color(MID_HDR)};'>{MID_HDR}</div><div class='h-label'>MID</div></div>"
f"        <div class='h-metric'><div class='h-pill' style='background:{_pro_rating_color(DEF_HDR)};'>{DEF_HDR}</div><div class='h-label'>DEF</div></div>"
f"      </div>"
f"      <div class='header-info'>"
f"        <div><b>Average Age:</b> {AVG_AGE:.2f}</div>"
f"        <div><b>League Position:</b> {LEAGUE_POSITION}</div>"
f"      </div>"
f"    </div>"
f"  </div>"
f"</div>"
)
st.markdown(header_html, unsafe_allow_html=True)

# =========================
# PERFORMANCE
# =========================
st.markdown("<div class='section-title'>PERFORMANCE</div>", unsafe_allow_html=True)
if PERFORMANCE_IMAGE_PATH and os.path.exists(PERFORMANCE_IMAGE_PATH):
    st.image(PERFORMANCE_IMAGE_PATH, use_container_width=True)
else:
    st.warning(f"Performance image not found: {PERFORMANCE_IMAGE_PATH}")

# =========================
# TEAM NOTES (Manual) — right below the team chart
# Put this DIRECTLY under the PERFORMANCE image block
# =========================

def _chip_html(items, color):
    if not items:
        return "<span class='chip'>—</span>"
    spans = [
        f"<span style='background:{color};color:#111;padding:2px 8px;border-radius:999px;"
        f"margin:0 8px 8px 0;display:inline-block;font-weight:800;font-size:13px;'>"
        f"{st.utils.escape_html(t)}</span>"
        for t in items[:20]
    ]
    return " ".join(spans)

def _parse_tags(s: str) -> list[str]:
    if not s:
        return []
    parts = re.split(r"[,\n]+", s.strip())
    tags = []
    for p in parts:
        t = p.strip()
        if not t:
            continue
        tags.append(t)
    # de-dupe preserve order
    seen = set()
    out = []
    for t in tags:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out

# =========================
# TEAM NOTES (MANUAL – EDIT HERE ONLY)
# =========================

TEAM_STYLE = [
    "Possession",
    "Pressing",
    "Structured",
]

TEAM_STRENGTHS = [
    "Chance Prevention",
    "Game Control",
    "Pressing Intensity",
]

TEAM_WEAKNESSES = [
    "Finishing",
    "Final 3rd Entries",
    "Set Pieces",
]

# =========================
# TEAM NOTES — DISPLAY (CHIPS ONLY)
# =========================

def _chip_row(items, bg):
    if not items:
        return ""
    return "".join(
        f"<span style='background:{bg};"
        f"color:#0b0d12;"
        f"padding:6px 14px;"
        f"border-radius:999px;"
        f"font-weight:800;"
        f"font-size:14px;"
        f"margin-right:8px;"
        f"display:inline-block;'>"
        f"{t}</span>"
        for t in items
    )

team_notes_html = f"""
<div style="margin-top:16px;margin-bottom:32px;">
  <div style="margin-bottom:12px;">
    <div style="color:#c9d3f2;font-weight:700;margin-bottom:6px;">Style:</div>
    {_chip_row(TEAM_STYLE, "#bfdbfe")}
  </div>

  <div style="margin-bottom:12px;">
    <div style="color:#c9d3f2;font-weight:700;margin-bottom:6px;">Strengths:</div>
    {_chip_row(TEAM_STRENGTHS, "#a7f3d0")}
  </div>

  <div>
    <div style="color:#c9d3f2;font-weight:700;margin-bottom:6px;">Weaknesses:</div>
    {_chip_row(TEAM_WEAKNESSES, "#fecaca")}
  </div>
</div>
"""

st.markdown(team_notes_html, unsafe_allow_html=True)





# =========================
# SQUAD FILTERS (moved ABOVE Pro Layout section)
# =========================
st.markdown("<div class='section-title' style='margin-top:10px;'>SQUAD</div>", unsafe_allow_html=True)

min_pool_default, max_pool_default = 500, 5000
age_min_default, age_max_default = 16, 45

cA, cB, cC = st.columns([2.2, 2.2, 1.6])
with cA:
    pool_minutes = st.slider(
        "Minutes (pool + display)",
        min_value=0,
        max_value=int(max(5000, df_all[mins_col].max() if len(df_all) else 5000)),
        value=(min_pool_default, max_pool_default),
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
# Compute POOL percentiles (minutes slider affects calculations)
# =========================
pool_mask = (df_all[mins_col] >= pool_min) & (df_all[mins_col] <= pool_max)
df_all = add_pool_percentiles(df_all, pool_mask=pool_mask, min_group=5)
df_all["RoleScores"] = df_all.apply(compute_role_scores_for_row, axis=1)

# =========================
# TEAM FILTER FOR DISPLAY LIST
# =========================
df_team = df_all[df_all["Team"].astype(str).str.strip() == TEAM_NAME].copy()
if df_team.empty:
    st.info(f"No players found for Team = '{TEAM_NAME}'.")
    st.stop()

df_disp = df_team[(df_team[mins_col] >= pool_min) & (df_team[mins_col] <= pool_max)].copy()

if "Age" in df_disp.columns:
    df_disp["Age_num"] = pd.to_numeric(df_disp["Age"], errors="coerce")
    df_disp = df_disp[(df_disp["Age_num"].fillna(0) >= age_min) & (df_disp["Age_num"].fillna(0) <= age_max)]

if visa_only and "Birth country" in df_disp.columns:
    bc_norm = _norm_series(df_disp["Birth country"])
    df_disp = df_disp[bc_norm.ne("china pr")]

df_disp = df_disp.sort_values(mins_col, ascending=False).reset_index(drop=True)

# =========================
# PLAYERS subtitle (Pro Layout section header)
# =========================
st.markdown("<div class='section-title' style='margin-top:10px;'>PLAYERS</div>", unsafe_allow_html=True)

# =========================
# PHOTO MAPS (hidden overrides + fotmob)
# =========================
local_overrides = load_local_photo_overrides(PLAYER_PHOTO_OVERRIDES_JSON)
fm_map = fotmob_photo_map(FOTMOB_TEAM_URL)

badge_uri = crest_uri  # same badge everywhere

# =========================
# RENDER SQUAD CARDS
# =========================
if df_disp.empty:
    st.info("No players match your filters.")
    st.stop()

for i, row in df_disp.iterrows():
    player = str(row.get("Player","—"))
    league  = str(row.get("League",""))
    pos     = str(row.get("Position",""))
    birth   = str(row.get("Birth country","")) if "Birth country" in df_disp.columns else ""
    foot    = _get_foot(row) or "—"
    age_txt = _age_text(row)
    contract_txt = _contract_year(row)
    mins = int(row.get(mins_col, 0) or 0)

    roles = row.get("RoleScores", {})
    if not isinstance(roles, dict):
        roles = {}
    roles_sorted = sorted(roles.items(), key=lambda x: x[1], reverse=True)

    pills_html = (
        "".join(
            f"<div class='row' style='align-items:center;'>"
            f"<span class='pill' style='background:{_pro_rating_color(v)}'>{_fmt2(v)}</span>"
            f"<span class='chip'>{k}</span>"
            f"</div>"
            for k, v in roles_sorted
        )
        if roles_sorted else
        "<div class='row'><span class='chip'>No role scores</span></div>"
    )

    flag = _flag_html(birth)
    pos_html = _positions_html(pos)
    avatar_url = resolve_player_photo(player, fm_map, local_overrides)

    badge_html = f"<img class='badge-mini' src='{badge_uri}' alt='badge' />" if badge_uri else ""
    teamline_html = f"<div class='teamline teamline-wrap'>{badge_html}<span>{TEAM_NAME} · {league}</span></div>"

    card_html = (
        f"<div class='pro-wrap'>"
        f"  <div class='pro-card'>"
        f"    <div>"
        f"      <div class='pro-avatar'><img src='{avatar_url}' alt='{player}' loading='lazy' /></div>"
        f"      <div class='row leftrow1'>{flag}<span class='chip'>{age_txt}</span><span class='chip'>{mins} mins</span></div>"
        f"      <div class='row leftrow-foot'><span class='chip'>{foot}</span></div>"
        f"      <div class='row leftrow-contract'><span class='chip'>{contract_txt}</span></div>"
        f"    </div>"
        f"    <div>"
        f"      <div class='name'>{player}</div>"
        f"      {pills_html}"
        f"      <div class='row' style='margin-top:10px;'>{pos_html}</div>"
        f"      {teamline_html}"
        f"    </div>"
        f"    <div class='rank'>#{_fmt2(i+1)}</div>"
        f"  </div>"
        f"</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)

    g = str(row.get("PosGroup","OTHER"))
    metric_blocks = METRICS_BY_GROUP.get(g, {})

    with st.expander("Individual Metrics", expanded=False):
        if not metric_blocks:
            st.info("No metric template for this position group.")
        else:
            sections_html = []
            for sec_title, pairs in metric_blocks.items():
                available_pairs = _available_metric_pairs(df_all, pairs)
                rows_html = []

                for lab, met in available_pairs:
                    pct = _metric_pct(row, met)
                    val = _metric_val(row, met)

                    if pd.isna(pct) or pd.isna(val):
                        continue

                    p_int = _pro_show99(pct)
                    val_txt = f"{val:.2f}"

                    rows_html.append(
                        f"<div class='m-row'>"
                        f"  <div class='m-label'>{lab}</div>"
                        f"  <div class='m-right'>"
                        f"    <div class='m-val'>{val_txt}</div>"
                        f"    <div class='m-badge' style='background:{_pro_rating_color(p_int)}'>{_fmt2(p_int)}</div>"
                        f"  </div>"
                        f"</div>"
                    )

                if rows_html:
                    sections_html.append(
                        f"<div class='m-sec'>"
                        f"  <div class='m-title'>{sec_title}</div>"
                        f"  {''.join(rows_html)}"
                        f"</div>"
                    )

            if sections_html:
                st.markdown(
                    "<div class='metrics-grid'>" + "".join(sections_html) + "</div>",
                    unsafe_allow_html=True
                )
            else:
                st.info("No available metrics found for this player (missing columns or no computed percentiles).")


# =========================
# SCATTERPLOT (Club View) — PLAYER PERFORMANCE
# - Visible controls ONLY:
#   - Position group (default CB)
#   - Minutes filter (default 1000–5000)
#   - X metric / Y metric (footballing RAW metrics only)
#   - Label all players toggle (TEAM players labeled by default)
#   - Export PNG button
# - Auto smart presets by position group
# - Median reference lines on both axes
# =========================
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, FormatStrFormatter
from io import BytesIO

st.markdown("---")
st.markdown("<div class='section-title'>PLAYER PERFORMANCE</div>", unsafe_allow_html=True)

# ---- helpers ----
def _as_num(s):
    return pd.to_numeric(s, errors="coerce")

def _nice_step(vmin, vmax, target_ticks=12):
    import math
    span = abs(vmax - vmin)
    if span <= 0 or not math.isfinite(span):
        return 1.0
    raw = span / max(target_ticks, 2)
    power = 10 ** math.floor(math.log10(raw))
    mult = raw / power
    if mult <= 1:
        k = 1
    elif mult <= 2:
        k = 2
    elif mult <= 2.5:
        k = 2.5
    elif mult <= 5:
        k = 5
    else:
        k = 10
    return k * power

def _decimals(step):
    if step >= 1:
        return 0
    if step >= 0.1:
        return 1
    if step >= 0.01:
        return 2
    return 3

def _padded_limits(arr, pad_frac=0.06, headroom=0.03):
    a = pd.Series(arr).dropna()
    if a.empty:
        return (0, 1)
    a_min, a_max = float(a.min()), float(a.max())
    if a_min == a_max:
        a_min -= 1e-6
        a_max += 1e-6
    span = a_max - a_min
    pad = span * pad_frac
    return a_min - pad, a_max + pad + span * headroom

def _pick_first_existing(options, candidates):
    for c in candidates:
        if c in options:
            return c
    return options[0] if options else None

# ---- footballing metrics only (RAW values) ----
FEATURES_SCATTER = sorted([m for m in metrics_used_by_roles() if m in df_all.columns])

metric_cols = []
for c in FEATURES_SCATTER:
    if _as_num(df_all[c]).notna().any():
        metric_cols.append(c)

if not metric_cols:
    st.info("No footballing metric columns available for scatter.")
else:
    # ---- smart presets (your spec) ----
    PRESET_BY_POS = {
        "CB": ("Progressive passes per 90", "Aerial duels won, %"),          # keep what you have now
        "GK": ("Exits per 90", "Prevented goals per 90"),
        "FB": ("Dribbles per 90", "Progressive passes per 90"),
        "CM": ("Dribbles per 90", "Progressive passes per 90"),
        "ATT": ("xG per 90", "xA per 90"),
        "CF": ("xG per 90", "Non-penalty goals per 90"),
        "OTHER": (None, None),
    }

    POS_TITLE = {
        "GK": "Goalkeeper Performance",
        "CB": "Center Back Performance",
        "FB": "Full Back Performance",
        "CM": "Central Midfield Performance",
        "ATT": "Attacker Performance",
        "CF": "Striker Performance",
        "OTHER": "Player Performance",
    }

    # ---- controls (ONLY intended ones) ----
    pos_options = ["CB", "FB", "CM", "ATT", "CF", "GK", "OTHER"]
    default_pos = "CB"  # ✅ default center backs

    # minutes default 1000–5000
    max_m = int(max(5000, float(df_all[mins_col].max() if len(df_all) else 5000)))
    default_mins = (1000, min(5000, max_m))

    # session defaults (so presets apply when switching position, but don't fight user)
    if "sc_last_pos" not in st.session_state:
        st.session_state["sc_last_pos"] = None
    if "sc_x_metric" not in st.session_state:
        st.session_state["sc_x_metric"] = None
    if "sc_y_metric" not in st.session_state:
        st.session_state["sc_y_metric"] = None

    with st.expander("Scatter settings", expanded=False):
        c1, c2, c3, c4 = st.columns([1.2, 2.2, 2.2, 1.6])

        with c1:
            pos_pick = st.selectbox(
                "Position group",
                pos_options,
                index=pos_options.index(default_pos),
                key="club_sc_pos",
            )

            m_min, m_max = st.slider(
                "Minutes filter",
                0, max_m,
                default_mins,
                step=10,
                key="club_sc_mins",
            )

        # apply smart preset when position changes OR when metrics not set yet
        preset_x, preset_y = PRESET_BY_POS.get(pos_pick, (None, None))

        needs_preset = (
            st.session_state["sc_last_pos"] != pos_pick
            or st.session_state["sc_x_metric"] not in metric_cols
            or st.session_state["sc_y_metric"] not in metric_cols
        )

        if needs_preset:
            # fallback safely if a preset metric is missing
            if preset_x not in metric_cols:
                preset_x = _pick_first_existing(metric_cols, ["Progressive passes per 90", "xG per 90", "Passes per 90"])
            if preset_y not in metric_cols:
                preset_y = _pick_first_existing(metric_cols, ["Aerial duels won, %", "xA per 90", "Non-penalty goals per 90"])
            st.session_state["sc_x_metric"] = preset_x
            st.session_state["sc_y_metric"] = preset_y
            st.session_state["sc_last_pos"] = pos_pick

        with c2:
            x_metric = st.selectbox(
                "X metric",
                metric_cols,
                index=metric_cols.index(st.session_state["sc_x_metric"]),
                key="club_sc_x",
            )
            st.session_state["sc_x_metric"] = x_metric

        with c3:
            y_metric = st.selectbox(
                "Y metric",
                metric_cols,
                index=metric_cols.index(st.session_state["sc_y_metric"]),
                key="club_sc_y",
            )
            st.session_state["sc_y_metric"] = y_metric

        with c4:
            label_all_players = st.checkbox("Label all players", value=False, key="club_sc_label_all")

    # ---- pool ----
    pool = df_all.copy()
    pool[mins_col] = _as_num(pool[mins_col]).fillna(0)

    pool = pool[pool["PosGroup"].astype(str) == pos_pick]
    pool = pool[pool[mins_col].between(m_min, m_max)]

    pool[x_metric] = _as_num(pool[x_metric])
    pool[y_metric] = _as_num(pool[y_metric])
    pool = pool.dropna(subset=[x_metric, y_metric, "Player", "Team"])

    if pool.empty:
        st.info("No players match the scatter filters.")
    else:
        team_mask = pool["Team"].astype(str).str.strip().eq(TEAM_NAME)
        others = pool[~team_mask].copy()
        team_players = pool[team_mask].copy()

        # ---- plot ----
        fig, ax = plt.subplots(figsize=(11.5, 6.5), dpi=120)
        fig.patch.set_facecolor("#0e0e0f")
        ax.set_facecolor("#0f151f")

        x_vals = pool[x_metric].to_numpy(float)
        y_vals = pool[y_metric].to_numpy(float)

        xlim = _padded_limits(x_vals)
        ylim = _padded_limits(y_vals)
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)

        ax.scatter(
            others[x_metric], others[y_metric],
            s=60, alpha=0.55, c="#cbd5e1",
            edgecolors="none", zorder=2
        )
        ax.scatter(
            team_players[x_metric], team_players[y_metric],
            s=110, alpha=0.98, c="#C81E1E",
            edgecolors="white", linewidths=1.2, zorder=4
        )

        # medians
        ax.axvline(float(np.nanmedian(x_vals)), color="#ffffff", ls=(0, (4, 4)), lw=2.2, zorder=3)
        ax.axhline(float(np.nanmedian(y_vals)), color="#ffffff", ls=(0, (4, 4)), lw=2.2, zorder=3)

        # labels: TEAM players by default; optional label all
        from matplotlib import patheffects as pe
        try:
            from adjustText import adjust_text
            _HAS_ADJUST = True
        except Exception:
            _HAS_ADJUST = False

        texts = []

        def _label_df(df_lbl, color, fs):
            for _, r in df_lbl.iterrows():
                nm = str(r.get("Player", "")).strip()
                if not nm:
                    continue
                xv = r.get(x_metric, np.nan)
                yv = r.get(y_metric, np.nan)
                if pd.isna(xv) or pd.isna(yv):
                    continue
                t = ax.annotate(
                    nm, (float(xv), float(yv)),
                    textcoords="offset points", xytext=(8, 8),
                    ha="left", va="bottom",
                    fontsize=fs, fontweight="semibold",
                    color=color, zorder=6, clip_on=True
                )
                t.set_path_effects([pe.withStroke(linewidth=2.2, foreground="#0b0d12", alpha=0.95)])
                texts.append(t)

        _label_df(team_players, "#ffffff", 10)
        if label_all_players:
            _label_df(others, "#e5e7eb", 9)

        if _HAS_ADJUST and label_all_players and texts:
            try:
                adjust_text(
                    texts, ax=ax,
                    only_move={"points": "y", "text": "xy"},
                    autoalign=True, precision=0.001, lim=120,
                    expand_text=(1.03, 1.06), expand_points=(1.03, 1.06),
                    force_text=(0.06, 0.10), force_points=(0.06, 0.10)
                )
            except Exception:
                pass

        # axes + denser ticks
        ax.set_xlabel(x_metric, fontsize=13, fontweight="semibold", color="#f5f5f5")
        ax.set_ylabel(y_metric, fontsize=13, fontweight="semibold", color="#f5f5f5")

        step_x = _nice_step(*xlim, target_ticks=12)
        step_y = _nice_step(*ylim, target_ticks=12)
        ax.xaxis.set_major_locator(MultipleLocator(base=step_x))
        ax.yaxis.set_major_locator(MultipleLocator(base=step_y))
        ax.xaxis.set_major_formatter(FormatStrFormatter(f"%.{_decimals(step_x)}f"))
        ax.yaxis.set_major_formatter(FormatStrFormatter(f"%.{_decimals(step_y)}f"))

        ax.grid(True, linewidth=0.7, alpha=0.25)
        ax.tick_params(colors="#e5e7eb")
        for spine in ax.spines.values():
            spine.set_color("#6b7280")
            spine.set_linewidth(0.9)

        # subtitle on chart only (position-dependent)
        ax.set_title(
            POS_TITLE.get(pos_pick, "Player Performance"),
            fontsize=14, fontweight="semibold", color="#f5f5f5", pad=10
        )

        # show plot
        st.pyplot(fig, use_container_width=True)

        # ---- export button ----
        png_buf = BytesIO()
        fig.savefig(png_buf, format="png", dpi=220, facecolor=fig.get_facecolor())
        png_buf.seek(0)

        safe_title = POS_TITLE.get(pos_pick, "Player Performance").replace(" ", "_").lower()
        st.download_button(
            "Export chart (PNG)",
            data=png_buf,
            file_name=f"{TEAM_NAME}_{safe_title}_{x_metric}_vs_{y_metric}.png".replace(" ", "_"),
            mime="image/png",
            key="club_sc_export_png",
        )

# ============================== FEATURE R — SQUAD PROFILE (Minimal UI) ==============================
from io import BytesIO
import uuid
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
from matplotlib import patheffects as pe

st.markdown("---")
st.header("SQUAD PROFILE")

# --------------------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------------------
CONTRACT_COL = "Contract expires"   # <= 2026 -> optional red highlight

# Optional smart label library
try:
    from adjustText import adjust_text
    HAVE_ADJUSTTEXT = True
except ImportError:
    HAVE_ADJUSTTEXT = False

# --------------------------------------------------------------------------------------
# MINIMAL CONTROLS (ONLY: team select + 2 toggles)
# --------------------------------------------------------------------------------------
teams_available = sorted(df_all["Team"].dropna().unique())

# Default team priority:
# 1) TEAM_NAME constant
# 2) player_row team if available
# 3) first in list
default_team = TEAM_NAME if "TEAM_NAME" in globals() else None
selected_player_name = None

player_row_obj = globals().get("player_row", pd.DataFrame())
if (default_team is None) and isinstance(player_row_obj, pd.DataFrame) and not player_row_obj.empty:
    default_team = player_row_obj.iloc[0].get("Team", None)

if isinstance(player_row_obj, pd.DataFrame) and not player_row_obj.empty:
    selected_player_name = player_row_obj.iloc[0].get("Player", None)

default_idx = teams_available.index(default_team) if default_team in teams_available else 0

cA, cB, cC = st.columns([2.2, 1.2, 1.2])
with cA:
    squad_team = st.selectbox("Squad (team)", options=teams_available, index=default_idx, key="sq_team_min")
with cB:
    auto_contract_red = st.checkbox("Contract ≤ 2026", value=False, key="sq_contract_toggle")  # NOT default
with cC:
    visa_highlight = st.checkbox("Visa players", value=False, key="sq_visa_toggle")            # NOT default

# --------------------------------------------------------------------------------------
# FIXED DEFAULTS (NO UI)
# --------------------------------------------------------------------------------------
mcol = mins_col if "mins_col" in globals() else "Minutes played"

# fixed filters (as requested)
min_minutes_s, max_minutes_s = 0, 3500
min_age_s, max_age_s = 16, 40

# fixed minutes bands
band_lines = sorted(
    [("Important Player", 1000),
     ("Crucial Player", 1750)],
    key=lambda x: x[1],
)

# fixed visual defaults
show_labels = True
label_size = 15
point_size = 300
point_alpha = 0.92

# theme/canvas defaults
PAGE_BG = "#0a0f1c"
PLOT_BG = "#0a0f1c"
GRID_MAJ = "#3a4050"
txt_col = "#f1f5f9"
w_px, h_px = 1600, 900
top_gap_px = 80
render_exact = True

# --------------------------------------------------------------------------------------
# FILTER SQUAD
# --------------------------------------------------------------------------------------
squad = df_all[df_all["Team"] == squad_team].copy()
if squad.empty:
    st.info("No players found for this squad.")
    st.stop()

squad[mcol] = pd.to_numeric(squad[mcol], errors="coerce")
squad["Age"] = pd.to_numeric(squad["Age"], errors="coerce")

squad = squad[
    squad[mcol].between(min_minutes_s, max_minutes_s)
    & squad["Age"].between(min_age_s, max_age_s)
]

if squad.empty:
    st.info("No players after applying filters.")
    st.stop()

# --------------------------------------------------------------------------------------
# HIGHLIGHTS: Contract ≤ 2026 (optional) + Visa players (optional) + Selected (if available)
# --------------------------------------------------------------------------------------
# Contract highlight (optional)
if auto_contract_red and CONTRACT_COL in squad.columns:
    contract_year = (
        squad[CONTRACT_COL]
        .astype(str)
        .str.extract(r"(\d{4})")[0]
        .astype(float)
    )
    squad["ContractYear"] = contract_year
    squad["AutoRed"] = squad["ContractYear"].le(2026)
else:
    squad["ContractYear"] = np.nan
    squad["AutoRed"] = False

# Visa highlight (optional): Birth country != "China PR"
if visa_highlight and ("Birth country" in squad.columns):
    bc_norm = _norm_series(squad["Birth country"])
    squad["VisaRed"] = bc_norm.ne("china pr")
else:
    squad["VisaRed"] = False

# Selected player (optional if your app has player_row defined)
squad["Selected"] = False
if selected_player_name:
    squad["Selected"] = squad["Player"] == selected_player_name

squad["IsRed"] = squad["AutoRed"] | squad["VisaRed"] | squad["Selected"]

# --------------------------------------------------------------------------------------
# SCATTER BASE
# --------------------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(w_px / 100, h_px / 100), dpi=100)
fig.patch.set_facecolor(PAGE_BG)
ax.set_facecolor(PLOT_BG)

ax.set_xlim(min_age_s, max_age_s)
ax.set_ylim(min_minutes_s, max_minutes_s)

ax.set_xlabel("Age", fontsize=16, fontweight="semibold", color=txt_col)
ax.xaxis.labelpad = 14
ax.set_ylabel("Minutes Played", fontsize=16, fontweight="semibold", color=txt_col)

ax.xaxis.set_major_locator(MultipleLocator(1))
ax.yaxis.set_major_locator(MultipleLocator(250))

for tick in ax.get_xticklabels() + ax.get_yticklabels():
    tick.set_fontweight("semibold")
    tick.set_color(txt_col)
    tick.set_fontsize(14)

ax.grid(True, color=GRID_MAJ, linewidth=0.6)
for s in ax.spines.values():
    s.set_color("#e5e7eb")
    s.set_linewidth(1.1)

# --------------------------------------------------------------------------------------
# AGE BANDS (fixed conceptual bands: 16–20, 21–24, 25–28, 29–32, 33–45)
# --------------------------------------------------------------------------------------
line_col = "#FFFFFF"
AGE_BAND_LABELS = ["YOUTH", "ASCENT", "PRIME", "EXPERIENCED", "OLD"]
AGE_BAND_EDGES = [16, 21, 25, 29, 33, 45]

for al in [21, 25, 29, 33]:
    if min_age_s <= al <= max_age_s:
        ax.axvline(al, color=line_col, linestyle=(0, (4, 4)), lw=1.5)

for i, label in enumerate(AGE_BAND_LABELS):
    band_start = AGE_BAND_EDGES[i]
    band_end = AGE_BAND_EDGES[i + 1]

    visible_start = max(band_start, min_age_s)
    visible_end = min(band_end, max_age_s)

    if visible_start >= visible_end or max_age_s == min_age_s:
        continue

    center = (visible_start + visible_end) / 2.0
    x_frac = (center - min_age_s) / float(max_age_s - min_age_s)

    ax.text(
        x_frac, 1.01, label,
        transform=ax.transAxes,
        fontsize=20, fontweight="bold",
        color=txt_col, ha="center", va="bottom",
    )

# --------------------------------------------------------------------------------------
# MINUTES BANDS
# --------------------------------------------------------------------------------------
for name, y_val in band_lines:
    if min_minutes_s <= y_val <= max_minutes_s:
        ax.axhline(y_val, color=line_col, linestyle=(0, (4, 4)), lw=1.5)
        ax.text(
            min_age_s + 0.2,
            y_val + (max_minutes_s - min_minutes_s) * 0.01,
            name,
            fontsize=14,
            fontweight="bold",
            color="#020617",
            bbox=dict(
                boxstyle="round,pad=0.35",
                facecolor="#e5e7eb",
                edgecolor="none",
                alpha=0.95,
            ),
            va="bottom",
        )

# --------------------------------------------------------------------------------------
# POINTS
# --------------------------------------------------------------------------------------
effective_point_size = point_size * 1.1
for is_red, grp in squad.groupby("IsRed"):
    ax.scatter(
        grp["Age"],
        grp[mcol],
        s=effective_point_size,
        c="#ef4444" if is_red else "#e5e7eb",
        alpha=point_alpha,
        edgecolors="none",
        linewidth=0,
        zorder=3 if is_red else 2,
    )

# --------------------------------------------------------------------------------------
# LABELS – ALL PLAYERS
# --------------------------------------------------------------------------------------
if show_labels:
    label_df = squad.copy()

    axis_height = max_minutes_s - min_minutes_s
    top_margin = axis_height * 0.04
    bottom_margin = axis_height * 0.03

    if HAVE_ADJUSTTEXT:
        texts = []
        xs = label_df["Age"].values
        ys = label_df[mcol].values

        for x, y, name, is_red in zip(xs, ys, label_df["Player"], label_df["IsRed"]):
            t = ax.text(
                x, y, name,
                fontsize=label_size,
                color=txt_col,
                weight="semibold",
                ha="center",
                va="bottom",
                zorder=6 if is_red else 5,
            )
            t.set_path_effects([pe.withStroke(linewidth=2, foreground="#020617", alpha=0.9)])
            texts.append(t)

        adjust_text(
            texts,
            x=xs, y=ys, ax=ax,
            autoalign="y",
            only_move={"points": "y", "text": "xy"},
            force_points=0.7,
            force_text=0.7,
            expand_points=(1.1, 1.5),
            expand_text=(1.1, 1.5),
            arrowprops=dict(arrowstyle="-", lw=0.6, color=txt_col, alpha=0.6),
        )

        for t in texts:
            x_lab, y_lab = t.get_position()
            y_lab = max(min_minutes_s + bottom_margin, min(y_lab, max_minutes_s - top_margin))
            t.set_position((x_lab, y_lab))

    else:
        base_offset = axis_height * 0.015
        min_y_delta = axis_height * 0.05
        age_tol = 0.7
        x_jitter = 0.25

        label_df_sorted = label_df.sort_values(mcol)
        placed = []
        positions = {}

        for _, r in label_df_sorted.iterrows():
            x = float(r["Age"])
            y = float(r[mcol])

            x_lab = x
            y_lab = y + base_offset
            y_lab = max(min_minutes_s + bottom_margin, min(y_lab, max_minutes_s - top_margin))

            direction_y = 1
            direction_x = 1
            attempts = 0
            max_attempts = 80

            while attempts < max_attempts:
                collision = False
                for (px, py) in placed:
                    if abs(x_lab - px) < age_tol and abs(y_lab - py) < min_y_delta:
                        collision = True
                        break
                if not collision:
                    break

                y_lab += direction_y * min_y_delta
                x_lab += direction_x * x_jitter
                direction_y *= -1
                direction_x *= -1

                y_lab = max(min_minutes_s + bottom_margin, min(y_lab, max_minutes_s - top_margin))
                x_lab = max(min_age_s + 0.2, min(x_lab, max_age_s - 0.2))
                attempts += 1

            placed.append((x_lab, y_lab))
            positions[r["Player"]] = (x_lab, y_lab)

        for _, r in label_df.iterrows():
            x = float(r["Age"])
            y = float(r[mcol])
            x_lab, y_lab = positions.get(r["Player"], (x, y + base_offset))

            if abs(x_lab - x) > 0.05 or abs(y_lab - (y + base_offset)) > 0.05:
                ax.plot([x, x_lab], [y, y_lab], linestyle="-", linewidth=0.5, color=txt_col, alpha=0.5, zorder=5)

            z = 6 if r["IsRed"] else 5
            t = ax.annotate(
                r["Player"],
                xy=(x_lab, y_lab),
                textcoords="data",
                fontsize=label_size,
                color=txt_col,
                weight="semibold",
                ha="center",
                va="bottom",
                zorder=z,
            )
            t.set_path_effects([pe.withStroke(linewidth=2, foreground="#020617", alpha=0.9)])

# --------------------------------------------------------------------------------------
# LAYOUT & RENDER
# --------------------------------------------------------------------------------------
fig.subplots_adjust(
    left=0.06,
    right=0.98,
    bottom=0.11,
    top=1.02 - top_gap_px / float(h_px),
)

if render_exact:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=PAGE_BG)
    buf.seek(0)
    st.image(buf, width=w_px)

    st.download_button(
        "⬇️ Download Squad Profile (PNG)",
        data=buf.getvalue(),
        file_name=f"squad_profile_{squad_team.replace(' ','_')}_{uuid.uuid4().hex[:6]}.png",
        mime="image/png",
    )
else:
    st.pyplot(fig)

plt.close(fig)
# ============================== END FEATURE R ==========================================




























