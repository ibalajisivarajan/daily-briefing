# ☀️ TPM Daily Briefing

A cloud-hosted daily briefing page that auto-generates every morning at 6:00 AM PST.

**Features:**
- Full-screen landscape wallpaper background (Unsplash)
- Real-time weather for Langley BC & Ferndale WA (OpenWeatherMap)
- Curated news across 5 categories (Google News)
- Traffic incidents for commute days (DriveBC & WSDOT)
- Daily TPM leadership quote
- Job market intelligence
- Zero cost, zero server dependencies

**Live:** https://ibalajisivarajan.github.io/daily-briefing

## Setup

### Secrets Required
Add these to your GitHub repo Settings → Secrets and variables → Actions:
- `OPENWEATHER_API_KEY` — from https://openweathermap.org (free account)
- `UNSPLASH_ACCESS_KEY` — from https://unsplash.com/developers (free account)

### Local Development
```bash
pip install -r requirements.txt
export OPENWEATHER_API_KEY=your_key_here
export UNSPLASH_ACCESS_KEY=your_key_here
python src/generate_briefing.py
open docs/index.html
```

### Deploy
Push to main branch. GitHub Actions runs daily at 6:00 AM PST.

## Architecture

- **Code:** Private GitHub repo
- **Execution:** GitHub Actions cron job
- **Hosting:** GitHub Pages (static HTML from /docs folder)
- **Storage:** None — fresh data every run

## Operational Hardening

V1 includes:
1. **Timezone handling** — DST-safe (America/Los_Angeles)
2. **API fallbacks** — Graceful degradation if any API fails
3. **Normalization layer** — Schema-first data handling
4. **Validation + dedup** — Clean data before render
5. **Logging** — Structured per-component logs
6. **Timeout + retry** — 5-second timeouts, immediate fallback

---

**Built by Balaji Sivarajan**
