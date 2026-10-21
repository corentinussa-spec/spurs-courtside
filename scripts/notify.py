#!/usr/bin/env python3
"""Rappel de midi : envoie une notification ntfy s'il y a un match des Spurs
dans les 24 h. Ne révèle jamais de résultat (anti-spoiler).

--test : envoie une notification de test, quelle que soit l'heure.
"""
import json, os, sys, datetime, urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOPIC = os.environ.get("NTFY_TOPIC", "spurs-courtside-11d649a9ae")
APP = "https://corentinussa-spec.github.io/spurs-courtside/"
PARIS, ET = ZoneInfo("Europe/Paris"), ZoneInfo("America/New_York")
JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

def send(title, body, tags="basketball"):
    req = urllib.request.Request(f"https://ntfy.sh/{TOPIC}", data=body.encode("utf-8"), method="POST",
                                 headers={"Title": title.encode("utf-8"), "Tags": tags, "Click": APP, "Priority": "default"})
    urllib.request.urlopen(req, timeout=20).read()

def main():
    test = "--test" in sys.argv
    now = datetime.datetime.now(datetime.timezone.utc)
    if not test and now.astimezone(PARIS).hour != 11:
        print("Pas 11 h à Paris : rien à faire."); return
    data = json.load(open(os.path.join(ROOT, "data.json"), encoding="utf-8"))
    nxt = None
    for g in sorted(data.get("games", []), key=lambda g: g["start"]):
        start = datetime.datetime.fromisoformat(g["start"].replace("Z", "+00:00"))
        if g.get("status") != "final" and start > now:
            nxt = (g, start); break
    if not nxt:
        if test: send("Spurs Courtside", "Test réussi : les notifications fonctionnent. Aucun match à venir.")
        return
    g, start = nxt
    p, e = start.astimezone(PARIS), start.astimezone(ET)
    sep = "vs" if g["home"] else "@"
    us_h = e.strftime("%I:%M %p").lstrip("0")
    body = (f"Spurs {sep} {g['oppName']} — {p.hour}h{p.minute:02d} (heure FR) · {us_h} ET "
            f"({JOURS[e.weekday()]} {e.day} {MOIS[e.month-1]} aux USA)")
    soon = start - now < datetime.timedelta(hours=24)
    if soon:
        send("🏀 Match cette nuit", body)
        print("Notification envoyée.")
    elif test:
        send("Spurs Courtside", "Test réussi : les notifications fonctionnent. Prochain match : " + body)
        print("Notification de test envoyée.")
    else:
        print("Pas de match dans les 24 h.")

if __name__ == "__main__":
    main()
