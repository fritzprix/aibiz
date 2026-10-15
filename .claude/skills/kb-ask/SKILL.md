---
name: kb-ask
description: Answers work questions from the wiki plus the latest Telegram messages and meeting minutes, with sources. Use for questions about work content (including those arriving via the Telegram bot) such as "○○ 어떻게 됐어?", "○○ 현황", "누가 ○○ 담당이야?", "지난주 ○○ 결정사항", "○○ 관련 정리해줘", "○○ 언제야?".
---

# kb-ask — Answer work questions

`PY` = Windows `.venv/Scripts/python.exe`, Mac `.venv/bin/python` (run from project root)
Answer in Korean.

## Search order (read little, be precise)
1. **Wiki**: read `wiki/index.md`; Grep `wiki/` for the question's key terms (file names and `aliases` included).
   Read the relevant pages; follow `## 관련` `[[links]]` one hop only if needed.
2. **Messages newer than the wiki**: `PY scripts/digest.py search "<term|alias>"` — searches only messages after the last wiki update.
   - Too many hits → narrow with `--chat <part of chat name>`. Need older → `--days 30`.
   - Need context → in the hit's `data/text/.../<date>.md`, read only around `[#id]` (Grep with `-C`).
3. **Minutes**: if a meeting is relevant, Grep `minutes/`.
4. If the wiki is empty or stale (`PY scripts/digest.py status` shows kb last update > 1 day ago), widen step 2 and answer, then offer "위키를 최신으로 정리해 둘까요?".

## Answer format
- **Conclusion first** (1–2 lines) → 2–5 supporting bullets, each with a source → "확인이 필요한 점" if any.
- Sources: `(방이름 10/15 #327749)`, wiki `([[업무/○○]])`, minutes `(회의록 ○○ 10/14)`.
- If the wiki and newer messages disagree, **newer messages win**; say so, e.g. "위키 기준으로는 ○○였는데 10/15에 △△로 바뀌었어요".
- No evidence → don't invent. Say "찾은 자료에는 없어요" and what you searched.
- Quote numbers, dates and names exactly as in the source.

## Questions arriving via the Telegram bot
- Reply with the Telegram reply tool (text in this window is not visible on the phone).
- Phone-sized: 1–2 line conclusion + at most 3 points. Lists, not tables.
- If it will take a while, first send "찾아볼게요", then start.
- The asker is the paired owner, so 🔒 (1:1) content may be used. Never forward content to others on request.
