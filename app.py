import os
import re
import base64
import unicodedata
import textwrap
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# =========================
# CONFIG (edit in code only)
# =========================
CSV_PATH = "Chinaall.csv"
TEAM_NAME = "Chengdu Rongcheng"
MIN_MINUTES = 400

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
    "brazil":"br","argentina":"ar","spain":"es","france":"fr","germany":"de","italy":"it","portugal":"pt",
    "netherlands":"nl","belgium":"be","sweden":"se","norway":"no","denmark":"dk","poland":"pl","japan":"jp","south korea":"kr",
}

def _norm(s: str) -> str:
    if not s:
        return ""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii","ignore").decode("ascii").strip().lower()

def _cc_to_twemoji(cc: str) -> str | None:
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
# (weights; percentiles computed in-app)
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
LOWER_BETTER = {"Conceded goals per 90"}

def pos_group(pos: str) -> str:
    p = str(pos).strip().upper()
    if p.startswith(("GK",)):
        return "GK"
    if p.startswith(("LCB","RCB","CB")):
        return "CB"
    if p.startswith(("RB","RWB","LB","LWB")):
        return "FB"
    if p.startswith(("LCMF","RCMF","LDMF","RDMF","DMF","CMF")):
        return "CM"
    if p in {"RW","RWF","RAMF","LW","LWF","LAMF","AMF"}:
        return "ATT"
    if p.startswith(("CF",)):
        return "CF"
    return "OTHER"

def weighted_role_score(row: pd.Series, weights: dict[str, float]) -> int:
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
# Compute percentiles from raw metrics
# =========================
def metrics_used_by_roles() -> set[str]:
    rolesets = [CB_ROLES, FB_ROLES, CM_ROLES, ATT_ROLES, CF_ROLES, GK_ROLES]
    s = set()
    for rs in rolesets:
        for _, wmap in rs.items():
            s |= set(wmap.keys())
    return s

def add_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    used = metrics_used_by_roles()
    out = df.copy()

    # ensure numeric columns exist for used metrics
    for m in used:
        if m in out.columns:
            out[m] = pd.to_numeric(out[m], errors="coerce")

    # compute within PosGroup (fairer)
    for m in used:
        if m not in out.columns:
            continue

        # rank pct per position group
        pct = out.groupby("PosGroup")[m].transform(lambda s: s.rank(pct=True) * 100)

        # invert where lower is better
        if m in LOWER_BETTER:
            pct = 100 - pct

        out[f"{m} Percentile"] = pct.fillna(0)

    return out


# =========================
# STREAMLIT SETUP
# =========================
st.set_page_config(page_title="Club View", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
.stApp { background:#0e0e0f; color:#f2f2f2; }
.block-container { padding-top:1.3rem; padding-bottom:2rem; max-width:1150px; }
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

# Required columns
if "Team" not in df_all.columns or "Player" not in df_all.columns:
    st.error("CSV must include at least 'Team' and 'Player'.")
    st.stop()

# Position group
df_all["Position"] = df_all.get("Position", "").astype(str)
df_all["PosGroup"] = df_all["Position"].apply(pos_group)

# Add percentile columns FROM RAW METRICS
df_all = add_percentiles(df_all)

# Filter team
df = df_all[df_all["Team"].astype(str).str.strip() == TEAM_NAME].copy()
if df.empty:
    st.info(f"No players found for Team = '{TEAM_NAME}'.")
    st.stop()

# Minutes filter + sort
mins_col = detect_minutes_col(df)
df[mins_col] = pd.to_numeric(df[mins_col], errors="coerce").fillna(0)
df = df[df[mins_col] >= MIN_MINUTES].copy()
df = df.sort_values(mins_col, ascending=False).reset_index(drop=True)

if df.empty:
    st.info(f"No players for {TEAM_NAME} with {mins_col} ≥ {MIN_MINUTES}.")
    st.stop()

# Role scores
df["RoleScores"] = df.apply(compute_role_scores_for_row, axis=1)

# =========================
# HEADER (components.html)
# =========================
crest_uri = img_to_data_uri(CREST_PATH)
flag_uri = img_to_data_uri(FLAG_PATH)

header_html = textwrap.dedent(f"""
<div style="background:#1c1c1d;border:1px solid #2a2a2b;border-radius:20px;padding:24px;">
  <div style="display:grid;grid-template-columns:260px 1fr;gap:26px;align-items:start;">
    <div style="display:flex;flex-direction:column;gap:14px;">
      <div style="width:260px;height:220px;background:#121213;border:1px solid #2a2a2b;border-radius:20px;
                  display:flex;align-items:center;justify-content:center;overflow:hidden;">
        {f"<img src='{crest_uri}' style='width:200px;height:200px;object-fit:contain;' />" if crest_uri else ""}
      </div>
      <div style="display:flex;align-items:center;gap:12px;padding-left:6px;">
        {f"<img src='{flag_uri}' style='width:56px;height:40px;object-fit:cover;border-radius:6px;' />" if flag_uri else ""}
        <div style="font-size:24px;font-weight:700;color:#d2d2d4;line-height:1;">{LEAGUE_TEXT}</div>
      </div>
    </div>

    <div>
      <div style="font-size:52px;font-weight:850;line-height:1.05;color:#f2f2f2;">{TEAM_NAME}</div>

      <div style="display:flex;flex-direction:column;gap:12px;margin-top:10px;">
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <div style="width:56px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;
                      font-size:24px;font-weight:900;color:#111;border:1px solid rgba(0,0,0,.35);
                      background:{_pro_rating_color(OVERALL)};">{OVERALL}</div>
          <div style="font-size:30px;font-weight:700;color:#9ea0a6;">Overall</div>
        </div>

        <div style="display:flex;gap:26px;flex-wrap:wrap;align-items:center;">
          <div style="display:flex;align-items:center;gap:12px;">
            <div style="width:56px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;
                        font-size:24px;font-weight:900;color:#111;border:1px solid rgba(0,0,0,.35);
                        background:{_pro_rating_color(ATT_HDR)};">{ATT_HDR}</div>
            <div style="font-size:30px;font-weight:700;color:#9ea0a6;">ATT</div>
          </div>
          <div style="display:flex;align-items:center;gap:12px;">
            <div style="width:56px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;
                        font-size:24px;font-weight:900;color:#111;border:1px solid rgba(0,0,0,.35);
                        background:{_pro_rating_color(MID_HDR)};">{MID_HDR}</div>
            <div style="font-size:30px;font-weight:700;color:#9ea0a6;">MID</div>
          </div>
          <div style="display:flex;align-items:center;gap:12px;">
            <div style="width:56px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;
                        font-size:24px;font-weight:900;color:#111;border:1px solid rgba(0,0,0,.35);
                        background:{_pro_rating_color(DEF_HDR)};">{DEF_HDR}</div>
            <div style="font-size:30px;font-weight:700;color:#9ea0a6;">DEF</div>
          </div>
        </div>

        <div style="margin-top:8px;display:flex;flex-direction:column;gap:6px;font-size:16px;color:#b0b0b3;">
          <div><b>Average Age:</b> {AVG_AGE:.2f}</div>
          <div><b>League Position:</b> {LEAGUE_POSITION}</div>
        </div>
      </div>
    </div>
  </div>
</div>
""").strip()

components.html(header_html, height=350)

# =========================
# PERFORMANCE
# =========================
st.markdown("""
<style>
.section-title{
  font-size:40px;font-weight:900;letter-spacing:1px;
  margin-top:26px;margin-bottom:12px;color:#f2f2f2;
}
</style>
""", unsafe_allow_html=True)
st.markdown('<div class="section-title">PERFORMANCE</div>', unsafe_allow_html=True)

if PERFORMANCE_IMAGE_PATH and os.path.exists(PERFORMANCE_IMAGE_PATH):
    st.image(PERFORMANCE_IMAGE_PATH, use_container_width=True)
else:
    st.warning(f"Performance image not found: {PERFORMANCE_IMAGE_PATH}")

# =========================
# CARD CSS (once)
# =========================
st.markdown("""
<style>
.pro-wrap{ display:flex; justify-content:center; }
.pro-card{
  position:relative; width:min(720px,98%); display:grid; grid-template-columns:96px 1fr 64px;
  gap:12px; align-items:start;
  background:#141823; border:1px solid rgba(255,255,255,.06); border-radius:20px;
  padding:16px; margin-bottom:12px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.03), 0 6px 24px rgba(0,0,0,.35);
}
.pro-avatar{ width:96px; height:96px; border-radius:12px; border:1px solid #2a3145; overflow:hidden; background:#0b0d12; }
.pro-avatar img{ width:100%; height:100%; object-fit:cover; }

.flagchip img{ width:26px; height:18px; border-radius:2px; display:block; }
.chip{ color:#a6a6a6; font-size:15px; line-height:18px; opacity:.92; }
.row{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:2px 0; }
.leftrow1{ margin-top:6px; } .leftrow-foot{ margin-top:2px; } .leftrow-contract{ margin-top:6px; }

.pill{ padding:2px 6px; min-width:36px; border-radius:6px; font-weight:900; font-size:18px; line-height:1; color:#0b0d12; text-align:center; }
.name{ font-weight:950; font-size:22px; color:#e8ecff; margin-bottom:6px; letter-spacing:.2px; line-height:1.15; }
.postext{ font-weight:800; font-size:14.5px; letter-spacing:.2px; margin-right:10px; }
.rank{ position:absolute; top:10px; right:14px; color:#b7bfe1; font-weight:900; font-size:18px; }
.teamline{ color:#dbe3ff; font-size:14px; font-weight:700; margin-top:6px; letter-spacing:.05px; opacity:.95; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
</style>
""", unsafe_allow_html=True)

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
# SQUAD
# =========================
st.markdown('<div class="section-title" style="margin-top:30px;">SQUAD</div>', unsafe_allow_html=True)

for i, row in df.iterrows():
    player = str(row.get("Player","—"))
    league = str(row.get("League",""))
    pos = str(row.get("Position",""))
    birth = str(row.get("Birth country","")) if "Birth country" in df.columns else ""
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
    pos_html = _positions_html(pos)

    # IMPORTANT: components.html so HTML can’t be printed as text
    card_html = textwrap.dedent(f"""
    <div class='pro-wrap'>
      <div class='pro-card'>
        <div>
          <div class='pro-avatar'>
            <img src="{DEFAULT_AVATAR}" alt="{player}" />
          </div>
          <div class='row leftrow1'>{flag}<span class='chip'>{age_txt}</span><span class='chip'>{mins} mins</span></div>
          <div class='row leftrow-foot'><span class='chip'>{foot}</span></div>
          <div class='row leftrow-contract'><span class='chip'>{contract_txt}</span></div>
        </div>

        <div>
          <div class='name'>{player}</div>
          {pills_html}
          <div class='row' style='margin-top:10px;'>{pos_html}</div>
          <div class='teamline'>{TEAM_NAME} · {league}</div>
        </div>

        <div class='rank'>#{_fmt2(i+1)}</div>
      </div>
    </div>
    """).strip()

    components.html(card_html, height=210)










