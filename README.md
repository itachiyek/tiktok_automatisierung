# tiktok_automatisierung

Automatisierte Highlight-Clips deutscher Creator (**Trymacs · Eligella · Sidney**) für TikTok —
als Partnermodell mit Einwilligung der Creator.

**Pipeline:** Quellen überwachen (Twitch/YouTube) → Highlights erkennen → vertikal schneiden +
Untertitel → Texte & Hashtags per KI → Review → Upload (TikTok Content Posting API) → Analyse.

➡️ **Der vollständige Plan steht in [`PLAN.md`](./PLAN.md).**

## Status
- [x] Projektplan (`PLAN.md`)
- [ ] Creator-Vereinbarungen (schriftlich)
- [ ] TikTok Content Posting API beantragt (Audit 2–6 Wochen)
- [ ] Repo-Grundgerüst / erster Ingest-Schritt

## Schnellstart (Konfiguration)
Creator-Profile in `config/creators.example.yaml` → nach `config/creators.yaml` kopieren und befüllen.
Keine API-Keys ins Repo — nur über Env-Variablen / Secret-Store.
