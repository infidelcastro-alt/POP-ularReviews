import re
import time
import random
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
from urllib.parse import quote_plus


HEADERS_POOL = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 Safari/604.1",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    },
]


def _get(url: str, timeout: int = 10) -> requests.Response | None:
    headers = random.choice(HEADERS_POOL)
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception:
        return None


def scrape_hobbydb(funko_name: str) -> List[Dict]:
    """Scrape HobbyDB catalog entries for community ratings."""
    reviews = []
    query = quote_plus(f"funko pop {funko_name}")
    url = f"https://www.hobbydb.com/marketplaces/hobbydb/catalog_items?q={query}&category=Funko+Pop%21"
    resp = _get(url)
    if not resp:
        return reviews
    soup = BeautifulSoup(resp.text, "lxml")
    cards = soup.select(".catalog-item-card")[:10]
    for card in cards:
        try:
            name_el = card.select_one(".catalog-item-name")
            rating_el = card.select_one(".rating-value")
            reviews_el = card.select_one(".rating-count")
            if not name_el:
                continue
            rating = float(rating_el.text.strip()) if rating_el else None
            count = int(re.sub(r"\D", "", reviews_el.text)) if reviews_el else 0
            reviews.append({
                "source": "HobbyDB",
                "subreddit": "",
                "title": name_el.text.strip(),
                "text": f"Community rating on HobbyDB. {count} ratings recorded.",
                "score": rating,
                "upvotes": count,
                "upvote_ratio": None,
                "num_comments": 0,
                "url": url,
                "date": datetime.now().isoformat(),
                "author": "HobbyDB Community",
                "flair": "Catalog",
            })
        except Exception:
            continue
    return reviews


def scrape_popprices(funko_name: str) -> List[Dict]:
    """Scrape PopPriceGuide for community popularity signals."""
    reviews = []
    query = quote_plus(funko_name)
    url = f"https://www.poppriceGuide.com/pops/?q={query}"
    resp = _get(url)
    if not resp:
        return reviews
    soup = BeautifulSoup(resp.text, "lxml")
    items = soup.select(".pop-item, .item-card")[:8]
    for item in items:
        try:
            name_el = item.select_one(".pop-name, .item-name, h3, h4")
            price_el = item.select_one(".pop-price, .price")
            wishlist_el = item.select_one(".wishlist-count, .want-count")
            if not name_el:
                continue
            wishlist = int(re.sub(r"\D", "", wishlist_el.text)) if wishlist_el else 0
            reviews.append({
                "source": "PopPriceGuide",
                "subreddit": "",
                "title": name_el.text.strip(),
                "text": f"Community demand signal: {wishlist} collectors have wishlisted this pop.",
                "score": _wishlist_to_score(wishlist),
                "upvotes": wishlist,
                "upvote_ratio": None,
                "num_comments": 0,
                "url": url,
                "date": datetime.now().isoformat(),
                "author": "PopPriceGuide",
                "flair": "Market",
            })
        except Exception:
            continue
    return reviews


def scrape_amazon_reviews(funko_name: str) -> List[Dict]:
    """Search Amazon for Funko reviews via public search page."""
    reviews = []
    query = quote_plus(f"funko pop {funko_name} vinyl figure")
    url = f"https://www.amazon.com/s?k={query}&rh=n%3A166995011"
    resp = _get(url)
    if not resp:
        return reviews
    soup = BeautifulSoup(resp.text, "lxml")
    items = soup.select('[data-component-type="s-search-result"]')[:6]
    for item in items:
        try:
            name_el = item.select_one("h2 span")
            rating_el = item.select_one(".a-icon-alt")
            review_count_el = item.select_one(".a-size-base.s-underline-text")
            if not name_el:
                continue
            rating_text = rating_el.text if rating_el else ""
            rating_match = re.search(r"([\d.]+) out of 5", rating_text)
            rating = float(rating_match.group(1)) if rating_match else None
            count_text = review_count_el.text if review_count_el else "0"
            count = int(re.sub(r"\D", "", count_text)) if count_text else 0
            reviews.append({
                "source": "Amazon",
                "subreddit": "",
                "title": name_el.text.strip(),
                "text": f"{count} customer reviews on Amazon. Avg rating: {rating}/5" if rating else f"{count} customer reviews on Amazon.",
                "score": rating,
                "upvotes": count,
                "upvote_ratio": None,
                "num_comments": count,
                "url": f"https://www.amazon.com/s?k={query}",
                "date": datetime.now().isoformat(),
                "author": "Amazon Customers",
                "flair": "Retail",
            })
        except Exception:
            continue
    return reviews


def scrape_entertainment_earth(funko_name: str) -> List[Dict]:
    """Scrape Entertainment Earth reviews."""
    reviews = []
    query = quote_plus(f"funko pop {funko_name}")
    url = f"https://www.entertainmentearth.com/s/{query}?brand=Funko"
    resp = _get(url)
    if not resp:
        return reviews
    soup = BeautifulSoup(resp.text, "lxml")
    items = soup.select(".product-item, .product-block")[:6]
    for item in items:
        try:
            name_el = item.select_one(".product-name, h3, .item-name")
            rating_el = item.select_one(".stars, .rating")
            if not name_el:
                continue
            star_count = len(item.select(".star-full, .fa-star")) if rating_el else 0
            rating = star_count if 1 <= star_count <= 5 else None
            reviews.append({
                "source": "Entertainment Earth",
                "subreddit": "",
                "title": name_el.text.strip(),
                "text": f"Listed on Entertainment Earth. Star rating: {rating}/5" if rating else "Listed on Entertainment Earth.",
                "score": float(rating) if rating else None,
                "upvotes": 0,
                "upvote_ratio": None,
                "num_comments": 0,
                "url": url,
                "date": datetime.now().isoformat(),
                "author": "Entertainment Earth",
                "flair": "Retail",
            })
        except Exception:
            continue
    return reviews


def scrape_google_snippets(funko_name: str) -> List[Dict]:
    """Use DuckDuckGo HTML search to pull review snippets."""
    reviews = []
    query = quote_plus(f'funko pop "{funko_name}" review')
    url = f"https://html.duckduckgo.com/html/?q={query}"
    resp = _get(url)
    if not resp:
        return reviews
    soup = BeautifulSoup(resp.text, "lxml")
    results = soup.select(".result__body")[:12]
    for result in results:
        try:
            title_el = result.select_one(".result__title")
            snippet_el = result.select_one(".result__snippet")
            link_el = result.select_one(".result__url")
            if not snippet_el:
                continue
            title = title_el.text.strip() if title_el else "Web Review"
            snippet = snippet_el.text.strip()
            link = link_el.text.strip() if link_el else ""
            # Skip reddit (handled separately) and Amazon (handled separately)
            if any(x in link.lower() for x in ["reddit.com", "amazon.com"]):
                continue
            reviews.append({
                "source": "Web",
                "subreddit": "",
                "title": title,
                "text": snippet,
                "score": None,  # Inferred via sentiment
                "upvotes": 0,
                "upvote_ratio": None,
                "num_comments": 0,
                "url": f"https://{link}" if link and not link.startswith("http") else link,
                "date": datetime.now().isoformat(),
                "author": link.split("/")[0] if link else "Web",
                "flair": "Web",
            })
        except Exception:
            continue
    return reviews


def _wishlist_to_score(count: int) -> float:
    """Map wishlist count to a 1–5 score."""
    if count >= 5000:
        return 5.0
    if count >= 2000:
        return 4.5
    if count >= 1000:
        return 4.0
    if count >= 500:
        return 3.5
    if count >= 100:
        return 3.0
    return 2.5
