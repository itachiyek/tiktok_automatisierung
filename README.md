# tiktok_automatisierung

Automatisierte Highlight-Clips deutscher Creator (**Trymacs · Eligella · Sidney**) für TikTok —
als Partnermodell mit Einwilligung der Creator.

**Pipeline:** Quellen überwachen (Twitch/YouTube) → Highlights erkennen → **1–2-Minuten**-Clips
vertikal (9:16) schneiden + **Untertitel oben** + Creator-Credit → Texte & Hashtags per KI (Claude)
→ Qualitäts-/Review-Gate → **Upload & Planung via [Zernio](https://zernio.com)** → Analyse.

**Vollautomatik per Cron:** `scripts/cron_run.sh` schneidet regelmäßig neue Highlights und plant
sie zeitlich gestaffelt über Zernio ein (kein eigenes TikTok-Audit nötig — Zernio ist die
auditierte App).

➡️ Strategie & Hintergrund: **[`PLAN.md`](./PLAN.md)**

---

## Schnellstart

```bash
# 1) Abhängigkeiten
python3 -m pip install -r requirements.txt
sudo apt-get install ffmpeg          # bzw. brew install ffmpeg

# 2) Konfiguration
cp config/creators.example.yaml config/creators.yaml   # Creator/Accounts anpassen
cp .env.example .env                                    # API-Keys eintragen (s. u.)
#   -> ZERNIO_API_KEY=sk_...  und  TWITCH_CLIENT_ID/SECRET  eintragen

# 3) Prüfen, was noch fehlt (zeigt jeden Key einzeln an)
python3 -m src.cli check

# 3b) TikTok-Konto(en) EINMALIG in Zernio verbinden: https://zernio.com
#     dann die verbundenen Konten/IDs anzeigen (optional als zernio_account_id eintragen):
python3 -m src.cli zernio-accounts

# 4) Trockenlauf – zeigt nur, welche Quellen gefunden würden (nichts wird hochgeladen)
python3 -m src.cli run --dry-run

# 4b) EINZELNES Video sofort posten (ohne Cut-Pipeline):
python3 -m src.cli post --file mein_clip.mp4 --caption "Krasse Aktion! 🔥 #fyp"
#   geplant statt sofort:   --in 30   (in 30 min)   oder   --at 2026-07-05T18:00:00Z
#   öffentliche URL statt Datei:  --url https://.../video.mp4
#   privat testen:  --privacy SELF_ONLY   ·   Vorschau ohne Senden:  --dry-run

# 5) VOLLAUTOMATIK (für Crons): schneiden + auto-freigeben + via Zernio gestaffelt einplanen
python3 -m src.cli auto --limit 3
#   sofort statt geplant veröffentlichen:  python3 -m src.cli auto --now

# --- oder halbautomatisch mit manueller Review ---
python3 -m src.cli run --creator trymacs --limit 3    # nur schneiden (kein Upload)
python3 -m src.cli clips --status pending_review      # erzeugte Clips ansehen
python3 -m src.cli approve 1 2 3                       # freigeben
python3 -m src.cli upload-approved --creator trymacs  # freigegebene hochladen (via Zernio)
```

> **Vollautomatik** (`auto`) gibt Clips automatisch frei und plant sie über Zernio ein.
> Für manuelle Kontrolle stattdessen `run` + `approve` + `upload-approved` nutzen.
> Privatsphäre steuerst du über `posting.privacy_level` (`PUBLIC_TO_EVERYONE` oder zum Testen `SELF_ONLY`).

### ⏰ Cron einrichten (vollautomatisch)

```bash
crontab scripts/crontab.example     # Pfad in der Datei vorher anpassen!
# oder manuell, z. B. 3x täglich:
#   0 9,14,19 * * * /pfad/zum/repo/scripts/cron_run.sh
```
`scripts/cron_run.sh` ruft `python3 -m src.cli auto` auf und loggt nach `data/cron.log`.
Steuerbar per Env: `CLIP_LIMIT`, `CREATOR`, `AUTO_FLAGS` (z. B. `--now`).

---

## 🔑 Welche API-Keys brauchst du? (in `.env` eintragen)

| Key | Wofür | Woher | Pflicht? |
|---|---|---|---|
| `ZERNIO_API_KEY` | **Upload & Planung auf TikTok** (empfohlener Weg) | https://zernio.com/dashboard/api-keys | **Ja** (zum Hochladen) |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | Twitch-Clips & VODs abrufen | https://dev.twitch.tv/console/apps | **Ja** (Hauptquelle) |
| `YOUTUBE_API_KEY` | neue YouTube-Uploads erkennen | https://console.cloud.google.com → „YouTube Data API v3" aktivieren → API-Key | Optional (nur mit `--youtube`) |
| `ANTHROPIC_API_KEY` | Caption & Hashtags per Claude | https://console.anthropic.com | Empfohlen (ohne → Template-Texte) |
| `TIKTOK_*` (Client Key/Secret, Access-Token) | **Legacy**-Direktupload ohne Zernio | https://developers.tiktok.com → **Content Posting API** (Audit 2–6 Wochen) | Optional (nur bei `posting.uploader: tiktok`) |

### 🟢 Warum Zernio? (empfohlen)

[Zernio](https://zernio.com) ist eine **bereits von TikTok auditierte** App und postet in deinem
Namen. Vorteile gegenüber dem TikTok-Direktupload:

- **Kein eigenes Content-Posting-Audit** nötig (spart die 2–6 Wochen Wartezeit) → sofort **öffentlich** posten.
- **Planung/Scheduling** eingebaut: Clips werden zeitlich gestaffelt eingeplant (`schedule_mode: spread`).
- Ein Key für alle Konten; TikTok-Konten einmalig unter https://zernio.com verbinden.

**So geht's:** Konto in Zernio verbinden → `ZERNIO_API_KEY` in `.env` → `python3 -m src.cli zernio-accounts`
zeigt die verbundenen Konten. Der passende `@handle` in `creators.yaml` (`tiktok_account`) wird
automatisch aufgelöst; alternativ `zernio_account_id` fest eintragen.

> Der **Upload-Weg** ist pro Creator über `posting.uploader` steuerbar (`zernio` = Standard, `tiktok` = Legacy).
> Der TikTok-Direktupload (`auth`, `TIKTOK_*`) bleibt als Alternative erhalten, ist aber **nicht** nötig, wenn du Zernio nutzt.

**Was du NICHT als Key brauchst:** Download (`yt-dlp`) und Untertitel (`faster-whisper`) laufen
lokal ohne Key. `ffmpeg` muss installiert sein.

---

## Struktur

```
src/
  config.py            # creators.yaml + .env laden, Key-Helper
  models.py            # SourceItem / Segment / Clip / ClipMeta
  db.py                # SQLite: Dedup + Clip-Status
  ingest/              # twitch.py · youtube.py · downloader.py (yt-dlp)
  highlight/           # audio_energy.py (Erkennung) · selector.py
  edit/                # editor.py (ffmpeg 9:16) · subtitles.py (Whisper→ASS, Text OBEN)
  metadata/            # generator.py (Claude → Caption/Hashtags, Fallback-Template)
  review/              # quality_gate.py (Dedup, Länge 1–2 min, Review-Status)
  upload/              # zernio.py (Zernio-Upload+Planung) · tiktok.py (Legacy-Direktupload)
  analytics/           # collector.py (Views/Engagement zurücklesen)
  pipeline.py          # Orchestrator (run, run_auto, Scheduling)
  cli.py               # Kommandozeile (check, run, auto, zernio-accounts, …)
scripts/               # cron_run.sh + crontab.example (Vollautomatik)
tests/                 # Logik-Tests (ohne Netz/Keys):  python3 -m pytest -q
config/creators.example.yaml
```

## Status
- [x] Projektplan (`PLAN.md`)
- [x] Lauffähige Pipeline + CLI + Tests
- [x] Clips 1–2 Minuten, Untertitel **oben**
- [x] Zernio-Upload & -Planung + Cron-Vollautomatik (`auto`, `scripts/cron_run.sh`)
- [ ] `.env` mit echten API-Keys (`ZERNIO_API_KEY`, `TWITCH_*` …)
- [ ] TikTok-Konten in Zernio verbunden (https://zernio.com)
- [ ] Creator-Vereinbarungen (schriftlich)
