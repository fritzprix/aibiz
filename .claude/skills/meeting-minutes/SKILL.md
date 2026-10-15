---
name: meeting-minutes
description: Takes a meeting recording, transcribes it (Gemini) and produces executive-ready minutes (md + Word). Use when an audio/voice file arrives (including Telegram bot attachments) or for "회의록 만들어줘", "녹음 정리", "전사해줘", and for Gemini API key setup/troubleshooting ("Gemini 설정", "AI Studio", "전사가 안 돼").
---

# meeting-minutes — Recording → minutes

The user is **non-technical**: plain Korean, one step at a time. Instead of "API" or "transcription engine", say things like "Google 의 AI(Gemini)로 녹음을 글로 바꿔요".
Text in `>` blocks is Korean copy to give the user as-is.

`PY` = Windows `.venv/Scripts/python.exe`, Mac `.venv/bin/python` (run from project root)

## 0. Check readiness
`PY scripts/transcribe.py doctor --offline` → if `[E-GEMINI-NO-KEY]`, start with "First-time setup".

## First-time setup (Gemini key)

### Key guide (give as-is)
> **Google AI 키 받는 방법 (3분)**
> 1. 컴퓨터 브라우저로 **https://aistudio.google.com/apikey** 에 들어가 Google 계정으로 로그인해요. (회사 Google 계정이 막혀 있으면 개인 계정도 돼요)
> 2. 처음이면 이용약관 동의 화면이 나와요 → 동의
> 3. **Create API key** (API 키 만들기) 를 눌러요. 프로젝트를 고르라고 하면 기본값 그대로.
> 4. `AIza…` 로 시작하는 긴 키가 나오면 **복사** 버튼을 눌러요.
> 5. ⚠ 이 키는 **채팅창에 붙여넣지 마세요.** 다음에 열리는 설정 창에 넣을 거예요.
>
> **꼭 해 주세요 — 결제 설정 (회의 내용 보호)**
> 무료로 쓰면 보낸 녹음이 Google 의 AI 개선에 쓰일 수 있어요. 같은 화면의 **Set up billing**(결제 설정)에서 카드를 등록하면 유료 등급이 되어 학습에 쓰이지 않아요. 비용은 1시간 회의에 몇백 원 수준이에요.

### Open the setup window
- Windows (PowerShell): `Start-Process -FilePath "<project root>\setup.bat" -ArgumentList "gemini"`
- Mac: `osascript -e 'tell application "Terminal" to do script "cd \"<project root>\" && bash setup.command gemini"'`
- If it doesn't open (security policy): give the user the "회의록용 Google AI 키" line from README section 6 ② to paste themselves.

> 설정 창이 열렸어요. 복사한 키를 붙여넣고 Enter. 결제 설정을 했는지 물으면 답해 주세요. 끝나면 "다 했어" 라고 말해 주세요.

Then `PY scripts/transcribe.py doctor` (live check). The model is auto-selected (latest available flash).
If the user pasted the key in chat: don't use it; say "채팅에 남았으니 AI Studio 에서 그 키를 삭제하고 새로 만들어 설정 창에 넣어 주세요."

## Getting the recording (three paths)
1. **File path / drag-and-drop**: use the given path.
2. **Telegram bot attachment ≤ 20MB**: download via the Telegram download tool using the attachment file id.
3. **Telegram bot attachment > 20MB** — bots cannot download large files. Use the account link instead:
   `PY scripts/tg_sync.py fetch-media` → use the `AUDIO:` path (latest recording the user sent in their bot chat within 24h).
   If an attachment is visible but the download fails or it's large, switch to this immediately. Never ask the user to resend.

If it came via Telegram, reply right away: "녹음 받았어요. 글로 바꾸는 중이에요 (1시간 녹음 기준 3~5분)."

## Producing the minutes
1. **Free-tier check**: if doctor shows `[E-GEMINI-FREE-TIER]`, ask once before starting:
   > 지금은 무료 등급이라 이 녹음이 Google 의 AI 개선에 쓰일 수 있어요. 그래도 진행할까요?
   (Via Telegram: ask by reply and wait.)
2. **Transcribe**: `PY scripts/transcribe.py run "<audio path>" --title "<title if known>" --speakers "<attendees if known, comma-separated>"` — run **in the background**. Use the final `TRANSCRIPT:` path.
   - Always pass attendees when known (speaker attribution is the weakest part, so this helps most). If the user sent "참석: ○○, △△" with the recording, use it. If unknown, don't ask — proceed; if `wiki/사람/` exists you may pass people related to the topic as candidates.
   - Recording date is parsed from the file name (e.g. `260430_083802`). If wrong: `--date "2026-04-30 08:38"`.
   - Audio is processed in 5-minute chunks; chunks with too little text are retried/split automatically. A rerun skips finished chunks.
3. **Write minutes**: hand to the `minutes-writer` agent (background):
   `Transcript: <TRANSCRIPT path>. Meeting date: <recording date (weekday)>. Today: <YYYY-MM-DD (weekday)>. Title/attendees/time if known: <user info>. Write the minutes.`
   (The weekday is needed to resolve phrases like "이번 주 금요일", "다음 주 화요일".)
4. **Word file**: `PY scripts/md2docx.py "<minutes md>"` → `DOCX:` path.
5. **Deliver**:
   - In this window: the 3-line summary + file locations + items needing confirmation.
   - Via Telegram: reply with the 3-line summary + action items, attach the Word file.
   - Finally ask about confirmation items, e.g. "화자2 가 누구인지 알려 주시면 이름으로 바꿔 드릴게요". Then fix the md and regenerate the Word file.
6. The next `kb-build` puts this meeting's decisions and action items into the work wiki.

## Sharing rules
- `minutes/` is for sharing among executives. Never mix in 🔒 (1:1 Telegram) content.
- Don't share raw transcripts (`data/transcripts/`) unless asked, and confirm first.
- Minutes are marked "AI 초안 · 검토 필요". When the user says it's reviewed, set front matter `status` to `확정` and regenerate the Word file.

## Troubleshooting
| Code / symptom | Guidance |
|---|---|
| `E-GEMINI-NO-KEY` | First-time setup |
| `E-GEMINI-BAD-KEY` | "키가 틀렸거나 지워졌어요." → new key in AI Studio → setup window |
| `E-GEMINI-QUOTA` | Likely free-tier limit → suggest billing, or retry later (`run` resumes) |
| `E-GEMINI-REGION` | Turn off VPN → else set up billing |
| `E-GEMINI-PERMISSION` | Create a new key |
| `E-GEMINI-MODEL` | Set `model` to `"auto"` in `config/meeting.json` |
| `E-GEMINI-SERVER` | Temporary Google issue → rerun `run` in a few minutes (resumes) |
| "녹음 파일을 읽을 수 없어요" | Corrupt or not audio. Get it again in another format (m4a/mp3) |
| Speakers mixed up | Speaker numbers can change across 5-min chunks → get attendee names and re-transcribe with `--speakers` (delete that recording's folder in `data/audio/work/` first), or unify by context in the minutes |
| Recordings over 1 hour | Fine (more chunks). ~3 min per hour of audio |
