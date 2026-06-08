import os
import asyncio
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import concurrent.futures

load_dotenv()

from scrapers.reddit_scraper import search_reddit
from scrapers.web_scraper import (
    scrape_google_snippets,
    scrape_amazon_reviews,
    scrape_hobbydb,
    scrape_popprices,
    scrape_entertainment_earth,
)
from scrapers.funko_catalog import resolve_funko, suggest_funko
from analysis.sentiment import enrich_reviews, compute_statistics

app = FastAPI(title="POP!ularReviews", version="2.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)


class AnalysisResponse(BaseModel):
    funko_name: str
    resolved_query: str          # canonical name used for scraping
    product: Optional[dict]      # Funko catalog product card (may be None)
    total_reviews: int
    sources_queried: List[str]
    statistics: dict
    reviews: List[dict]
    source_breakdown: dict


@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


@app.get("/api/resolve")
async def resolve_product(q: str = Query(..., min_length=2)):
    """Resolve query → best Funko product card (used after selection)."""
    loop = asyncio.get_event_loop()
    product = await loop.run_in_executor(_executor, resolve_funko, q)
    return {"query": q, "product": product}


@app.get("/api/suggest")
async def suggest_products(q: str = Query(..., min_length=2)):
    """Typeahead: return all catalog candidates for a partial query."""
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(_executor, suggest_funko, q)
    return {"query": q, "results": results}


@app.get("/api/analyze", response_model=AnalysisResponse)
async def analyze_funko(
    name: str = Query(..., min_length=2),
    sources: Optional[str] = Query("all"),
    limit: int = Query(100, ge=10, le=300),
):
    loop = asyncio.get_event_loop()

    # ── Step 1: resolve to canonical Funko product (runs in parallel with scrapers) ──
    catalog_future = loop.run_in_executor(_executor, resolve_funko, name)

    # ── Step 2: build scraper search string ──
    reddit_configured = bool(os.getenv("REDDIT_CLIENT_ID"))
    default_sources = {"reddit", "amazon", "web", "hobbydb", "ppg", "ee"} if reddit_configured \
                      else {"amazon", "web", "hobbydb", "ppg", "ee"}
    requested = (
        set(sources.lower().split(","))
        if sources != "all"
        else default_sources
    )

    scraper_tasks = {}
    if "reddit" in requested:
        scraper_tasks["Reddit"] = loop.run_in_executor(_executor, search_reddit, name, limit)
    if "amazon" in requested:
        scraper_tasks["Amazon"] = loop.run_in_executor(_executor, scrape_amazon_reviews, name)
    if "web" in requested:
        scraper_tasks["Web"] = loop.run_in_executor(_executor, scrape_google_snippets, name)
    if "hobbydb" in requested:
        scraper_tasks["HobbyDB"] = loop.run_in_executor(_executor, scrape_hobbydb, name)
    if "ppg" in requested:
        scraper_tasks["PopPriceGuide"] = loop.run_in_executor(_executor, scrape_popprices, name)
    if "ee" in requested:
        scraper_tasks["Entertainment Earth"] = loop.run_in_executor(_executor, scrape_entertainment_earth, name)

    # ── Step 3: await everything ──
    all_futures = [catalog_future] + list(scraper_tasks.values())
    all_results = await asyncio.gather(*all_futures, return_exceptions=True)

    product = all_results[0] if not isinstance(all_results[0], Exception) else None
    scraper_results = all_results[1:]

    # ── Step 4: canonical query for display ──
    resolved_query = product["title"] if product and product.get("title") else name

    # ── Step 5: collate reviews ──
    all_reviews = []
    source_counts = {}
    sources_queried = []

    for source_name, result in zip(scraper_tasks.keys(), scraper_results):
        sources_queried.append(source_name)
        if isinstance(result, Exception) or not result:
            source_counts[source_name] = 0
            continue
        enriched = enrich_reviews(result)
        all_reviews.extend(enriched)
        source_counts[source_name] = len(enriched)

    if not all_reviews:
        raise HTTPException(
            status_code=404,
            detail=f"No reviews found for '{resolved_query}'. Try a broader search term, e.g. just the character name without 'Pop!'.",
        )

    all_reviews.sort(key=lambda r: r.get("date", ""), reverse=True)
    stats = compute_statistics(all_reviews)

    return AnalysisResponse(
        funko_name=name,
        resolved_query=resolved_query,
        product=product,
        total_reviews=len(all_reviews),
        sources_queried=sources_queried,
        statistics=stats,
        reviews=all_reviews[:limit],
        source_breakdown=source_counts,
    )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "reddit_configured": bool(os.getenv("REDDIT_CLIENT_ID")),
        "version": "2.1.0",
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
