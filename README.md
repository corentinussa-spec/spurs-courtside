# Spurs Courtside

Application autonome (PWA) : calendrier, fiches match, classement, blessures et stats des San Antonio Spurs, avec mode anti-spoiler.

- **Données** : `scripts/update.py` (source ESPN) met à jour `data.json` deux fois par jour via GitHub Actions.
- **Records** : carrière (historique des matchs de chaque joueur), NBA (`scripts/records_nba.json`) et saison.
- **Rappel** : `scripts/notify.py` envoie une notification push à l'appli à 12h45 (heure de Paris) les jours de match. Téléphones abonnés : dossier `push/`.
- **Lancer à la main** : onglet Actions → « Mise à jour Spurs » → Run workflow.
