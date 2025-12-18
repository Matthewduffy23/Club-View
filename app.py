import os
import re
import json
import base64
import unicodedata
import textwrap
from typing import Dict, Tuple, Optional, List

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Optional: used for FotMob scraping (Streamlit Cloud usually allows this)
try:
    import requests
except Exception:
    requests = None

# ============================================================
# CONFIG
# ============================================================
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

# Default avatar (fallback)
DEFAULT_AVATAR = "https://i.redd.it/43axcjdu59nd1.jpeg"

# FotMob team id for Chengdu Rongcheng FC
FOTMOB_TEAM_ID = 737052

# Local cache for photo overrides (optional)
PHOTO_OVERRIDE_PATH = "player_photos.json"

# ============================================================
# COLORS / FORMATTING
# ============================================================
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

# ============================================================
# POSITION CHIP COLORS
# ============================================================
_POS_COLORS = {
    "CF":"#6EA8FF","LWF":"#6EA8FF","LW":"#6EA8FF","LAMF":"#6EA8FF","RW":"#6EA8FF","RWF":"#6EA8FF","RAMF":"#6EA8FF",
    "AMF":"#7FE28A","LCMF":"#5FD37A","RCMF":"#5FD37A","RDMF":"#31B56B","LDMF":"#31B56B","DMF":"#31B56B","CMF":"#5FD37A",
    "LWB":"#FFD34D","RWB":"#FFD34D","LB":"#FF9A3C","RB":"#FF9A3C",
    "RCB":"#D1763A","CB":"#D1763A","LCB":"#D1763A",
    "GK":"#B8A1FF",
}

def _pro_chip_color(p: str) -> str:
    return _POS_COLORS.get(str(p).strip().upper(), "#2d3550")

# ============================================================
# FLAGS (Twemoji)
# - includes China PR => cn
# ============================================================
TWEMOJI_SPECIAL = {
    "eng":"1f3f4-e0067-e0062-e0065-e006e-e0067-e007f",
    "sct":"1f3f4-e0067-e0062-e0073-e0063-e0074-e007f",
    "wls":"1f3f4-e0067-e0062-e0077-e006c-e0073-e007f",
}

COUNTRY_TO_CC = {
    "china":"cn",
    "china pr":"cn",
    "people's republic of china":"cn",

    "england":"eng","scotland":"sct","wales":"wls",
    "united kingdom":"gb","great britain":"gb",

    "brazil":"br","argentina":"ar","spain":"es","france":"fr","germany":"de","italy":"it","portugal":"pt",
    "netherlands":"nl","belgium":"be","sweden":"se","norway":"no","denmark":"dk","poland":"pl",
    "japan":"jp","south korea":"kr","korea republic":"kr","korea, republic of":"kr",
    "israel":"il","austria":"at","croatia":"hr","serbia":"rs","uruguay":"uy",
}

def _norm_scalar(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()

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
    n = _norm_scalar(country_name)
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

# ============================================================
# SAFE FOOT EXTRACTOR
# ============================================================
def _get_foot(row: pd.Series) -> str:
    for col in ("Foot", "Preferred foot", "Preferred Foot"):
        if col in row.index:
            v = row.get(col)
            try:
                if pd.isna(v):
                    continue
            except Exception:
                pass
            s = str(v).strip()
            if s and s.lower() not in {"nan", "none", "null"}:
                return s
    return ""

# ============================================================
# ROLES (weights)
# ============================================================
CB_ROLES = {
    "Ball Playing CB": {"Passes per 90":2,"Accurate passes, %":2,"Forward passes per 90":2,"Accurate forward passes, %":2,
                        "Progressive passes per 90":2,"Progressive runs per 90":1.5,"Dribbles per 90":1.5,
                        "Accurate long passes, %":1,"Passes to final third per 90":1.5},
    "Wide CB": {"Defensive duels per 90":1.5,"Defensive duels won, %":2,"Dribbles per 90":2,
                "Forward passes per 90":1,"Progressive passes per 90":1,"Progressive runs per 90":2},
    "Box Defender": {"Aerial duels per 90":1,"Aerial duels won, %":3,"PAdj Interceptions":2,"Shots blocked per 90":1,"Defensive duels won, %":4},
}

FB_ROLES = {
    "Build Up FB": {"Passes per 90":2,"Accurate passes, %":1.5,"Forward passes per 90":2,"Accurate forward passes, %":2,
                    "Progressive passes per 90":2.5,"Progressive runs per 90":2,"Dribbles per 90":2,
                    "Passes to final third per 90":2,"xA per 90":1},
    "Attacking FB": {"Crosses per 90":2,"Dribbles per 90":3.5,"Accelerations per 90":1,"Successful dribbles, %":1,
                     "Touches in box per 90":2,"Progressive runs per 90":3,"Passes to penalty area per 90":2,"xA per 90":3},
    "Defensive FB": {"Aerial duels per 90":1,"Aerial duels won, %":1.5,"Defensive duels per 90":2,
                     "PAdj Interceptions":3,"Shots blocked per 90":1,"Defensive duels won, %":3.5},
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
    "Link-Up CF": {"Passes per 90":2,"Passes to penalty area per 90":1.5,"Deep completions per 90":1,"Smart passes per 90":1.5,
                   "Accurate passes, %":1.5,"Key passes per 90":1,"Dribbles per 90":2,"Successful dribbles, %":1,
                   "Progressive runs per 90":2,"xA per 90":3},
}

GK_ROLES = {
    "Shot Stopper GK": {"Prevented goals per 90":3, "Save rate, %":1},
    "Ball Playing GK": {"Passes per 90":1, "Accurate passes, %":3, "Accurate long passes, %":2},
    "Sweeper GK": {"Exits per 90":1},
}

# lower is better -> invert percentile
LOWER_BETTER = {
    "Conceded goals per 90",   # specifically requested
}

# ============================================================
# POSITION GROUPING (uses Primary Position)
# ============================================================
ATT_PRIMARY = {"RW","LW","LWF","RWF","AMF","LAMF","RAMF"}
CM_PREFIXES = ("LCMF","RCMF","LDMF","RDMF","DMF","CMF")

def pos_group_from_primary(primary_pos: str) -> str:
    p = str(primary_pos or "").strip().upper()
    if p.startswith("GK"):
        return "GK"
    if p.startswith(("LCB","RCB","CB")):
        return "CB"
    if p.startswith(("RB","RWB","LB","LWB")):
        return "FB"
    if p.startswith(CM_PREFIXES):
        return "CM"
    if p in ATT_PRIMARY:
        return "ATT"
    if p.startswith("CF"):
        return "CF"
    return "OTHER"

# ============================================================
# UTIL: minutes col
# ============================================================
def detect_minutes_col(df: pd.DataFrame) -> str:
    for c in ["Minutes played","Minutes Played","Minutes","mins","minutes","Min"]:
        if c in df.columns:
            return c
    return "Minutes played"

# ============================================================
# UTIL: images
# ============================================================
def img_to_data_uri(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    ext = os.path.splitext(path)[1].lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/{ext};base64,{b64}"

# ============================================================
# PERCENTILES
# - computed after pool minutes filter (as requested)
# ============================================================
def metrics_used_everywhere() -> set:
    used = set()

    # role metrics
    for roleset in (CB_ROLES, FB_ROLES, CM_ROLES, ATT_ROLES, CF_ROLES, GK_ROLES):
        for _, wmap in roleset.items():
            used |= set(wmap.keys())

    # individual metric sections (ensures they never show 00 if column exists)
    # GK
    used |= {
        "Exits per 90","Prevented goals per 90","Conceded goals per 90","Save rate, %","Shots against per 90","xG against per 90",
        "Passes per 90","Accurate passes, %","Long passes per 90","Accurate long passes, %",
    }
    # CB
    used |= {
        "Non-penalty goals per 90","xG per 90","Offensive duels per 90","Offensive duels won, %","Progressive runs per 90",
        "Aerial duels per 90","Aerial duels won, %","Defensive duels per 90","Defensive duels won, %","PAdj Interceptions",
        "Shots blocked per 90","Successful defensive actions per 90",
        "Accelerations per 90","Dribbles per 90","Successful dribbles, %","Forward passes per 90","Accurate forward passes, %",
        "Long passes per 90","Accurate long passes, %","Passes per 90","Accurate passes, %","Passes to final third per 90",
        "Accurate passes to final third, %","Progressive passes per 90","Accurate progressive passes, %",
    }
    # FB/CM/ATT shared
    used |= {
        "Crosses per 90","Accurate crosses, %","Shots per 90","Shots on target, %","Touches in box per 90","xA per 90",
        "Deep completions per 90","Key passes per 90","Passes to penalty area per 90","Accurate passes to penalty area, %",
        "Smart passes per 90","Passes to final third per 90","Accurate passes to final third, %",
        "Accelerations per 90","Progressive runs per 90",
    }
    # CF
    used |= {
        "Goal conversion, %","Head goals per 90",
    }

    return used

def add_percentiles(df_pool: pd.DataFrame) -> pd.DataFrame:
    used = metrics_used_everywhere()
    out = df_pool.copy()

    for m in used:
        if m in out.columns:
            out[m] = pd.to_numeric(out[m], errors="coerce")

    # rank within PosGroup
    for m in used:
        if m not in out.columns:
            continue

        pct = out.groupby("PosGroup")[m].transform(lambda s: s.rank(pct=True) * 100)

        if m in LOWER_BETTER:
            pct = 100 - pct

        out[f"{m} Percentile"] = pct

    return out

# ============================================================
# ROLE SCORES
# ============================================================
def weighted_role_score(row: pd.Series, weights: Dict[str, float]) -> int:
    num, den = 0.0, 0.0
    for metric, w in weights.items():
        col = f"{metric} Percentile"
        v = row.get(col, np.nan)
        if pd.isna(v):
            continue
        try:
            v = float(v)
        except Exception:
            continue
        num += w * v
        den += w
    score_0_100 = (num / den) if den > 0 else 0.0
    return _pro_show99(score_0_100)

def compute_role_scores_for_row(row: pd.Series) -> Dict[str, int]:
    g = row.get("PosGroup","OTHER")
    if g == "GK":
        return {k: weighted_role_score(row, w) for k, w in GK_ROLES.items()}
    if g == "CB":
        return {k: weighted_role_score(row, w) for k, w in CB_ROLES.items()}
    if g == "FB":
        return {k: weighted_role_score(row, w) for k, w in FB_ROLES.items()}
    if g == "CM":
        roles = {k: weighted_role_score(row, w) for k, w in CM_ROLES.items()}
        # top 3 only
        return dict(sorted(roles.items(), key=lambda x: x[1], reverse=True)[:3])
    if g == "ATT":
        return {k: weighted_role_score(row, w) for k, w in ATT_ROLES.items()}
    if g == "CF":
        return {k: weighted_role_score(row, w) for k, w in CF_ROLES.items()}
    return {}

# ============================================================
# PLAYER PHOTO: FotMob scrape + local overrides (hidden)
# ============================================================
def load_photo_overrides() -> Dict[str, str]:
    if os.path.exists(PHOTO_OVERRIDE_PATH):
        try:
            with open(PHOTO_OVERRIDE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_photo_overrides(d: Dict[str, str]) -> None:
    try:
        with open(PHOTO_OVERRIDE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _name_key(player_name: str) -> str:
    # key is normalized full name
    return _norm_scalar(player_name)

def try_fetch_fotmob_player_map(team_id: int) -> Dict[str, int]:
    """
    Returns {normalized_player_name: fotmob_player_id}
    Best-effort scrape from fotmob squad page.
    """
    if requests is None:
        return {}

    url = f"https://www.fotmob.com/teams/{team_id}/squad/chengdu-rongcheng-fc"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code != 200:
            return {}
        html = r.text
    except Exception:
        return {}

    # Common FotMob pattern: /players/<id>/...
    ids = re.findall(r"/players/(\d+)/", html)
    # Names usually appear nearby in HTML; fallback: use "aria-label" / json blocks.
    # We'll grab player cards blocks: "players/<id>" then next quoted name-ish chunk.
    # This is heuristic but works often.
    mapping: Dict[str, int] = {}
    for pid in set(ids):
        # try to find a name close to pid
        m = re.search(rf"/players/{pid}/[^\"']*[^>]*>([^<]{{2,60}})<", html)
        if m:
            nm = m.group(1).strip()
            if nm and len(nm) < 60:
                mapping[_name_key(nm)] = int(pid)

    # If above didn’t catch names, try JSON-ish: "name":"...","id":pid
    # (order varies; do two passes)
    for pid in set(ids):
        m2 = re.search(rf'"id"\s*:\s*{pid}\s*,\s*"name"\s*:\s*"([^"]+)"', html)
        if m2:
            mapping[_name_key(m2.group(1))] = int(pid)
        m3 = re.search(rf'"name"\s*:\s*"([^"]+)"\s*,\s*"id"\s*:\s*{pid}', html)
        if m3:
            mapping[_name_key(m3.group(1))] = int(pid)

    return mapping

def fotmob_img_url(player_id: int) -> str:
    return f"https://images.fotmob.com/image_resources/playerimages/{player_id}.png"

def resolve_player_photo(player_name: str,
                         fotmob_map: Dict[str, int],
                         overrides: Dict[str, str]) -> str:
    k = _name_key(player_name)
    if k in overrides and overrides[k]:
        return overrides[k]
    # exact name
    if k in fotmob_map:
        return fotmob_img_url(fotmob_map[k])

    # fallback: try surname match (requested)
    parts = [p for p in _norm_scalar(player_name).split() if p]
    surname = parts[-1] if parts else ""
    if surname:
        # find any fotmob name with same surname
        for nm_key, pid in fotmob_map.items():
            nm_parts = [p for p in nm_key.split() if p]
            if nm_parts and nm_parts[-1] == surname:
                return fotmob_img_url(pid)

    return DEFAULT_AVATAR

# ============================================================
# INDIVIDUAL METRIC SECTIONS (your order + abbreviations)
# ============================================================
def val_of(row: pd.Series, metric: str) -> Tuple[bool, str]:
    """Return (exists, formatted_raw_value)."""
    if metric not in row.index:
        return (False, "—")
    v = row.get(metric, np.nan)
    if pd.isna(v):
        return (False, "—")
    try:
        fv = float(v)
        # reasonable formatting
        if abs(fv) >= 100:
            return (True, f"{fv:.0f}")
        if abs(fv) >= 10:
            return (True, f"{fv:.1f}")
        return (True, f"{fv:.2f}")
    except Exception:
        s = str(v).strip()
        return (True, s if s else "—")

def pct_of(row: pd.Series, metric: str) -> Optional[float]:
    col = f"{metric} Percentile"
    if col not in row.index:
        return None
    v = row.get(col, np.nan)
    if pd.isna(v):
        return None
    try:
        return float(v)
    except Exception:
        return None

def metric_sections_for_group(pos_group: str):
    # GK
    if pos_group == "GK":
        GOALKEEPING = [
            ("Exits", "Exits per 90"),
            ("Goals Prevented", "Prevented goals per 90"),
            ("Goals Conceded", "Conceded goals per 90"),  # LOWER is better already inverted in percentiles
            ("Save Rate", "Save rate, %"),
            ("Shots Against", "Shots against per 90"),
            ("xG Against", "xG against per 90"),
        ]
        POSSESSION = [
            ("Passes", "Passes per 90"),
            ("Passing %", "Accurate passes, %"),
            ("Long Passes", "Long passes per 90"),
            ("Long Pass %", "Accurate long passes, %"),
        ]
        return [("GOALKEEPING", GOALKEEPING), ("POSSESSION", POSSESSION)]

    # CB (special)
    if pos_group == "CB":
        ATTACKING = [
            ("NPG", "Non-penalty goals per 90"),
            ("xG", "xG per 90"),
            ("Off. Duels", "Offensive duels per 90"),
            ("Off. Duel %", "Offensive duels won, %"),
            ("Prog Runs", "Progressive runs per 90"),
        ]
        DEFENSIVE = [
            ("Aerial Duels", "Aerial duels per 90"),
            ("Aerial %", "Aerial duels won, %"),
            ("Def Duels", "Defensive duels per 90"),
            ("Def Duel %", "Defensive duels won, %"),
            ("PAdj Int", "PAdj Interceptions"),
            ("Blocks", "Shots blocked per 90"),
            ("Succ Def Acts", "Successful defensive actions per 90"),
        ]
        POSSESSION = [
            ("Accel", "Accelerations per 90"),
            ("Dribbles", "Dribbles per 90"),
            ("Dribble %", "Successful dribbles, %"),
            ("Fwd Passes", "Forward passes per 90"),
            ("Fwd Pass %", "Accurate forward passes, %"),
            ("Long Passes", "Long passes per 90"),
            ("Long Pass %", "Accurate long passes, %"),
            ("Passes", "Passes per 90"),
            ("Pass %", "Accurate passes, %"),
            ("Pass to F3rd", "Passes to final third per 90"),
            ("F3rd %", "Accurate passes to final third, %"),
            ("Prog Passes", "Progressive passes per 90"),
            ("Prog Pass %", "Accurate progressive passes, %"),
        ]
        return [("ATTACKING", ATTACKING), ("DEFENSIVE", DEFENSIVE), ("POSSESSION", POSSESSION)]

    # FB / CM / ATT (shared)
    if pos_group in {"FB","CM","ATT"}:
        ATTACKING = [
            ("Crosses", "Crosses per 90"),
            ("Cross %", "Accurate crosses, %"),
            ("NPG", "Non-penalty goals per 90"),
            ("xG", "xG per 90"),
            ("xA", "xA per 90"),
            ("Off. Duels", "Offensive duels per 90"),
            ("Off. Duel %", "Offensive duels won, %"),
            ("Shots", "Shots per 90"),
            ("SoT %", "Shots on target, %"),
            ("Touches box", "Touches in box per 90"),
        ]
        DEFENSIVE = [
            ("Aerial Duels", "Aerial duels per 90"),
            ("Aerial %", "Aerial duels won, %"),
            ("Def Duels", "Defensive duels per 90"),
            ("Def Duel %", "Defensive duels won, %"),
            ("PAdj Int", "PAdj Interceptions"),
            ("Blocks", "Shots blocked per 90"),
            ("Succ Def Acts", "Successful defensive actions per 90"),
        ]
        POSSESSION = [
            ("Accel", "Accelerations per 90"),
            ("Deep comp", "Deep completions per 90"),
            ("Dribbles", "Dribbles per 90"),
            ("Dribble %", "Successful dribbles, %"),
            ("Fwd Passes", "Forward passes per 90"),
            ("Fwd Pass %", "Accurate forward passes, %"),
            ("Key passes", "Key passes per 90"),
            ("Long Passes", "Long passes per 90"),
            ("Long Pass %", "Accurate long passes, %"),
            ("Passes", "Passes per 90"),
            ("Pass %", "Accurate passes, %"),
            ("Pass to F3rd", "Passes to final third per 90"),
            ("F3rd %", "Accurate passes to final third, %"),
            ("Pass PenA", "Passes to penalty area per 90"),
            ("PenA %", "Accurate passes to penalty area, %"),
            ("Prog Passes", "Progressive passes per 90"),
            ("Prog Pass %", "Accurate progressive passes, %"),
            ("Prog Runs", "Progressive runs per 90"),
            ("Smart", "Smart passes per 90"),
        ]
        return [("ATTACKING", ATTACKING), ("DEFENSIVE", DEFENSIVE), ("POSSESSION", POSSESSION)]

    # CF (striker)
    if pos_group == "CF":
        ATTACKING = [
            ("Crosses", "Crosses per 90"),
            ("Cross %", "Accurate crosses, %"),
            ("NPG", "Non-penalty goals per 90"),
            ("xG", "xG per 90"),
            ("Conv %", "Goal conversion, %"),
            ("Head goals", "Head goals per 90"),
            ("xA", "xA per 90"),
            ("Off. Duels", "Offensive duels per 90"),
            ("Off. Duel %", "Offensive duels won, %"),
            ("Prog Runs", "Progressive runs per 90"),
            ("Shots", "Shots per 90"),
            ("SoT %", "Shots on target, %"),
            ("Touches box", "Touches in box per 90"),
        ]
        DEFENSIVE = [
            ("Aerial Duels", "Aerial duels per 90"),
            ("Aerial %", "Aerial duels won, %"),
            ("Def Duels", "Defensive duels per 90"),
            ("Def Duel %", "Defensive duels won, %"),
            ("PAdj Int", "PAdj Interceptions"),
            ("Succ Def Acts", "Successful defensive actions per 90"),
        ]
        POSSESSION = [
            ("Deep comp", "Deep completions per 90"),
            ("Dribbles", "Dribbles per 90"),
            ("Dribble %", "Successful dribbles, %"),
            ("Key passes", "Key passes per 90"),
            ("Passes", "Passes per 90"),
            ("Pass %", "Accurate passes, %"),
            ("Pass PenA", "Passes to penalty area per 90"),
            ("PenA %", "Accurate passes to penalty area, %"),
            ("Smart", "Smart passes per 90"),
        ]
        return [("ATTACKING", ATTACKING), ("DEFENSIVE", DEFENSIVE), ("POSSESSION", POSSESSION)]

    return []

# ============================================================
# STREAMLIT PAGE SETUP + CSS
# ============================================================
st.set_page_config(page_title="Club View", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.stApp { background:#0e0e0f; color:#f2f2f2; }
.block-container { padding-top:1.1rem; padding-bottom:2rem; max-width:980px; } /* tighter overall width */
header, footer { visibility:hidden; }

/* Keep your original “pro” smoothing */
html, body, .block-container *{
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; text-rendering:optimizeLegibility;
  font-feature-settings:"liga","kern","tnum"; font-variant-numeric:tabular-nums;
}

/* Section title */
.section-title{
  font-size:40px;font-weight:900;letter-spacing:1px;
  margin-top:24px;margin-bottom:10px;color:#f2f2f2;
}

/* Compact header card (mobile responsive) */
.club-card{
  background:#1c1c1d; border:1px solid #2a2a2b; border-radius:18px; padding:16px;
}
.header-grid{
  display:grid; grid-template-columns: 210px 1fr; gap: 16px; align-items:start;
}
@media (max-width: 720px){
  .header-grid{ grid-template-columns: 1fr; }
}
.crest-tile{
  width:210px; height:170px; background:#121213; border:1px solid #2a2a2b;
  border-radius:16px; display:flex; align-items:center; justify-content:center; overflow:hidden;
}
@media (max-width: 720px){
  .crest-tile{ width:100%; height:150px; }
}
.crest-img{ width:140px; height:140px; object-fit:contain; display:block; }
.team-title{ font-size:44px; font-weight:900; margin:0; line-height:1.05; color:#f2f2f2; }
@media (max-width: 720px){
  .team-title{ font-size:38px; }
}
.league-row{ display:flex; align-items:center; gap:10px; margin-top:10px; }
.flag-img{ width:44px; height:32px; object-fit:cover; border-radius:6px; display:block; }
.league-text{ font-size:22px; font-weight:800; color:#d2d2d4; }

.metricrow{ display:flex; gap:14px; flex-wrap:wrap; margin-top:12px; align-items:center; }
.pillhdr{
  width:50px; height:38px; border-radius:12px; display:flex; align-items:center; justify-content:center;
  font-size:22px; font-weight:950; color:#111; border:1px solid rgba(0,0,0,.35);
  box-shadow: 0 1px 0 rgba(255,255,255,0.06) inset;
}
.hlabel{ font-size:26px; font-weight:800; color:#9ea0a6; }
.info{ margin-top:10px; display:flex; flex-direction:column; gap:4px; font-size:15px; color:#b0b0b3; }

/* Pro cards */
.pro-wrap{ display:flex; justify-content:center; }
.pro-card{
  position:relative; width:min(760px,98%);
  display:grid; grid-template-columns:96px 1fr 64px; gap:12px; align-items:start;
  background:#141823; border:1px solid rgba(255,255,255,.06); border-radius:20px;
  padding:16px; margin-bottom:12px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.03), 0 6px 24px rgba(0,0,0,.35);
}
.pro-avatar{ width:96px; height:96px; border-radius:12px; border:1px solid #2a3145; overflow:hidden; background:#0b0d12; }
.pro-avatar img{ width:100%; height:100%; object-fit:cover; }

.flagchip{ display:inline-flex; align-items:center; gap:6px; background:transparent; border:none; padding:0; height:auto; }
.flagchip img{ width:26px; height:18px; border-radius:2px; display:block; }

.chip{ background:transparent; color:#a6a6a6; border:none; padding:0; border-radius:0; font-size:15px; line-height:18px; opacity:.92; }
.row{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:2px 0; }
.leftrow1{ margin-top:6px; } .leftrow-foot{ margin-top:2px; } .leftrow-contract{ margin-top:8px; }

.pill{ padding:2px 8px; min-width:40px; border-radius:8px; font-weight:900; font-size:18px; line-height:1; color:#0b0d12; text-align:center; display:inline-block; }
.name{ font-weight:950; font-size:22px; color:#e8ecff; margin-bottom:6px; letter-spacing:.2px; line-height:1.15; }
.sub{ color:#a8b3cf; font-size:15px; opacity:.92; }

.posrow{ margin-top:10px; }
.postext{ font-weight:800; font-size:14.5px; letter-spacing:.2px; margin-right:10px; }
.rank{ position:absolute; top:10px; right:14px; color:#b7bfe1; font-weight:900; font-size:18px; text-align:right; }

.teamline{ color:#dbe3ff; font-size:14px; font-weight:700; margin-top:6px; letter-spacing:.05px; opacity:.95; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.teamline-wrap{ display:flex; align-items:center; gap:8px; }
.badge-mini{ width:18px; height:18px; border-radius:4px; object-fit:contain; }

/* Metrics expander grid */
.m-sec{ background:#121621; border:1px solid #242b3b; border-radius:16px; padding:10px 12px; }
.m-title{ color:#e8ecff; font-weight:900; letter-spacing:.02em; margin:4px 0 10px 0; }
.m-row{ display:flex; justify-content:space-between; align-items:center; padding:8px 8px; border-radius:10px; }
.m-label{ color:#c9d3f2; font-size:15px; letter-spacing:.1px; flex:1 1 auto; }
.m-right{ display:flex; align-items:center; gap:8px; }
.m-raw{ color:#93a0c7; font-size:13px; opacity:.9; min-width:52px; text-align:right; }
.m-badge{ flex:0 0 auto; min-width:44px; text-align:center; padding:2px 10px; border-radius:8px; font-weight:900; font-size:18px; color:#0b0d12; border:1px solid rgba(0,0,0,.15); }
.metrics-grid{ display:grid; grid-template-columns:1fr; gap:12px; }
@media (min-width: 720px){ .metrics-grid{ grid-template-columns:repeat(3,1fr);} }

/* Squad filters row under SQUAD */
.filters-row{
  background:#10131b; border:1px solid rgba(255,255,255,.06);
  border-radius:16px; padding:12px 12px; margin:10px 0 16px 0;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# LOAD CSV
# ============================================================
if not os.path.exists(CSV_PATH):
    st.error(f"CSV not found at: {CSV_PATH} (repo root).")
    st.stop()

df_all = pd.read_csv(CSV_PATH)

# required
for req in ("Team", "Player", "Position"):
    if req not in df_all.columns:
        st.error(f"CSV must include '{req}' column.")
        st.stop()

mins_col = detect_minutes_col(df_all)
if mins_col not in df_all.columns:
    st.error("Could not detect a minutes column (expected 'Minutes played').")
    st.stop()

# Primary position (fix attackers)
df_all["Primary Position"] = df_all["Position"].astype(str).str.split(",").str[0].str.strip()
df_all["PosGroup"] = df_all["Primary Position"].apply(pos_group_from_primary)

# ============================================================
# HEADER (compact + responsive)
# ============================================================
crest_uri = img_to_data_uri(CREST_PATH)
flag_uri = img_to_data_uri(FLAG_PATH)

header_html = f"""
<div class="club-card">
  <div class="header-grid">
    <div>
      <div class="crest-tile">
        {f"<img class='crest-img' src='{crest_uri}' />" if crest_uri else ""}
      </div>
      <div class="league-row">
        {f"<img class='flag-img' src='{flag_uri}' />" if flag_uri else ""}
        <div class="league-text">{LEAGUE_TEXT}</div>
      </div>
    </div>

    <div>
      <div class="team-title">{TEAM_NAME}</div>

      <div class="metricrow">
        <div style="display:flex;align-items:center;gap:10px;">
          <div class="pillhdr" style="background:{_pro_rating_color(OVERALL)}">{OVERALL}</div>
          <div class="hlabel">Overall</div>
        </div>

        <div style="display:flex;align-items:center;gap:10px;">
          <div class="pillhdr" style="background:{_pro_rating_color(ATT_HDR)}">{ATT_HDR}</div>
          <div class="hlabel">ATT</div>
        </div>

        <div style="display:flex;align-items:center;gap:10px;">
          <div class="pillhdr" style="background:{_pro_rating_color(MID_HDR)}">{MID_HDR}</div>
          <div class="hlabel">MID</div>
        </div>

        <div style="display:flex;align-items:center;gap:10px;">
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
"""
components.html(header_html, height=330)

# ============================================================
# PERFORMANCE
# ============================================================
st.markdown('<div class="section-title">PERFORMANCE</div>', unsafe_allow_html=True)
if PERFORMANCE_IMAGE_PATH and os.path.exists(PERFORMANCE_IMAGE_PATH):
    st.image(PERFORMANCE_IMAGE_PATH, use_container_width=True)
else:
    st.warning(f"Performance image not found: {PERFORMANCE_IMAGE_PATH}")

# ============================================================
# SQUAD + FILTERS (under SQUAD subtitle)
# ============================================================
st.markdown('<div class="section-title" style="margin-top:22px;">SQUAD</div>', unsafe_allow_html=True)

# Base team filter (always)
df_team = df_all[df_all["Team"].astype(str).str.strip() == TEAM_NAME].copy()
if df_team.empty:
    st.info(f"No players found for Team = '{TEAM_NAME}'.")
    st.stop()

# Minutes slider affects POOL + DISPLAY + calculations (requested)
# Age slider affects DISPLAY ONLY (requested)
with st.container():
    st.markdown('<div class="filters-row">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2.2, 1.8, 2.2])

    with c1:
        min_m, max_m = st.slider(
            "Minutes (pool + display)",
            min_value=0,
            max_value=int(max(5000, df_team[mins_col].fillna(0).max() if mins_col in df_team.columns else 5000)),
            value=(500, 5000),
            step=50,
        )
    with c2:
        age_min, age_max = st.slider(
            "Age (display only)",
            min_value=16, max_value=45,
            value=(16, 45),
            step=1,
        )
    with c3:
        visa_only = st.checkbox("Visa players (exclude China PR)", value=False)

    st.markdown("</div>", unsafe_allow_html=True)

# Numeric minutes
df_team[mins_col] = pd.to_numeric(df_team[mins_col], errors="coerce").fillna(0)

# POOL (for percentiles/role scores) = team + minutes range
df_pool = df_team[(df_team[mins_col] >= min_m) & (df_team[mins_col] <= max_m)].copy()
if df_pool.empty:
    st.info("No players in the selected minutes range (pool).")
    st.stop()

# Compute percentiles on pool
df_pool = add_percentiles(df_pool)

# Role scores on pool
df_pool["RoleScores"] = df_pool.apply(compute_role_scores_for_row, axis=1)

# DISPLAY list starts from pool (since minutes affects display too)
df_disp = df_pool.copy()

# Age filter (display only; does NOT affect pool already computed — but we’re filtering df_disp which is displayed)
if "Age" in df_disp.columns:
    df_disp["Age_num"] = pd.to_numeric(df_disp["Age"], errors="coerce")
    df_disp = df_disp[(df_disp["Age_num"].fillna(-1) >= age_min) & (df_disp["Age_num"].fillna(999) <= age_max)]

# Visa toggle (display only) exclude China PR
if visa_only and "Birth country" in df_disp.columns:
    bc = df_disp["Birth country"].astype(str).map(_norm_scalar)
    df_disp = df_disp[bc.ne("china pr")]

# Sort by minutes desc (always)
df_disp = df_disp.sort_values(mins_col, ascending=False).reset_index(drop=True)
if df_disp.empty:
    st.info("No players match the display filters.")
    st.stop()

# ============================================================
# Photos
# - load overrides
# - try FotMob map once
# - resolve each player photo
# ============================================================
overrides = load_photo_overrides()

fotmob_map = {}
# best-effort; if requests blocked it just becomes {}
if requests is not None:
    fotmob_map = try_fetch_fotmob_player_map(FOTMOB_TEAM_ID)

# Crest badge mini used on every card
badge_mini_html = f"<img class='badge-mini' src='{crest_uri}' />" if crest_uri else ""

# ============================================================
# Render cards
# ============================================================
def _age_text(row: pd.Series) -> str:
    if "Age_num" in row.index and not pd.isna(row["Age_num"]):
        try:
            return f"{int(row['Age_num'])}y.o."
        except Exception:
            pass
    if "Age" in row.index and not pd.isna(row["Age"]):
        try:
            return f"{int(float(row['Age']))}y.o."
        except Exception:
            pass
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

def metrics_section_html(title: str, pairs: List[Tuple[str, str]], row: pd.Series) -> str:
    rows = []
    for lab, met in pairs:
        p = pct_of(row, met)
        raw_ok, raw_txt = val_of(row, met)

        # If metric exists but percentile missing, compute a fallback display:
        # show "—" instead of misleading "00"
        if p is None:
            badge_txt = "—"
            badge_col = "#2d3550"
        else:
            pi = _pro_show99(p)
            badge_txt = _fmt2(pi)
            badge_col = _pro_rating_color(pi)

        rows.append(
            "<div class='m-row'>"
            f"<div class='m-label'>{lab}</div>"
            "<div class='m-right'>"
            f"<div class='m-raw'>{raw_txt if raw_ok else '—'}</div>"
            f"<div class='m-badge' style='background:{badge_col}'>{badge_txt}</div>"
            "</div>"
            "</div>"
        )
    return f"<div class='m-sec'><div class='m-title'>{title}</div>{''.join(rows)}</div>"

# ============================================================
# OPTIONAL ADMIN (hidden) for photo overrides
# - requires st.secrets["ADMIN_PASSWORD"]
# ============================================================
def admin_panel():
    pwd = st.secrets.get("ADMIN_PASSWORD", None)
    if not pwd:
        return

    with st.expander("Admin (hidden tools)", expanded=False):
        entered = st.text_input("Password", type="password")
        if entered != pwd:
            st.caption("Enter password to manage player photos.")
            return

        st.success("Admin unlocked.")
        st.caption("Set a photo URL per player (stored server-side in player_photos.json).")
        player_pick = st.selectbox("Player", options=df_team["Player"].astype(str).tolist())
        url = st.text_input("Image URL (FotMob / any https)", value=overrides.get(_name_key(player_pick), ""))

        colA, colB = st.columns(2)
        with colA:
            if st.button("Save override"):
                overrides[_name_key(player_pick)] = url.strip()
                save_photo_overrides(overrides)
                st.success("Saved.")
                st.rerun()
        with colB:
            if st.button("Clear override"):
                overrides.pop(_name_key(player_pick), None)
                save_photo_overrides(overrides)
                st.info("Cleared.")
                st.rerun()

admin_panel()

# ============================================================
# MAIN LIST
# ============================================================
for i, row in df_disp.iterrows():
    player = str(row.get("Player", "—"))
    league = str(row.get("League", ""))
    pos = str(row.get("Position", ""))
    birth = str(row.get("Birth country", "")) if "Birth country" in df_disp.columns else ""
    foot = _get_foot(row) or "—"
    age_txt = _age_text(row)
    contract_txt = _contract_year(row)
    mins = int(row.get(mins_col, 0) or 0)

    primary = str(row.get("Primary Position", "")).strip().upper()
    pg = str(row.get("PosGroup", "OTHER"))

    # roles
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
    ) if roles_sorted else "<div class='row'><span class='sub'>No role scores</span></div>"

    flag = _flag_html(birth)
    pos_html = _positions_html(pos)

    # player photo (auto fotmob → overrides → fallback)
    photo_url = resolve_player_photo(player, fotmob_map, overrides)

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
    st.markdown(card_html, unsafe_allow_html=True)

    # ===== Individual Metrics dropdown (per position group) =====
    sections = metric_sections_for_group(pg)

    with st.expander("Individual Metrics", expanded=False):
        if not sections:
            st.info("No metric sections available for this position.")
        else:
            blocks = []
            for title, pairs in sections:
                blocks.append(metrics_section_html(title, pairs, row))

            st.markdown(
                "<div class='metrics-grid'>" + "".join(blocks) + "</div>",
                unsafe_allow_html=True
            )

















