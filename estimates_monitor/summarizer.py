import json
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import List

# Minimal wrapper for chunking and prompting. Actual LLM call is injected for testability.
# Prompts live in prompts/*.md — edit those files to tune wording.

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> Template:
    return Template((_PROMPTS_DIR / name).read_text(encoding="utf-8"))


def chunk_text(text: str, max_chars: int = 3500) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunks.append(text[start:end])
        start = end
    return chunks


def build_section_prompt(section_text: str) -> str:
    return _load_prompt("section.md").substitute(section_text=section_text)


def build_thread_prompt(section_summaries: List[str], title: str, pdf_url: str, max_tweets: int = 8) -> str:
    return _load_prompt("thread.md").substitute(
        max_tweets=max_tweets,
        title=title,
        section_summaries="\n---\n".join(section_summaries),
        pdf_url=pdf_url,
    )


def summarise_pipeline(text: str, title: str, pdf_url: str, openai_call_func, max_tweets: int = 8):
    # map
    chunks = chunk_text(text)
    summaries = []
    for c in chunks:
        prompt = build_section_prompt(c)
        res = openai_call_func(prompt)
        summaries.append(res)
    # reduce
    thread_prompt = build_thread_prompt(summaries, title, pdf_url, max_tweets)
    thread_json = openai_call_func(thread_prompt)
    return thread_json


# ---------- Thread validation ----------

MAX_TWEET_CHARS = 280


@dataclass
class ValidationResult:
    valid: bool
    tweets: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def validate_thread(raw_json: str, max_tweets: int = 8) -> ValidationResult:
    """Validate LLM thread output: must be valid JSON with tweets list,
    each tweet ≤ 280 chars, thread ≤ max_tweets."""
    errors: List[str] = []

    # Parse JSON
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return ValidationResult(valid=False, errors=[f"Invalid JSON: {exc}"])

    # Must have tweets list
    if not isinstance(data, dict) or "tweets" not in data:
        return ValidationResult(valid=False, errors=["Missing 'tweets' key in response"])

    tweets_raw = data["tweets"]
    if not isinstance(tweets_raw, list) or len(tweets_raw) == 0:
        return ValidationResult(valid=False, errors=["'tweets' must be a non-empty list"])

    # Extract text from each tweet object
    tweets: List[str] = []
    for i, item in enumerate(tweets_raw):
        if isinstance(item, dict):
            text = item.get("text", "")
        elif isinstance(item, str):
            text = item
        else:
            errors.append(f"Tweet {i + 1}: unexpected type {type(item).__name__}")
            continue
        tweets.append(text)

    # Thread length
    if len(tweets) > max_tweets:
        errors.append(f"Thread has {len(tweets)} tweets, max is {max_tweets}")

    # Tweet length
    for i, text in enumerate(tweets):
        if len(text) > MAX_TWEET_CHARS:
            errors.append(f"Tweet {i + 1}: {len(text)} chars (max {MAX_TWEET_CHARS})")

    return ValidationResult(valid=len(errors) == 0, tweets=tweets, errors=errors)
