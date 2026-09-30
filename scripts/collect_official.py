from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; TCGNewsRadar/1.0; +https://github.com/)"

NAV_WORDS = {
    "home", "news", "events", "products", "cards", "rules", "about", "shop",
    "contact", "more", "read more", "learn more", "view all", "see all",
    "inicio", "início", "notícias", "eventos", "produtos", "saiba mais",
    "ニュース", "商品", "イベント", "查看更多", "最新资讯",
}

MONTHS = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,"sep":9,"sept":9,
    "oct":10,"nov":11,"dec":12,
}

DATE_YMD = re.compile(r"\b(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\b")
DATE_DMY = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b")
DATE_CJK = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")
DATE_EN = re.compile(r"\b(" + "|".join(MONTHS) + r")\.?\s+(\d{1,2}),?\s+(20\d{2})\b", re.I)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()

def normalize_title(value):
    return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", " ", clean(value).lower()).strip()

def parse_date(text):
    text = clean(text)
    for rx, order in ((DATE_YMD,"ymd"), (DATE_DMY,"dmy"), (DATE_CJK,"ymd")):
        m = rx.search(text)
        if m:
            a,b,c = map(int, m.groups())
            y,mo,d = (a,b,c) if order=="ymd" else (c,b,a)
            try:
                return datetime(y,mo,d,tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
    m = DATE_EN.search(text)
    if m:
        try:
            return datetime(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)), tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return None

def same_site(a, b):
    ha = (urlparse(a).hostname or "").lower().removeprefix("www.")
    hb = (urlparse(b).hostname or "").lower().removeprefix("www.")
    return ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha)

def stable_id(source_id, url, title):
    seed = f"{source_id}|{urldefrag(url)[0]}|{normalize_title(title)}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]

def candidate_text(anchor):
    own = clean(anchor.get_text(" ", strip=True))
    if own and own.lower() not in NAV_WORDS and len(own) >= 12:
        return own
    parent = anchor
    for _ in range(4):
        parent = getattr(parent, "parent", None)
        if parent is None:
            break
        text = clean(parent.get_text(" ", strip=True))
        if 18 <= len(text) <= 420:
            return text
    return own

def context_text(anchor):
    parent = anchor
    chunks = []
    for _ in range(3):
        parent = getattr(parent, "parent", None)
        if parent is None:
            break
        chunks.append(clean(parent.get_text(" ", strip=True)))
    return " ".join(chunks)[:1200]

def collect_source(source):
    r = requests.get(
        source["url"],
        headers={"User-Agent": USER_AGENT, "Accept-Language": source.get("language","en")},
        timeout=int(source.get("timeout", 20)),
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    include_re = re.compile(source.get("include_path_regex", "."), re.I)
    seen, candidates = set(), []

    for a in soup.find_all("a", href=True):
        href = clean(a.get("href", ""))
        if not href or href.startswith(("#","javascript:","mailto:","tel:")):
            continue

        url = urldefrag(urljoin(source["url"], href))[0]
        if not same_site(source["url"], url):
            continue

        parsed = urlparse(url)
        if not include_re.search(parsed.path + (("?" + parsed.query) if parsed.query else "")):
            continue
        if url in seen or url.rstrip("/") == source["url"].rstrip("/"):
            continue

        title = candidate_text(a)
        if len(title) < 12 or title.lower().strip(" .:-") in NAV_WORDS:
            continue

        context = context_text(a)
        published = parse_date(context)
        score = 5 + (3 if published else 0) + (2 if 18 <= len(title) <= 180 else 0)
        candidates.append((score, published or "", title, url))
        seen.add(url)

    candidates.sort(key=lambda x:(x[1],x[0]), reverse=True)

    out = []
    for score, published, title, url in candidates[:int(source.get("max_items",40))]:
        out.append({
            "id": stable_id(source["id"], url, title),
            "game_id": source["game_id"],
            "game": source["game"],
            "language": source["language"],
            "locale": source["language"],
            "region": source.get("region","global"),
            "title": title[:300],
            "excerpt": "",
            "url": url,
            "source": source["name"],
            "source_home": source["url"],
            "source_domain": (urlparse(source["url"]).hostname or "").lower(),
            "official": True,
            "published_at": published or now_iso(),
            "discovered_at": now_iso(),
            "status": "pending",
            "collector": "official-page",
            "source_id": source["id"],
            "confidence": "high" if published else "medium",
        })
    return out

def collect_official_sources(sources):
    items, errors = [], []
    for source in sources:
        try:
            print(f"[OFFICIAL] {source['name']} / {source.get('language','?')}")
            found = collect_source(source)
            items.extend(found)
            print(f"           {len(found)} links")
        except Exception as exc:
            errors.append({
                "source_id": source.get("id"),
                "source": source.get("name"),
                "url": source.get("url"),
                "error": str(exc)[:400],
            })
            print(f"[WARN] {source.get('name')}: {exc}")
    return items, errors
