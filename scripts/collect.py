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



CONTENT_RULES = {
    "lore": ["lore", "story", "stories", "narrative", "worldbuilding", "rathe", "história", "historia", "histoire", "récit", "物語", "ストーリー", "世界観", "剧情", "故事", "世界观"],
    "deck": ["deck", "decklist", "deck tech", "deckbuilding", "build", "archetype", "baralho", "lista", "mazo", "baraja", "デッキ", "デッキリスト", "卡组", "牌组"],
    "combo": ["combo", "combos", "synergy", "synergies", "interaction", "loop", "sinergia", "sinergias", "combinação", "combinación", "synergie", "コンボ", "シナジー", "连招", "组合"],
    "meta": ["meta", "metagame", "tier list", "matchup", "matchups", "competitive", "tournament", "world tour", "nationals", "regional", "campeonato", "competitivo", "torneio", "tournoi", "大会", "環境", "比赛", "环境"],
    "rules": ["rules", "ruling", "rulings", "judge", "faq", "errata", "comprehensive rules", "policy", "regra", "regras", "juiz", "reglas", "arbitraje", "règles", "juge", "ルール", "裁定", "规则", "裁定"],
    "rumor": ["rumor", "rumour", "leak", "leaked", "leaks", "unconfirmed", "vazamento", "vazou", "rumor", "filtración", "filtrado", "rumeur", "fuite", "噂", "リーク", "传闻", "泄露"],
    "speculation": ["speculation", "speculative", "theory", "prediction", "predict", "clues", "what if", "especulação", "teoria", "previsão", "especulación", "predicción", "théorie", "prévision", "考察", "予想", "推测", "预测"],
    "curiosity": ["trivia", "curiosity", "curiosities", "did you know", "fun fact", "curiosidade", "curiosidades", "curiosidad", "anecdote", "saviez-vous", "豆知識", "小知识", "冷知识"],
    "design": ["design", "designer", "development", "developer", "dev talk", "behind the scenes", "mechanic", "mechanics", "desenvolvimento", "designer", "mecânica", "diseño", "développement", "デザイン", "開発", "设计", "开发"],
    "market": ["price", "prices", "market", "finance", "buyout", "spike", "value", "preço", "mercado", "precio", "marché", "価格", "相場", "价格", "市场"],
    "industry": ["industry", "distribution", "distributor", "publisher", "licensing", "retailer", "indústria", "distribuição", "industria", "distribution", "業界", "流通", "行业", "发行"],
    "news": ["news", "announcement", "announced", "release", "released", "revealed", "update", "ban", "banned", "restricted", "launch", "product", "set", "new ", "notícia", "anúncio", "lançamento", "revelado", "atualização", "banido", "noticia", "anuncio", "lanzamiento", "nouveau", "annonce", "sortie", "ニュース", "発表", "発売", "新弾", "新闻", "公布", "发布", "新品"],
}

TYPE_PRIORITY = ["rumor", "speculation", "lore", "combo", "deck", "rules", "meta", "design", "curiosity", "market", "industry", "news"]
CORE_GAME_IDS = {"flesh-and-blood", "pokemon", "magic"}


def classify_content(item: dict) -> list[str]:
    text = normalize_title(" ".join([
        str(item.get("title", "")),
        str(item.get("excerpt", "")),
        str(item.get("source", "")),
    ]))
    types = []
    for hint in item.get("default_content_types", []) or []:
        if hint not in types:
            types.append(hint)
    for content_type, keywords in CONTENT_RULES.items():
        if any(normalize_title(keyword) in text for keyword in keywords):
            if content_type not in types:
                types.append(content_type)
    if not types:
        types = ["news"]
    return sorted(types, key=lambda x: TYPE_PRIORITY.index(x) if x in TYPE_PRIORITY else 999)


def enrich_item(item: dict) -> dict:
    item["content_types"] = classify_content(item)
    item["primary_type"] = item["content_types"][0] if item["content_types"] else "news"
    item["game_group"] = "principal" if item.get("game_id") in CORE_GAME_IDS else "outros"
    if not item.get("trust"):
        item["trust"] = "official" if item.get("official") else "media"
    item.pop("default_content_types", None)
    return item


def detect_game(text: str, games: list[dict]) -> tuple[str, str]:
    haystack = normalize_title(text)
    best = None
    for game in games:
        aliases = [game.get("name", ""), *game.get("aliases", [])]
        for alias in aliases:
            a = normalize_title(alias)
            if a and a in haystack:
                score = len(a)
                if not best or score > best[0]:
                    best = (score, game["id"], game["name"])
    if best:
        return best[1], best[2]
    return "novidades", "Novos TCGs"


def collect_independent_search(source: dict, locales: list[dict], games: list[dict]) -> list[dict]:
    locale_id = source.get("locale", "en-US")
    locale = next((loc for loc in locales if loc.get("id") == locale_id), None)
    if not locale:
        locale = next((loc for loc in locales if loc.get("language") == source.get("language")), locales[0])

    parsed = feedparser.parse(google_news_url(source["query"], locale))
    if getattr(parsed, "bozo", False) and not parsed.entries:
        print(f"[WARN] Fonte independente falhou: {source['name']}: {parsed.bozo_exception}", file=sys.stderr)
        return []

    out = []
    for entry in parsed.entries[:int(source.get("max_items", 20))]:
        title = strip_html(getattr(entry, "title", ""))
        if not title:
            continue
        published_at = parse_entry_date(entry)
        if not published_at:
            continue
        source_name, source_home = entry_source(entry)
        excerpt = strip_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))[:700]
        text = f"{title} {excerpt}"
        game_id = source.get("game_id")
        game_name = source.get("game")
        if not game_id:
            game_id, game_name = detect_game(text, games)
        link = normalize_space(getattr(entry, "link", ""))
        item = {
            "id": make_id(game_id, source.get("language", locale["language"]), title, source["name"], published_at),
            "game_id": game_id,
            "game": game_name,
            "language": source.get("language", locale["language"]),
            "locale": locale.get("id"),
            "region": source.get("region", locale.get("gl", "global").lower()),
            "title": title,
            "excerpt": excerpt,
            "url": link,
            "source": source.get("name") or source_name,
            "source_home": source_home,
            "source_domain": source.get("domain") or domain_of(source_home),
            "official": False,
            "published_at": published_at,
            "discovered_at": now_iso(),
            "status": "pending",
            "collector": "independent-search",
            "trust": source.get("trust", "media"),
            "confidence": "medium",
            "date_verified": True,
            "evergreen": bool(source.get("evergreen", False)),
            "retention_days": int(source.get("retention_days", 180)),
            "default_content_types": source.get("default_content_types", []),
        }
        out.append(item)
    return out

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
    future_limit = now + timedelta(days=2)

    kept = []
    for item in by_id.values():
        raw_date = item.get("published_at")

        # Conteúdo evergreen pode ser útil mesmo sem data estruturada.
        if not raw_date:
            if item.get("evergreen"):
                kept.append(enrich_item(item))
            continue

        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
        except Exception:
            continue

        retention = int(item.get("retention_days") or RETENTION_DAYS)
        cutoff = now - timedelta(days=retention)
        if cutoff <= dt <= future_limit:
            kept.append(enrich_item(item))

    kept.sort(
        key=lambda x: x.get("published_at") or x.get("discovered_at") or "",
        reverse=True,
    )
    return kept


def main():
    games_cfg = load_yaml(CONFIG / "games.yml")
    locales_cfg = load_yaml(CONFIG / "locales.yml")
    official_cfg = load_yaml(CONFIG / "official_domains.yml")
    direct_cfg = load_yaml(CONFIG / "official_sources.yml")
    independent_cfg = load_yaml(CONFIG / "independent_sources.yml")

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
        if item.get("collector") in {"official-page", "independent-page"}
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

    # Busca temática adicional para os três jogos principais: não só notícia,
    # mas também lore, decks, combos, rumores, especulação, regras e curiosidades.
    for game in games:
        if game.get("group") != "principal" or not game.get("content_query"):
            continue
        overrides = game.get("content_query_overrides", {})
        for locale in locales:
            query = overrides.get(locale["language"], game["content_query"])
            print(f"[CONTENT] {game['name']} / {locale['id']}")
            collected.extend(collect_feed(game, locale, query, official_domains))
            time.sleep(REQUEST_PAUSE_SECONDS)

    # Portais independentes: páginas especializadas e buscas por domínio.
    independent_items = []
    independent_errors = []
    page_sources = [s for s in independent_cfg.get("sources", []) if s.get("mode") == "page"]
    search_sources = [s for s in independent_cfg.get("sources", []) if s.get("mode") == "search"]

    if page_sources:
        page_items, page_errors = collect_official_sources(page_sources, summary_cache=summary_cache)
        independent_items.extend(page_items)
        independent_errors.extend(page_errors)

    for source in search_sources:
        print(f"[INDEPENDENT] {source['name']}")
        try:
            independent_items.extend(collect_independent_search(source, locales, games))
        except Exception as exc:
            independent_errors.append({
                "source_id": source.get("id"),
                "source": source.get("name"),
                "url": source.get("domain") or source.get("url"),
                "error": str(exc)[:400],
            })

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
        if item.get("collector") not in {"official-page", "independent-page"}
        and (item.get("date_verified") is True or item.get("evergreen"))
    ]
    items = merge_items(existing_items, direct_items + independent_items + collected)

    payload = {
        "generated_at": now_iso(),
        "count": len(items),
        "collectors": {
            "official_page_items": len(direct_items),
            "google_news_items": len(collected),
            "official_source_errors": len(direct_errors),
            "independent_items": len(independent_items),
            "independent_source_errors": len(independent_errors),
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
        "independent_sources_configured": len(independent_cfg.get("sources", [])),
        "independent_sources_failed": len(independent_errors),
        "errors": direct_errors + independent_errors,
    }
    health_serialized = json.dumps(health_payload, ensure_ascii=False, indent=2)
    HEALTH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_HEALTH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH.write_text(health_serialized + "\n", encoding="utf-8")
    DOCS_HEALTH.write_text(health_serialized + "\n", encoding="utf-8")

    print(
        f"[OK] oficiais={len(direct_items)} independentes={len(independent_items)} "
        f"google={len(collected)} radar={len(items)} "
        f"erros={len(direct_errors) + len(independent_errors)}"
    )


if __name__ == "__main__":
    main()
