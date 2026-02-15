# Estimates Monitor — OpenClaw Setup Handover

This document tells you (the OpenClaw agent) how to install and configure the
estimates-monitor skill and cron job on your machine.

## Prerequisites

- This repo is cloned on your machine (via GitHub)
- Python 3.13+ available
- OpenClaw Gateway running

## Step 1: Set up the Python environment

From the repo root:

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv/Scripts/activate on Windows
pip install -r requirements.txt
```

Verify everything works:

```bash
python -m pytest tests/ -v
```

All 54 tests should pass.

## Step 2: Verify the skill is loaded

The skill lives at `skills/estimates-monitor/SKILL.md` in this workspace. Since
OpenClaw loads workspace skills from `<workspace>/skills/`, it should be
automatically available.

Verify by checking the skills list — you should see `estimates-monitor` with
the 🏛️ emoji.

## Step 3: Configure X API credentials

The skill requires 4 environment variables for posting to X. Add them to your
OpenClaw config at `~/.openclaw/openclaw.json`:

```json
{
  "skills": {
    "entries": {
      "estimates-monitor": {
        "enabled": true,
        "env": {
          "X_API_KEY": "<Consumer Key from X developer console>",
          "X_API_SECRET": "<Secret Key from X developer console>",
          "X_ACCESS_TOKEN": "<Access Token from X developer console>",
          "X_ACCESS_SECRET": "<Access Token Secret from X developer console>"
        }
      }
    }
  }
}
```

The user will provide these credentials. They are for the @MxaLabs X account.

**Important:** The Access Token must have been generated with **Read and Write**
permissions. If posting returns a 403 "oauth1-permissions" error, the tokens
need to be regenerated in the X developer console after setting permissions to
Read+Write.

## Step 4: Create the cron job

Set up a daily check at 8am AEST (Sydney time). This runs as an isolated
session and announces results back to the user:

```bash
openclaw cron add \
  --name "Estimates transcript check" \
  --cron "0 8 * * *" \
  --tz "Australia/Sydney" \
  --session isolated \
  --message "Run the estimates-monitor skill: check the APH schedule for new Senate Estimates transcripts. If a new transcript is found, download the PDF, extract text, generate a summary X thread, save it as pending, and announce it for my approval. If ParlInfo returns 403, use your browser to bypass the WAF and download the PDF." \
  --announce
```

Note: Add `--channel <channel> --to "<target>"` if you want delivery to a
specific channel (e.g. `--channel whatsapp --to "+61..."` or
`--channel telegram --to "chatid"`). Without those flags, the announce
will be delivered to the last active channel.

## Step 5: Manual test run

Test the full pipeline manually before relying on the cron:

```bash
openclaw cron run <job-id>
```

Or just ask the agent to "run the estimates-monitor skill" in a normal session.

Expected flow:
1. Runs `python scripts/fetch_transcript.py`
2. If ParlInfo 403 → opens browser, downloads PDF, registers it
3. Extracts text from PDF
4. Generates X thread (agent acts as the LLM for summarisation)
5. Saves pending thread
6. Announces: "New thread ready — say 'approve' to publish"

## How approval works

When the cron job (or manual run) finds a new transcript, it will announce
something like:

> **New Senate Estimates thread ready for review**
> Title: Rural and Regional Affairs 2026-02-10
> Tweets: 6
> Thread ID: a1b2c3d4e5f6

The user can then say:
- **"show dry-run a1b2c3d4e5f6"** — preview exact tweet payloads
- **"approve a1b2c3d4e5f6"** — approve for publishing
- **"reject a1b2c3d4e5f6"** — discard the thread

After approval, the user says **"publish a1b2c3d4e5f6"** (or you can
auto-publish after approval if the user prefers).

If publishing fails mid-thread, the partial progress is saved. Re-approve
and publish again to resume from where it left off.

## File layout reference

```
estimates_monitor/     # Python package
  cli.py               # CLI commands (latest, download-latest, status, approve, reject, publish)
  schedule.py          # APH schedule parser
  parlinfo.py          # ParlInfo PDF link extractor
  downloader.py        # Deterministic PDF downloader
  parser.py            # MarkItDown PDF text extraction
  summarizer.py        # Map-reduce summarisation + thread validation
  pending.py           # Pending thread store (data/pending/*.json)
  x_client.py          # X API client (OAuth1, thread posting)
  storage.py           # State tracking (data/state.json)
scripts/
  fetch_transcript.py  # Main workflow script (single command entry point)
prompts/
  section.md           # Map-phase prompt template
  thread.md            # Reduce-phase prompt template
skills/
  estimates-monitor/
    SKILL.md           # This skill definition
data/                  # Runtime data (gitignored)
  state.json           # Seen/posted tracking
  pdfs/                # Downloaded transcript PDFs
  pending/             # Pending thread JSON files
```

## Troubleshooting

- **"No published transcripts found"**: Senate Estimates sessions are periodic.
  If no new transcripts have been published, this is normal.
- **ParlInfo 403**: Use your browser tool to navigate the ParlInfo URL. The WAF
  challenge resolves automatically in a real browser.
- **X API 403 "oauth1-permissions"**: Access tokens were generated with
  Read-only permissions. Regenerate them in the X developer console after
  setting the app to Read+Write.
- **Empty PDF text**: The PDF may be scanned images. Report to the user.
- **Tests failing**: Run `pip install -r requirements.txt` to ensure all
  dependencies are installed.
