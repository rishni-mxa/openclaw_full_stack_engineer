from typing import List

# Minimal wrapper for chunking and prompting. Actual LLM call is injected for testability.

def chunk_text(text: str, max_chars: int = 3500) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunks.append(text[start:end])
        start = end
    return chunks


def build_section_prompt(section_text: str) -> str:
    return ("You are a journalist assistant. Summarise the following transcript section into 2-4 concise bullet points, each 1-2 sentences:\n\n" + section_text)


def build_thread_prompt(section_summaries: List[str], title: str, pdf_url: str, max_tweets: int = 8) -> str:
    intro = (f"Create a top-down Twitter thread of up to {max_tweets} tweets summarising the transcript titled: {title}.\n"
             "Structure: 1) 1-tweet headline summary, 2) 4-6 tweets of key points and named stakeholders, 3) 1 tweet with notable quote(s) if any, 4) final tweet linking to the PDF.\n"
             "Return the thread as JSON: {\"tweets\": [{\"text\": \"...\"}], \"notes\": \"...\"}\n\n")
    body = "\n\nSECTION_SUMMARIES:\n" + "\n---\n".join(section_summaries)
    body += f"\n\nPDF: {pdf_url}\n"
    return intro + body


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
