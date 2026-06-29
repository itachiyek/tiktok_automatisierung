# Projektplan: Automatisierte TikTok-Clips (Trymacs · Eligella · Sidney)

> Ziel: Aus den YouTube-/Twitch-Inhalten von **Trymacs, Eligella und Sidney**
> automatisiert Highlight-Clips schneiden, vertikal aufbereiten, mit guten Texten &
> Hashtags versehen und auf TikTok hochladen — als legales Partnermodell mit den
> Creatorn (Einwilligung liegt vor) und mit dem Ziel, daraus Einnahmen zu erzielen.

Stand: 2026-06-29 · Branch: `claude/tiktok-clips-automation-plan-6fmit4`

---

## 0. Kurzfassung (TL;DR)

1. **Rechtlich:** Mit Einwilligung der Creator (schriftlich festhalten!) ist das Modell
   sauber. Achte zusätzlich auf Fremd-Rechte *in* den Clips (Hintergrundmusik/GEMA,
   Spiel-Publisher, dritte Personen) und auf TikToks „unoriginal content"-Regel.
2. **Technik:** Pipeline in 7 Stufen — Quellen überwachen → Highlights erkennen →
   vertikal schneiden + Untertitel → Texte/Hashtags per KI → Review → planen/hochladen
   (TikTok Content Posting API) → Analyse-Feedback.
3. **Cleverer Shortcut:** Twitch hat bereits **Community-Clips** (von Zuschauern erstellt).
   Das sind vorkuratierte Highlights — der mit Abstand günstigste & beste Startpunkt.
4. **Build vs. Buy:** Erst mit fertigen KI-Clip-Tools starten (schnell live), dann
   schrittweise eigene Pipeline für Kosten & Kontrolle bauen.
5. **Geld:** TikTok Creator Rewards (DE freigeschaltet, ab 10k Follower + 100k Views/30 Tage,
   Videos > 60 Sek.), Revenue-Share mit Creatorn, Traffic auf ihre Hauptkanäle/Merch,
   später Markendeals / TikTok Shop.
6. **Wichtig sofort:** TikTok-API-Freigabe **jetzt** beantragen (Audit dauert 2–6 Wochen)
   und mit den 3 Creatorn eine kurze schriftliche Vereinbarung machen.

---

## 1. Geschäftsmodell & rechtlicher Rahmen

### 1.1 Warum die Einwilligung alles ändert
Ein Reupload fremder Videos/Highlights ohne Erlaubnis ist in DE eine Urheberrechts­verletzung
(§§ 94, 95 UrhG) und führt zu Abmahnungen. **Mit** Einwilligung des Creators (= Rechteinhaber
am eigenen Stream/Video) wird daraus ein normales Partner-/Lizenzmodell. → Genau das machen wir.

**To-do (nicht-technisch, aber kritisch):**
- Pro Creator eine kurze **schriftliche Vereinbarung**: Was darf geclippt werden, welche
  Accounts, Namensnennung/Verlinkung, Revenue-Share, Kündigung. Reicht formlos per Mail/PDF.
- Klären, ob die Clips auf **euren** Accounts oder den **offiziellen** Accounts der Creator laufen.

### 1.2 Rest-Risiken trotz Einwilligung (im Clip enthaltene Fremdrechte)
Der Creator kann nur *seine* Rechte freigeben — nicht die Dritter im Material:
- **Musik/GEMA:** Hintergrundmusik in Streams kann auf TikTok stumm geschaltet/gesperrt werden.
  → Clips ohne Musik bevorzugen, Musik erkennen & stummschalten/ersetzen, oder TikToks
  kommerzielle Sound-Bibliothek nutzen.
- **Spiele/Let's Plays:** i. d. R. von Publishern geduldet; trotzdem als Risiko notieren.
- **Dritte Personen** (z. B. in „Just Chatting"-Reactions): Persönlichkeitsrechte beachten.

### 1.3 TikTok-Plattformregeln
- **„Unoriginal content":** Reine 1:1-Reuploads ohne Mehrwert werden abgestraft.
  → Echte Bearbeitung (Schnitt, Reframe, animierte Untertitel, Hook, Branding) = Mehrwert.
- **Branding-Regel der API:** Kein fremdes Wasserzeichen/Logo/Werbetext einbrennen
  (TikTok prüft das im Audit). Eigene dezente Creator-Nennung ist ok und fair.
- **Spam-Vermeidung:** Maßvolle Posting-Frequenz, variierende Inhalte, saubere Accounts.

---

## 2. Wie verdient man damit konkret Geld?

| Quelle | Voraussetzung | Realistische Größenordnung |
|---|---|---|
| **TikTok Creator Rewards** | DE-Account, ≥ 10k Follower, ≥ 100k Views/30 Tage, Videos **> 60 Sek.**, original | RPM ca. $0,40–1,00 (Standard), bis $1–6 in Hoch-Retention-Nischen |
| **Revenue-Share mit Creatorn** | Vereinbarung | Aufteilung der Erlöse als Anreiz/Fairness |
| **Traffic → Hauptkanäle/Merch** | Verlinkung in Bio/Text | Mehrwert für die Creator (= macht den Deal attraktiv) |
| **Markendeals / Sponsoring** | gewachsene Accounts | später, skaliert mit Reichweite |
| **TikTok Shop / Affiliate** | je nach Nische | Zusatzkanal |

> Realistisch: Creator Rewards allein trägt erst ab ordentlicher Reichweite. Der Hebel ist
> **Menge × Trefferquote** (viele Accounts/Clips, davon einige viral) plus die starken,
> bereits etablierten Namen Trymacs/Eligella/Sidney als Reichweiten-Booster.

**Konto-Strategie:** Pro Creator ein eigener Clip-Account (`@trymacs.clips` etc.) ist sauber
und thematisch fokussiert (besser für den Algorithmus) als ein Sammel-Account.

---

## 3. Technische Architektur (die Pipeline)

```
 ┌──────────────┐   ┌───────────────┐   ┌────────────────┐   ┌───────────────┐
 │ 1. Quellen-  │──▶│ 2. Highlight- │──▶│ 3. Clip-Editing│──▶│ 4. Texte &    │
 │   Monitoring │   │   Erkennung   │   │   (9:16 + Subs)│   │   Hashtags(KI)│
 └──────────────┘   └───────────────┘   └────────────────┘   └───────┬───────┘
        ▲                                                              │
        │            ┌───────────────┐   ┌────────────────┐   ┌──────▼────────┐
        └────────────│ 7. Analyse &  │◀──│ 6. Upload &    │◀──│ 5. Review &    │
                     │   Feedback    │   │   Scheduling   │   │   Qualitätsgate│
                     └───────────────┘   └────────────────┘   └────────────────┘
```

### Stufe 1 — Quellen-Monitoring & Ingestion
- **Twitch:** Helix-API → neue VODs **und** vorhandene **Community-Clips** abrufen
  (Clips = bereits kuratierte Highlights, riesiger Vorteil). Download via `yt-dlp`.
- **YouTube:** Data API v3 → neue Uploads der Kanäle überwachen. Download via `yt-dlp`.
- Zustandshaltung (was wurde schon verarbeitet?) in einer DB, damit nichts doppelt läuft.

### Stufe 2 — Highlight-Erkennung (für volle VODs)
Signale, kombiniert gewichtet:
- **Chat-Velocity** (Nachrichten-/Emote-Bursts) — bestes Signal bei Twitch (vgl. PogChampNet).
- **Audio-Energie** (Lautstärke-/Tonhöhen-Spikes = Aufregung, Lachen, Reaktion).
- **YouTube „Most replayed"**-Heatmap, wo verfügbar.
- **KI-Clipper** (siehe Abschnitt 4) als Alternative/Ergänzung.
- Spacing/Mindestabstand & Score-Schwelle, damit Clips nicht überlappen.

### Stufe 3 — Clip-Editing
- Schnitt mit **ffmpeg**; Hook in den ersten 1–2 Sek.
- **9:16-Reframe** mit Subjekt-/Gesichts-Tracking (Auto-Crop), nicht stures Mittelschneiden.
- **Animierte Untertitel** aus Whisper-Transkription (Burn-in, Stil pro Creator).
- Dezentes Branding/Creator-Credit, Länge ggf. auf **> 60 Sek.** ziehen (Monetarisierung).
- Musik-Check (siehe 1.2): kritische Musik stummschalten/ersetzen.

### Stufe 4 — Texte & Hashtags (KI)
- **Claude API** generiert pro Clip: Hook-Titel, Caption, 5–10 Hashtags — auf Deutsch,
  im Ton des jeweiligen Creators/der Nische. Stil-Profil pro Creator als Prompt-Vorlage.

### Stufe 5 — Review & Qualitätsgate
- Dedup (kein Clip doppelt), Mindestqualität, Länge/Format prüfen.
- **Anfangs menschliche Freigabe** (Review-Queue) — schützt vor peinlichen/falschen Clips
  und vor TikTok-Strikes; später stichprobenartig automatisieren.

### Stufe 6 — Upload & Scheduling
- **TikTok Content Posting API** (Direct Post). Audit nötig (sonst nur „privat" sichtbar).
- Vor jedem Post Creator-Username & Avatar anzeigen (API-Pflicht).
- Posting-Kadenz pro Account moderat (z. B. 1–3/Tag), zu Stoßzeiten geplant.

### Stufe 7 — Analyse & Feedback
- Views/Watchtime/Retention je Clip zurückspielen → lernt, welche Highlight-Typen/Hooks
  ziehen → fließt in Stufe 2 & 4 ein.

---

## 4. Build vs. Buy — Tool-Auswahl

**Empfehlung: Hybrid.** Schnell mit fertigen Tools live gehen, parallel eigene Pipeline bauen.

| Bedarf | Fertige Tools (Buy) | Eigenbau (Build) |
|---|---|---|
| Gaming-Highlights (Trymacs FIFA/EAFC etc.) | **Eklipse** (gaming-trainiert, Twitch-Auto-Clips), **Choppity** (API + Posting) | Chat-Velocity + Audio-Detektor selbst |
| Reaction/„Just Chatting" | **OpusClip, Vizard, Klap, Reap** | Whisper + Score-Modell |
| Download | — | **yt-dlp** |
| Schnitt/Reframe/Subs | in obigen Tools enthalten | **ffmpeg + Whisper + (moviepy)** |
| Auto-Posting | Choppity (nativ), Buffer u. ä. | **TikTok Content Posting API** direkt |

> Pragmatischer Start: für Twitch zuerst **vorhandene Community-Clips** + ein KI-Tool wie
> Eklipse/OpusClip nutzen → minimale eigene Entwicklung, sofort Output. Eigenbau lohnt sich
> erst bei Volumen (Kosten) und für volle Kontrolle.

---

## 5. Tech-Stack (Vorschlag)

- **Sprache/Runtime:** Python (yt-dlp, ffmpeg, faster-whisper, moviepy, scenedetect)
- **APIs:** Twitch Helix, YouTube Data v3, TikTok Content Posting, **Claude API** (Texte)
- **Datenbank/Storage:** **Supabase** (Postgres + Storage) — für Job-Zustand, Clip-Metadaten,
  Analytics. (MCP-Anbindung in dieser Umgebung vorhanden.)
- **Orchestrierung:** Job-Queue (Redis/Celery) oder zum Start **n8n**/einfacher Scheduler (cron).
- **Dashboard (optional):** kleines Web-UI (Next.js auf **Vercel**) für Review-Queue & Analytics.
- **Secrets:** API-Keys/Tokens über Env-Variablen / Secret-Store, nie im Repo.

### Vorgeschlagene Repo-Struktur
```
tiktok_automatisierung/
├── PLAN.md                  # dieser Plan
├── README.md
├── config/
│   └── creators.example.yaml   # Creator-Profile (Quellen, Account, Stil, Revenue-Share)
├── src/
│   ├── ingest/              # Twitch/YouTube Monitoring + yt-dlp
│   ├── highlight/           # Chat-/Audio-Score, KI-Clipper-Anbindung
│   ├── edit/               # ffmpeg-Schnitt, 9:16-Reframe, Whisper-Untertitel
│   ├── metadata/           # Claude-Prompts für Titel/Caption/Hashtags
│   ├── review/             # Qualitätsgate / Review-Queue
│   ├── upload/             # TikTok Content Posting API
│   └── analytics/          # Performance-Rückkanal
├── data/                   # (gitignored) Downloads, Renders
└── requirements.txt
```

---

## 6. Roadmap / Phasen

**Phase 0 — Fundament (Woche 1–2)**
- [ ] Schriftliche Vereinbarung mit Trymacs, Eligella, Sidney (Scope, Accounts, Revenue-Share).
- [ ] **TikTok Developer App anlegen + Content Posting API beantragen** (Audit 2–6 Wochen → sofort!).
- [ ] Twitch- & YouTube-API-Zugänge einrichten. Clip-Accounts (pro Creator) anlegen.
- [ ] Repo-Grundgerüst + `creators.yaml` befüllen.

**Phase 1 — MVP / Validierung (Woche 2–4)**
- [ ] Für 1 Creator: vorhandene **Twitch-Clips** ziehen → mit KI-Tool aufbereiten → **manuell** posten.
- [ ] Testen, welche Clips/Hooks performen. Ziel: Beweis, dass die Clips ziehen.

**Phase 2 — Automatisierung (Monat 2)**
- [ ] Pipeline Stufe 1–6 end-to-end für alle 3 Creator.
- [ ] Auto-Posting via TikTok API (sobald Audit durch). Review-Queue aktiv.

**Phase 3 — Skalierung & Optimierung (ab Monat 3)**
- [ ] Analytics-Feedback (Stufe 7), Hook-/Hashtag-Optimierung.
- [ ] Mehr Accounts/Frequenz, eigene Highlight-Erkennung statt Tool-Kosten, weitere Creator.

---

## 7. Kostenrahmen (grobe Hausnummer, monatlich)

| Posten | Größenordnung |
|---|---|
| KI-Clip-Tool(s) (Buy-Phase) | ~ $15–50 je Tool/Account-Volumen |
| Claude API (Texte) | gering (wenige $ bei Textmengen) |
| Server/Compute (Eigenbau-Phase, Rendering) | je nach Volumen, klein starten |
| Supabase / Vercel | Free-Tier zum Start, dann gering |
| Whisper/Transkription | lokal ~ gratis (GPU) oder API-Kosten |

> Strategie: in der Buy-Phase niedrig halten, erst bei Volumen in Eigenbau investieren,
> wenn die Tool-Kosten den Eigenbau übersteigen.

---

## 8. Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| TikTok „unoriginal content" / Spam-Strike | echte Bearbeitung + Mehrwert, moderate Frequenz, saubere Accounts |
| Musik/GEMA-Sperren in Clips | Musik erkennen & stummschalten/ersetzen, musikfreie Clips bevorzugen |
| TikTok-API-Audit verzögert/abgelehnt | früh beantragen, UX-Vorgaben (Username/Avatar, kein Fremd-Branding) einhalten |
| Account-Sperren | Plattformregeln strikt befolgen, mehrere Accounts, nichts „faken" |
| Schlechte Trefferquote der KI-Clips | mit Twitch-Community-Clips starten, mehrere Tools testen, Review-Queue |
| Abhängigkeit von 1 Tool | Pipeline modular halten, Anbieter austauschbar |

---

## 9. Entscheidungen, die du noch treffen solltest

1. **Account-Modell:** Clips auf *euren* Accounts oder den *offiziellen* der Creator?
2. **Build vs. Buy zum Start:** Erst fertige Tools (schneller) oder direkt Eigenbau (mehr Kontrolle)?
3. **Revenue-Share-Höhe** pro Creator.
4. **Hosting:** Supabase/Vercel (in dieser Umgebung verfügbar) oder eigener Server?

> Sag mir, wie du dich bei 1–4 entscheidest (oder ob ich pragmatische Defaults setzen soll),
> dann baue ich das Repo-Grundgerüst (`creators.yaml` + Module-Skelett + erster Ingest-Schritt)
> als nächsten Schritt auf.

---

## Quellen
- TikTok Content Posting API (Direct Post): https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
- TikTok Content Sharing Guidelines (Branding/UX): https://developers.tiktok.com/doc/content-sharing-guidelines
- TikTok Creator Rewards (Eligibility, DE): https://www.tiktok.com/creator-academy/article/eligibility
- Reupload & Urheberrecht (DE, §§ 94/95 UrhG): https://www.ratgeberrecht.eu/aktuell/reuploads-und-urheberrecht/
- Let's Play & Urheberrecht: https://www.e-recht24.de/urheberrecht/13280-lets-play-urheberrecht.html
- Automatische Highlight-Erkennung via Chat (PogChampNet): https://medium.com/@farzatv/pogchampnet-how-we-used-twitch-chat-deep-learning-to-create-automatic-game-highlights-with-only-61ed7f7b22d4
- AI-Clip-Tools Vergleich 2026 (OpusClip-Alternativen): https://www.choppity.com/blog/best-opus-clip-alternatives/
- Twitch Auto-Clips Guide: https://www.streamladder.com/blog/twitch-auto-clips-your-guide-to-automatically-capturing-stream-highlights
- Eklipse (Gaming-Highlights): https://eklipse.gg/features/ai-highlights/
