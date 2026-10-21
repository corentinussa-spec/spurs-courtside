#!/usr/bin/env python3
"""Mise à jour autonome de data.json pour Spurs Courtside.

Source : API publique d'ESPN (sans clé). Tourne dans GitHub Actions.
Chaque section est indépendante : si une source échoue, la section
précédente de data.json est conservée.
"""
import json, os, sys, time, datetime, urllib.request, urllib.error
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.json")
CACHE = os.path.join(ROOT, "cache")
RECORDS = os.path.join(ROOT, "scripts", "records_nba.json")
SEASON = int(os.environ.get("SEASON", "2027"))      # saison 2026-27 = 2027 chez ESPN
SEASON_LABEL = f"{SEASON-1}-{str(SEASON)[2:]}"
ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
WEB = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"

# Abréviations ESPN -> abréviations de l'appli
ESPN2US = {"SA": "SAS", "GS": "GSW", "NO": "NOP", "NY": "NYK", "UTAH": "UTA", "WSH": "WAS",
           "PHO": "PHX", "BRK": "BKN", "CHO": "CHA"}
US2ESPN = {"SAS": "sa", "GSW": "gs", "NOP": "no", "NYK": "ny", "UTA": "utah", "WAS": "wsh"}
def us(a): a = (a or "").upper(); return ESPN2US.get(a, a)
def espn(a): return US2ESPN.get(a, a.lower())

NAMES = {"ATL":"Atlanta Hawks","BOS":"Boston Celtics","BKN":"Brooklyn Nets","CHA":"Charlotte Hornets","CHI":"Chicago Bulls","CLE":"Cleveland Cavaliers","DAL":"Dallas Mavericks","DEN":"Denver Nuggets","DET":"Detroit Pistons","GSW":"Golden State Warriors","HOU":"Houston Rockets","IND":"Indiana Pacers","LAC":"LA Clippers","LAL":"Los Angeles Lakers","MEM":"Memphis Grizzlies","MIA":"Miami Heat","MIL":"Milwaukee Bucks","MIN":"Minnesota Timberwolves","NOP":"New Orleans Pelicans","NYK":"New York Knicks","OKC":"Oklahoma City Thunder","ORL":"Orlando Magic","PHI":"Philadelphia 76ers","PHX":"Phoenix Suns","POR":"Portland Trail Blazers","SAC":"Sacramento Kings","SAS":"San Antonio Spurs","TOR":"Toronto Raptors","UTA":"Utah Jazz","WAS":"Washington Wizards"}

def log(*a): print(*a, flush=True)

def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 spurs-courtside", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            log(f"  HTTP {e.code} sur {url}")
        except Exception as e:
            log(f"  erreur {e} sur {url}")
        time.sleep(2 * (i + 1))
    return None

def rjson(p, default=None):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def wjson(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

def num(v, default=0):
    try: return float(str(v).replace("+", ""))
    except Exception: return default

def made_att(v):
    try: m, a = str(v).split("-"); return int(m), int(a)
    except Exception: return 0, 0

def iso(dt): return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_date(s):
    s = s.replace("Z", "+00:00")
    if len(s) == 22 and s[16] == "+": s = s[:16] + ":00" + s[16:]   # 2026-10-21T01:30+00:00
    return datetime.datetime.fromisoformat(s)

# ---------------------------------------------------------------- calendrier
def schedule(team):
    out = {}
    for st in (2, 3):     # saison régulière (+ phase finale si elle existe)
        j = get(f"{SITE}/teams/{espn(team)}/schedule?season={SEASON}&seasontype={st}")
        for ev in (j or {}).get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            cs = comp.get("competitors", [])
            me = next((c for c in cs if us(c.get("team", {}).get("abbreviation")) == team), None)
            op = next((c for c in cs if c is not me), None)
            if not me or not op: continue
            start = parse_date(ev["date"])
            done = comp.get("status", ev.get("status", {})).get("type", {}).get("completed", False)
            out[ev["id"]] = {"espnId": ev["id"], "start": iso(start), "opp": us(op["team"]["abbreviation"]),
                             "home": me.get("homeAway") == "home", "final": bool(done), "playoffs": st == 3}
    return out

# ---------------------------------------------------------------- feuilles de match
STAT_KEYS = {"MIN": "min", "PTS": "pts", "REB": "reb", "AST": "ast", "STL": "stl", "BLK": "blk",
             "TO": "tov", "+/-": "pm", "OREB": "oreb", "DREB": "dreb", "PF": "pf"}

def box(event_id):
    """Feuille de match analysée, mise en cache (un match terminé ne change plus)."""
    p = os.path.join(CACHE, "games", f"{event_id}.json")
    c = rjson(p)
    if c: return c
    j = get(f"{SITE}/summary?event={event_id}")
    if not j: return None
    comp = (j.get("header", {}).get("competitions") or [{}])[0]
    if not comp.get("status", {}).get("type", {}).get("completed"): return None
    res = {"teams": {}, "start": iso(parse_date(comp.get("date", "2000-01-01T00:00Z")))}
    for c in comp.get("competitors", []):
        a = us(c["team"]["abbreviation"])
        lines = [int(num(l.get("displayValue", l.get("value", 0)))) for l in c.get("linescores", [])]
        res["teams"][a] = {"score": int(num(c.get("score"))), "home": c.get("homeAway") == "home",
                           "periods": lines, "players": [], "extra": {}}
    for t in j.get("boxscore", {}).get("teams", []):
        a = us(t["team"]["abbreviation"])
        if a not in res["teams"]: continue
        for s in t.get("statistics", []):
            n = s.get("name", "")
            if n in ("pointsInPaint", "fastBreakPoints", "benchPoints"):
                res["teams"][a]["extra"][n] = int(num(s.get("displayValue")))
    for t in j.get("boxscore", {}).get("players", []):
        a = us(t["team"]["abbreviation"])
        if a not in res["teams"]: continue
        for grp in t.get("statistics", []):
            names = grp.get("names") or grp.get("labels") or []
            for ath in grp.get("athletes", []):
                if ath.get("didNotPlay") or not ath.get("stats"): continue
                st = dict(zip(names, ath["stats"]))
                info = ath.get("athlete", {})
                p_ = {"id": str(info.get("id", "")), "name": info.get("displayName", "?"),
                      "pos": (info.get("position") or {}).get("abbreviation", ""), "starter": bool(ath.get("starter"))}
                for k, v in STAT_KEYS.items(): p_[v] = int(num(st.get(k, 0)))
                p_["fgm"], p_["fga"] = made_att(st.get("FG", "0-0"))
                p_["tpm"], p_["tpa"] = made_att(st.get("3PT", "0-0"))
                p_["ftm"], p_["fta"] = made_att(st.get("FT", "0-0"))
                res["teams"][a]["players"].append(p_)
    if len(res["teams"]) != 2: return None
    wjson(p, res)
    return res

def team_totals(t):
    P = t["players"]; s = lambda k: sum(p[k] for p in P)
    bench = t["extra"].get("benchPoints", sum(p["pts"] for p in P if not p["starter"]))
    return {"pts": t["score"], "reb": s("reb"), "ast": s("ast"), "stl": s("stl"), "blk": s("blk"), "tov": s("tov"),
            "fgm": s("fgm"), "fga": s("fga"), "tpm": s("tpm"), "tpa": s("tpa"), "ftm": s("ftm"), "fta": s("fta"),
            "paint": t["extra"].get("pointsInPaint", 0), "fastbreak": t["extra"].get("fastBreakPoints", 0), "bench": bench}

def box_rows(t):
    keys = ["name", "pos", "pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "pm"]
    return sorted([{k: p[k] for k in keys} for p in t["players"]], key=lambda x: -x["pts"])

# ---------------------------------------------------------------- moyennes saison
def season_stats(team, boxes):
    """boxes : feuilles de match terminées de l'équipe, saison régulière."""
    if not boxes: return None, []
    g = len(boxes); tot = {}; opp_pts = 0; pl = {}
    for b in boxes:
        me = b["teams"][team]; op = next(v for k, v in b["teams"].items() if k != team)
        tt = team_totals(me); opp_pts += op["score"]
        for k, v in tt.items(): tot[k] = tot.get(k, 0) + v
        for p in me["players"]:
            if not (p["min"] or p["pts"] or p["reb"] or p["ast"] or p["fga"] or p["fta"]): continue
            r = pl.setdefault(p["id"] or p["name"], {"name": p["name"], "pos": p["pos"], "gp": 0})
            r["gp"] += 1
            for k in ["pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "min"]:
                r[k] = r.get(k, 0) + p[k]
    pct = lambda m, a: round(100 * m / a, 1) if a else None
    stats = {"gp": g, "ppg": round(tot["pts"] / g, 1), "oppg": round(opp_pts / g, 1), "rpg": round(tot["reb"] / g, 1),
             "apg": round(tot["ast"] / g, 1), "spg": round(tot["stl"] / g, 1), "bpg": round(tot["blk"] / g, 1),
             "tov": round(tot["tov"] / g, 1), "fg": pct(tot["fgm"], tot["fga"]), "tp": pct(tot["tpm"], tot["tpa"]),
             "ft": pct(tot["ftm"], tot["fta"])}
    players = []
    for r in pl.values():
        n = r["gp"]; row = {"name": r["name"], "pos": r["pos"], "gp": n}
        for k in ["pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "min"]:
            row[k] = round(r[k] / n, 2)
        players.append(row)
    players.sort(key=lambda x: -x["pts"])
    return stats, players

# ---------------------------------------------------------------- records
REC_STATS = [("pts", "PTS", "points"), ("reb", "REB", "rebonds"), ("ast", "AST", "passes décisives"),
             ("stl", "STL", "interceptions"), ("blk", "BLK", "contres"), ("tpm", "3PT", "paniers à 3 pts")]
UNIT = {"pts": "pts", "reb": "reb", "ast": "passes", "stl": "int.", "blk": "contres", "tpm": "tirs à 3 pts"}

def career_before(athlete_id):
    """Meilleures marques en carrière AVANT la saison en cours (saison régulière), en cache."""
    p = os.path.join(CACHE, "careers", f"{athlete_id}.json")
    c = rjson(p)
    if c and c.get("through") == SEASON - 1: return c["best"]
    best = {k: 0 for k, _, _ in REC_STATS}; found = False; empty = 0; yr = SEASON - 1
    while yr >= 1990 and empty < (2 if found else 4):
        j = get(f"{WEB}/athletes/{athlete_id}/gamelog?season={yr}")
        labels = (j or {}).get("labels") or (j or {}).get("names") or []
        events = []
        for stp in (j or {}).get("seasonTypes", []):
            if "regular" not in stp.get("displayName", "").lower(): continue
            for cat in stp.get("categories", []): events += cat.get("events", [])
        if not events: empty += 1; yr -= 1; continue
        found = True; empty = 0
        for e in events:
            st = dict(zip(labels, e.get("stats", [])))
            for k, lab, _ in REC_STATS:
                v = made_att(st.get(lab, "0-0"))[0] if lab == "3PT" else int(num(st.get(lab, 0)))
                best[k] = max(best[k], v)
        yr -= 1
    if j is None and not found: return None          # source injoignable : on ne conclut rien
    wjson(p, {"through": SEASON - 1, "best": best})
    return best

def find_records(game_box, season_boxes_before, games_played_before):
    """Records des Spurs sur ce match : NBA, carrière, saison (joueur et équipe)."""
    nba = rjson(RECORDS, {})
    me = game_box["teams"]["SAS"]; out = []
    for p in me["players"]:
        for k, lab, label in REC_STATS:
            v = p[k]
            if v <= 0: continue
            r = nba.get("player", {}).get(k)
            if r and v >= r["value"]:
                out.append({"who": p["name"], "value": f"{v} {UNIT[k]}", "kind": "nba",
                            "label": ("Nouveau record NBA" if v > r["value"] else "Égale le record NBA") + f" de {label} en un match (ancien : {r['value']}, {r['holder']})"})
                continue
            prev_season = max([q[k] for b in season_boxes_before for q in b["teams"]["SAS"]["players"] if (q["id"] or q["name"]) == (p["id"] or p["name"])] or [0])
            car = career_before(p["id"]) if p["id"] else None
            if car is not None:
                prev = max(car[k], prev_season)
                notable = v >= (10 if k in ("pts", "reb", "ast") else 4)
                if prev > 0 and v > prev and notable:
                    out.append({"who": p["name"], "value": f"{v} {UNIT[k]}", "kind": "career",
                                "label": f"Record en carrière de {label} (ancien : {prev})"})
                    continue
            if games_played_before >= 4 and v > prev_season and v >= 8:
                best_team = max([q[k] for b in season_boxes_before for q in b["teams"]["SAS"]["players"]] or [0])
                if v > best_team:
                    out.append({"who": p["name"], "value": f"{v} {UNIT[k]}", "kind": "season",
                                "label": f"Meilleure marque d'un Spur cette saison en {label} (ancienne : {best_team})"})
    tt = team_totals(me)
    r = nba.get("team", {}).get("pts")
    if r and tt["pts"] >= r["value"]:
        out.append({"who": "San Antonio Spurs", "value": f"{tt['pts']} pts", "kind": "nba",
                    "label": ("Nouveau record NBA" if tt["pts"] > r["value"] else "Égale le record NBA") + f" de points en un match (ancien : {r['value']}, {r['holder']})"})
    elif games_played_before >= 4:
        for k, label in (("pts", "points"), ("tpm", "paniers à 3 pts"), ("ast", "passes décisives"), ("reb", "rebonds"), ("blk", "contres")):
            prev = max([team_totals(b["teams"]["SAS"])[k] for b in season_boxes_before] or [0])
            if tt[k] > prev:
                out.append({"who": "San Antonio Spurs", "value": f"{tt[k]} {UNIT.get(k, k)}", "kind": "team",
                            "label": f"Record d'équipe de la saison en {label} (ancien : {prev})"})
    return out

# ---------------------------------------------------------------- classement
def standings():
    j = get("https://site.api.espn.com/apis/v2/sports/basketball/nba/standings")
    if not j: return None
    res = {}
    for conf in j.get("children", []):
        key = "east" if "east" in (conf.get("name", "") + conf.get("abbreviation", "")).lower() else "west"
        rows = []
        for e in conf.get("standings", {}).get("entries", []):
            st = {s.get("name"): s.get("value") for s in e.get("stats", [])}
            w, l = int(st.get("wins") or 0), int(st.get("losses") or 0)
            rows.append({"abbr": us(e["team"]["abbreviation"]), "w": w, "l": l, "seed": st.get("playoffSeed") or 99,
                         "pct": w / (w + l) if w + l else 0})
        rows.sort(key=lambda r: (r["seed"] if r["w"] + r["l"] else 99, -r["pct"], r["abbr"]))
        res[key] = [{"rank": i + 1, "abbr": r["abbr"], "w": r["w"], "l": r["l"]} for i, r in enumerate(rows)]
    if len(res.get("east", [])) < 10 or len(res.get("west", [])) < 10: return None
    res["asOf"] = datetime.date.today().isoformat()
    return res

# ---------------------------------------------------------------- blessures
STATUS = {"out": "Absent", "day-to-day": "Jour après jour", "questionable": "Incertain", "doubtful": "Douteux",
          "probable": "Probable", "suspension": "Suspendu", "out for season": "Absent pour la saison", "game time decision": "Incertain (décision avant le match)"}
BODY = {"knee": "Genou", "ankle": "Cheville", "calf": "Mollet", "hamstring": "Ischio-jambiers", "hip": "Hanche", "back": "Dos",
        "foot": "Pied", "toe": "Orteil", "groin": "Aine", "shoulder": "Épaule", "wrist": "Poignet", "hand": "Main",
        "finger": "Doigt", "thumb": "Pouce", "elbow": "Coude", "achilles": "Tendon d'Achille", "quadriceps": "Quadriceps",
        "quad": "Quadriceps", "thigh": "Cuisse", "shin": "Tibia", "lower leg": "Jambe", "leg": "Jambe", "neck": "Cou",
        "head": "Tête", "concussion": "Commotion cérébrale", "face": "Visage", "nose": "Nez", "eye": "Œil", "rib": "Côtes",
        "ribs": "Côtes", "chest": "Poitrine", "abdomen": "Abdomen", "oblique": "Oblique", "illness": "Maladie",
        "rest": "Repos", "personal": "Raisons personnelles", "not injury related": "Hors blessure", "heel": "Talon",
        "pelvis": "Bassin", "forearm": "Avant-bras", "jaw": "Mâchoire", "knee-acl": "Genou (ligament croisé)", "acl": "Ligament croisé"}
DETAIL = {"sprain": "entorse", "strain": "élongation", "soreness": "douleur", "fracture": "fracture", "surgery": "opération",
          "contusion": "contusion", "tear": "déchirure", "bruise": "contusion", "tendinitis": "tendinite", "tendinopathy": "tendinopathie",
          "inflammation": "inflammation", "dislocation": "luxation", "torn ligament": "rupture ligamentaire", "spasms": "spasmes",
          "stress reaction": "fracture de fatigue", "impingement": "conflit articulaire", "tightness": "contracture", "bone bruise": "œdème osseux",
          "injury recovery": "rééducation", "management": "gestion de la charge", "laceration": "coupure", "discomfort": "gêne"}
SIDE = {"left": "gauche", "right": "droit", "bilateral": "des deux côtés"}
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

def tr(d, s):
    if not s: return ""
    return d.get(str(s).strip().lower(), str(s).strip())

def fr_date(s):
    try:
        d = datetime.date.fromisoformat(str(s)[:10])
        return f"{'1er' if d.day == 1 else d.day} {MOIS[d.month-1]}"
    except Exception: return ""

def injuries(teams):
    j = get(f"{SITE}/injuries")
    if not j: return None
    out = {t: [] for t in teams}
    for grp in j.get("injuries", []):
        a = None
        for cand in (grp.get("abbreviation"), (grp.get("team") or {}).get("abbreviation")):
            if cand: a = us(cand)
        if not a:
            dn = grp.get("displayName", "")
            a = next((k for k, v in NAMES.items() if v == dn or (dn and v.endswith(dn.split()[-1]))), None)
        if a not in out: continue
        for inj in grp.get("injuries", []):
            ath = inj.get("athlete", {}); det = inj.get("details") or {}
            part = tr(BODY, det.get("type") or (inj.get("type") or {}).get("description"))
            extra = [x for x in (tr(DETAIL, det.get("detail")), tr(SIDE, det.get("side"))) if x and x.lower() not in ("not specified", "")]
            injury = part + (f" ({', '.join(extra)})" if extra and part else ", ".join(extra))
            status = tr(STATUS, inj.get("status") or det.get("fantasyStatus", {}).get("description"))
            ret = fr_date(det.get("returnDate"))
            out[a].append({"player": ath.get("displayName", "?"), "pos": (ath.get("position") or {}).get("abbreviation", ""),
                           "injury": injury or "Non précisée", "status": status or "Incertain",
                           "duration": f"Retour estimé : {ret}" if ret else ("Toute la saison" if "season" in str(inj.get("status", "")).lower() else "Non communiquée"),
                           "updated": str(inj.get("date", ""))[:10]})
    return {"teams": out, "asOf": datetime.date.today().isoformat()}


# ---------------------------------------------------------------- effectif
def roster(team="SAS"):
    j = get(f"{SITE}/teams/{espn(team)}/roster")
    if not j: return None
    raw = j.get("athletes", [])
    if raw and isinstance(raw[0], dict) and "items" in raw[0]:
        raw = [a for grp in raw for a in grp.get("items", [])]
    out = []
    for a in raw:
        aid = str(a.get("id", ""))
        if not aid: continue
        pos = a.get("position") or {}
        status = (a.get("status") or {}).get("type") or ""
        out.append({"id": aid, "name": a.get("displayName") or a.get("fullName") or "?",
                    "jersey": str(a.get("jersey") or ""), "pos": pos.get("abbreviation", ""),
                    "heightIn": num(a.get("height"), None), "weightLb": num(a.get("weight"), None),
                    "age": a.get("age"), "exp": (a.get("experience") or {}).get("years"),
                    "photo": (a.get("headshot") or {}).get("href") or f"https://a.espncdn.com/i/headshots/nba/players/full/{aid}.png",
                    "active": status != "inactive"})
    return out or None

def player_games(boxes, gids, games_by_id):
    """Ligne de stats de chaque joueur des Spurs pour chaque match joué (saison régulière)."""
    keys = ["min", "pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "pm"]
    out = {}
    for b, gid in zip(boxes, gids):
        g = games_by_id.get(gid, {})
        for p in b["teams"]["SAS"]["players"]:
            pid = p["id"] or p["name"]
            row = {"gid": gid, "opp": g.get("opp"), "home": g.get("home"), "start": g.get("start")}
            for k in keys: row[k] = p[k]
            out.setdefault(pid, []).append(row)
    return out


# ---------------------------------------------------------------- actualités
import hashlib, urllib.parse
TR_CACHE = os.path.join(CACHE, "translations.json")
_tr = None
def translate(text):
    """Traduction anglais -> français (service gratuit), mise en cache. Échec : texte d'origine."""
    global _tr
    if not text: return text
    if _tr is None: _tr = rjson(TR_CACHE, {}) or {}
    k = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    if k in _tr: return _tr[k]
    url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=fr&dt=t&q=" + urllib.parse.quote(text)
    j = get(url, tries=2)
    try:
        out = "".join(seg[0] for seg in j[0] if seg and seg[0])
    except Exception:
        return text
    if out:
        _tr[k] = out
        wjson(TR_CACHE, _tr)
    return out or text

MOVE_WORDS = ("trade", "traded", "acquire", "sign ", "signs", "signed", "waive", "waived", "release", "extension", "contract", "two-way", "10-day", "deal", "claim")
TALK_WORDS = ("press conference", "media day", "postgame", "presser", "practice", "coach", "mitch johnson", "shootaround", "interview")
def espn_news():
    j = get(f"{SITE}/news?team=sa&limit=40")
    if not j: return None
    out = []
    for a in j.get("articles", []):
        aid = str(a.get("id") or a.get("dataSourceIdentifier") or a.get("headline", ""))[:64]
        head = a.get("headline") or ""; desc = a.get("description") or ""
        if not head or not a.get("published"): continue
        cats = [c.get("description", "") for c in a.get("categories", []) if c.get("type") == "team"]
        if cats and "San Antonio Spurs" not in cats: continue
        low = (head + " " + desc).lower()
        kind = "effectif" if any(w in low for w in MOVE_WORDS) else ("conference" if any(w in low for w in TALK_WORDS) else "presse")
        out.append({"id": "espn-" + aid, "kind": kind, "time": iso(parse_date(a["published"])),
                    "title": translate(head), "text": translate(desc), "url": ((a.get("links") or {}).get("web") or {}).get("href", ""),
                    "source": "ESPN"})
    return out

def auto_events(old, new, now_iso, first_run):
    """Arrivées/départs de joueurs et changements de blessures, détectés entre deux mises à jour."""
    ev = []
    oro = {r["id"]: r for r in old.get("roster", [])}; nro = {r["id"]: r for r in new.get("roster", [])}
    changes = len(set(oro) ^ set(nro))
    if oro and nro and changes <= 4:        # au-delà : probablement une liste incomplète côté source, on ignore
        for i, r in nro.items():
            if i not in oro:
                ev.append({"id": f"in-{i}-{now_iso[:10]}", "kind": "effectif", "time": now_iso, "title": f"{r['name']} rejoint l'effectif",
                           "text": " · ".join(x for x in [f"n° {r['jersey']}" if r.get("jersey") else "", r.get("pos", "")] if x)})
        for i, r in oro.items():
            if i not in nro:
                ev.append({"id": f"out-{i}-{now_iso[:10]}", "kind": "effectif", "time": now_iso, "title": f"{r['name']} quitte l'effectif", "text": ""})
    oi = {p["player"]: p for p in ((old.get("injuries") or {}).get("teams") or {}).get("SAS", [])}
    ni = {p["player"]: p for p in ((new.get("injuries") or {}).get("teams") or {}).get("SAS", [])}
    if not (new.get("injuries") or {}).get("teams"): return ev
    for n, p in ni.items():
        o = oi.get(n)
        if first_run or not o or o.get("status") != p.get("status"):
            t = (p.get("updated") + "T12:00:00Z") if first_run and p.get("updated") else now_iso
            dur = p.get("duration", "")
            ev.append({"id": f"inj-{n}-{p.get('status')}-{t[:10]}", "kind": "blessure", "time": t,
                       "title": f"{n} : {p.get('status', '').lower()}" if p.get("status") else n,
                       "text": p.get("injury", "") + (f" · {dur[0].lower() + dur[1:]}" if dur and "communiqu" not in dur else ""),
                       "severity": "out" if "absent" in p.get("status", "").lower() else "q"})
    if not first_run:
        for n in oi:
            if n not in ni:
                ev.append({"id": f"back-{n}-{now_iso[:10]}", "kind": "blessure", "time": now_iso, "title": f"{n} est de retour",
                           "text": "N'apparaît plus sur le rapport des blessures", "severity": "ok"})
    return ev

# ---------------------------------------------------------------- assemblage
def main():
    data = rjson(DATA, {}) or {}
    old_games = {g["id"]: g for g in data.get("games", [])}
    now = datetime.datetime.now(UTC)

    sched = schedule("SAS")
    if not sched:
        log("Calendrier injoignable : données inchangées."); sys.exit(1)
    log(f"Calendrier : {len(sched)} matchs")

    games = []; sas_boxes = []; sas_gids = []
    for ev in sorted(sched.values(), key=lambda e: e["start"]):
        start = parse_date(ev["start"])
        gid = start.astimezone(ET).strftime("%Y%m%d") + "-" + ev["opp"]
        g = {"id": gid, "espnId": ev["espnId"], "start": ev["start"], "opp": ev["opp"], "oppName": NAMES.get(ev["opp"], ev["opp"]),
             "home": ev["home"], "status": "scheduled"}
        if ev["playoffs"]: g["playoffs"] = True
        if ev["final"]:
            b = box(ev["espnId"])
            if b and "SAS" in b["teams"]:
                me, op = b["teams"]["SAS"], b["teams"][ev["opp"]] if ev["opp"] in b["teams"] else next(v for k, v in b["teams"].items() if k != "SAS")
                before = list(sas_boxes)
                prev = old_games.get(gid, {})
                recs = prev.get("records") if prev.get("status") == "final" and prev.get("recordsV") == 2 else None
                if recs is None:
                    try: recs = find_records(b, before, len(before))
                    except Exception as e: log("  records :", e); recs = []
                n = max(len(me["periods"]), len(op["periods"]))
                g.update({"status": "final", "score": {"SAS": me["score"], "OPP": op["score"]},
                          "periods": [{"q": str(i + 1), "SAS": (me["periods"] + [0] * n)[i], "OPP": (op["periods"] + [0] * n)[i]} for i in range(n)],
                          "teamStats": {"SAS": team_totals(me), "OPP": team_totals(op)},
                          "box": {"SAS": box_rows(me), "OPP": box_rows(op)}, "records": recs, "recordsV": 2})
                if not ev["playoffs"]: sas_boxes.append(b); sas_gids.append(gid)
            elif gid in old_games:
                g = old_games[gid]
        games.append(g)
    data["games"] = games

    # équipes suivies : Spurs, 3 prochains adversaires, dernier adversaire
    upcoming = [g["opp"] for g in games if g["status"] != "final" and parse_date(g["start"]) > now - datetime.timedelta(hours=3)]
    played = [g["opp"] for g in games if g["status"] == "final"]
    follow = ["SAS"] + list(dict.fromkeys(upcoming[:3] + played[-1:]))
    teams = data.get("teams", {}); players = data.get("players", {})
    st = standings()
    if st: data["standings"] = st
    wl = {r["abbr"]: (r["w"], r["l"]) for c in ("east", "west") for r in (data.get("standings") or {}).get(c, [])}
    for t in follow:
        if t == "SAS": bx = sas_boxes
        else:
            sc = schedule(t); bx = []
            for ev in sc.values():
                if ev["final"] and not ev["playoffs"]:
                    b = box(ev["espnId"])
                    if b and t in b["teams"]: bx.append(b)
        s, pl = season_stats(t, bx)
        w, l = wl.get(t, (None, None))
        if w is None and t == "SAS":
            w = sum(1 for b in bx if b["teams"]["SAS"]["score"] > max(v["score"] for k, v in b["teams"].items() if k != "SAS")); l = len(bx) - w
        teams[t] = {"abbr": t, "name": NAMES.get(t, t), "w": w or 0, "l": l or 0, "stats": s}
        players[t] = {"abbr": t, "players": pl}
        log(f"Équipe {t} : {len(bx)} matchs analysés")
    data["teams"] = teams; data["players"] = players

    # effectif : fiches joueurs
    by_id = {g["id"]: g for g in games}
    data["playerGames"] = player_games(sas_boxes, sas_gids, by_id)
    ro = roster("SAS")
    if ro: data["roster"] = ro
    best = data.get("careerBest", {})
    for r in data.get("roster", []):
        try:
            c = career_before(r["id"])
            if c is not None: best[r["id"]] = c
        except Exception as e: log("  carrière", r["name"], e)
    data["careerBest"] = best
    log(f"Effectif : {len(data.get('roster', []))} joueurs, {len(data['playerGames'])} avec des matchs")

    inj = injuries(["SAS"] + upcoming[:2])
    if inj: data["injuries"] = inj

    # actualités
    prev = rjson(DATA, {}) or {}
    first = "news" not in prev
    items = {n["id"]: n for n in prev.get("news", [])}
    try:
        for n in auto_events(prev, data, iso(now), first): items.setdefault(n["id"], n)
    except Exception as e: log("  actus auto :", e)
    try:
        for n in (espn_news() or []): items[n["id"]] = n
    except Exception as e: log("  actus ESPN :", e)
    data["news"] = sorted(items.values(), key=lambda n: n["time"], reverse=True)[:80]
    log(f"Actualités : {len(data['news'])}")

    data["meta"] = {"updatedAt": iso(now), "season": SEASON_LABEL, "source": "ESPN", "note": "Mise à jour automatique (GitHub Actions)"}
    tmp = DATA + ".tmp"; wjson(tmp, data); json.load(open(tmp, encoding="utf-8")); os.replace(tmp, DATA)
    log("data.json écrit :", len(games), "matchs")

if __name__ == "__main__":
    main()
