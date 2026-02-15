"""X (Twitter) API client — post tweets and threads.

The client is injected as a callable for testability (mock in tests, real API in prod).
Credentials come from env vars: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET.
"""
import os
from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass
class PostResult:
    post_id: str
    text: str


# Type alias for the post function: (text, reply_to_id?) → PostResult
PostFunc = Callable[[str, Optional[str]], PostResult]


def create_thread(tweets: List[str], post_func: PostFunc) -> List[PostResult]:
    """Post a thread: first tweet is root, subsequent are replies.

    Returns list of PostResult for each successfully posted tweet.
    Raises on failure — caller should catch and handle partial progress.
    """
    if not tweets:
        raise ValueError("No tweets to post")
    results: List[PostResult] = []
    reply_to: Optional[str] = None
    for text in tweets:
        result = post_func(text, reply_to)
        results.append(result)
        reply_to = result.post_id
    return results


def publish_thread(
    thread_id: str,
    post_func: PostFunc,
) -> dict:
    """Full publish flow: load approved thread, post, record results.

    Returns dict with status and post IDs.
    Handles partial failure: records which tweets succeeded so retry can resume.
    """
    from estimates_monitor import pending, storage

    thread = pending.load_thread(thread_id)

    # Idempotency: already published
    if thread["status"] == "published":
        return {
            "thread_id": thread_id,
            "status": "already_published",
            "x_post_ids": thread["x_post_ids"],
        }

    # Must be approved (or failed for retry)
    if thread["status"] not in ("approved", "failed"):
        raise ValueError(f"Thread {thread_id} is '{thread['status']}', must be 'approved' or 'failed' to publish")

    # For retry: skip already-posted tweets
    already_posted = thread.get("x_post_ids", [])
    tweets_remaining = thread["tweets"][len(already_posted):]

    if not tweets_remaining:
        # All tweets were posted in a previous attempt — just mark published
        pending.mark_published(thread_id, x_post_ids=already_posted)
        storage.mark_posted(thread["transcript_id"], already_posted[0], already_posted)
        return {
            "thread_id": thread_id,
            "status": "published",
            "x_post_ids": already_posted,
        }

    # Determine reply_to for resume: last successful post ID, or None for fresh start
    reply_to = already_posted[-1] if already_posted else None

    try:
        # Post remaining tweets as a continuation
        new_results = []
        for text in tweets_remaining:
            result = post_func(text, reply_to)
            new_results.append(result)
            reply_to = result.post_id

        all_post_ids = already_posted + [r.post_id for r in new_results]
        pending.mark_published(thread_id, x_post_ids=all_post_ids)
        storage.mark_posted(thread["transcript_id"], all_post_ids[0], all_post_ids)
        return {
            "thread_id": thread_id,
            "status": "published",
            "x_post_ids": all_post_ids,
        }

    except Exception as exc:
        # Record partial progress so retry can resume
        partial_ids = already_posted + [r.post_id for r in new_results]
        pending.mark_failed(thread_id, error=str(exc))
        # Update x_post_ids with partial progress
        thread_data = pending.load_thread(thread_id)
        thread_data["x_post_ids"] = partial_ids
        pending._write(thread_data)
        return {
            "thread_id": thread_id,
            "status": "failed",
            "error": str(exc),
            "x_post_ids": partial_ids,
            "tweets_remaining": len(thread["tweets"]) - len(partial_ids),
        }


def make_post_func() -> PostFunc:
    """Create a real X API post function using env var credentials.

    Requires: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET
    Loads from .env files in estimates_monitor/ and project root if present.
    """
    import requests
    from dotenv import load_dotenv
    from requests_oauthlib import OAuth1

    # Load .env from both common locations
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / "estimates_monitor" / ".env")
    load_dotenv(project_root / ".env")

    auth = OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_SECRET"],
    )
    endpoint = "https://api.x.com/2/tweets"

    def _post(text: str, reply_to_id: Optional[str] = None) -> PostResult:
        payload: dict = {"text": text}
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}
        resp = requests.post(endpoint, json=payload, auth=auth, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        post_id = data["data"]["id"]
        return PostResult(post_id=post_id, text=text)

    return _post
