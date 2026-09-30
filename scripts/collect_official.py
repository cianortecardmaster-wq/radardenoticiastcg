from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; TCGNewsRadar/1.2; +https://github.com/)"

NAV_WORDS = {
    "home", "news", "events", "products", "cards", "rules", "about", "shop",
    "contact", "more", "read more", "learn more", "view all", "see all",
    "inicio", "início", "notícias", "eventos", "produtos", "saiba mais",
    "ニュース", "商品", "イベント", "查看更多", "最新资讯",
}

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

DATE_YMD = re.compile(r"\b(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\b")
DATE_DMY = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b")
DATE_CJK = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")
DATE_EN_MD = re.compile(r"\b(" + "|".join(MONTHS) + r")\.?\s+(\d{1,2}),?\s+(20\d{2})\b", re.I)
DATE_EN_DM = re.compile(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\.?,?\s+(20\d{2})\b", re.I)
ISO_TIMESTAMP = re.compile(r"\b20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\b")
PAGINATION_RE = re.compile(r"^(page\s+\d+\s+of\s+\d+|next page|previous page)\b", re.I)

BAD_SUMMARY_PARTS = (
    "cookie", "privacy policy", "terms of use", "all rights reserved", "copyright",
    "subscribe", "sign up", "accept cookies", "javascript", "enable cookies",
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_title(value):
    return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", " ", clean(value).lower()).strip()


def _valid_date(dt):
    if not dt:
        return None
    # Uma notícia pode ser coletada com atraso, mas a data de publicação não deve
    # estar semanas no futuro. Isso evita confundir data de lançamento citada no texto.
    if dt > datetime.now(timezone.utc) + timedelta(days=2):
        return None
    return dt.isoformat()


def parse_date(text):
    text = clean(text)

    m = DATE_YMD.search(text)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return _valid_date(datetime(y, mo, d, tzinfo=timezone.utc))
        except ValueError:
            pass

    m = DATE_DMY.search(text)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return _valid_date(datetime(y, mo, d, tzinfo=timezone.utc))
        except ValueError:
            pass

    m = DATE_CJK.search(text)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return _valid_date(datetime(y, mo, d, tzinfo=timezone.utc))
        except ValueError:
            pass

    m = DATE_EN_MD.search(text)
    if m:
        try:
            return _valid_date(datetime(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)), tzinfo=timezone.utc))
        except ValueError:
            pass

    m = DATE_EN_DM.search(text)
    if m:
        try:
            return _valid_date(datetime(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)), tzinfo=timezone.utc))
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


def nearest_context(anchor):
    """Escolhe um bloco local para não misturar várias notícias da página."""
    candidate = anchor
    best = anchor
    for _ in range(5):
        candidate = getattr(candidate, "parent", None)
        if candidate is None:
            break
        text = clean(candidate.get_text(" ", strip=True))
        if 20 <= len(text) <= 1800:
            best = candidate
        if getattr(candidate, "name", None) in {"article", "li"}:
            break
    return best


def extract_title(anchor, context):
    for area in (anchor, context):
        if area is None:
            continue
        heading = area.find(["h1", "h2", "h3", "h4"])
        if heading:
            text = clean(heading.get_text(" ", strip=True))
            if 12 <= len(text) <= 240 and not PAGINATION_RE.search(text):
                return text

    own = clean(anchor.get_text(" ", strip=True))
    if 12 <= len(own) <= 260 and own.lower().strip(" .:-") not in NAV_WORDS:
        return own
    return own


def tidy_title(title):
    title = clean(title)
    title = ISO_TIMESTAMP.sub(" ", title)
    title = re.sub(
        r"^News\s+\d{1,2}\s+(?:" + "|".join(MONTHS) + r")\.?,?\s+20\d{2}\s+",
        "",
        title,
        flags=re.I,
    )
    title = re.sub(r"^\d{1,2}\s+(?:" + "|".join(MONTHS) + r")\.?,?\s+20\d{2}\s+", "", title, flags=re.I)
    title = re.sub(r"^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+", "", title)
    title = re.sub(r"\s+(?:More|Read more|Learn more|View News)\s*$", "", title, flags=re.I)
    return clean(title)


def good_summary(text, title=""):
    text = clean(text)
    if title and text.startswith(title):
        text = clean(text[len(title):])
    lower = text.lower()
    if len(text) < 45:
        return ""
    if any(part in lower for part in BAD_SUMMARY_PARTS):
        return ""
    if PAGINATION_RE.search(text):
        return ""
    return text[:900]


def listing_summary(context, title):
    if context is None:
        return ""

    paragraphs = []
    for p in context.find_all("p"):
        text = good_summary(p.get_text(" ", strip=True), title)
        if text and text not in paragraphs:
            paragraphs.append(text)
        if len(" ".join(paragraphs)) >= 500:
            break

    if paragraphs:
        return clean(" ".join(paragraphs))[:900]

    full = clean(context.get_text(" ", strip=True))
    full = full.replace(title, " ", 1)
    full = re.sub(r"\b(?:More|Read more|Learn more|View News)\b", " ", full, flags=re.I)
    full = clean(full)
    return good_summary(full, title)


def article_summary(url, language):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": language or "en"},
            timeout=12,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        selectors = [
            ('meta[property="og:description"]', "content"),
            ('meta[name="description"]', "content"),
            ('meta[name="twitter:description"]', "content"),
        ]
        for selector, attr in selectors:
            tag = soup.select_one(selector)
            if tag:
                text = good_summary(tag.get(attr, ""))
                if text:
                    return text

        areas = soup.select("article p, main p") or soup.find_all("p")
        chunks = []
        for p in areas:
            text = good_summary(p.get_text(" ", strip=True))
            if text and text not in chunks:
                chunks.append(text)
            if len(" ".join(chunks)) >= 650:
                break
        return clean(" ".join(chunks))[:900]
    except Exception:
        return ""


def collect_source(source, summary_cache=None):
    summary_cache = summary_cache or {}
    response = requests.get(
        source["url"],
        headers={"User-Agent": USER_AGENT, "Accept-Language": source.get("language", "en")},
        timeout=int(source.get("timeout", 20)),
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    include_re = re.compile(source.get("include_path_regex", "."), re.I)
    seen = set()
    candidates = []

    for anchor in soup.find_all("a", href=True):
        href = clean(anchor.get("href", ""))
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        url = urldefrag(urljoin(source["url"], href))[0]
        if not same_site(source["url"], url):
            continue

        parsed = urlparse(url)
        path_plus = parsed.path + (("?" + parsed.query) if parsed.query else "")
        if not include_re.search(path_plus):
            continue
        if url in seen or url.rstrip("/") == source["url"].rstrip("/"):
            continue

        context = nearest_context(anchor)
        raw_anchor_text = clean(anchor.get_text(" ", strip=True))
        raw_context_text = clean(context.get_text(" ", strip=True)) if context else raw_anchor_text

        if PAGINATION_RE.search(raw_anchor_text) or PAGINATION_RE.search(raw_context_text):
            continue

        # A data visível no próprio item tem prioridade sobre qualquer data citada no resumo.
        published = parse_date(raw_anchor_text) or parse_date(raw_context_text)

        title = tidy_title(extract_title(anchor, context))
        if len(title) < 12 or title.lower().strip(" .:-") in NAV_WORDS:
            continue
        if PAGINATION_RE.search(title):
            continue

        excerpt = listing_summary(context, title)
        cached = clean(summary_cache.get(url, ""))
        if not excerpt and cached:
            excerpt = cached

        score = 5 + (3 if published else 0) + (2 if 18 <= len(title) <= 180 else 0) + (2 if excerpt else 0)
        candidates.append({
            "score": score,
            "published": published or "",
            "title": title,
            "url": url,
            "excerpt": excerpt,
        })
        seen.add(url)

    candidates.sort(key=lambda x: (x["published"], x["score"]), reverse=True)
    candidates = candidates[:int(source.get("max_items", 40))]

    # Busca o detalhe somente para as notícias mais recentes que ainda não têm resumo.
    # O cache do news.json evita repetir a mesma requisição em execuções futuras.
    fetch_limit = int(source.get("summary_fetch_limit", 6))
    fetched = 0
    for candidate in candidates:
        if candidate["excerpt"] or fetched >= fetch_limit:
            continue
        candidate["excerpt"] = article_summary(candidate["url"], source.get("language", "en"))
        fetched += 1
        time.sleep(0.08)

    out = []
    for candidate in candidates:
        out.append({
            "id": stable_id(source["id"], candidate["url"], candidate["title"]),
            "game_id": source["game_id"],
            "game": source["game"],
            "language": source["language"],
            "locale": source["language"],
            "region": source.get("region", "global"),
            "title": candidate["title"][:300],
            "excerpt": candidate["excerpt"][:900],
            "url": candidate["url"],
            "source": source["name"],
            "source_home": source["url"],
            "source_domain": (urlparse(source["url"]).hostname or "").lower(),
            "official": True,
            "published_at": candidate["published"] or now_iso(),
            "discovered_at": now_iso(),
            "status": "pending",
            "collector": "official-page",
            "source_id": source["id"],
            "confidence": "high" if candidate["published"] else "medium",
        })
    return out


def collect_official_sources(sources, summary_cache=None):
    items = []
    errors = []
    summary_cache = summary_cache or {}

    for source in sources:
        try:
            print(f"[OFFICIAL] {source['name']} / {source.get('language', '?')}")
            found = collect_source(source, summary_cache=summary_cache)
            items.extend(found)
            with_summary = sum(bool(item.get("excerpt")) for item in found)
            print(f"           {len(found)} links / {with_summary} com resumo")
        except Exception as exc:
            errors.append({
                "source_id": source.get("id"),
                "source": source.get("name"),
                "url": source.get("url"),
                "error": str(exc)[:400],
            })
            print(f"[WARN] {source.get('name')}: {exc}")

    return items, errors
