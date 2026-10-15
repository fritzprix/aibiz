---
name: morning-briefing
description: Builds the executive morning briefing (today's to-dos, yesterday's key issues, status by workstream) and sends it via Telegram. Use for "브리핑", "아침 브리핑", "오늘 뭐 해야 해", "어제 무슨 일 있었어", "브리핑 다시 해줘", "브리핑 시간 바꿔", "브리핑 켜/꺼", and for the scheduled run (`/morning-briefing auto`).
---

# morning-briefing — Morning briefing

`PY` = Windows `.venv/Scripts/python.exe`, Mac `.venv/bin/python` (run from project root)

Briefing = **new messages since the last briefing** + **current state of the work wiki**. Monday naturally includes the weekend.

## When the argument is `auto` (scheduled run — nobody is watching, never ask questions)
`scripts/briefing.py auto` launches headless Claude with this argument. Collection and sending are done by that program; here you **only produce files**.
1. Update the wiki: follow `kb-build` steps 1–4 exactly (new messages → `kb-builder`, then `digest.py commit kb`). Skip on `NOTHING_NEW`.
2. `PY scripts/digest.py prep briefing` → `PART:` list. (Continue even on `NOTHING_NEW` — write from wiki status alone.)
3. Run the `briefing-writer` agent (foreground):
   `Today: <YYYY-MM-DD (weekday)>. Message batches: <PART list or 'none'>. Using wiki/ and the latest briefing in briefings/, write briefings/<today>.md and briefings/<today>.telegram.txt.`
4. Confirm both files exist and stop. **Do not run `digest.py commit briefing`** (the program does it after a successful send).

## When a person asks ("브리핑 해줘", "브리핑 다시 해줘")
- If today's briefing file exists, show it (regenerate only if asked).
- To regenerate: run `PY scripts/briefing.py auto` **in the background** (collect → write → send to Telegram in one go). Say it takes 5–15 minutes.
  When done, also show `briefings/<today>.telegram.txt` in this window.
- If requested via the Telegram bot: reply "만들고 있어요, 10분 정도 걸려요", then run as above (the program sends it).

## Schedule management
| Request | Command |
|---|---|
| Turn on (default weekdays 07:30) | `PY scripts/briefing.py schedule` |
| Change time/days | `PY scripts/briefing.py schedule --time 08:00 --days daily` |
| Turn off | `PY scripts/briefing.py unschedule` |
| Status | `PY scripts/briefing.py status` |

When turning on, tell the user:
> 평일 아침 7시 30분에 텔레그램으로 브리핑을 보내 드려요. 컴퓨터가 켜져 있어야 해요 (잠자기 상태면 깨어날 때 바로 보내요). 비서 창은 꺼져 있어도 돼요.

Prerequisites: bot link + pairing (`tg-bot`) and account link (`tg-sync`). If `status` shows '받는 사람: 없음', start with `tg-bot`.

## Troubleshooting
| Symptom | Check |
|---|---|
| "브리핑이 안 왔어" | `briefing.py status` last result → tail of `logs/briefing.log` → explain the cause simply. If the PC was off: "비서 창에서 '브리핑 다시 해줘'" |
| "Claude Code 를 찾지 못했어요" | Claude Code moved after reinstall/update → run `briefing.py schedule` again (re-detects the path) |
| No briefing file produced | Check `logs/briefing_claude_last.log`. If login expired, have the user open the assistant window once and log in |
| Too long / too short | Adjust the item counts in `.claude/agents/briefing-writer.md` per the user's request |
| Wrong / missing to-do | Find the message that caused it, explain, and fix the to-do in the wiki workstream page (reflected next briefing) |
