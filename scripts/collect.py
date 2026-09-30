#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse

import feedparser
import yaml
from bs4 import BeautifulSoup

from collect_official import collect_official_sources

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
DATA = ROOT / "data" / "news.json"
DOCS_DATA = ROOT / "docs" / "data" / "news.json"
HEALTH = ROOT / "data" / "collector-health.json"
DOCS_HEALTH = ROOT / "docs" / "data" / "collector-health.json"

MAX_ITEMS_PER_FEED = 15
RETENTION_DAYS = 45
REQUEST_PAUSE_SECONDS = 0.08


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_html(value: str) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    return normalize_space(html.unescape(soup.get_text(" ", strip=True)))


def normalize_title(value: str) -> str:
    value = strip_html(value).lower()
    value = re.sub(r"[^\w\sÀ-ÿ\u3040-\u30ff\u3400-\u9fff-]", " ", value, flags=re.UNICODE)
    return normalize_space(value)


def domain_of(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def domain_matches(host: str, candidates: list[str]) -> bool:
    host = (host or "").lower()
    for candidate in candidates:
        c = candidate.lower()
        if host == c or host.endswith("." + c):
            return True
    return False


def google_news_url(query: str, locale: dict) -> str:
    params = {
        "q": query,
        "hl": locale["hl"],
        "gl": locale["gl"],
        "ceid": locale["ceid"],
    }
    return "https://news.google.com/rss/search?" + urlencode(params)


def parse_entry_date(entry) -> str | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None

    dt = datetime(*parsed[:6], tzinfo=timezone.utc)

    # Não aceite datas muito no futuro.
    if dt > datetime.now(timezone.utc) + timedelta(days=2):
        return None

    return dt.isoformat()


def entry_source(entry) -> tuple[str, str]:
    source = getattr(entry, "source", None) or {}
    if isinstance(source, dict):
        return normalize_space(source.get("title", "")), normalize_space(source.get("href", ""))
    title = normalize_space(getattr(source, "title", ""))
    href = normalize_space(getattr(source, "href", ""))
    return title, href


def make_id(game_id: str, language: str, title: str, source_name: str, published_at: str) -> str:
    seed = "|".join([
        game_id,
        language,
        normalize_title(title),
        source_name.lower().strip(),
        published_at[:10],
    ])
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]


def load_existing() -> dict:
    if not DATA.exists():
        return {"generated_at": None, "count": 0, "items": []}
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except Exception:
        return {"generated_at": None, "count": 0, "items": []}


def collect_feed(game: dict, locale: dict, query: str, official_domains: dict) -> list[dict]:
    url = google_news_url(query, locale)
    parsed = feedparser.parse(url)

    if getattr(parsed, "bozo", False) and not parsed.entries:
        print(f"[WARN] Feed falhou: {game['name']} / {locale['id']}: {parsed.bozo_exception}", file=sys.stderr)
        return []

    items = []
    official_for_game = official_domains.get(game["id"], [])

    for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
        title = strip_html(getattr(entry, "title", ""))
        if not title:
            continue

        link = normalize_space(getattr(entry, "link", ""))
        source_name, source_home = entry_source(entry)
        source_host = domain_of(source_home)

        published_at = parse_entry_date(entry)
        if not published_at:
            # Sem data real no feed, não inventamos "hoje".
            continue

        excerpt = strip_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        if excerpt == title:
            excerpt = ""
        excerpt = excerpt[:700]

        item = {
            "id": make_id(game["id"], locale["language"], title, source_name, published_at),
            "game_id": game["id"],
            "game": game["name"],
            "language": locale["language"],
            "locale": locale["id"],
            "region": locale["gl"].lower(),
            "title": title,
            "excerpt": excerpt,
            "url": link,
            "source": source_name or source_host or "Fonte não identificada",
            "source_home": source_home,
            "source_domain": source_host,
            "official": domain_matches(source_host, official_for_game),
            "published_at": published_at,
            "discovered_at": now_iso(),
            "status": "pending",
            "collector": "google-news-rss",
            "confidence": "medium",
            "date_verified": True,
        }
        items.append(item)

    return items


def merge_items(existing_items: list[dict], new_items: list[dict]) -> list[dict]:
    by_id = {item.get("id"): item for item in existing_items if item.get("id")}

    # Evita duplicatas exatas dentro da mesma língua e jogo.
    exact_index = {}
    for item in existing_items:
        key = (item.get("game_id"), item.get("language"), normalize_title(item.get("title", "")), item.get("source", "").lower())
        exact_index[key] = item.get("id")

    for item in new_items:
        key = (item["game_id"], item["language"], normalize_title(item["title"]), item["source"].lower())
        existing_id = exact_index.get(key)

        if existing_id and existing_id in by_id:
            old = by_id[existing_id]
            preserved_status = old.get("status", "pending")
            preserved_discovered = old.get("discovered_at", item["discovered_at"])
            old.update(item)
            old["status"] = preserved_status
            old["discovered_at"] = preserved_discovered
            continue

        if item["id"] in by_id:
            old = by_id[item["id"]]
            preserved_status = old.get("status", "pending")
            preserved_discovered = old.get("discovered_at", item["discovered_at"])
            old.update(item)
            old["status"] = preserved_status
            old["discovered_at"] = preserved_discovered
        else:
            by_id[item["id"]] = item
            exact_index[key] = item["id"]

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    future_limit = now + timedelta(days=2)

    kept = []
    for item in by_id.values():
        raw_date = item.get("published_at")
        if not raw_date:
            continue

        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
        except Exception:
            continue

        if cutoff <= dt <= future_limit:
            kept.append(item)

    kept.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return kept


def main():
    games_cfg = load_yaml(CONFIG / "games.yml")
    locales_cfg = load_yaml(CONFIG / "locales.yml")
    official_cfg = load_yaml(CONFIG / "official_domains.yml")
    direct_cfg = load_yaml(CONFIG / "official_sources.yml")

    games = games_cfg["games"]
    discovery = games_cfg["discovery"]
    locales = locales_cfg["locales"]
    official_domains = official_cfg["official_domains"]

    # Carrega o estado anterior antes da coleta direta para reaproveitar resumos
    # já extraídos de páginas oficiais e evitar bater novamente nas mesmas URLs.
    existing = load_existing()
    summary_cache = {
        item.get("url"): item.get("excerpt", "")
        for item in existing.get("items", [])
        if item.get("collector") == "official-page"
        and item.get("url")
        and item.get("excerpt")
    }

    direct_items, direct_errors = collect_official_sources(
        direct_cfg["sources"],
        summary_cache=summary_cache,
    )
    collected = []

    for game in games:
        overrides = game.get("query_overrides", {})
        for locale in locales:
            query = overrides.get(locale["language"], game["query"])
            print(f"[GET] {game['name']} / {locale['id']}")
            collected.extend(collect_feed(game, locale, query, official_domains))
            time.sleep(REQUEST_PAUSE_SECONDS)

    discovery_game = {
        "id": discovery["id"],
        "name": discovery["name"],
    }
    official_domains.setdefault(discovery["id"], [])

    for locale in locales:
        query = discovery["queries"][locale["language"]]
        print(f"[GET] {discovery['name']} / {locale['id']}")
        collected.extend(collect_feed(discovery_game, locale, query, official_domains))
        time.sleep(REQUEST_PAUSE_SECONDS)

    # Itens oficiais diretos são reconstruídos em cada execução. Assim, erros
    # antigos de parsing (título/data/menu) não ficam presos por 45 dias.
    existing_items = [
        item for item in existing.get("items", [])
        if item.get("collector") != "official-page"
        and item.get("date_verified") is True
    ]
    items = merge_items(existing_items, direct_items + collected)

    payload = {
        "generated_at": now_iso(),
        "count": len(items),
        "collectors": {
            "official_page_items": len(direct_items),
            "google_news_items": len(collected),
            "official_source_errors": len(direct_errors),
        },
        "items": items,
    }

    DATA.parent.mkdir(parents=True, exist_ok=True)
    DOCS_DATA.parent.mkdir(parents=True, exist_ok=True)

    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    DATA.write_text(serialized + "\n", encoding="utf-8")
    DOCS_DATA.write_text(serialized + "\n", encoding="utf-8")

    health_payload = {
        "generated_at": now_iso(),
        "official_sources_configured": len(direct_cfg["sources"]),
        "official_sources_ok": len(direct_cfg["sources"]) - len(direct_errors),
        "official_sources_failed": len(direct_errors),
        "errors": direct_errors,
    }
    health_serialized = json.dumps(health_payload, ensure_ascii=False, indent=2)
    HEALTH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_HEALTH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH.write_text(health_serialized + "\n", encoding="utf-8")
    DOCS_HEALTH.write_text(health_serialized + "\n", encoding="utf-8")

    print(
        f"[OK] oficiais={len(direct_items)} google={len(collected)} "
        f"radar={len(items)} erros_oficiais={len(direct_errors)}"
    )


if __name__ == "__main__":
    main()
