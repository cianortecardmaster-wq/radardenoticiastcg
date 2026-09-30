from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; TCGNewsRadar/1.3; +https://github.com/)"

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


def _parse_machine_date(value):
    value = clean(value)
    if not value:
        return None

    # ISO 8601 / RFC3339, common in meta tags and JSON-LD.
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return _valid_date(dt)
    except Exception:
        pass

    return parse_date(value)


def _json_date(value):
    if isinstance(value, dict):
        for key in ("datePublished", "dateCreated", "uploadDate"):
            if value.get(key):
                parsed = _parse_machine_date(str(value[key]))
                if parsed:
                    return parsed
        for child in value.values():
            parsed = _json_date(child)
            if parsed:
                return parsed

    if isinstance(value, list):
        for child in value:
            parsed = _json_date(child)
            if parsed:
                return parsed

    return None


def article_details(url, language):
    """Retorna (resumo, data_publicacao).

    A regra é deliberadamente conservadora: se a página não expõe uma data
    de publicação verificável, a notícia NÃO recebe a data de hoje.
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": language or "en"},
            timeout=12,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        published = None

        # Metadados estruturados são as fontes mais confiáveis.
        date_selectors = [
            ('meta[property="article:published_time"]', "content"),
            ('meta[property="og:published_time"]', "content"),
            ('meta[name="date"]', "content"),
            ('meta[name="publish-date"]', "content"),
            ('meta[name="pubdate"]', "content"),
            ('meta[itemprop="datePublished"]', "content"),
            ('time[datetime]', "datetime"),
        ]
        for selector, attr in date_selectors:
            tag = soup.select_one(selector)
            if tag:
                published = _parse_machine_date(tag.get(attr, ""))
                if published:
                    break

        # JSON-LD costuma trazer datePublished em sites de notícias modernos.
        if not published:
            import json
            for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
                raw = script.string or script.get_text(" ", strip=True)
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                published = _json_date(payload)
                if published:
                    break

        summary = ""
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
                    summary = text
                    break

        if not summary:
            areas = soup.select("article p, main p") or soup.find_all("p")
            chunks = []
            for p in areas:
                text = good_summary(p.get_text(" ", strip=True))
                if text and text not in chunks:
                    chunks.append(text)
                if len(" ".join(chunks)) >= 650:
                    break
            summary = clean(" ".join(chunks))[:900]

        return summary, published
    except Exception:
        return "", None

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

    # Consulta a matéria quando falta resumo OU data.
    # Data ausente nunca é substituída pela data da coleta.
    fetch_limit = int(source.get("detail_fetch_limit", max(int(source.get("summary_fetch_limit", 6)), 12)))
    fetched = 0
    for candidate in candidates:
        needs_summary = not candidate["excerpt"]
        needs_date = not candidate["published"]

        if not (needs_summary or needs_date):
            continue
        if fetched >= fetch_limit:
            continue

        detail_summary, detail_published = article_details(
            candidate["url"],
            source.get("language", "en"),
        )
        fetched += 1

        if needs_summary and detail_summary:
            candidate["excerpt"] = detail_summary
        if needs_date and detail_published:
            candidate["published"] = detail_published

        time.sleep(0.08)

    # Para um radar de notícias atuais, "data desconhecida" não pode significar
    # "hoje". Se não conseguimos verificar a data, descartamos a entrada.
    candidates = [candidate for candidate in candidates if candidate["published"]]

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
            "published_at": candidate["published"],
            "discovered_at": now_iso(),
            "status": "pending",
            "collector": "official-page",
            "source_id": source["id"],
            "confidence": "high",
            "date_verified": True,
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
