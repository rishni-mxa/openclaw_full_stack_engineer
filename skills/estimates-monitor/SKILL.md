---
name: estimates-monitor
description: >
  Monitor Australian Senate Estimates transcripts. Checks the APH schedule for
  newly published transcripts, downloads the PDF, extracts text, generates a
  summary X (Twitter) thread, and manages an approval gate before publishing.
  Handles ParlInfo WAF 403 via browser fallback.
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "🏛️",
        "requires":
          {
            "env":
              [
                "X_API_KEY",
                "X_API_SECRET",
                "X_ACCESS_TOKEN",
                "X_ACCESS_SECRET",
              ],
          },
      },
  }
---

# Estimates Monitor

You monitor Australian Senate Estimates transcripts published on the APH website
and create X (Twitter) thread summaries for the MXA Consulting account.

All commands run from the workspace root directory:
`{baseDir}/..`

The Python venv is at `.venv/`. Always activate it or use the full path:
`.venv/bin/python` (Linux/macOS) or `.venv/Scripts/python.exe` (Windows).

## Pipeline overview

1. **Check schedule** — detect new "Published in full" transcripts
2. **Download PDF** — via HTTP, or browser fallback if ParlInfo returns 403
3. **Extract text** — convert PDF to text using markitdown
4. **Summarise** — generate an X thread via LLM (map-reduce over chunks)
5. **Save pending thread** — store for human approval
6. **Announce** — tell the user a thread is ready for review
7. **On approval** — publish the thread to X

## Step 1: Check schedule and download PDF

Run the workflow script:

```
python scripts/fetch_transcript.py
```

Parse the JSON after `===RESULT===` in the output.

**If `status` is `"downloaded"`:** PDF is saved. Proceed to Step 2 with the
`pdf_path` from the result.

**If `status` is `"browser_required"`:** ParlInfo returned 403 (WAF challenge).
You must use your browser tool:

1. Open the `parlinfo_url` from the result in your browser.
2. Wait for the page to fully load (the WAF challenge resolves automatically).
3. Find the PDF download link — look for a link containing `/toc_pdf/` in the href.
4. Download that PDF file and save it to `data/pdfs/`.
5. Then register it:
   ```
   python scripts/fetch_transcript.py --register-pdf data/pdfs/<filename>.pdf
   ```

**If `status` is `"already_posted"`:** Nothing to do. Report that no new
transcripts are available.

**If `status` is `"error"`:** Report the error to the user.

## Step 2: Extract text from PDF

```python
from estimates_monitor.parser import extract_text
text = extract_text("<pdf_path>")
```

Or via exec:
```
python -c "from estimates_monitor.parser import extract_text; print(len(extract_text('<pdf_path>')))"
```

The text will be very long (hundreds of thousands of characters). That is normal.

## Step 3: Generate the X thread

Use the summariser pipeline. It needs an LLM call function — use yourself as the
LLM by reading the prompts and generating the responses inline.

The prompts are in `prompts/section.md` and `prompts/thread.md`. The pipeline:

1. **Map phase:** Split the extracted text into chunks (~3500 chars each) using
   `estimates_monitor.summarizer.chunk_text()`. For each chunk, read the prompt
   template from `prompts/section.md`, substitute the chunk text, and generate
   2-4 bullet points summarising that section.

2. **Reduce phase:** Collect all section summaries. Read the prompt template from
   `prompts/thread.md`, substitute the summaries, title, and PDF URL. Generate
   the final X thread as JSON: `{"tweets": [{"text": "..."}], "notes": "..."}`.

3. **Validate:** Run validation on the output:
   ```python
   from estimates_monitor.summarizer import validate_thread
   result = validate_thread(thread_json_string, max_tweets=8)
   ```
   Every tweet must be ≤ 280 characters. The thread must be ≤ 8 tweets.
   If validation fails, regenerate with corrections.

## Step 4: Save as pending thread

```python
from estimates_monitor.pending import save_thread
data = save_thread(
    transcript_id="<page_url from step 1>",
    title="<title from step 1>",
    pdf_url="<pdf_url or parlinfo_url>",
    tweets=["tweet 1 text", "tweet 2 text", ...],
)
thread_id = data["thread_id"]
```

## Step 5: Announce for approval

Tell the user:

> **New Senate Estimates thread ready for review**
>
> **Title:** [title]
> **Tweets:** [count]
> **Thread ID:** [thread_id]
>
> Say "approve [thread_id]" to publish, or "show dry-run [thread_id]" to preview
> tweet payloads, or "reject [thread_id]" to discard.

## Approval commands (user-initiated)

When the user asks to approve, reject, preview, or publish:

**Preview (dry-run):**
```
python -m estimates_monitor.cli approve <thread_id> --dry-run
```
Shows exact tweet payloads without changing state.

**Approve:**
```
python -m estimates_monitor.cli approve <thread_id>
```

**Publish (after approval):**
```
python -m estimates_monitor.cli publish <thread_id>
```
This posts the thread to X. Requires X API credentials in environment.

**Reject:**
```
python -m estimates_monitor.cli reject <thread_id>
```

**Check status:**
```
python -m estimates_monitor.cli status
python -m estimates_monitor.cli status --filter pending
```

## Error handling

- If `publish` fails mid-thread, it records which tweets succeeded. The thread
  status becomes `"failed"`. Re-approve and publish again to resume from where
  it left off.
- If the schedule page structure changes and parsing fails, report the error
  to the user with the exact exception message.
- If PDF extraction produces empty text, report it — the PDF may be scanned
  images rather than text.

## Important notes

- All CLI commands output JSON for easy parsing.
- The `data/` directory stores state (`state.json`), PDFs (`data/pdfs/`), and
  pending threads (`data/pending/`).
- Never publish without explicit user approval.
- The X API credentials are injected via environment variables by OpenClaw
  skill config — do not hardcode them.
