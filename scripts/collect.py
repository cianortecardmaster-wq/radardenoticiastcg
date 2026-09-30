#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlencode, urljoin, urlparse

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

from collect_official import collect_official_sources

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
DATA = ROOT / "data" / "news.json"
DOCS_DATA = ROOT / "docs" / "data" / "news.json"
HEALTH = ROOT / "data" / "collector-health.json"
DOCS_HEALTH = ROOT / "docs" / "data" / "collector-health.json"
MEDIA_DATA = ROOT / "data" / "media.json"
DOCS_MEDIA_DATA = ROOT / "docs" / "data" / "media.json"

MAX_ITEMS_PER_FEED = 15
MAX_MEDIA_ITEMS_PER_SOURCE = 12
RETENTION_DAYS = 7
REQUEST_PAUSE_SECONDS = 0.08
FUTURE_TOLERANCE_HOURS = 6


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
    if dt > datetime.now(timezone.utc) + timedelta(hours=FUTURE_TOLERANCE_HOURS):
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
    "art": ["fan art", "fanart", "artwork", "illustration", "alter", "altered", "painted", "painting", "artist", "playmat", "sleeves", "token art", "cosplay", "arte", "ilustração", "ilustracao", "pintura"],
    "meme": ["meme", "memes", "humor", "funny", "joke", "shitpost", "circlejerk", "comedy", "engraçado", "engracado", "piada"],
    "play": ["gameplay", "game play", "play of the", "crazy play", "misplay", "lethal", "damage", "match video", "game review", "how would you play", "jogada", "partida", "turno"],
    "discussion": ["discussion", "question", "thoughts", "what do you think", "hot take", "debate", "opinion", "opinião", "opiniao", "discussão", "discussao", "pergunta"],
    "video": ["video", "clip", "shorts", "youtube", "twitch", "stream", "livestream", "reel", "vídeo", "clipe", "live"],
    "community": ["community", "armory", "local game store", "lgs", "meetup", "fan friday", "content creator", "creator spotlight", "community corner", "comunidade", "evento local", "criador"],
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

TYPE_PRIORITY = ["meme", "art", "play", "video", "discussion", "community", "rumor", "speculation", "lore", "combo", "deck", "rules", "meta", "design", "curiosity", "market", "industry", "news"]
CORE_GAME_IDS = {"flesh-and-blood", "pokemon", "magic"}


def classify_content(item: dict) -> list[str]:
    text = normalize_title(" ".join([
        str(item.get("title", "")),
        str(item.get("excerpt", "")),
        str(item.get("source", "")),
        str(item.get("reddit_flair", "")),
        str(item.get("media_kind", "")),
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


def _reddit_preview(data: dict) -> str:
    preview = data.get("preview") or {}
    images = preview.get("images") or []
    if images:
        src = ((images[0] or {}).get("source") or {}).get("url") or ""
        if src:
            return html.unescape(src)
    thumb = data.get("thumbnail") or ""
    if isinstance(thumb, str) and thumb.startswith(("http://", "https://")):
        return html.unescape(thumb)
    return ""


def _reddit_hints(data: dict, source: dict) -> list[str]:
    hints = list(source.get("default_content_types", []) or [])
    flair = normalize_title(data.get("link_flair_text") or "")
    title = normalize_title(data.get("title") or "")
    domain = (data.get("domain") or "").lower()
    post_hint = (data.get("post_hint") or "").lower()
    text = f"{flair} {title}"

    def add(kind: str):
        if kind not in hints:
            hints.append(kind)

    if "meme" in text or "humor" in text or "shitpost" in text or "circlejerk" in source.get("subreddit", "").lower():
        add("meme")
    if any(k in text for k in ["fan art", "fanart", "alter", "artwork", "art project", "painted", "painting", "playmat", "cosplay"]):
        add("art")
    if any(k in text for k in ["discussion", "question", "thoughts", "what do you think", "hot take"]):
        add("discussion")
    if any(k in text for k in ["gameplay", "how would you play", "crazy play", "misplay", "lethal", "damage", "match"]):
        add("play")
    if post_hint in {"hosted:video", "rich:video"} or data.get("is_video") or domain in {"youtube.com", "youtu.be", "twitch.tv", "clips.twitch.tv"}:
        add("video")
    return hints


def collect_reddit_source(source: dict) -> list[dict]:
    subreddit = source["subreddit"]
    max_items = int(source.get("max_items", 60))
    sorts = source.get("sorts", ["new", "top"])
    time_filter = source.get("time_filter", "week")
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    future_limit = datetime.now(timezone.utc) + timedelta(hours=FUTURE_TOLERANCE_HOURS)
    headers = {"User-Agent": "CCMaster-TCGRadar/1.0 (+https://github.com/)"}
    by_post = {}

    def add_json_post(data: dict):
        post_id = data.get("id")
        title = normalize_space(data.get("title") or "")
        if not post_id or not title or data.get("over_18"):
            return
        try:
            dt = datetime.fromtimestamp(float(data.get("created_utc")), tz=timezone.utc)
        except Exception:
            return
        if not (cutoff <= dt <= future_limit):
            return

        permalink = data.get("permalink") or ""
        reddit_url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink
        outbound = data.get("url_overridden_by_dest") or data.get("url") or reddit_url
        excerpt = normalize_space(data.get("selftext") or "")[:700]
        flair = normalize_space(data.get("link_flair_text") or "")
        score = int(data.get("score") or 0)
        comments = int(data.get("num_comments") or 0)
        hints = _reddit_hints(data, source)
        preview = _reddit_preview(data)
        media_kind = "video" if "video" in hints else ("image" if preview else "post")
        published_at = dt.isoformat()
        item = {
            "id": make_id(source["game_id"], source.get("language", "en"), title, source["name"], published_at),
            "game_id": source["game_id"],
            "game": source["game"],
            "language": source.get("language", "en"),
            "locale": source.get("locale", "en-US"),
            "region": source.get("region", "global"),
            "title": title,
            "excerpt": excerpt,
            "url": reddit_url or outbound,
            "outbound_url": outbound,
            "source": source["name"],
            "source_home": f"https://www.reddit.com/r/{subreddit}/",
            "source_domain": "reddit.com",
            "official": False,
            "published_at": published_at,
            "discovered_at": now_iso(),
            "status": "pending",
            "collector": "reddit-json",
            "trust": source.get("trust", "community"),
            "confidence": "high",
            "date_verified": True,
            "retention_days": RETENTION_DAYS,
            "default_content_types": hints,
            "reddit_flair": flair,
            "author": data.get("author") or "",
            "score": score,
            "num_comments": comments,
            "engagement_score": score + comments * 2,
            "image_url": preview,
            "media_kind": media_kind,
        }
        old = by_post.get(post_id)
        if not old or item["engagement_score"] >= old.get("engagement_score", 0):
            by_post[post_id] = item

    def add_rss_entry(entry):
        title = strip_html(getattr(entry, "title", ""))
        published_at = parse_entry_date(entry)
        link = normalize_space(getattr(entry, "link", ""))
        if not title or not published_at or not link:
            return
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if not (cutoff <= dt <= future_limit):
            return
        summary_html = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        excerpt = strip_html(summary_html)[:700]
        soup = BeautifulSoup(summary_html, "html.parser")
        img = soup.find("img")
        image_url = html.unescape(img.get("src", "")) if img and img.get("src") else ""
        entry_id = normalize_space(getattr(entry, "id", "")) or link
        hints = list(source.get("default_content_types", []) or [])
        text = normalize_title(f"{title} {excerpt}")
        if "meme" in text or "circlejerk" in subreddit.lower():
            hints.append("meme") if "meme" not in hints else None
        if any(k in text for k in ["fan art", "fanart", "alter", "artwork", "painted", "playmat", "cosplay"]):
            hints.append("art") if "art" not in hints else None
        if any(k in text for k in ["gameplay", "how would you play", "misplay", "lethal", "damage"]):
            hints.append("play") if "play" not in hints else None
        if any(k in text for k in ["discussion", "question", "thoughts", "hot take"]):
            hints.append("discussion") if "discussion" not in hints else None
        if any(k in text for k in ["youtube", "twitch", "video", "clip", "stream"]):
            hints.append("video") if "video" not in hints else None
        item = {
            "id": make_id(source["game_id"], source.get("language", "en"), title, source["name"], published_at),
            "game_id": source["game_id"], "game": source["game"],
            "language": source.get("language", "en"), "locale": source.get("locale", "en-US"),
            "region": source.get("region", "global"), "title": title, "excerpt": excerpt,
            "url": link, "source": source["name"], "source_home": f"https://www.reddit.com/r/{subreddit}/",
            "source_domain": "reddit.com", "official": False, "published_at": published_at,
            "discovered_at": now_iso(), "status": "pending", "collector": "reddit-rss",
            "trust": source.get("trust", "community"), "confidence": "medium", "date_verified": True,
            "retention_days": RETENTION_DAYS, "default_content_types": hints,
            "image_url": image_url, "media_kind": "image" if image_url else "post",
            "score": 0, "num_comments": 0, "engagement_score": 0,
        }
        by_post.setdefault(entry_id, item)

    for sort in sorts:
        params = {"limit": min(max_items, 100), "raw_json": 1}
        if sort == "top":
            params["t"] = time_filter
        json_url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        try:
            response = requests.get(json_url, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            listing = response.json().get("data", {}).get("children", [])
            for child in listing:
                add_json_post(child.get("data") or {})
        except Exception as json_exc:
            rss_url = f"https://www.reddit.com/r/{subreddit}/{sort}/.rss"
            rss_params = {"t": time_filter} if sort == "top" else {}
            try:
                response = requests.get(rss_url, params=rss_params, headers=headers, timeout=20)
                response.raise_for_status()
                parsed = feedparser.parse(response.content)
                for entry in parsed.entries[:max_items]:
                    add_rss_entry(entry)
                print(f"[WARN] Reddit JSON falhou; RSS usado em r/{subreddit}/{sort}: {json_exc}", file=sys.stderr)
            except Exception as rss_exc:
                print(f"[WARN] Reddit falhou em r/{subreddit}/{sort}: JSON={json_exc}; RSS={rss_exc}", file=sys.stderr)
        time.sleep(REQUEST_PAUSE_SECONDS)

    return list(by_post.values())

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
    future_limit = now + timedelta(hours=FUTURE_TOLERANCE_HOURS)

    kept = []
    for item in by_id.values():
        raw_date = item.get("published_at")

        # O radar de novidades só exibe conteúdo com data de publicação verificável.
        # Fontes evergreen continuam configuradas como referência, mas não entram
        # na lista recente se não houver uma data confiável.
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

        # A vitrine é deliberadamente curta: somente publicações dos últimos 7 dias.
        # Valores maiores em fontes antigas servem apenas como metadado histórico e
        # não podem fazer conteúdo velho reaparecer como novidade.
        retention = min(int(item.get("retention_days") or RETENTION_DAYS), RETENTION_DAYS)
        cutoff = now - timedelta(days=retention)
        if cutoff <= dt <= future_limit:
            kept.append(enrich_item(item))

    kept.sort(
        key=lambda x: x.get("published_at") or x.get("discovered_at") or "",
        reverse=True,
    )
    return kept



def media_source_id(source: dict) -> str:
    seed = "|".join([
        str(source.get("game_id", "")),
        str(source.get("platform", "")),
        str(source.get("name", "")),
    ])
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def load_existing_media() -> dict:
    if not MEDIA_DATA.exists():
        return {"generated_at": None, "count": 0, "sources": []}
    try:
        return json.loads(MEDIA_DATA.read_text(encoding="utf-8"))
    except Exception:
        return {"generated_at": None, "count": 0, "sources": []}


def within_recent_window(value: str | None, days: int = RETENTION_DAYS) -> bool:
    if not value:
        return False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
    except Exception:
        return False
    now = datetime.now(timezone.utc)
    return now - timedelta(days=days) <= dt <= now + timedelta(hours=FUTURE_TOLERANCE_HOURS)


def media_item_id(source_id: str, url: str, title: str) -> str:
    seed = f"{source_id}|{url}|{normalize_title(title)}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]


def extract_text_field(value) -> str:
    if isinstance(value, dict):
        if value.get("simpleText"):
            return normalize_space(str(value["simpleText"]))
        runs = value.get("runs") or []
        return normalize_space("".join(str(run.get("text", "")) for run in runs if isinstance(run, dict)))
    return normalize_space(str(value or ""))


def iter_nested_values(obj, wanted_key: str):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == wanted_key:
                yield value
            yield from iter_nested_values(value, wanted_key)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_nested_values(value, wanted_key)


def extract_balanced_json(text: str, marker: str):
    idx = text.find(marker)
    if idx < 0:
        return None
    start = text.find("{", idx + len(marker))
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for pos in range(start, len(text)):
        ch = text[pos]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:pos + 1])
                except Exception:
                    return None
    return None


def youtube_initial_data(html_text: str):
    for marker in ("var ytInitialData =", "ytInitialData =", 'window["ytInitialData"] ='):
        data = extract_balanced_json(html_text, marker)
        if data:
            return data
    match = re.search(r'"ytInitialData"\s*:\s*', html_text)
    if match:
        return extract_balanced_json(html_text[match.start():], '"ytInitialData"')
    return None


def name_similarity(a: str, b: str) -> float:
    a_norm = re.sub(r"[^a-z0-9]+", " ", normalize_title(a)).strip()
    b_norm = re.sub(r"[^a-z0-9]+", " ", normalize_title(b)).strip()
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 1.0
    if a_norm in b_norm or b_norm in a_norm:
        return 0.92
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def youtube_search_query(source: dict) -> str:
    if source.get("search_query"):
        return str(source["search_query"])
    configured_url = str(source.get("url") or "")
    try:
        params = parse_qs(urlparse(configured_url).query)
        if params.get("search_query"):
            return str(params["search_query"][0]).replace("+", " ").strip()
    except Exception:
        pass
    game = "Flesh and Blood" if source.get("game_id") == "flesh-and-blood" else "Magic MTG"
    return f"{source.get('name', '')} {game}".strip()


def resolve_youtube_channel(source: dict, previous: dict | None = None) -> tuple[str | None, str | None, str | None]:
    previous = previous or {}
    cached_id = source.get("youtube_channel_id") or previous.get("resolved_channel_id")
    if cached_id:
        channel_id = str(cached_id).strip()
        return channel_id, f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}", f"https://www.youtube.com/channel/{channel_id}"

    configured_url = str(source.get("channel_url") or source.get("url") or "")
    channel_match = re.search(r"youtube\.com/channel/(UC[\w-]+)", configured_url)
    if channel_match:
        channel_id = channel_match.group(1)
        return channel_id, f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}", configured_url

    direct_url = configured_url if "youtube.com/" in configured_url and "/results?" not in configured_url else ""
    if direct_url:
        try:
            response = requests.get(direct_url, headers={"User-Agent": "Mozilla/5.0 TCG-Radar/1.0"}, timeout=20)
            response.raise_for_status()
            for pattern in (r'"channelId":"(UC[\w-]+)"', r'"externalId":"(UC[\w-]+)"', r'"browseId":"(UC[\w-]+)"'):
                match = re.search(pattern, response.text)
                if match:
                    channel_id = match.group(1)
                    return channel_id, f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}", direct_url
        except Exception:
            pass

    query = youtube_search_query(source)
    search_url = "https://www.youtube.com/results?" + urlencode({"search_query": query, "hl": "en"})
    response = requests.get(search_url, headers={"User-Agent": "Mozilla/5.0 TCG-Radar/1.0", "Accept-Language": "en-US,en;q=0.8"}, timeout=20)
    response.raise_for_status()
    initial = youtube_initial_data(response.text)
    candidates = []
    if initial:
        for renderer in iter_nested_values(initial, "channelRenderer"):
            if not isinstance(renderer, dict):
                continue
            channel_id = renderer.get("channelId") or (renderer.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId"))
            title = extract_text_field(renderer.get("title"))
            if channel_id and str(channel_id).startswith("UC"):
                candidates.append((name_similarity(source.get("name", ""), title), str(channel_id), title))
    if not candidates:
        # Fallback para mudanças menores no HTML do YouTube.
        for match in re.finditer(r'"channelId":"(UC[\w-]+)"', response.text):
            candidates.append((0.25, match.group(1), ""))
            if len(candidates) >= 5:
                break
    if not candidates:
        return None, None, None
    candidates.sort(key=lambda row: row[0], reverse=True)
    score, channel_id, _ = candidates[0]
    if score < 0.35 and len(candidates) > 1:
        return None, None, None
    return channel_id, f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}", f"https://www.youtube.com/channel/{channel_id}"


def parse_relative_youtube_time(value: str) -> str | None:
    text = normalize_space(value).lower()
    text = re.sub(r"^(streamed|premiered)\s+", "", text)
    if text in {"today", "just now"}:
        return now_iso()
    match = re.search(r"(\d+)\s+(minute|hour|day|week)s?\s+ago", text)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    delta = {
        "minute": timedelta(minutes=amount),
        "hour": timedelta(hours=amount),
        "day": timedelta(days=amount),
        "week": timedelta(weeks=amount),
    }[unit]
    dt = datetime.now(timezone.utc) - delta
    return dt.isoformat()


def youtube_search_recent_items(source: dict, source_id: str, strict_owner: bool = True) -> list[dict]:
    query = youtube_search_query(source)
    search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp=CAI%253D&hl=en"
    response = requests.get(search_url, headers={"User-Agent": "Mozilla/5.0 TCG-Radar/1.0", "Accept-Language": "en-US,en;q=0.8"}, timeout=20)
    response.raise_for_status()
    initial = youtube_initial_data(response.text)
    if not initial:
        return []
    items = []
    for renderer in iter_nested_values(initial, "videoRenderer"):
        if not isinstance(renderer, dict):
            continue
        video_id = renderer.get("videoId")
        title = extract_text_field(renderer.get("title"))
        owner = extract_text_field(renderer.get("ownerText") or renderer.get("longBylineText"))
        relative = extract_text_field(renderer.get("publishedTimeText"))
        published_at = parse_relative_youtube_time(relative)
        if not video_id or not title or not published_at or not within_recent_window(published_at):
            continue
        if strict_owner and owner and name_similarity(source.get("name", ""), owner) < 0.42:
            continue
        thumbs = ((renderer.get("thumbnail") or {}).get("thumbnails") or [])
        image_url = thumbs[-1].get("url") if thumbs and isinstance(thumbs[-1], dict) else ""
        url = f"https://www.youtube.com/watch?v={video_id}"
        items.append({
            "id": media_item_id(source_id, url, title),
            "title": title,
            "url": url,
            "published_at": published_at,
            "image_url": image_url,
            "kind": "video",
            "content_platform": "youtube",
            "author": owner or source.get("name", ""),
        })
        if len(items) >= MAX_MEDIA_ITEMS_PER_SOURCE:
            break
    return items


def feed_entry_thumbnail(entry) -> str:
    for attr in ("media_thumbnail", "media_content"):
        values = getattr(entry, attr, None) or []
        if values and isinstance(values[0], dict) and values[0].get("url"):
            return str(values[0]["url"])
    image = getattr(entry, "image", None)
    if isinstance(image, dict) and image.get("href"):
        return str(image["href"])
    return ""


def collect_feed_recent_items(feed_url: str, source: dict, source_id: str, kind: str, content_platform: str) -> list[dict]:
    response = requests.get(feed_url, headers={"User-Agent": "Mozilla/5.0 TCG-Radar/1.0"}, timeout=20)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        raise RuntimeError(str(getattr(parsed, "bozo_exception", "feed inválido")))
    items = []
    for entry in parsed.entries[:40]:
        title = strip_html(getattr(entry, "title", ""))
        url = normalize_space(getattr(entry, "link", ""))
        published_at = parse_entry_date(entry)
        if not title or not url or not published_at or not within_recent_window(published_at):
            continue
        items.append({
            "id": media_item_id(source_id, url, title),
            "title": title,
            "url": url,
            "published_at": published_at,
            "image_url": feed_entry_thumbnail(entry),
            "kind": kind,
            "content_platform": content_platform,
            "author": normalize_space(getattr(entry, "author", "")) or source.get("name", ""),
            "excerpt": strip_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))[:360],
        })
        if len(items) >= MAX_MEDIA_ITEMS_PER_SOURCE:
            break
    items.sort(key=lambda item: item["published_at"], reverse=True)
    return items


def discover_rss_from_page(url: str) -> str | None:
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 TCG-Radar/1.0"}, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel") or []).lower()
        mime = str(link.get("type") or "").lower()
        href = str(link.get("href") or "")
        if href and "alternate" in rel and any(token in mime for token in ("rss", "atom", "xml")):
            return urljoin(url, href)
    return None


def resolve_podcast_feed(source: dict, previous: dict | None = None) -> str | None:
    previous = previous or {}
    if source.get("feed_url"):
        return str(source["feed_url"])
    if previous.get("resolved_feed_url"):
        return str(previous["resolved_feed_url"])
    url = str(source.get("url") or "")
    apple_match = re.search(r"podcasts\.apple\.com/.+?/id(\d+)", url)
    if apple_match:
        lookup = requests.get(
            "https://itunes.apple.com/lookup",
            params={"id": apple_match.group(1), "entity": "podcast"},
            headers={"User-Agent": "Mozilla/5.0 TCG-Radar/1.0"},
            timeout=20,
        )
        lookup.raise_for_status()
        results = lookup.json().get("results") or []
        if results and results[0].get("feedUrl"):
            return str(results[0]["feedUrl"])
    host = domain_of(url)
    if host.endswith("podbean.com"):
        slug = host.split(".")[0]
        candidate = f"https://feed.podbean.com/{slug}/feed.xml"
        try:
            test = requests.get(candidate, headers={"User-Agent": "Mozilla/5.0 TCG-Radar/1.0"}, timeout=20)
            if test.ok and ("xml" in test.headers.get("content-type", "").lower() or "<rss" in test.text[:1000].lower()):
                return candidate
        except Exception:
            pass
    try:
        return discover_rss_from_page(url)
    except Exception:
        return None


def twitch_login_from_source(source: dict) -> str | None:
    if source.get("twitch_login"):
        return str(source["twitch_login"]).strip().lstrip("@").lower()
    url = str(source.get("url") or "")
    parsed = urlparse(url)
    if "twitch.tv" in (parsed.hostname or "") and parsed.path and not parsed.path.startswith("/search"):
        first = parsed.path.strip("/").split("/")[0]
        if first and first not in {"directory", "videos"}:
            return first.lower()
    return None


def parse_twitch_video_page(video_id: str, source: dict, source_id: str) -> dict | None:
    url = f"https://www.twitch.tv/videos/{video_id}"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 TCG-Radar/1.0"}, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    title = ""
    image_url = ""
    published_at = None
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or script.get_text() or "{}")
        except Exception:
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("@type", "")).lower() in {"videoobject", "broadcastEvent".lower()} or candidate.get("uploadDate"):
                title = normalize_space(str(candidate.get("name") or title))
                raw_thumb = candidate.get("thumbnailUrl")
                if isinstance(raw_thumb, list):
                    image_url = str(raw_thumb[0]) if raw_thumb else image_url
                elif raw_thumb:
                    image_url = str(raw_thumb)
                raw_date = candidate.get("uploadDate") or candidate.get("datePublished") or candidate.get("startDate")
                if raw_date:
                    try:
                        dt = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        published_at = dt.astimezone(timezone.utc).isoformat()
                    except Exception:
                        pass
    if not title:
        meta = soup.find("meta", attrs={"property": "og:title"})
        title = normalize_space(meta.get("content", "")) if meta else ""
    if not image_url:
        meta = soup.find("meta", attrs={"property": "og:image"})
        image_url = normalize_space(meta.get("content", "")) if meta else ""
    if not published_at:
        for pattern in (r'"publishedAt":"([^"]+)"', r'"createdAt":"([^"]+)"', r'"uploadDate":"([^"]+)"'):
            match = re.search(pattern, response.text)
            if match:
                try:
                    dt = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    published_at = dt.astimezone(timezone.utc).isoformat()
                    break
                except Exception:
                    pass
    if not title or not published_at or not within_recent_window(published_at):
        return None
    return {
        "id": media_item_id(source_id, url, title),
        "title": title,
        "url": url,
        "published_at": published_at,
        "image_url": image_url,
        "kind": "vod",
        "content_platform": "twitch",
        "author": source.get("name", ""),
    }


def collect_twitch_recent_items(source: dict, source_id: str) -> tuple[list[dict], str | None]:
    login = twitch_login_from_source(source)
    if not login:
        return [], None
    videos_url = f"https://www.twitch.tv/{login}/videos?filter=archives&sort=time"
    response = requests.get(videos_url, headers={"User-Agent": "Mozilla/5.0 TCG-Radar/1.0"}, timeout=20)
    response.raise_for_status()
    ids = []
    for match in re.finditer(r'(?:twitch\.tv/videos/|/videos/)(\d+)', response.text):
        vid = match.group(1)
        if vid not in ids:
            ids.append(vid)
        if len(ids) >= min(MAX_MEDIA_ITEMS_PER_SOURCE, 6):
            break
    items = []
    for vid in ids:
        try:
            item = parse_twitch_video_page(vid, source, source_id)
            if item:
                items.append(item)
        except Exception:
            continue
        time.sleep(REQUEST_PAUSE_SECONDS)
    items.sort(key=lambda item: item["published_at"], reverse=True)
    return items, f"https://www.twitch.tv/{login}"


def collect_media_source(source: dict, previous: dict | None = None) -> tuple[dict, str | None]:
    previous = previous or {}
    source_id = media_source_id(source)
    result = dict(source)
    result["id"] = source_id
    result["recent_items"] = []
    result["last_checked_at"] = now_iso()
    result["resolved_url"] = previous.get("resolved_url") or source.get("url")
    result["resolved_feed_url"] = previous.get("resolved_feed_url")
    result["resolved_channel_id"] = previous.get("resolved_channel_id")
    error = None

    try:
        platform = source.get("platform")
        url = str(source.get("url") or "")
        if platform == "youtube":
            channel_id, feed_url, channel_url = resolve_youtube_channel(source, previous)
            result["resolved_channel_id"] = channel_id
            result["resolved_feed_url"] = feed_url
            result["resolved_url"] = channel_url or source.get("url")
            if feed_url:
                result["recent_items"] = collect_feed_recent_items(feed_url, source, source_id, "video", "youtube")
            else:
                result["recent_items"] = youtube_search_recent_items(source, source_id, strict_owner=True)
        elif platform == "podcast" and "youtube.com" in url:
            # Muitos podcasts da configuração são encontrados pelo próprio canal do YouTube.
            # A busca é restrita ao nome do programa e ordenada por data; não exigimos que
            # o nome do canal seja idêntico ao nome do podcast (ex.: Drive to Work).
            result["recent_items"] = youtube_search_recent_items(source, source_id, strict_owner=False)
            result["resolved_url"] = source.get("url")
        elif platform == "podcast":
            feed_url = resolve_podcast_feed(source, previous)
            result["resolved_feed_url"] = feed_url
            if feed_url:
                result["recent_items"] = collect_feed_recent_items(feed_url, source, source_id, "episode", "podcast")
            else:
                raise RuntimeError("feed do podcast não localizado")
        elif platform == "twitch":
            recent, channel_url = collect_twitch_recent_items(source, source_id)
            result["recent_items"] = recent
            if channel_url:
                result["resolved_url"] = channel_url
        else:
            result["recent_items"] = []
    except Exception as exc:
        error = str(exc)[:400]
        # Se uma fonte falhar temporariamente, preserva somente itens antigos que ainda
        # estejam dentro da janela de sete dias. Conteúdo vencido nunca reaparece.
        result["recent_items"] = [
            item for item in (previous.get("recent_items") or [])
            if within_recent_window(item.get("published_at"))
        ][:MAX_MEDIA_ITEMS_PER_SOURCE]

    result["recent_items"] = [item for item in result.get("recent_items", []) if within_recent_window(item.get("published_at"))]
    result["recent_items"].sort(key=lambda item: item.get("published_at") or "", reverse=True)
    result["recent_items"] = result["recent_items"][:MAX_MEDIA_ITEMS_PER_SOURCE]
    result["recent_count"] = len(result["recent_items"])
    result["latest_published_at"] = result["recent_items"][0]["published_at"] if result["recent_items"] else None
    if error:
        result["last_error"] = error
    else:
        result.pop("last_error", None)
    return result, error


def write_media_catalog() -> dict:
    path = CONFIG / "media_sources.yml"
    if not path.exists():
        return {"configured": 0, "active": 0, "items": 0, "errors": []}
    cfg = load_yaml(path) or {}
    sources = cfg.get("sources", [])
    previous_payload = load_existing_media()
    previous_by_id = {item.get("id") or media_source_id(item): item for item in previous_payload.get("sources", [])}

    enriched_sources = []
    errors = []
    for index, source in enumerate(sources, start=1):
        source_id = media_source_id(source)
        print(f"[MEDIA {index}/{len(sources)}] {source.get('name')} / {source.get('platform')}")
        enriched, error = collect_media_source(source, previous_by_id.get(source_id))
        enriched_sources.append(enriched)
        if error:
            errors.append({
                "source_id": source_id,
                "source": source.get("name"),
                "platform": source.get("platform"),
                "error": error,
            })
        time.sleep(REQUEST_PAUSE_SECONDS)

    enriched_sources.sort(
        key=lambda item: (
            item.get("latest_published_at") or "",
            item.get("name") or "",
        ),
        reverse=True,
    )
    total_items = sum(len(item.get("recent_items") or []) for item in enriched_sources)
    active_sources = sum(1 for item in enriched_sources if item.get("recent_items"))
    payload = {
        "generated_at": now_iso(),
        "window_days": RETENTION_DAYS,
        "count": len(enriched_sources),
        "active_count": active_sources,
        "content_count": total_items,
        "content_ready": True,
        "errors_count": len(errors),
        "sources": enriched_sources,
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    MEDIA_DATA.parent.mkdir(parents=True, exist_ok=True)
    DOCS_MEDIA_DATA.parent.mkdir(parents=True, exist_ok=True)
    MEDIA_DATA.write_text(serialized, encoding="utf-8")
    DOCS_MEDIA_DATA.write_text(serialized, encoding="utf-8")
    return {
        "configured": len(enriched_sources),
        "active": active_sources,
        "items": total_items,
        "errors": errors,
    }


def main():
    media_stats = write_media_catalog()

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
    reddit_sources = [s for s in independent_cfg.get("sources", []) if s.get("mode") == "reddit"]

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

    reddit_items = []
    for source in reddit_sources:
        print(f"[REDDIT] {source['name']}")
        try:
            found = collect_reddit_source(source)
            reddit_items.extend(found)
            independent_items.extend(found)
        except Exception as exc:
            independent_errors.append({
                "source_id": source.get("id"),
                "source": source.get("name"),
                "url": f"https://www.reddit.com/r/{source.get('subreddit', '')}/",
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
            "reddit_items": len(reddit_items),
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
        "media_sources_configured": media_stats.get("configured", 0),
        "media_sources_active_7d": media_stats.get("active", 0),
        "media_items_7d": media_stats.get("items", 0),
        "media_sources_failed": len(media_stats.get("errors", [])),
        "errors": direct_errors + independent_errors + media_stats.get("errors", []),
    }
    health_serialized = json.dumps(health_payload, ensure_ascii=False, indent=2)
    HEALTH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_HEALTH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH.write_text(health_serialized + "\n", encoding="utf-8")
    DOCS_HEALTH.write_text(health_serialized + "\n", encoding="utf-8")

    print(
        f"[OK] oficiais={len(direct_items)} independentes={len(independent_items)} "
        f"google={len(collected)} radar={len(items)} "
        f"mídia_7d={media_stats.get('items', 0)} "
        f"erros={len(direct_errors) + len(independent_errors) + len(media_stats.get('errors', []))}"
    )


if __name__ == "__main__":
    main()
