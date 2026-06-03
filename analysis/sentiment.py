import re
import numpy as np
from scipy import stats
from typing import List, Dict, Any
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

# Funko-specific lexicon additions
FUNKO_LEXICON = {
    "grail": 3.0, "chase": 1.5, "exclusive": 1.0, "flocked": 1.0,
    "glow": 0.8, "gitd": 0.8, "metallic": 0.5, "supersized": 0.5,
    "vaulted": 1.0, "stickered": 0.5, "con exclusive": 1.5,
    "damaged box": -2.0, "paint defect": -2.5, "qc": -1.0,
    "quality control": -1.0, "warped": -2.0, "melted": -2.5,
    "overproduced": -1.5, "underrated": 1.5, "overrated": -1.5,
    "must have": 2.0, "preorder": 0.3, "in hand": 0.5,
    "worth it": 1.5, "not worth": -1.5, "pass": -0.5,
    "cop": 1.0, "copped": 1.0, "skip": -1.0,
    "beautiful": 2.0, "stunning": 2.5, "perfect": 2.5,
    "disappointed": -2.0, "disappointing": -2.0, "underwhelming": -1.5,
}
for word, score in FUNKO_LEXICON.items():
    analyzer.lexicon[word] = score


def analyze_text(text: str) -> Dict[str, float]:
    clean = re.sub(r"http\S+|www\S+", "", text.lower())
    scores = analyzer.polarity_scores(clean)
    compound = scores["compound"]
    star = _compound_to_stars(compound)
    return {
        "compound": round(compound, 4),
        "positive": round(scores["pos"], 4),
        "negative": round(scores["neg"], 4),
        "neutral": round(scores["neu"], 4),
        "inferred_stars": round(star, 2),
        "sentiment_label": _label(compound),
    }


def enrich_reviews(reviews: List[Dict]) -> List[Dict]:
    for r in reviews:
        text = f"{r.get('title', '')} {r.get('text', '')}"
        r["sentiment"] = analyze_text(text)
        # If no explicit score, use sentiment-inferred stars
        if r.get("score") is None:
            r["score"] = r["sentiment"]["inferred_stars"]
    return reviews


def compute_statistics(reviews: List[Dict]) -> Dict[str, Any]:
    if not reviews:
        return {}

    scores = [r["score"] for r in reviews if r.get("score") is not None]
    compounds = [r["sentiment"]["compound"] for r in reviews if "sentiment" in r]

    if not scores:
        return {}

    n = len(scores)
    arr = np.array(scores)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    sem = float(stats.sem(arr)) if n > 1 else 0.0

    ci_95 = stats.t.interval(0.95, df=n - 1, loc=mean, scale=sem) if n > 1 else (mean, mean)
    ci_99 = stats.t.interval(0.99, df=n - 1, loc=mean, scale=sem) if n > 1 else (mean, mean)

    # Distribution of star buckets
    buckets = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for s in scores:
        bucket = max(1, min(5, round(s)))
        buckets[bucket] += 1

    # Sentiment breakdown
    sentiments = {"positive": 0, "neutral": 0, "negative": 0}
    for r in reviews:
        if "sentiment" in r:
            sentiments[r["sentiment"]["sentiment_label"]] += 1

    # Top keywords in positive vs negative reviews
    pos_words = _extract_keywords([r for r in reviews if r.get("sentiment", {}).get("sentiment_label") == "positive"])
    neg_words = _extract_keywords([r for r in reviews if r.get("sentiment", {}).get("sentiment_label") == "negative"])

    # Normality test (Shapiro-Wilk if n < 50, else D'Agostino)
    normality = {}
    if n >= 3:
        if n < 50:
            stat, p = stats.shapiro(arr)
            normality = {"test": "Shapiro-Wilk", "statistic": round(float(stat), 4), "p_value": round(float(p), 4)}
        else:
            stat, p = stats.normaltest(arr)
            normality = {"test": "D'Agostino-Pearson", "statistic": round(float(stat), 4), "p_value": round(float(p), 4)}

    # Compute NPS-like score: promoters (4-5 stars) - detractors (1-2 stars) / n * 100
    promoters = sum(1 for s in scores if s >= 4.0)
    detractors = sum(1 for s in scores if s <= 2.0)
    nps = round((promoters - detractors) / n * 100, 1)

    compound_arr = np.array(compounds) if compounds else arr

    return {
        "n": n,
        "mean_score": round(mean, 3),
        "median_score": round(float(np.median(arr)), 3),
        "std_dev": round(std, 3),
        "sem": round(sem, 4),
        "min_score": round(float(np.min(arr)), 2),
        "max_score": round(float(np.max(arr)), 2),
        "ci_95": [round(ci_95[0], 3), round(ci_95[1], 3)],
        "ci_99": [round(ci_99[0], 3), round(ci_99[1], 3)],
        "star_distribution": buckets,
        "sentiment_breakdown": sentiments,
        "nps_score": nps,
        "positive_keywords": pos_words[:10],
        "negative_keywords": neg_words[:10],
        "normality_test": normality,
        "mean_compound_sentiment": round(float(np.mean(compound_arr)), 4),
        "performance_grade": _grade(mean, nps),
    }


def _compound_to_stars(compound: float) -> float:
    # Map -1..1 to 1..5
    return round(1 + ((compound + 1) / 2) * 4, 2)


def _label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def _grade(mean: float, nps: float) -> str:
    score = (mean / 5) * 70 + (max(min(nps, 100), -100) + 100) / 200 * 30
    if score >= 85:
        return "A"
    if score >= 75:
        return "B+"
    if score >= 65:
        return "B"
    if score >= 55:
        return "C+"
    if score >= 45:
        return "C"
    return "D"


STOPWORDS = {
    "the", "a", "an", "is", "it", "this", "that", "and", "or", "but",
    "for", "of", "in", "to", "my", "i", "me", "was", "are", "be",
    "have", "has", "had", "with", "on", "at", "by", "from", "as",
    "pop", "funko", "figure", "vinyl", "one", "got", "get", "just",
    "really", "very", "so", "its", "it's", "would", "could", "should",
    "not", "no", "like", "pretty", "kind", "bit", "lot",
}


def _extract_keywords(reviews: List[Dict]) -> List[str]:
    from collections import Counter
    text = " ".join(f"{r.get('title', '')} {r.get('text', '')}" for r in reviews)
    words = re.findall(r"\b[a-z]{4,}\b", text.lower())
    filtered = [w for w in words if w not in STOPWORDS]
    return [w for w, _ in Counter(filtered).most_common(20)]
