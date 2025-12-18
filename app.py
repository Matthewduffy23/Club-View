# app.py — Club View (single-file Streamlit app)
# ✅ Fixes:
# - NO HTML printing-as-text (all cards + header render via st.markdown(unsafe_allow_html=True), no per-card iframes)
# - Compact header for mobile
# - "PLAYERS" subtitle, then filters directly underneath (minutes pool+display, age display-only, Visa players display-only)
# - Attackers load correctly (uses Primary Position = first token of Position)
# - Visa toggle works (Birth country == "China PR" treated as domestic; checked = show only non–China PR)
# - Individual Metrics dropdown per-position, only shows metrics that exist (no “00” rows for missing metrics)
# - GK: Conceded goals per 90 is inverted (lower = better) + other GK lower-better metrics also inverted
# - No league label in player card footer (team only)
# - Player photos: tries FotMob squad page (cached) + optional hidden repo mapping file (no UI)

import os
import re
import base64
import unicodedata
import textwrap
from typing import Dict, List, Tuple, Optional

import pandas as pd
import numpy as np
import streamlit as st

# =========================
# CONFIG (edit in code only)
# =========================
CSV_PATH = "Chinaall.csv"
TEAM_NAME = "Chengdu Rongcheng"
MIN_MINUTES_DEFAULT = (500, 5000)  # pool + display
AGE_DISPLAY_DEFAULT = (16, 45)     # display only

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

# Optional: hidden mapping (NO UI)
# Put a CSV in your repo root named "player_images.csv" with columns:
# Player,ImageURL
# Example:
# Felipe,https://images.fotmob.com/image_resources/playerimages/12345.png
PLAYER_IMAGE_MAP_PATH = "player_images.csv"

# FotMob squad page for this club (used to auto-match by surname; cached)
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
        x = float(x)
    except Exception:
        x = 0.0
    if np.isnan(x):
        x = 0.0
    return int(max(0, min(99, round(x))))

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
# FLAGS (Twemoji) — include China PR
# =========================
TWEMOJI_SPECIAL = {
    "eng":"1f3f4-e0067-e0062-e0065-e006e-e0067-e007f",
    "sct":"1f3f4-e0067-e0062-e0073-e0063-e0074-e007f",
    "wls":"1f3f4-e0067-e0062-e0077-e006c-e0073-e007f",
}
COUNTRY_TO_CC = {
    "china":"cn",
    "china pr":"cn",
    "england":"eng","scotland":"sct","wales":"wls",
    "united kingdom":"gb","great britain":"gb",
    "brazil":"br","argentina":"ar","spain":"es","france":"fr","germany":"de","italy":"it","portugal":"pt",
    "netherlands":"nl","belgium":"be","sweden":"se","norway":"no","denmark":"dk","poland":"pl","japan":"jp","south korea":"kr",
    "israel":"il","netherlands":"nl",
}

def _norm_str(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode("ascii")
    return s.strip().lower()

def _cc_to_twemoji(cc: str) -> Optional[str]:
    if not cc or len(cc) != 2:
        return None
    a, b = cc.upper()
    cp1 = 0x1F1E6 + (ord(a)-ord("A"))
    cp2 = 0x1F1E6 + (ord(b)-ord("A"))
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
# Utilities
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

def detect_minutes_col(df: pd.DataFrame) -> str:
    for c in ["Minutes played","Minutes Played","Minutes","mins","minutes","Min"]:
        if c in df.columns:
            return c
    return "Minutes played"

def make_primary_position(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["Position"] = out.get("Position", "").astype(str)
    out["Primary Position"] = out["Position"].astype(str).str.split(",").str[0].str.strip()
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
    if p in {"RW","RWF","RAMF","LW","LWF","LAMF","AMF"}:
        return "ATT"
    if p.startswith("CF"):
        return "CF"
    return "OTHER"

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
# Roles (same as your last working version)
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

# lower is better -> invert percentile
LOWER_BETTER = {
    "Conceded goals per 90",
    "Shots against per 90",
    "xG against per 90",
}

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

    # compute within PosGroup
    for m in used:
        if m not in out.columns:
            continue

        def _pct(series: pd.Series) -> pd.Series:
            s = pd.to_numeric(series, errors="coerce")
            n = s.notna().sum()
            if n <= 1:
                return pd.Series([50.0]*len(s), index=s.index)
            # rank pct in [0..100]
            p = s.rank(pct=True) * 100.0
            return p

        pct = out.groupby("PosGroup")[m].transform(_pct)

        if m in LOWER_BETTER:
            pct = 100.0 - pct

        # keep within 0..99 (prevents “100” and reduces mass “99” feeling)
        pct = pct.clip(0, 100) * 0.99

        out[f"{m} Percentile"] = pct.fillna(0.0)

    return out

def weighted_role_score(row: pd.Series, weights: Dict[str, float]) -> int:
    num, den = 0.0, 0.0
    for metric, w in weights.items():
        col = f"{metric} Percentile"
        v = row.get(col, 0.0)
        try:
            v = float(v)
        except Exception:
            v = 0.0
        if np.isnan(v):
            v = 0.0
        num += w * v
        den += w
    score = (num / den) if den > 0 else 0.0
    return _pro_show99(score)

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
# Player images (FotMob + hidden mapping)
# =========================
def load_player_image_map() -> Dict[str, str]:
    m = {}
    if os.path.exists(PLAYER_IMAGE_MAP_PATH):
        try:
            dfm = pd.read_csv(PLAYER_IMAGE_MAP_PATH)
            if {"Player","ImageURL"}.issubset(dfm.columns):
                for _, r in dfm.iterrows():
                    p = str(r["Player"]).strip()
                    u = str(r["ImageURL"]).strip()
                    if p and u and u.lower() != "nan":
                        m[_norm_str(p)] = u
        except Exception:
            pass
    return m

@st.cache_data(show_spinner=False, ttl=60*60*24)
def fetch_fotmob_surname_map(url: str) -> Dict[str, str]:
    """
    Returns {surname_lower: image_url} for the squad page.
    Requires internet on Streamlit Cloud runtime (works there).
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except Exception:
        return {}

    try:
        r = requests.get(url, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code != 200:
            return {}
        soup = BeautifulSoup(r.text, "html.parser")

        # FotMob squad pages embed image urls in <img ...> in player rows/cards.
        # We map by the visible player name nearby.
        out = {}

        # heuristic: find all img tags that look like player images
        imgs = soup.find_all("img")
        for img in imgs:
            src = img.get("src") or ""
            alt = img.get("alt") or ""
            if not src:
                continue
            # player image resources commonly contain "playerimages"
            if "playerimages" not in src and "image_resources" not in src:
                continue

            name = alt.strip()
            if not name:
                continue
            surname = _norm_str(name).split(" ")[-1]
            if surname and surname not in out:
                out[surname] = src

        return out
    except Exception:
        return {}

def resolve_player_avatar(player_name: str, hidden_map: Dict[str, str], surname_map: Dict[str, str]) -> str:
    # 1) hidden repo mapping by full name
    key = _norm_str(player_name)
    if key in hidden_map:
        return hidden_map[key]

    # 2) FotMob by surname
    surname = key.split(" ")[-1] if key else ""
    if surname and surname in surname_map:
        return surname_map[surname]

    # fallback
    return DEFAULT_AVATAR

# =========================
# Individual Metrics definitions (your exact naming/order)
# =========================
GK_GOALKEEPING = [
    ("Exits", "Exits per 90"),
    ("Goals Prevented", "Prevented goals per 90"),
    ("Goals Conceded", "Conceded goals per 90"),
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

ALL_ATTACKING = [
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
ALL_DEFENSIVE = [
    ("Aerial Duels", "Aerial duels per 90"),
    ("Aerial Win %", "Aerial duels won, %"),
    ("Defensive Duels", "Defensive duels per 90"),
    ("Defensive Duel %", "Defensive duels won, %"),
    ("PAdj Interceptions", "PAdj Interceptions"),
    ("Shots blocked", "Shots blocked per 90"),
    ("Succ. def acts", "Successful defensive actions per 90"),
]
ALL_POSSESSION = [
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

ST_ATTACKING = [
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
ST_DEFENSIVE = [
    ("Aerial Duels", "Aerial duels per 90"),
    ("Aerial Duel Success %", "Aerial duels won, %"),
    ("Defensive Duels", "Defensive duels per 90"),
    ("Defensive Duel Success %", "Defensive duels won, %"),
    ("PAdj. Interceptions", "PAdj Interceptions"),
    ("Successful Def. Actions", "Successful defensive actions per 90"),
]
ST_POSSESSION = [
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

def metric_available(df: pd.DataFrame, met: str) -> bool:
    return (met in df.columns) and (f"{met} Percentile" in df.columns)

def pct_of(row: pd.Series, met: str) -> Optional[float]:
    col = f"{met} Percentile"
    if col not in row.index:
        return None
    try:
        v = float(row[col])
    except Exception:
        return None
    if np.isnan(v):
        return None
    return v

def val_of(row: pd.Series, met: str) -> Optional[float]:
    if met not in row.index:
        return None
    try:
        v = float(row[met])
    except Exception:
        return None
    if np.isnan(v):
        return None
    return v

def build_metrics_sections(df_all: pd.DataFrame, row: pd.Series) -> List[Tuple[str, List[Tuple[str, int]]]]:
    """
    Returns list of (section_title, [(label, percentile_int)]).
    Only includes metrics that exist & are calculated (no empty/00 due to missing cols).
    """
    g = row.get("PosGroup","OTHER")

    def take(pairs: List[Tuple[str,str]]) -> List[Tuple[str,int]]:
        out = []
        for lab, met in pairs:
            if not metric_available(df_all, met):
                continue
            p = pct_of(row, met)
            v = val_of(row, met)
            if p is None or v is None:
                continue
            out.append((lab, _pro_show99(p)))
        return out

    if g == "GK":
        s1 = take(GK_GOALKEEPING)
        s2 = take(GK_POSSESSION)
        sections = []
        if s1: sections.append(("GOALKEEPING", s1))
        if s2: sections.append(("POSSESSION", s2))
        return sections

    if g == "CB":
        a = take(CB_ATTACKING)
        d = take(CB_DEFENSIVE)
        p = take(CB_POSSESSION)
        sections = []
        if a: sections.append(("ATTACKING", a))
        if d: sections.append(("DEFENSIVE", d))
        if p: sections.append(("POSSESSION", p))
        return sections

    if g == "CF":
        a = take(ST_ATTACKING)
        d = take(ST_DEFENSIVE)
        p = take(ST_POSSESSION)
        sections = []
        if a: sections.append(("ATTACKING", a))
        if d: sections.append(("DEFENSIVE", d))
        if p: sections.append(("POSSESSION", p))
        return sections

    # FB / CM / ATT (and everything else non-GK/CB/CF): use ALL_
    a = take(ALL_ATTACKING)
    d = take(ALL_DEFENSIVE)
    p = take(ALL_POSSESSION)
    sections = []
    if a: sections.append(("ATTACKING", a))
    if d: sections.append(("DEFENSIVE", d))
    if p: sections.append(("POSSESSION", p))
    return sections

# =========================
# STREAMLIT SETUP
# =========================
st.set_page_config(page_title="Club View", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
/* --- global --- */
html, body, .stApp, .block-container{
  background:#0e0e0f !important;
  color:#f2f2f2;
}
.block-container{
  padding-top:1.0rem;
  padding-bottom:2rem;
  max-width:1150px;
}
header, footer { visibility:hidden; }

/* keep original “smooth + tabular nums” feel */
html, body, .block-container *{
  -webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;
  text-rendering:optimizeLegibility;
  font-feature-settings:"liga","kern","tnum";
  font-variant-numeric:tabular-nums;
}

/* --- section titles --- */
.section-title{
  font-size:40px;
  font-weight:900;
  letter-spacing:1px;
  margin-top:24px;
  margin-bottom:12px;
  color:#f2f2f2;
}

/* =========================
   Compact Header (mobile-first)
========================= */
.hdr-wrap{
  background:#1c1c1d;
  border:1px solid #2a2a2b;
  border-radius:18px;
  padding:16px;
}
.hdr-grid{
  display:grid;
  grid-template-columns:110px 1fr;
  gap:14px;
  align-items:center;
}
.hdr-crestbox{
  width:110px;
  height:110px;
  border-radius:16px;
  background:#121213;
  border:1px solid #2a2a2b;
  display:flex;
  align-items:center;
  justify-content:center;
  overflow:hidden;
}
.hdr-crestbox img{ width:92px; height:92px; object-fit:contain; }
.hdr-team{ font-size:38px; font-weight:900; line-height:1.05; margin-bottom:6px; }
.hdr-league{
  display:flex; align-items:center; gap:10px;
  margin-top:6px;
  color:#d2d2d4;
  font-weight:800;
  font-size:22px;
  line-height:1;
}
.hdr-league img{ width:42px; height:30px; border-radius:6px; object-fit:cover; }

.hdr-metrics{
  display:flex; gap:16px; flex-wrap:wrap; align-items:center; margin-top:8px;
}
.hdr-metric{ display:flex; align-items:center; gap:10px; }
.hdr-pill{
  width:48px; height:36px; border-radius:12px;
  display:flex; align-items:center; justify-content:center;
  font-weight:900; font-size:20px; color:#111;
  border:1px solid rgba(0,0,0,.35);
}
.hdr-label{ font-size:22px; font-weight:800; color:#9ea0a6; }

.hdr-info{
  margin-top:8px;
  display:flex;
  gap:16px;
  flex-wrap:wrap;
  font-size:14px;
  color:#b0b0b3;
}
.hdr-info b{ color:#d0d0d3; }

/* even tighter on small phones */
@media (max-width: 520px){
  .hdr-team{ font-size:30px; }
  .hdr-grid{ grid-template-columns:92px 1fr; }
  .hdr-crestbox{ width:92px; height:92px; }
  .hdr-crestbox img{ width:76px; height:76px; }
  .hdr-league{ font-size:18px; }
  .hdr-league img{ width:36px; height:26px; }
  .hdr-pill{ width:44px; height:34px; font-size:18px; }
  .hdr-label{ font-size:18px; }
}

/* =========================
   Pro cards
========================= */
:root { --card:#141823; --soft:#1e2533; }

.pro-wrap{ display:flex; justify-content:center; }
.pro-card{
  position:relative;
  width:min(720px,98%);
  display:grid;
  grid-template-columns:96px 1fr 64px;
  gap:12px;
  align-items:start;
  background:var(--card);
  border:1px solid rgba(255,255,255,.06);
  border-radius:20px;
  padding:16px;
  margin-bottom:12px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.03), 0 6px 24px rgba(0,0,0,.35);
}
.pro-avatar{ width:96px; height:96px; border-radius:12px; border:1px solid #2a3145; overflow:hidden; background:#0b0d12; }
.pro-avatar img{ width:100%; height:100%; object-fit:cover; }

.flagchip{ display:inline-flex; align-items:center; }
.flagchip img{ width:26px; height:18px; border-radius:2px; display:block; }

.chip{ color:#a6a6a6; font-size:15px; line-height:18px; opacity:.92; }
.row{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:2px 0; }
.leftrow1{ margin-top:6px; } .leftrow-foot{ margin-top:2px; } .leftrow-contract{ margin-top:10px; }

.pill{ padding:2px 6px; min-width:36px; border-radius:6px; font-weight:900; font-size:18px; line-height:1; color:#0b0d12; text-align:center; display:inline-block; }
.name{ font-weight:950; font-size:22px; color:#e8ecff; margin-bottom:6px; letter-spacing:.2px; line-height:1.15; }
.sub{ color:#a8b3cf; font-size:15px; opacity:.9; }
.postext{ font-weight:800; font-size:14.5px; letter-spacing:.2px; margin-right:10px; }
.rank{ position:absolute; top:10px; right:14px; color:#b7bfe1; font-weight:900; font-size:18px; }

.teamline{
  color:#dbe3ff;
  font-size:14px;
  font-weight:700;
  margin-top:6px;
  letter-spacing:.05px;
  opacity:.95;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
  display:flex;
  align-items:center;
  gap:8px;
}
.badge-mini{ width:16px; height:16px; border-radius:50%; object-fit:cover; display:inline-block; }

/* =========================
   Individual metrics cards
========================= */
.metrics-grid{ display:grid; grid-template-columns:1fr; gap:12px; }
@media (min-width: 720px){ .metrics-grid{ grid-template-columns:repeat(3,1fr);} }
.m-sec{ background:#121621; border:1px solid #242b3b; border-radius:16px; padding:10px 12px; }
.m-title{ color:#e8ecff; font-weight:900; letter-spacing:.04em; margin:4px 0 10px 0; font-size:13px; }
.m-row{ display:flex; justify-content:space-between; align-items:center; padding:8px 8px; border-radius:10px; }
.m-label{ color:#c9d3f2; font-size:15px; letter-spacing:.1px; flex:1 1 auto; }
.m-badge{ flex:0 0 auto; min-width:44px; text-align:center; padding:2px 10px; border-radius:8px; font-weight:900; font-size:18px; color:#0b0d12; border:1px solid rgba(0,0,0,.15); }

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

df_all = make_primary_position(df_all)
df_all["PosGroup"] = df_all["Primary Position"].apply(pos_group)

# =========================
# HEADER (compact + rendered, not printed)
# =========================
crest_uri = img_to_data_uri(CREST_PATH)
flag_uri = img_to_data_uri(FLAG_PATH)

header_html = f"""
<div class="hdr-wrap">
  <div class="hdr-grid">
    <div style="display:flex;flex-direction:column;gap:10px;align-items:flex-start;">
      <div class="hdr-crestbox">
        {f"<img src='{crest_uri}' alt='crest'/>" if crest_uri else ""}
      </div>
      <div class="hdr-league">
        {f"<img src='{flag_uri}' alt='flag'/>" if flag_uri else ""}
        <div>{LEAGUE_TEXT}</div>
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
# PLAYERS + FILTERS (directly under subtitle)
# =========================
st.markdown('<div class="section-title" style="margin-top:30px;">PLAYERS</div>', unsafe_allow_html=True)

# Minutes slider affects pool + display (your requirement)
mins_low, mins_high = st.slider(
    "Minutes (pool + display)",
    min_value=0,
    max_value=6000,
    value=MIN_MINUTES_DEFAULT,
    step=10,
    key="mins_slider",
)

# Age is display-only (does NOT affect pool; applied after pool calc)
age_low, age_high = st.slider(
    "Age (display only)",
    min_value=16,
    max_value=45,
    value=AGE_DISPLAY_DEFAULT,
    step=1,
    key="age_slider",
)

visa_only = st.checkbox(
    "Visa players (exclude China PR)",
    value=False,
    key="visa_only",
)

# =========================
# TEAM FILTER + MINUTES POOL FILTER
# =========================
df_team = df_all[df_all["Team"].astype(str).str.strip() == TEAM_NAME].copy()
if df_team.empty:
    st.info(f"No players found for Team = '{TEAM_NAME}'.")
    st.stop()

mins_col = detect_minutes_col(df_team)
df_team[mins_col] = pd.to_numeric(df_team[mins_col], errors="coerce").fillna(0)

# pool filter
df_pool = df_team[(df_team[mins_col] >= mins_low) & (df_team[mins_col] <= mins_high)].copy()
if df_pool.empty:
    st.info(f"No players for {TEAM_NAME} with {mins_col} in [{mins_low}, {mins_high}].")
    st.stop()

# compute percentiles on the POOL (so sliders affect calculation)
df_pool = add_percentiles(df_pool)

# role scores
df_pool["RoleScores"] = df_pool.apply(compute_role_scores_for_row, axis=1)

# =========================
# DISPLAY FILTERS (age + visa) — do NOT affect pool percentiles
# =========================
df_disp = df_pool.copy()

# age filter (display only)
if "Age" in df_disp.columns:
    df_disp["Age_num"] = pd.to_numeric(df_disp["Age"], errors="coerce")
    df_disp = df_disp[(df_disp["Age_num"].fillna(0) >= age_low) & (df_disp["Age_num"].fillna(0) <= age_high)].copy()

# visa filter (display only)
if visa_only and "Birth country" in df_disp.columns:
    bc = df_disp["Birth country"].astype(str).map(_norm_str)
    df_disp = df_disp[bc.ne("china pr")].copy()

# sort by minutes (display ordering)
df_disp = df_disp.sort_values(mins_col, ascending=False).reset_index(drop=True)

if df_disp.empty:
    st.info("No players match the display filters.")
    st.stop()

# =========================
# Player photos
# =========================
hidden_img_map = load_player_image_map()
fotmob_surname_map = fetch_fotmob_surname_map(FOTMOB_SQUAD_URL)

badge_uri = crest_uri  # badge icon == team crest (your instruction)

# =========================
# Render cards + metrics dropdown
# =========================
for i, row in df_disp.iterrows():
    player = str(row.get("Player","—"))
    pos = str(row.get("Position",""))
    primary = str(row.get("Primary Position",""))
    birth = str(row.get("Birth country","")) if "Birth country" in df_disp.columns else ""
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

    avatar_url = resolve_player_avatar(player, hidden_img_map, fotmob_surname_map)

    teamline_badge = f"<img class='badge-mini' src='{badge_uri}' alt='badge'/>" if badge_uri else ""
    # NO LEAGUE LABEL (your request): team only
    teamline = f"<div class='teamline'>{teamline_badge}<span>{TEAM_NAME}</span></div>"

    card_html = f"""
    <div class='pro-wrap'>
      <div class='pro-card'>
        <div>
          <div class='pro-avatar'><img src="{avatar_url}" alt="{player}" loading="lazy"/></div>
          <div class='row leftrow1'>{flag}<span class='chip'>{age_txt}</span><span class='chip'>{mins} mins</span></div>
          <div class='row leftrow-foot'><span class='chip'>{foot}</span></div>
          <div class='row leftrow-contract'><span class='chip'>{contract_txt}</span></div>
        </div>

        <div>
          <div class='name'>{player}</div>
          {pills_html}
          <div class='row' style='margin-top:10px;'>{pos_html}</div>
          {teamline}
        </div>

        <div class='rank'>#{_fmt2(i+1)}</div>
      </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

    # --- Individual Metrics dropdown (per position) ---
    sections = build_metrics_sections(df_pool, row)
    if sections:
        with st.expander("Individual Metrics", expanded=False):
            def _sec_html(title: str, pairs: List[Tuple[str,int]]) -> str:
                rows = []
                for lab, p in pairs:
                    rows.append(
                        f"<div class='m-row'>"
                        f"<div class='m-label'>{lab}</div>"
                        f"<div class='m-badge' style='background:{_pro_rating_color(p)}'>{_fmt2(p)}</div>"
                        f"</div>"
                    )
                return f"<div class='m-sec'><div class='m-title'>{title}</div>{''.join(rows)}</div>"

            st.markdown(
                "<div class='metrics-grid'>"
                + "".join(_sec_html(t, pairs) for t, pairs in sections)
                + "</div>",
                unsafe_allow_html=True
            )





















