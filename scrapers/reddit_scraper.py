import os
import praw
from datetime import datetime, timezone
from typing import List, Dict


def get_reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID", ""),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
        user_agent=os.getenv("REDDIT_USER_AGENT", "POP!ularReviews/1.0"),
    )


FUNKO_SUBREDDITS = ["funkopop", "funkotrade", "funkocollectors", "Funko"]


def search_reddit(funko_name: str, limit: int = 150) -> List[Dict]:
    reviews = []
    try:
        reddit = get_reddit_client()
        for subreddit_name in FUNKO_SUBREDDITS:
            try:
                subreddit = reddit.subreddit(subreddit_name)
                results = subreddit.search(funko_name, sort="relevance", limit=limit // len(FUNKO_SUBREDDITS))
                for post in results:
                    score = _normalize_reddit_score(post.score, post.upvote_ratio)
                    reviews.append({
                        "source": "Reddit",
                        "subreddit": f"r/{subreddit_name}",
                        "title": post.title,
                        "text": post.selftext[:800] if post.selftext else post.title,
                        "score": score,
                        "upvotes": post.score,
                        "upvote_ratio": post.upvote_ratio,
                        "num_comments": post.num_comments,
                        "url": f"https://reddit.com{post.permalink}",
                        "date": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat(),
                        "author": str(post.author) if post.author else "[deleted]",
                        "flair": post.link_flair_text or "",
                    })
                    # Also grab top comments
                    post.comments.replace_more(limit=0)
                    for comment in list(post.comments)[:5]:
                        if len(comment.body) > 30:
                            reviews.append({
                                "source": "Reddit Comment",
                                "subreddit": f"r/{subreddit_name}",
                                "title": f"Comment on: {post.title[:60]}",
                                "text": comment.body[:600],
                                "score": _normalize_reddit_score(comment.score, 0.8),
                                "upvotes": comment.score,
                                "upvote_ratio": 0.8,
                                "num_comments": 0,
                                "url": f"https://reddit.com{post.permalink}",
                                "date": datetime.fromtimestamp(comment.created_utc, tz=timezone.utc).isoformat(),
                                "author": str(comment.author) if comment.author else "[deleted]",
                                "flair": "",
                            })
            except Exception:
                continue
    except Exception:
        pass
    return reviews


def _normalize_reddit_score(upvotes: int, ratio: float) -> float:
    """Convert upvotes + ratio to a 1–5 star equivalent."""
    if upvotes <= 0:
        return 2.5
    sentiment = ratio  # 0–1 scale
    # Map 0–1 ratio to 1–5 stars, weighted by engagement
    star = 1 + (sentiment * 4)
    return round(min(max(star, 1.0), 5.0), 2)
