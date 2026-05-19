# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Daily English News for macOS — every day at 07:00, it fetches 5 English articles via RSS, calls `claude -p` (using the user's Pro subscription, no API key) to generate bilingual summaries + vocabulary, commits the result to `docs/news.json`, and pushes to GitHub Pages at `https://sammyandshen.github.io/daily-news/`.

## Running the Pipeline

```bash
# Full daily run (fetch → generate → retry → push)
cd ~/Documents/CC/daily-news
bash daily-update.sh

# Watch the log in real time
tail -f logs/$(date +%Y-%m-%d).log

# Re-run only the retry step (fixes failed stories for today)
TODAY=$(date +%Y-%m-%d) python3 scripts/retry_failed.py

# Manually fix failed stories for a specific past date
TODAY=2026-05-10 python3 scripts/retry_failed.py
```

## Scheduled Tasks (launchd)

```bash
bash install-launchd.sh          # install / reinstall both tasks
bash install-launchd.sh status   # check status + last exit code
bash install-launchd.sh remove   # uninstall
```

Two tasks are installed:
- `com.user.daily-news` — 07:00 daily, runs `daily-update.sh`
- `com.user.daily-news-retry` — 12:00 daily, re-runs `retry_failed.py` and pushes if changed

**Critical macOS TCC constraint**: The plist must NOT use `StandardOutPath`/`StandardErrorPath` pointing to `~/Documents` — launchd cannot open files there (exit code 78). Logs go to `~/Library/Logs/daily-news/`. The plist must also use `bash -c "cd ... && bash daily-update.sh"` rather than passing the script path directly, because `bash` launched by launchd cannot read script files from `~/Documents` (exit code 126).

## Architecture

```
daily-update.sh          # orchestrator: calls the three Python scripts in order
scripts/
  fetch_news.py          # RSS fetch → scores by keyword → writes docs/_candidates.json
  generate_with_claude_code.py  # reads _candidates.json → calls claude -p for each → writes docs/news.json
  retry_failed.py        # re-runs generate for any story where headlineCn contains "生成失败"
docs/
  news.json              # the live data file; GitHub Pages SPA reads this
  index.html             # single-page frontend (vanilla JS, no build step)
launchd/                 # plist templates (USERNAME placeholder replaced at install time)
logs/                    # daily run logs named YYYY-MM-DD.log
```

`docs/news.json` schema: `{ lastUpdated, level, days: { "YYYY-MM-DD": { label, stories: [...] } } }`. Stories older than 30 days are pruned on each write.

## Key Implementation Details

**Claude invocation** (`generate_with_claude_code.py`): uses `claude -p <prompt> --output-format json`. The outer JSON envelope's `result` field contains Claude's text response (properly escaped), eliminating JSON parsing failures from unescaped Chinese quotes. Falls back to `json_repair` if parse still fails, then to a `template_fallback` with `headlineCn = "（生成失败 · 见下方摘要）"`.

**Detecting failures**: `retry_failed.py` identifies stories by checking `"生成失败" in story["headlineCn"]`. It writes to `news.json` after each successful story (not in batch) to survive interruptions.

**ANTHROPIC_API_KEY**: explicitly removed from the subprocess environment before calling `claude -p`, to ensure the Pro subscription is used rather than API billing.

**Python dependencies**: `feedparser`, `requests` (see `scripts/requirements.txt`). Install with `pip3 install --user -r scripts/requirements.txt`.
