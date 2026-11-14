#!/usr/bin/env python3
"""Rappel du midi : notification push envoyée directement à l'appli
(Web Push) les jours de match des Spurs. Ne révèle jamais de résultat (anti-spoiler).

GitHub retarde souvent les tâches planifiées de plusieurs heures : le script est donc
lancé plusieurs fois par jour (et peut l'être par un service externe à 12h45 pile).
Il envoie au premier passage après 12h30 (heure de Paris) et une seule fois par match
(mémorisé dans cache/notify_sent.json).

Abonnements : fichiers push/*.json (créés depuis l'appli).
Clé privée : secret GitHub VAPID_PRIVATE_KEY.
--test : envoie une notification de test, quelle que soit l'heure.
"""
import glob, json, os, sys, datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARIS, ET = ZoneInfo("Europe/Paris"), ZoneInfo("America/New_York")
JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

def send_all(title, body):
    from pywebpush import webpush, WebPushException
    key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if not key:
        print("Secret VAPID_PRIVATE_KEY absent : impossible d'envoyer."); sys.exit(1)
    subs = sorted(glob.glob(os.path.join(ROOT, "push", "*.json")))
    if not subs:
        print("Aucun téléphone abonné (dossier push/ vide)."); return 0
    ok = 0
    for f in subs:
        try:
            sub = json.load(open(f, encoding="utf-8"))
            webpush(subscription_info=sub, data=json.dumps({"title": title, "body": body}, ensure_ascii=False),
                    vapid_private_key=key, vapid_claims={"sub": "mailto:spurs-bot@users.noreply.github.com"}, ttl=6 * 3600)
            ok += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", "?")
            print(f"{os.path.basename(f)} : échec ({code})" + (" — abonnement expiré, réactive le rappel dans l'appli" if code in (404, 410) else ""))
        except Exception as e:
            print(f"{os.path.basename(f)} : erreur {e}")
    print(f"Notification envoyée à {ok}/{len(subs)} téléphone(s).")
    return ok

SENT = os.path.join(ROOT, "cache", "notify_sent.json")

def main():
    test = "--test" in sys.argv
    now = datetime.datetime.now(datetime.timezone.utc)
    loc = now.astimezone(PARIS); mins = loc.hour * 60 + loc.minute
    data = json.load(open(os.path.join(ROOT, "data.json"), encoding="utf-8"))
    nxt = None
    for g in sorted(data.get("games", []), key=lambda g: g["start"]):
        start = datetime.datetime.fromisoformat(g["start"].replace("Z", "+00:00"))
        if g.get("status") != "final" and start > now:
            nxt = (g, start); break
    if not nxt:
        if test: send_all("Spurs Courtside", "Test réussi : les rappels fonctionnent. Aucun match à venir.")
        else: print("Aucun match à venir.")
        return
    g, start = nxt
    p, e = start.astimezone(PARIS), start.astimezone(ET)
    sep = "vs" if g["home"] else "@"
    us_h = e.strftime("%I:%M %p").lstrip("0")
    cup = " · NBA Cup" if g.get("cup") else ""
    body = (f"Spurs {sep} {g['oppName']}{cup} — {p.hour}h{p.minute:02d} (heure FR) · {us_h} ET "
            f"({JOURS[e.weekday()]} {e.day} {MOIS[e.month-1]} aux USA)")
    if test:
        send_all("Spurs Courtside", "Test réussi : les rappels fonctionnent. Prochain match : " + body); return
    if mins < 12 * 60 + 30:
        print(f"Il est {loc:%H:%M} à Paris : le rappel part à partir de 12h30."); return
    left = start - now
    if left > datetime.timedelta(hours=18):
        print(f"Pas de match cette nuit (prochain : {body})."); return
    if left < datetime.timedelta(minutes=20):
        print("Le match commence dans moins de 20 min : trop tard pour le rappel."); return
    try: sent = json.load(open(SENT, encoding="utf-8"))
    except Exception: sent = {}
    if sent.get("game") == g["id"]:
        print(f"Rappel déjà envoyé pour ce match ({sent.get('at')})."); return
    if not send_all("🏀 Match cette nuit" if p.hour < 12 or p.date() > loc.date() else "🏀 Match ce soir", body):
        return   # rien n'est parti : on retentera au prochain passage
    os.makedirs(os.path.dirname(SENT), exist_ok=True)
    json.dump({"game": g["id"], "at": f"{loc:%Y-%m-%d %H:%M}"}, open(SENT, "w", encoding="utf-8"))

if __name__ == "__main__":
    main()
