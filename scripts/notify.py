#!/usr/bin/env python3
"""Rappel de 12h45 : notification push envoyée directement à l'appli
(Web Push) s'il y a un match des Spurs dans les 24 h.
Ne révèle jamais de résultat (anti-spoiler).

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
        print("Aucun téléphone abonné (dossier push/ vide)."); return
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

def main():
    test = "--test" in sys.argv
    now = datetime.datetime.now(datetime.timezone.utc)
    loc = now.astimezone(PARIS); mins = loc.hour * 60 + loc.minute
    if not test and not (12 * 60 + 30 <= mins < 13 * 60 + 30):   # fenêtre 12h30-13h29 (GitHub peut retarder un peu)
        print(f"Il est {loc:%H:%M} à Paris : hors de la fenêtre du rappel."); return
    data = json.load(open(os.path.join(ROOT, "data.json"), encoding="utf-8"))
    nxt = None
    for g in sorted(data.get("games", []), key=lambda g: g["start"]):
        start = datetime.datetime.fromisoformat(g["start"].replace("Z", "+00:00"))
        if g.get("status") != "final" and start > now:
            nxt = (g, start); break
    if not nxt:
        if test: send_all("Spurs Courtside", "Test réussi : les rappels fonctionnent. Aucun match à venir.")
        return
    g, start = nxt
    p, e = start.astimezone(PARIS), start.astimezone(ET)
    sep = "vs" if g["home"] else "@"
    us_h = e.strftime("%I:%M %p").lstrip("0")
    body = (f"Spurs {sep} {g['oppName']} — {p.hour}h{p.minute:02d} (heure FR) · {us_h} ET "
            f"({JOURS[e.weekday()]} {e.day} {MOIS[e.month-1]} aux USA)")
    if start - now < datetime.timedelta(hours=24):
        send_all("🏀 Match cette nuit", body)
    elif test:
        send_all("Spurs Courtside", "Test réussi : les rappels fonctionnent. Prochain match : " + body)
    else:
        print("Pas de match dans les 24 h.")

if __name__ == "__main__":
    main()
