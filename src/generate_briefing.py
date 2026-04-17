#!/usr/bin/env python3
import logging
import os
import random
import sys
from datetime import datetime
from pathlib import Path

import pytz
import requests
from gnews import GNews
from jinja2 import Environment, FileSystemLoader

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

LANGLEY = {"lat": 49.1044, "lon": -122.6608, "name": "langley"}
FERNDALE = {"lat": 48.8465, "lon": -122.5910, "name": "ferndale"}

WEATHER_ICONS = {
    "clear": "☀️",
    "clouds": "☁️",
    "rain": "🌧️",
    "drizzle": "🌦️",
    "thunderstorm": "⛈️",
    "snow": "❄️",
    "mist": "🌫️",
    "fog": "🌫️",
    "haze": "🌫️",
    "smoke": "🌫️",
}

DRIVEBC_FEED = "https://www.drivebc.ca/api/events/?format=json&status=ACTIVE"
WSDOT_FEED = "https://www.wsdot.wa.gov/Traffic/api/Traveler/TravelerInfoRest.svc/GetBorderCrossingsAsJson"

GOOGLE_MAPS_URL = (
    "https://www.google.com/maps/dir/Langley,+BC/Ferndale,+WA/@49.0,+-122.6,10z"
)

RELEVANT_ROUTES = ["hwy 1", "highway 1", "i-5", "i5", "hwy 99", "highway 99",
                   "fraser", "chilliwack", "abbotsford", "langley", "surrey",
                   "blaine", "ferndale", "bellingham", "border", "peace arch"]


def fetch_weather(location: dict) -> dict:
    fallback = {"temp": "N/A", "condition": "Unavailable", "icon": "❓"}
    if not OPENWEATHER_KEY:
        log.warning("weather_fetch: no API key for %s", location["name"])
        return fallback
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        resp = requests.get(
            url,
            params={
                "lat": location["lat"],
                "lon": location["lon"],
                "appid": OPENWEATHER_KEY,
                "units": "metric",
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        temp = round(data["main"]["temp"])
        condition = data["weather"][0]["description"].title()
        main = data["weather"][0]["main"].lower()
        icon = WEATHER_ICONS.get(main, "🌡️")
        log.info("weather_fetch: success (%s: %d°C)", location["name"], temp)
        return {"temp": temp, "condition": condition, "icon": icon}
    except Exception as exc:
        log.error("weather_fetch: failed for %s — %s", location["name"], exc)
        return fallback


def fetch_wallpaper() -> dict:
    fallback = {
        "url": "",
        "photographer": "Unknown",
        "photographer_url": "https://unsplash.com",
        "attribution": "Photo from Unsplash",
    }
    if not UNSPLASH_KEY:
        log.warning("wallpaper_fetch: no API key")
        return fallback
    try:
        resp = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": "landscape", "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        photo_id = data["id"]
        url = data["urls"]["full"]
        photographer = data["user"]["name"]
        photographer_url = data["user"]["links"]["html"]
        log.info("wallpaper_fetch: success (photo_id: %s)", photo_id)
        return {
            "url": url,
            "photographer": photographer,
            "photographer_url": photographer_url,
            "attribution": f"Photo by {photographer} on Unsplash",
        }
    except Exception as exc:
        log.error("wallpaper_fetch: failed — %s", exc)
        return fallback


def _parse_news_item(item: dict) -> dict:
    title = (item.get("title") or "").strip()
    title = title[:100] if len(title) > 100 else title
    pub = item.get("published date") or item.get("published_date") or ""
    if pub:
        try:
            dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z")
            pub = dt.strftime("%b %d")
        except Exception:
            pub = pub[:10]
    return {
        "title": title,
        "source": (item.get("publisher") or {}).get("title", "Unknown"),
        "url": item.get("url") or "#",
        "date": pub,
    }


def fetch_news(query: str, country: str = "CA", max_results: int = 5) -> list:
    try:
        gn = GNews(language="en", country=country, max_results=max_results)
        results = gn.get_news(query)
        return results or []
    except Exception as exc:
        log.error("news_fetch: failed for '%s' — %s", query, exc)
        return []


def deduplicate(items: list, seen_urls: set, seen_titles: set) -> list:
    unique = []
    for item in items:
        url = item.get("url", "")
        title = item.get("title", "").lower()
        if url in seen_urls or title in seen_titles:
            continue
        if not title:
            continue
        seen_urls.add(url)
        seen_titles.add(title)
        unique.append(item)
    return unique


def fetch_all_news() -> dict:
    seen_urls: set = set()
    seen_titles: set = set()

    queries = [
        ("geopolitics", "world geopolitics", "CA", 5),
        ("technology", "technology", "CA", 5),
        ("finance", "finance markets economy", "CA", 5),
        ("local", "Langley BC Fraser Valley", "CA", 5),
        ("jobs", "technical program manager hiring layoffs", "US", 5),
    ]

    news: dict = {}
    counts = {}
    for key, query, country, max_r in queries:
        raw = fetch_news(query, country=country, max_results=max_r)
        parsed = [_parse_news_item(i) for i in raw]
        unique = deduplicate(parsed, seen_urls, seen_titles)
        news[key] = unique[:3]
        counts[key] = len(news[key])

    log.info(
        "news_fetch: %d items (geopolitics: %d, tech: %d, finance: %d, local: %d, jobs: %d)",
        sum(counts.values()),
        counts.get("geopolitics", 0),
        counts.get("technology", 0),
        counts.get("finance", 0),
        counts.get("local", 0),
        counts.get("jobs", 0),
    )
    return news


def _is_relevant(text: str) -> bool:
    text_lower = text.lower()
    return any(route in text_lower for route in RELEVANT_ROUTES)


def _time_ago(updated_str: str) -> str:
    try:
        formats = ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]
        dt = None
        for fmt in formats:
            try:
                dt = datetime.strptime(updated_str[:19], fmt[:len(fmt)])
                break
            except Exception:
                continue
        if dt is None:
            return updated_str
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        now = datetime.now(pytz.utc)
        diff = now - dt
        minutes = int(diff.total_seconds() / 60)
        if minutes < 60:
            return f"{minutes} mins ago"
        hours = minutes // 60
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    except Exception:
        return updated_str


def fetch_drivebc_incidents() -> list:
    incidents = []
    try:
        resp = requests.get(DRIVEBC_FEED, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        events = data if isinstance(data, list) else data.get("events", [])
        for event in events:
            headline = event.get("headline", "") or ""
            description = event.get("description", "") or ""
            location = event.get("roads", [{}])[0].get("name", "") if event.get("roads") else ""
            text = f"{headline} {description} {location}"
            if not _is_relevant(text):
                continue
            itype = event.get("event_type", "Incident").replace("_", " ").title()
            updated = event.get("updated", "")
            incidents.append({
                "type": itype,
                "location": location or headline[:60],
                "updated": _time_ago(updated),
            })
            if len(incidents) >= 5:
                break
    except Exception as exc:
        log.error("incidents_fetch: DriveBC failed — %s", exc)
    return incidents


def fetch_wsdot_incidents() -> list:
    incidents = []
    try:
        resp = requests.get(
            "https://www.wsdot.wa.gov/Traffic/api/Traveler/TravelerInfoRest.svc/GetHighwayAlertsAsJson",
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        alerts = data if isinstance(data, list) else []
        for alert in alerts:
            location_desc = alert.get("Region", "") or ""
            highway = alert.get("RoadName", "") or ""
            text = f"{location_desc} {highway}"
            if not _is_relevant(text):
                continue
            itype = alert.get("EventCategory", "Alert")
            start_road = alert.get("StartRoadwayLocation", {}) or {}
            loc = start_road.get("Description", highway or location_desc)
            updated = alert.get("LastUpdatedTime", "")
            if updated:
                updated = updated.replace("/Date(", "").replace(")/", "")
                try:
                    ts = int(updated.split("+")[0].split("-")[0]) / 1000
                    dt = datetime.fromtimestamp(ts, tz=pytz.utc)
                    updated = _time_ago(dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
                except Exception:
                    updated = "recently"
            incidents.append({
                "type": itype,
                "location": loc[:60],
                "updated": updated or "recently",
            })
            if len(incidents) >= 5:
                break
    except Exception as exc:
        log.error("incidents_fetch: WSDOT failed — %s", exc)
    return incidents


def fetch_traffic(now: datetime) -> dict:
    weekday = now.weekday()  # Monday=0, Wednesday=2
    show_banner = weekday in (0, 2)

    if not show_banner:
        return {"show_banner": False, "incidents": [], "google_maps_url": GOOGLE_MAPS_URL}

    drivebc = fetch_drivebc_incidents()
    wsdot = fetch_wsdot_incidents()
    incidents = (drivebc + wsdot)[:6]

    log.info(
        "incidents_fetch: %d items (%s)",
        len(incidents),
        ", ".join(f"{i['type']} on {i['location']}" for i in incidents) or "none",
    )

    return {
        "show_banner": True,
        "incidents": incidents,
        "google_maps_url": GOOGLE_MAPS_URL,
    }


def build_context() -> dict:
    now = datetime.now(TZ)

    hour = now.hour
    greeting = "Good morning, Bala." if hour < 12 else "Good afternoon, Bala."

    date_str = now.strftime("%A, %B %-d, %Y")
    time_str = now.strftime("%H:%M")
    generated_at = now.strftime("%Y-%m-%d %H:%M %Z")

    langley_weather = fetch_weather(LANGLEY)
    ferndale_weather = fetch_weather(FERNDALE)

    wallpaper = fetch_wallpaper()
    news = fetch_all_news()
    traffic = fetch_traffic(now)
    quote = random.choice(QUOTES)

    return {
        "date": date_str,
        "time": time_str,
        "greeting": greeting,
        "weather": {
            "langley": langley_weather,
            "ferndale": ferndale_weather,
        },
        "wallpaper": wallpaper,
        "news": news,
        "traffic": traffic,
        "quote": quote,
        "generated_at": generated_at,
    }


def render(context: dict) -> str:
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    template = env.get_template("briefing.html")
    return template.render(**context)


def main():
    log.info("generate_briefing: starting")
    context = build_context()
    html = render(context)

    out_path = Path(__file__).parent.parent / "docs" / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    log.info("render: complete (%d bytes) → %s", len(html), out_path)


if __name__ == "__main__":
    main()
