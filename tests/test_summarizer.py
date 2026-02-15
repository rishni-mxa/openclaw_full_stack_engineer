"""Tests for summariser: mock LLM → validate thread JSON structure."""
import json
from estimates_monitor.summarizer import (
    chunk_text,
    summarise_pipeline,
    validate_thread,
    ValidationResult,
    MAX_TWEET_CHARS,
)


# ── validate_thread ──────────────────────────────────────────────

def test_valid_thread():
    data = {"tweets": [{"text": "Tweet one"}, {"text": "Tweet two"}], "notes": "ok"}
    result = validate_thread(json.dumps(data))
    assert result.valid
    assert result.tweets == ["Tweet one", "Tweet two"]
    assert result.errors == []


def test_tweet_over_280_chars():
    data = {"tweets": [{"text": "x" * 281}]}
    result = validate_thread(json.dumps(data))
    assert not result.valid
    assert any("281 chars" in e for e in result.errors)


def test_thread_over_max_tweets():
    data = {"tweets": [{"text": f"t{i}"} for i in range(10)]}
    result = validate_thread(json.dumps(data), max_tweets=8)
    assert not result.valid
    assert any("10 tweets" in e for e in result.errors)


def test_invalid_json():
    result = validate_thread("not json at all")
    assert not result.valid
    assert any("Invalid JSON" in e for e in result.errors)


def test_missing_tweets_key():
    result = validate_thread(json.dumps({"data": []}))
    assert not result.valid
    assert any("Missing 'tweets'" in e for e in result.errors)


def test_empty_tweets_list():
    result = validate_thread(json.dumps({"tweets": []}))
    assert not result.valid
    assert any("non-empty" in e for e in result.errors)


def test_accepts_plain_string_tweets():
    data = {"tweets": ["First tweet", "Second tweet"]}
    result = validate_thread(json.dumps(data))
    assert result.valid
    assert result.tweets == ["First tweet", "Second tweet"]


def test_multiple_errors_reported():
    data = {"tweets": [{"text": "x" * 300}] * 10}
    result = validate_thread(json.dumps(data), max_tweets=3)
    assert not result.valid
    assert len(result.errors) > 1  # both over-length and over-count


# ── summarise_pipeline with mock LLM ─────────────────────────────

def _mock_llm(prompt: str) -> str:
    """Return bullet points for section prompts, thread JSON for thread prompt."""
    if "SECTION_SUMMARIES" in prompt:
        return json.dumps({
            "tweets": [
                {"text": "Headline: Senate Estimates hearing covered key topics."},
                {"text": "Senator X questioned Dept Y on budget overruns."},
                {"text": "PDF: https://example.com/transcript.pdf"},
            ],
            "notes": "Mock summary",
        })
    return "• Key point from section."


def test_pipeline_returns_valid_thread():
    text = "A" * 8000  # enough to get multiple chunks
    result_json = summarise_pipeline(
        text=text,
        title="Test Committee 2026-02-10",
        pdf_url="https://example.com/transcript.pdf",
        openai_call_func=_mock_llm,
        max_tweets=8,
    )
    result = validate_thread(result_json)
    assert result.valid
    assert len(result.tweets) == 3
    assert all(len(t) <= MAX_TWEET_CHARS for t in result.tweets)


def test_chunk_text_splits_correctly():
    text = "A" * 10000
    chunks = chunk_text(text, max_chars=3500)
    assert len(chunks) == 3  # 3500 + 3500 + 3000
    assert "".join(chunks) == text
