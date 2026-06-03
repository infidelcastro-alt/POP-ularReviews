"""
Funko catalog resolver — uses funko.com's Demandware (SFCC) suggest endpoint.
No auth required; parses HTML fragments returned by the search service.
"""
import re
import difflib
import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict, List

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "X-Requested-With": "XMLHttpRequest",
}
BASE = "https://funko.com"
SUGGEST_URL = BASE + "/on/demandware.store/Sites-FunkoUS-Site/en_US/SearchServices-GetSuggestions"


def resolve_funko(query: str) -> Optional[Dict]:
    """Best single match — resolves and enriches for use in full analysis."""
    candidates = _suggest(query)
    if not candidates:
        return None
    best = _pick_best(query, candidates)
    if not best:
        return None
    return _enrich(best)


def suggest_funko(query: str) -> List[Dict]:
    """Return all raw candidates (no enrichment) for the typeahead dropdown."""
    return _suggest(query)


# ── internal helpers ──────────────────────────────────────────────────────────

def _suggest(query: str) -> List[Dict]:
    try:
        resp = requests.get(SUGGEST_URL, params={"q": query}, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return _parse_suggest_html(resp.text)
    except Exception:
        return []


def _parse_suggest_html(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    products = []

    # Both "shop" (current) and "vault" (retired) tabs
    for item in soup.select(".item a.product-result"):
        name_el    = item.select_one("h2.name")
        license_el = item.select_one("span.license")
        img_el     = item.select_one("img")
        href       = item.get("href", "")

        if not name_el:
            continue

        title   = name_el.get_text(strip=True)
        series  = license_el.get_text(strip=True) if license_el else ""
        image   = img_el.get("src", "") if img_el else ""
        # Make image URL absolute and bump resolution
        if image.startswith("/"):
            image = BASE + image
        image = re.sub(r"sw=\d+", "sw=300", image)
        image = re.sub(r"sh=\d+", "sh=300", image)

        url = BASE + href if href.startswith("/") else href

        # Extract product ID from URL (e.g. /pop-batman-hush/66906.html → 66906)
        pid_match = re.search(r"/(\d+)\.html", href)
        pid = pid_match.group(1) if pid_match else ""

        products.append({
            "title":       title,
            "series":      series,
            "image":       image,
            "url":         url,
            "pid":         pid,
            "number":      _extract_number(title),
            "description": "",
            "variants":    [],
            "vendor":      "Funko",
        })

    return products


def _enrich(product: Dict) -> Dict:
    """Fetch the product detail page to get number, description, and variants."""
    if not product.get("url"):
        return product
    try:
        resp = requests.get(product["url"], headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Pop number — often in the title or a dedicated attribute span
        number = product.get("number", "")
        for el in soup.select(".product-number, [class*='item-number'], .pdp-number"):
            m = re.search(r"(\d+)", el.get_text())
            if m:
                number = m.group(1)
                break
        # Fallback: look in page title / h1
        if not number:
            h1 = soup.select_one("h1.product-name, h1.pdp-title")
            if h1:
                number = _extract_number(h1.get_text())

        # Description
        desc = ""
        for sel in [".product-description", ".pdp-description", "[class*='description']"]:
            el = soup.select_one(sel)
            if el:
                raw = el.get_text(" ", strip=True)
                desc = re.sub(r"\s{2,}", " ", raw)[:400]
                break

        # Series / license from breadcrumb
        series = product.get("series", "")
        bc = soup.select(".breadcrumb a, .breadcrumbs a")
        if len(bc) >= 2:
            series = bc[-1].get_text(strip=True) or series

        # Better image from OG tag or product gallery
        image = product.get("image", "")
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            image = og_img["content"]

        return {
            **product,
            "number":      number,
            "series":      series,
            "description": desc,
            "image":       image,
        }
    except Exception:
        return product


def _pick_best(query: str, candidates: List[Dict]) -> Optional[Dict]:
    if not candidates:
        return None
    q = query.lower()
    titles = [c["title"].lower() for c in candidates]
    matches = difflib.get_close_matches(q, titles, n=1, cutoff=0.25)
    if matches:
        return candidates[titles.index(matches[0])]
    return candidates[0]


def _extract_number(title: str) -> str:
    m = re.search(r"#\s*(\d+)", title)
    return m.group(1) if m else ""
