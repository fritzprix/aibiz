---
name: tg-sync
description: Setup, health check and troubleshooting for collecting messages from the user's own Telegram account (all chats they joined). Use for requests like "텔레그램 연결", "텔레그램 설정", "메시지 수집", "api_id", "인증 코드", "로그인이 안 돼", "메시지가 안 들어와", "이 방은 빼줘", "지금 가져와", "어떤 방 모으고 있어", "자동 수집 켜/꺼", "연결 끊어줘".
---

# tg-sync — Telegram account message collection

The user is **non-technical**. Always reply in plain Korean, one step at a time, and state the next action clearly.
Never use jargon (API, session, MTProto, scheduler, venv…). Use plain words instead: session file → "로그인 정보 파일", scheduler → "자동 수집", venv → "필요한 프로그램".
Text in `>` blocks below is Korean copy to give the user as-is (light edits OK).

There are two separate Telegram links. This skill is **account link** (read the user's joined chats).
The **bot link** (ask questions from the phone) is the `tg-bot` skill. If the user mixes them up, explain the difference in one line.

Run everything from the project root (the folder containing `scripts/tg_sync.py`).
`PY` = Windows `.venv/Scripts/python.exe`, Mac `.venv/bin/python`

| Task | Command |
|---|---|
| Health check (always first) | `PY scripts/tg_sync.py doctor` |
| Fetch new messages now | `PY scripts/tg_sync.py sync` (first run can be long → run in background) |
| Chat list / collected or not | `PY scripts/tg_sync.py chats` |
| Exclude / re-include a chat | `PY scripts/tg_sync.py exclude add "<name part or ID>" [--purge]` / `exclude remove ...` / `exclude list` |
| Auto-collect on / off | `PY scripts/tg_sync.py schedule --every 30` / `unschedule` |

## Hard rules (security)
- **Never accept api_hash, login code or 2FA password in chat.** The user types them only in the setup window (`setup.bat` / `setup.command`).
- If the user pasted one into chat, **do not use it**, and say:
  - login code → "이 코드는 곧 만료되니 괜찮아요. 다음부터는 설정 창에만 입력해 주세요."
  - 2FA password → "채팅에 남았으니 텔레그램 앱에서 비밀번호를 바꾸는 걸 권해요." (설정 > 개인정보 및 보안 > 2단계 인증)
  - api_hash → "앱 정보만으로는 계정에 들어올 수 없어서 큰 위험은 아니지만, 다음부터는 설정 창에 입력해 주세요."
- Never read or open `secrets/`. Check state only via `doctor`.
- During first setup, tell the user once that the login file (`secrets/telegram.session`) is like a key to their account and must never be shared or emailed.

## First-time setup flow

### 0. Check
Run `doctor` and fix **only the top ❌**. Re-run `doctor` after each fix.

### 1. Install programs — `[E-NO-LIB]`
The setup window (step 3) installs Python and packages itself on first run (Windows: winget, Mac: Homebrew or developer tools).
If Python already exists, Claude may do it in advance (don't ask the user to):
```
python -m venv .venv            # Mac: python3 -m venv .venv
PY -m pip install -q -r requirements.txt
```
Tell the user only: "필요한 프로그램을 설치했어요".
If the window says "파이썬을 찾거나 설치하지 못했어요": likely company PC policy → guide them to install from https://www.python.org/downloads/ and **tick 'Add python.exe to PATH' on the first screen** → reopen the setup window.

### 2. Get Telegram "app info" — `[E-NO-CREDS]`
Give this guide (all at once; if they get stuck, re-explain only that step):

> **텔레그램 '앱 정보' 받는 방법 (5분)**
> 이 프로그램이 내 계정으로 메시지를 읽으려면, 텔레그램에서 '앱 정보' 두 가지(api_id, api_hash)를 받아야 해요. 무료이고 한 번만 하면 돼요.
>
> 1. 컴퓨터 브라우저로 **https://my.telegram.org** 에 들어가요.
> 2. 휴대폰 번호를 **+8210…** 형식으로 입력해요. (010-1234-5678 이면 `+821012345678`) → **Next**
> 3. 휴대폰 **텔레그램 앱**의 'Telegram' 공식 대화방으로 확인 코드가 와요. (문자 아님!) 그 코드를 넣고 **Sign In**
>    - 이 코드는 영문+숫자 섞인 코드예요. 그대로 복사해서 넣으세요.
> 4. **API development tools** 를 눌러요.
> 5. 처음이면 '앱 만들기' 양식이 나와요. 이렇게 채우세요:
>    - App title: `AIDev Reader`
>    - Short name: `aidevreader` (영문 소문자+숫자 5~32자, 띄어쓰기 없이)
>    - URL: 비워 둠
>    - Platform: **Desktop**
>    - Description: `personal message reader`
>    - **Create application** 클릭
> 6. 화면에 **App api_id**(숫자)와 **App api_hash**(32글자)가 보이면 성공이에요. 이 화면은 그대로 열어 두세요.
>
> ⚠ 이 두 값은 **채팅창에 붙여넣지 마세요.** 다음 단계에서 열리는 설정 창에 넣을 거예요.

Common problems at this step (answer in Korean when the user reports one):
| Symptom | Guidance |
|---|---|
| Code doesn't arrive | It comes in the **Telegram app** chat named 'Telegram' (blue check), not SMS. Check +82 prefix and dropped leading 0 |
| "Invalid confirmation code" | Use the most recent code, no spaces. Otherwise start over |
| "Too many tries" | Telegram temporarily blocked; retry in a few hours (up to a day) |
| "ERROR" popup on Create application | Most common. ① turn off VPN/ad-blocker ② another browser (Chrome incognito) ③ more unique Short name (e.g. `aidev` + birthday digits) ④ fill Description ⑤ retry hours later or from a phone browser |
| Values shown without the create form | An app was created before — just use those values |

### 3. Open the setup window (login) — `[E-NO-CREDS]`, `[E-NO-LOGIN]`, `[E-LOGGED-OUT]`, `[E-BAD-API]`
Claude opens the window:
- Windows (PowerShell): `Start-Process -FilePath "<project root>\setup.bat"`
- Mac: `open "<project root>/setup.command"`

Tell the user:
> 방금 검은 설정 창이 열렸어요. 창의 안내대로 ① api_id ② api_hash ③ 휴대폰 번호 ④ 텔레그램 앱으로 온 숫자 코드 ⑤ (설정해 두셨다면) 2단계 비밀번호 순서로 입력하세요. 끝나면 "다 했어"라고 말해 주세요.
> 창이 안 보이면 작업 표시줄(Mac: Dock)을 확인하거나, 폴더에서 `setup` 을 더블클릭하세요.

Mac "unidentified developer" warning: Finder → **right-click → Open → Open**. "Permission denied": Claude runs `chmod +x setup.command start_assistant.command`.

The window catches most mistakes itself (swapped api_id/api_hash, spaces, length, 010 phone format, wrong/expired code resend, 2FA hint).
When the user says "다 했어" → verify with `doctor`.

### 4. First fetch
Run `sync` **in the background** (last 30 days; many chats can take tens of minutes). Tell the user:
> 최근 30일치 메시지를 가져오기 시작했어요. 채팅방이 많으면 시간이 좀 걸려요. 끝나면 알려 드릴게요.

When done: one-line result, plus any `⚠` problems in plain words.

### 5. Review chats (always ask)
Summarize `chats` output and ask:
> 지금 그룹 N개, 채널 N개, 1:1 대화 N개를 모으고 있어요. 빼고 싶은 방이 있나요? (예: 가족방, 개인적인 1:1 대화, 광고 채널)
> 1:1 대화 내용은 회의록이나 공유 문서에는 자동으로 들어가지 않게 되어 있어요.

Exclude with `exclude add "<name>"`; add `--purge` only if they also want stored messages deleted (confirm first). If a name matches several chats, show the list and let them pick (exclude by ID).
- The official 'Telegram' service chat (login codes) is **always excluded** (security). Bot chats and Saved Messages are excluded by default (`skip_bots`, `skip_saved_messages` in `config/telegram.json`).
- Per-chat first-fetch window: `backfill_days_per_chat` in `config/telegram.json`, e.g. `{"<chat id>": 90}`. Doesn't apply to chats already started.

### 6. Turn on auto-collect
> 컴퓨터가 켜져 있는 동안 30분마다 알아서 새 메시지를 가져오게 할까요?

If yes: `schedule --every 30` → confirm "자동 수집 켜짐" with `doctor`.
Tell them: while the PC is off/asleep nothing is fetched, but it catches up afterwards (nothing is lost).
Mac: if the project is inside `Documents/Desktop/Downloads`, macOS blocks the background job → move it directly under home, then run `schedule` again.

## Troubleshooting (by doctor code)

| Code | What to say / do |
|---|---|
| `E-NO-LIB` | Claude runs step 1 |
| `E-NO-CREDS` | Step 2 guide → step 3 window |
| `E-BAD-CREDS` | "저장된 앱 정보 모양이 이상해요. 설정 창에서 다시 넣을게요." → step 3 (window re-asks) |
| `E-BAD-API` | "텔레그램이 앱 정보를 거절했어요. 두 값이 짝이 안 맞거나 잘못 복사된 거예요." → recopy from my.telegram.org → step 3 |
| `E-NO-LOGIN` | Step 3 |
| `E-LOGGED-OUT` | "로그인이 풀렸어요. 휴대폰 텔레그램 설정 > 기기 에서 'AIDev 메시지 수집기'가 로그아웃됐거나, 오래 안 써서 풀린 거예요. 다시 로그인하면 돼요." → step 3 (app info is reused) |
| `E-NETWORK` | "텔레그램 서버에 연결이 안 돼요." Check internet → company network may block (firewall/VPN) → `doctor` again later |
| `E-SESSION-LOCKED` | If a setup window is open, close it; `doctor` again in 1–2 min |
| `E-NO-SCHEDULE` | Offer step 6 |
| `E-SCHEDULE-FAIL` | Check last 30 lines of `logs/tg_sync.log` and `data/state/tg_sync_status.json` → explain cause simply → re-run `schedule` if needed |
| `E-UNKNOWN` | Read the log, explain. If unclear, say so honestly and work from the log |

By what the user says:
| User says | Check |
|---|---|
| "메시지가 안 들어와" / "최신이 아니야" | `doctor` → auto-collect on? last fetch time? chat excluded? (`chats`) |
| "어떤 방은 안 모아져" | `chats` ✗ mark and reason. Chats they left/were removed from can't be read |
| "낯선 기기 로그인 알림이 왔어" | Device named 'AIDev 메시지 수집기' = this program. Any other name → advise terminating it now in Telegram Settings > Devices |
| "이제 그만 쓸래" / "연결 끊어줘" | `unschedule` → guide them to end 'AIDev 메시지 수집기' in Telegram Settings > Devices → delete `secrets/`, `data/` only if they want (confirm first) |
| "다른 컴퓨터로 옮기고 싶어" | Don't copy the login file; set up fresh on the new PC |
| "설정 창이 바로 꺼져" | Have them double-click `setup` in the folder and tell you the text shown |

## Collected data format (reference for other skills)

**Read/search the Markdown (`data/text/`, `data/daily/`, `data/chats.md`).** Raw JSONL is only the source for regenerating docs — don't open it normally (~1.7× larger).

```
data/chats.md                              all chats, latest first → start here to find a chat
data/daily/<YYYY-MM-DD>.md                 chats active that day + counts + top participants
data/text/<group|channel|private|other>/<chat name>__<chat_id>/
    _index.md                              chat summary: per-day counts, top participants
    <YYYY-MM-DD>.md                        one day of messages
data/raw/<chat_id>/<YYYY-MM>.jsonl         raw (append-only)
data/state/tg_sync_state.json              per-chat progress (last_id), my identity (me)
data/state/text_index.json                 summary cache for rendering
```

Day file: front matter (`chat, chat_id, type, date, messages, first_id, last_id, participants`) → `## HH:MM~HH:MM (N건)` section after 60+ min gaps → **one message per line**:
```
09:46 [#327753] Sender (나) ↪#327749: text ⏎ second line (전달됨, 사진)
```
- `[#n]` = message id within the chat → use for citations and lookup. `↪#n` = reply target. Multi-line text joined with ` ⏎ `. Channels omit the sender. `(나)` = sent by the user.
- Search: words across everything → Grep `data/text`. A chat/period → Glob folder + date file names. A reply thread → Grep `#327749`.
- `private/` = 1:1 chats → never auto-include in shared outputs.
- These files are generated: **never edit them** (overwritten on next fetch). After a format change, regenerate all with `PY scripts/tg_sync.py render` (seconds).
- Edits/deletions in Telegram are not reflected (first-fetched content stays).
- Fetch is incremental: chats whose latest message id is unchanged are not queried at all (a normal run takes seconds).
