#!/usr/bin/env python3
import json
import logging
import os
import random
import sys
from datetime import datetime
from pathlib import Path

import pytz
import requests
from gnews import GNews

from quotes import QUOTES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

TZ = pytz.timezone("America/Los_Angeles")
TIMEOUT = 5

OPENWEATHER_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
UNSPLASH_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")

LANGLEY  = {"lat": 49.1044, "lon": -122.6608, "name": "langley",  "city": "Langley, BC"}
FERNDALE = {"lat": 48.8465, "lon": -122.5910, "name": "ferndale", "city": "Ferndale, WA"}

WEATHER_ICONS = {
    "clear": "☀️", "clouds": "☁️", "rain": "🌧️", "drizzle": "🌦️",
    "thunderstorm": "⛈️", "snow": "❄️", "mist": "🌫️", "fog": "🌫️",
    "haze": "🌫️", "smoke": "🌫️",
}

DRIVEBC_FEED = "https://www.drivebc.ca/api/events/?format=json&status=ACTIVE"
GOOGLE_MAPS_URL = "https://www.google.com/maps/dir/Langley,+BC/Ferndale,+WA/@49.0,+-122.6,10z"

RELEVANT_ROUTES = [
    "hwy 1", "highway 1", "i-5", "i5", "hwy 99", "highway 99",
    "fraser", "chilliwack", "abbotsford", "langley", "surrey",
    "blaine", "ferndale", "bellingham", "border", "peace arch",
]


def fetch_weather(location: dict) -> dict:
    fallback = {"city": location["city"], "temp": "N/A", "condition": "Unavailable", "icon": "❓"}
    if not OPENWEATHER_KEY:
        log.warning("weather_fetch: no API key for %s", location["name"])
        return fallback
    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": location["lat"], "lon": location["lon"],
                    "appid": OPENWEATHER_KEY, "units": "metric"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        temp = round(data["main"]["temp"])
        condition = data["weather"][0]["description"].title()
        icon = WEATHER_ICONS.get(data["weather"][0]["main"].lower(), "🌡️")
        log.info("weather_fetch: success (%s: %d°C)", location["name"], temp)
        return {"city": location["city"], "temp": temp, "condition": condition, "icon": icon}
    except Exception as exc:
        log.error("weather_fetch: failed for %s — %s", location["name"], exc)
        return fallback


def fetch_wallpaper() -> str:
    if not UNSPLASH_KEY:
        log.warning("wallpaper_fetch: no API key")
        return ""
    try:
        resp = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": "landscape", "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        url = data["urls"]["full"]
        log.info("wallpaper_fetch: success (photo_id: %s)", data["id"])
        return url
    except Exception as exc:
        log.error("wallpaper_fetch: failed — %s", exc)
        return ""


def _parse_news_item(item: dict) -> dict:
    title = (item.get("title") or "").strip()[:100]
    pub = item.get("published date") or ""
    if pub:
        try:
            pub = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").strftime("%b %d")
        except Exception:
            pub = pub[:10]
    publisher = item.get("publisher") or {}
    source = publisher.get("title", "Unknown") if isinstance(publisher, dict) else str(publisher).strip() or "Unknown"
    return {"title": title, "source": source, "url": item.get("url") or "#", "date": pub}


def fetch_news(query: str, country: str = "CA", max_results: int = 5) -> list:
    try:
        results = GNews(language="en", country=country, max_results=max_results).get_news(query)
        return results or []
    except Exception as exc:
        log.error("news_fetch: failed for '%s' — %s", query, exc)
        return []


def fetch_all_news() -> dict:
    seen_urls: set = set()
    seen_titles: set = set()

    def dedup(items):
        out = []
        for item in items:
            url, title = item.get("url", ""), item.get("title", "").lower()
            if url in seen_urls or title in seen_titles or not title:
                continue
            seen_urls.add(url)
            seen_titles.add(title)
            out.append(item)
        return out

    queries = [
        ("geopolitics", "world geopolitics",                       "CA", 5),
        ("technology",  "technology",                              "CA", 5),
        ("finance",     "finance markets economy",                 "CA", 5),
        ("local",       "Langley BC Fraser Valley",                "CA", 5),
        ("jobs",        "technical program manager hiring layoffs", "US", 5),
    ]

    news: dict = {}
    counts = {}
    for key, query, country, max_r in queries:
        raw = fetch_news(query, country=country, max_results=max_r)
        parsed = [_parse_news_item(i) for i in raw]
        news[key] = dedup(parsed)[:3]
        counts[key] = len(news[key])

    log.info(
        "news_fetch: %d items (geopolitics: %d, tech: %d, finance: %d, local: %d, jobs: %d)",
        sum(counts.values()), counts.get("geopolitics", 0), counts.get("technology", 0),
        counts.get("finance", 0), counts.get("local", 0), counts.get("jobs", 0),
    )
    return news


def fetch_traffic(now: datetime) -> dict:
    weekday = now.weekday()
    if weekday not in (0, 2):
        return {"show_banner": False, "incidents": [], "google_maps_url": GOOGLE_MAPS_URL}

    incidents = []
    try:
        resp = requests.get(DRIVEBC_FEED, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        events = data if isinstance(data, list) else data.get("events", [])
        for event in events:
            text = " ".join(filter(None, [
                event.get("headline", ""), event.get("description", ""),
                (event.get("roads") or [{}])[0].get("name", ""),
            ]))
            if not any(r in text.lower() for r in RELEVANT_ROUTES):
                continue
            incidents.append({
                "type": event.get("event_type", "Incident").replace("_", " ").title(),
                "location": (event.get("roads") or [{}])[0].get("name", text[:60]),
                "updated": event.get("updated", "")[:16],
            })
            if len(incidents) >= 5:
                break
    except Exception as exc:
        log.error("incidents_fetch: DriveBC failed — %s", exc)

    log.info("incidents_fetch: %d items", len(incidents))
    return {"show_banner": True, "incidents": incidents, "google_maps_url": GOOGLE_MAPS_URL}


def build_data() -> dict:
    now = datetime.now(TZ)
    return {
        "date":               now.strftime("%A, %B %-d, %Y"),
        "time":               now.strftime("%H:%M"),
        "greeting":           "Good morning, Bala." if now.hour < 12 else "Good afternoon, Bala.",
        "quote":              random.choice(QUOTES),
        "background_image_url": fetch_wallpaper(),
        "weather": {
            "langley":  fetch_weather(LANGLEY),
            "ferndale": fetch_weather(FERNDALE),
        },
        "news":    fetch_all_news(),
        "traffic": fetch_traffic(now),
        "github_token": os.environ.get("GITHUB_TOKEN", ""),
        "generated_at": now.strftime("%Y-%m-%d %H:%M %Z"),
    }


def main():
    log.info("generate_briefing: starting")
    data = build_data()

    out_path = Path(__file__).parent.parent / "data.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("render: complete (%d bytes) → %s", out_path.stat().st_size, out_path)


if __name__ == "__main__":
    main()
