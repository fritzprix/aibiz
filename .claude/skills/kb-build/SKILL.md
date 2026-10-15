---
name: kb-build
description: Updates the work wiki (wiki/) from newly collected Telegram messages and new meeting minutes. Use for "위키 업데이트", "지식 정리", "정리해 둬", "위키 반영", "kb-build", or before a briefing/answer when the wiki is stale.
---

# kb-build — Update the work wiki

Tell the user simply, in Korean: "새 대화 내용을 업무 위키에 정리할게요".

`PY` = Windows `.venv/Scripts/python.exe`, Mac `.venv/bin/python` (run from project root)

## Steps
1. **Prepare**: `PY scripts/digest.py prep kb`
   - `NOTHING_NEW` → say "새로 정리할 내용이 없어요" and stop (still do step 3).
   - "이미 진행 중" → another update is running. If stale for 6+ hours: `PY scripts/digest.py release kb`, then retry.
   - First run covers the last 14 days → several batches. Tell the user "처음이라 10~20분 걸려요".
2. **Apply**: for each printed `PART:` file, run the `kb-builder` agent **one at a time, in order**.
   - Prompt: `Batch file: <PART path>. Apply this batch to wiki/. Today: <YYYY-MM-DD (weekday)>.`
   - Never run batches in parallel (concurrent edits overwrite each other).
   - In an interactive window that must stay responsive to Telegram, run in the background and start the next batch when each finishes.
3. **New minutes**: if `minutes/` has `*.md` files newer than the last entry in `wiki/log.md`, pass each to `kb-builder`:
   `Minutes file: <path>. Apply decisions, action items and work status to wiki/. Cite as (회의록 <title> <date>).`
4. **Mark done**: only if every batch succeeded: `PY scripts/digest.py commit kb`.
   On any failure: `PY scripts/digest.py release kb` (next run redoes the same batch) and tell the user simply.
5. **Report**: merge the agents' "주요 변화" into 3–7 Korean lines.

## Principles
- Each person builds their own wiki (not shared via git).
- 1:1 chat content may enter the wiki but is marked 🔒. Never put 🔒 content into shareable outputs (distributed minutes etc.).
- The user may edit wiki pages directly; kb-builder respects existing content and appends.
- Cost: a normal day is 1–2 batches. Only the first run is large. Channels are capped at 40 posts per chat per run.
