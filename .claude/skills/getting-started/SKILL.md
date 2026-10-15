---
name: getting-started
description: Guides a new user through the whole first-time setup of this assistant, end to end. Use for "처음 시작", "처음 시작하기", "시작하기", "설정해줘", "세팅", "처음 써요", "뭐부터 해야 해", "설치했어", "처음 시작하기 이어서", or when nothing is set up yet.
---

# getting-started — First-time setup

The user is **non-technical**. Plain Korean, one step at a time; after each step say "다음은 ○○이에요".
Text in `>` blocks is Korean copy to give the user as-is.
Start by showing the big picture briefly:

> 업무 비서를 쓰려면 다섯 단계를 거쳐요. 전부 합쳐 30분 정도 걸리고, 그중 절반은 기다리기만 하면 돼요.
> 1. **내 텔레그램 연결** — 내가 참여한 채팅방 메시지를 비서가 읽을 수 있게 (5~10분)
> 2. **휴대폰 질문용 봇 만들기** — 밖에서도 휴대폰으로 비서에게 물어볼 수 있게 (5분)
> 3. **회의록용 Google AI 키** — 녹음을 글로 바꾸기 위해 (3분)
> 4. **업무 위키 처음 만들기** — 최근 2주 대화를 업무별로 정리 (기다리기 10~20분)
> 5. **아침 브리핑 켜기** — 매일 아침 휴대폰으로 오늘 할 일·어제 이슈·업무 현황 (1분)
>
> 중간에 멈춰도 괜찮아요. 다음에 "처음 시작하기 이어서"라고 하면 멈춘 곳부터 해요.

`PY` = Windows `.venv/Scripts/python.exe`, Mac `.venv/bin/python` (run from project root)

## Steps

### 0. Find current state
`PY scripts/tg_sync.py doctor --bot --offline`. If `.venv` doesn't exist yet, skip the check and go to step 1 — the setup window prepares everything on first run.
For steps already done, say "○○은 이미 되어 있어요" and move on.

Mac: if the project is inside `Documents`, `Desktop` or `Downloads`, first recommend moving it directly under home (e.g. `~/aibiz`) — macOS blocks background jobs there.

### 1. Telegram account link → follow `tg-sync` "First-time setup flow"
Start the first fetch in the background and move straight to step 2 (no need to wait).
In step 5 of tg-sync (chat review), help the user exclude personal chats (family, friends, hobby groups) — they would otherwise leak into the work wiki and briefings.

### 2. Phone bot → follow `tg-bot` "First-time setup flow"
Its step 4 closes this window, so say beforehand:
> 다시 열고 나서 "처음 시작하기 이어서"라고 말해 주세요.

### 3. Google AI key for minutes → follow `meeting-minutes` "First-time setup"
Never skip the billing (paid tier) guidance. If the user says "회의록은 안 쓸래", skip.

### 4. Build the wiki the first time → `kb-build` skill
First confirm step 1's first fetch finished (`doctor` "최근 수집"). Then start in the background:
> 최근 2주 대화를 업무별로 정리하고 있어요. 10~20분 걸리니 다음 단계를 먼저 할게요.

### 5. Turn on morning briefing → `morning-briefing` "Schedule"
Ask the time (default weekdays 07:30). If the wiki is done, offer "지금 한 번 미리 받아 볼까요?" → if yes, `briefing.py auto`.

### 6. Wrap up
Run `doctor --bot`, `transcribe.py doctor`, `briefing.py status`; confirm all OK, then explain usage briefly:

> 🎉 설정이 끝났어요! 이렇게 쓰시면 돼요:
> - **매일 아침**: 휴대폰으로 브리핑이 와요. (컴퓨터만 켜져 있으면 돼요)
> - **휴대폰 질문**: 폴더의 `start_assistant` 를 더블클릭해서 비서를 켜 두세요. (이 창이 켜져 있을 때만 답해요)
> - **질문**: 이 창이나 휴대폰 봇에 그냥 물어보세요. 예) "이번 주 ○○ 프로젝트 결정사항 정리해줘"
> - **회의록**: 녹음 파일을 봇에게 보내거나 이 창에 끌어다 놓으세요.
> - **뭔가 이상하면**: "점검해줘" 라고 말하세요.

## Principles
- If the user seems tired or says "나중에", stop immediately and say in one line where they stopped and how to resume.
- Secrets (app info, login code, 2FA password, bot token, API key) are **never** taken in chat — always the setup window.
- If one step fails 3+ times, write a short message summarizing what was tried that the user can send to the person who installed it.
