# 업무 비서 — 사용 설명서

텔레그램 대화를 업무별로 정리해 두었다가 질문에 답하고, 매일 아침 브리핑을 보내고, 회의 녹음으로 회의록을 만들어 주는 비서예요.
컴퓨터의 **Claude Code** 위에서 동작하고, 휴대폰 **텔레그램**으로도 쓸 수 있어요.

| 할 수 있는 일 | 어떻게 |
|---|---|
| 📨 아침 브리핑 | 평일 아침 7:30 휴대폰으로 자동 도착 — 오늘 할 일, 어제 주요 이슈, 업무별 현황 |
| 💬 업무 질문 | 비서 창이나 휴대폰 봇에 그냥 물어보기 — "OpenAI 건 어떻게 됐어?" |
| 🎙 회의록 | 녹음 파일을 봇에 보내거나 창에 끌어다 놓기 → 회의록(Word) |
| 📚 업무 위키 | 텔레그램 대화가 업무·사람·조직별 문서로 자동 정리 (`wiki/` 폴더, Obsidian 으로 보기 좋음) |

---

## 1. 설치 (처음 한 번)

### Windows
1. 시작 메뉴에서 **PowerShell** 을 열고 아래 두 줄을 차례로 붙여넣어 실행해요.
   ```
   winget install -e --id Git.Git
   irm https://claude.ai/install.ps1 | iex
   ```
2. PowerShell 창을 닫았다가 다시 열고, 이 폴더를 받아요 (설치해 주는 분이 알려준 방법으로).
   ```
   gh repo clone fritzprix/aibiz $HOME\aibiz
   ```

### Mac
1. **터미널** 앱을 열고 아래 줄을 붙여넣어 실행해요.
   ```
   curl -fsSL https://claude.ai/install.sh | bash
   ```
2. 이 폴더를 **홈 폴더 바로 아래**에 받아요 (예: `~/aibiz`).
   ⚠ '문서', '데스크탑', '다운로드' 안에 두면 Mac 보안 때문에 자동 수집·브리핑이 안 돼요.

> 파이썬 등 나머지 필요한 프로그램은 처음 설정할 때 **설정 창이 알아서 설치**해요.

---

## 2. 비서 시작하기

폴더 안의 **`start_assistant`** 를 더블클릭하세요. (Windows: `start_assistant.bat`, Mac: `start_assistant.command`)
- Mac 에서 "확인되지 않은 개발자" 경고가 나오면: 파일을 **우클릭 → 열기 → 열기**

### 처음 열 때 한 번만
1. **Claude 로그인** — 브라우저가 열리면 Claude 계정으로 로그인해요.
2. **"이 폴더를 신뢰할까요?"** → 신뢰한다(Yes)고 답해요.
3. **텔레그램 플러그인 설치** — 설치를 권하는 안내가 나오면 설치해요.
   안내가 안 나오면 창에 아래를 그대로 입력해요:
   ```
   /plugin install telegram@claude-plugins-official
   ```
4. 플러그인을 설치했으면 **창을 닫고 `start_assistant` 로 다시 열어요.**
5. 창에 **`처음 시작하기`** 라고 입력해요. 이후는 비서가 한 단계씩 안내해요 (30분 정도):
   1. 내 텔레그램 연결 (휴대폰으로 온 코드 입력)
   2. 휴대폰 질문용 봇 만들기
   3. 회의록용 Google AI 키
   4. 업무 위키 처음 만들기 (기다리기만)
   5. 아침 브리핑 켜기

> 🔒 **비밀번호·인증 코드·키는 절대 채팅창에 붙여넣지 마세요.** 비서가 열어 주는 **설정 창**에만 입력해요.
>
> 💡 봇 만들기·텔레그램 앱 정보·Google AI 키는 아래 **7. 부록** 을 보고 미리 받아 두면 설정이 빨라요.

### 왜 `start_assistant` 로 열어야 하나요?
휴대폰 봇으로 보낸 메시지는 **`start_assistant` 로 연 창에서만** 받아요. 이 파일은 아래 명령으로 Claude 를 실행해요:
```
claude --channels plugin:telegram@claude-plugins-official --permission-mode acceptEdits --allowedTools ...
```
- `--channels plugin:telegram@claude-plugins-official` — 휴대폰 봇 메시지를 이 창으로 받음 (그냥 `claude` 로 열면 안 들어와요)
- `--permission-mode acceptEdits`, `--allowedTools ...` — 비서 전용 프로그램과 텔레그램 답장을 미리 허용. 밖에서 휴대폰으로 질문했을 때 PC 화면의 "허용할까요?" 창 때문에 답이 멈추지 않게 해요. 그 밖의 명령은 여전히 물어봐요.

비서 창은 **하나만** 열어 두세요. 두 개를 열면 휴대폰 메시지가 한쪽으로만 가요.

---

## 3. 매일 쓰는 법

### 📨 아침 브리핑
- 평일 07:30 에 휴대폰 텔레그램으로 와요. 요약 메시지 + 전체본 파일.
- **컴퓨터만 켜져 있으면 돼요** (비서 창은 꺼져 있어도 됨). 잠자기 상태였으면 깨어날 때 보내요.
- 바꾸기: "브리핑 8시로 바꿔줘", "주말에도 보내줘", "브리핑 꺼줘"
- 다시 받기: "브리핑 다시 해줘"

### 💬 질문하기
비서 창이나 휴대폰 봇에 평소 말투로 물어보세요.
- "Google TPUaaS 지금 어디까지 됐어?"
- "이번 주 결정된 것들 정리해줘"
- "OpenAI 화상미팅 언제야?"
- "황두현 팀장이 맡은 일 뭐 있어?"

답에는 근거가 된 대화방·날짜가 붙어요. 위키에 아직 정리되지 않은 최신 대화까지 찾아봐요.
⚠ 휴대폰 질문은 **컴퓨터에 `start_assistant` 창이 켜져 있을 때만** 답해요.

### 🎙 회의록
- 녹음 파일을 **봇에게 보내거나**, 비서 창에 **끌어다 놓으세요.** 크기 제한 없음 (큰 파일도 자동으로 받아요).
- 참석자를 같이 알려 주면 정확도가 올라가요: "참석: 김상무, 이지용 팀장, Rodrigo"
- 1시간 녹음 → 약 5분 뒤 회의록(Word)이 와요. "확인 필요" 항목을 알려 주면 고쳐서 다시 만들어요.
- 회의록은 `minutes/` 폴더에 저장돼요.

### 📚 업무 위키
- 아침 브리핑 때마다 새 대화가 자동으로 정리돼요. 바로 정리하려면: "위키 업데이트해줘"
- `wiki/` 폴더를 [Obsidian](https://obsidian.md) 으로 열면 업무·사람·조직 문서와 연결 그래프를 볼 수 있어요.
- 직접 고쳐도 돼요. 다음 정리 때 고친 내용을 존중해요.

### 자주 쓰는 말
| 이렇게 말하면 | 비서가 하는 일 |
|---|---|
| 점검해줘 | 텔레그램·봇·회의록·브리핑 상태를 한 번에 확인 |
| 지금 메시지 가져와 | 텔레그램 새 메시지 바로 수집 |
| ○○ 방은 빼줘 | 그 대화방을 수집·위키·브리핑에서 제외 |
| 어떤 방들 모으고 있어? | 수집 중인 대화방 목록 |
| 처음 시작하기 이어서 | 첫 설정을 멈춘 곳부터 |

---

## 4. 문제가 생기면

먼저 비서 창에 **"점검해줘"** 라고 하세요. ❌ 표시와 함께 해결 방법을 안내해요.

| 증상 | 해결 |
|---|---|
| 휴대폰 봇이 답을 안 해요 | 컴퓨터가 켜져 있고 `start_assistant` 창이 **하나만** 열려 있는지 확인 |
| 아침 브리핑이 안 왔어요 | 컴퓨터가 꺼져/잠자기였는지 확인 → 비서 창에 "브리핑 다시 해줘" |
| 텔레그램에 '새 기기 로그인' 알림이 왔어요 | 기기 이름이 **AIDev 메시지 수집기** 면 이 비서예요. 다른 이름이면 텔레그램 설정 > 기기에서 즉시 종료 |
| 설정 창이 바로 꺼져요 | 폴더에서 `setup` 을 더블클릭해 보고, 창에 나온 문구를 비서에게 알려 주세요 |
| `start_assistant` / `setup` 이 안 열려요 (회사 보안 정책) | 아래 **6. 실행 파일이 막혀 있을 때** 의 명령을 복사해서 붙여넣으세요 |
| "로그인이 풀렸어요" | 비서에게 "텔레그램 다시 연결해줘" |
| Claude 로그인 만료 | `start_assistant` 를 열어 다시 로그인 (아침 브리핑도 이 로그인을 써요) |

창에 나온 안내 문구를 그대로 비서에게 알려 주면 대부분 해결 방법을 알려줘요. (인증 코드·비밀번호는 빼고)

---

## 5. 개인정보와 데이터

- 모든 데이터는 **이 컴퓨터에만** 저장돼요. 텔레그램 대화는 읽기만 하고 보내거나 지우지 않아요.
- 1:1 대화 내용은 🔒 로 표시되고, 회의록 같은 공유용 문서에는 들어가지 않아요.
- 회의 녹음은 글로 바꾸기 위해 Google AI(Gemini)로 보내져요. **AI Studio 결제 설정을 하면 학습에 쓰이지 않아요.**
- 저장 위치: `wiki/` 위키 · `minutes/` 회의록 · `briefings/` 브리핑 · `data/` 원본 메시지·녹음 · `secrets/` 로그인 정보 (절대 다른 곳에 복사하거나 보내지 마세요)

### 그만 쓰려면
비서에게 "연결 끊어줘" → 자동 수집·브리핑을 끄고 정리 방법을 안내해요. 휴대폰 텔레그램 설정 > 기기에서 'AIDev 메시지 수집기'도 종료하세요.

### 새 버전 받기
비서 창에 "업데이트해줘" 또는 폴더에서 `git pull`. (개인 데이터는 영향 없음)

---

## 6. 실행 파일이 막혀 있을 때 (복사해서 붙여넣기)

회사 보안 정책 때문에 `start_assistant` / `setup` 파일을 더블클릭해도 열리지 않으면, 아래 명령을 **통째로 복사해서** 터미널에 붙여넣고 Enter 를 누르세요.
파일을 실행하는 대신 같은 일을 하는 명령을 직접 입력하는 방법이에요.
- Windows: 시작 메뉴 → **PowerShell**
- Mac: 응용 프로그램 → 유틸리티 → **터미널**

폴더 위치가 다르면 첫 줄의 `aibiz` 경로만 실제 위치로 바꾸세요.

### ① 처음 한 번: 필요한 프로그램 준비

**Windows (PowerShell)**
```powershell
cd $HOME\aibiz
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { winget install -e --id Python.Python.3.12 --scope user; Write-Host "파이썬 설치 완료. PowerShell 을 닫고 새로 연 다음 이 블록을 한 번 더 붙여넣으세요."; return }
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Mac (터미널)**
```bash
cd ~/aibiz
python3 -m venv .venv || { echo "개발자 도구 설치 창이 뜨면 '설치'를 누르고, 끝나면 이 블록을 다시 붙여넣으세요."; xcode-select --install; }
.venv/bin/python -m pip install -r requirements.txt
```

### ② 설정 창 대신 (비서가 "설정 창을 열었어요"라고 했는데 안 열렸을 때)

비서가 말한 설정 종류에 맞는 **한 줄**만 붙여넣으세요. 안내는 터미널에 나와요.

| 설정 | Windows (PowerShell) | Mac (터미널) |
|---|---|---|
| 내 텔레그램 연결 | `cd $HOME\aibiz; .venv\Scripts\python.exe scripts\tg_sync.py setup` | `cd ~/aibiz && .venv/bin/python scripts/tg_sync.py setup` |
| 휴대폰 질문용 봇 | `cd $HOME\aibiz; .venv\Scripts\python.exe scripts\tg_sync.py bot-setup` | `cd ~/aibiz && .venv/bin/python scripts/tg_sync.py bot-setup` |
| 회의록용 Google AI 키 | `cd $HOME\aibiz; .venv\Scripts\python.exe scripts\transcribe.py setup` | `cd ~/aibiz && .venv/bin/python scripts/transcribe.py setup` |

### ③ 비서 시작 (`start_assistant` 대신)

**Windows (PowerShell)**
```powershell
cd $HOME\aibiz
$PY = ".venv/Scripts/python.exe"
$tools = @(
  "Bash($PY scripts/tg_sync.py:*)", "Bash($PY scripts/transcribe.py:*)", "Bash($PY scripts/digest.py:*)",
  "Bash($PY scripts/briefing.py:*)", "Bash($PY scripts/md2docx.py:*)", "Bash($PY scripts/directive.py:*)",
  "mcp__plugin_telegram_telegram__reply", "mcp__plugin_telegram_telegram__react",
  "mcp__plugin_telegram_telegram__edit_message", "mcp__plugin_telegram_telegram__download_attachment",
  "Agent", "Skill"
)
claude --channels plugin:telegram@claude-plugins-official --permission-mode acceptEdits --allowedTools @tools
```

**Mac (터미널)**
```bash
cd ~/aibiz
PY=.venv/bin/python
TOOLS=(
  "Bash($PY scripts/tg_sync.py:*)" "Bash($PY scripts/transcribe.py:*)" "Bash($PY scripts/digest.py:*)"
  "Bash($PY scripts/briefing.py:*)" "Bash($PY scripts/md2docx.py:*)" "Bash($PY scripts/directive.py:*)"
  "mcp__plugin_telegram_telegram__reply" "mcp__plugin_telegram_telegram__react"
  "mcp__plugin_telegram_telegram__edit_message" "mcp__plugin_telegram_telegram__download_attachment"
  "Agent" "Skill"
)
claude --channels plugin:telegram@claude-plugins-official --permission-mode acceptEdits --allowedTools "${TOOLS[@]}"
```

### ④ 매일 편하게 (선택)
③ 을 매번 붙여넣기 번거로우면, 아래를 **한 번만** 실행해 두세요. 이후로는 터미널에 `aibiz` 만 입력하면 비서가 켜져요.

**Windows (PowerShell)**
```powershell
New-Item -ItemType File -Force -Path $PROFILE | Out-Null
Add-Content $PROFILE @'
function aibiz {
  Set-Location $HOME\aibiz
  $PY = ".venv/Scripts/python.exe"
  $tools = @("Bash($PY scripts/tg_sync.py:*)","Bash($PY scripts/transcribe.py:*)","Bash($PY scripts/digest.py:*)","Bash($PY scripts/briefing.py:*)","Bash($PY scripts/md2docx.py:*)", "Bash($PY scripts/directive.py:*)","mcp__plugin_telegram_telegram__reply","mcp__plugin_telegram_telegram__react","mcp__plugin_telegram_telegram__edit_message","mcp__plugin_telegram_telegram__download_attachment","Agent","Skill")
  claude --channels plugin:telegram@claude-plugins-official --permission-mode acceptEdits --allowedTools @tools
}
'@
```
(PowerShell 이 "스크립트 실행이 비활성화"라고 하면 이 방법은 건너뛰고 ③ 을 그대로 쓰세요.)

**Mac (터미널)**
```bash
cat >> ~/.zshrc <<'EOF'
aibiz() {
  cd ~/aibiz || return
  local PY=.venv/bin/python
  claude --channels plugin:telegram@claude-plugins-official --permission-mode acceptEdits --allowedTools \
    "Bash($PY scripts/tg_sync.py:*)" "Bash($PY scripts/transcribe.py:*)" "Bash($PY scripts/digest.py:*)" \
    "Bash($PY scripts/briefing.py:*)" "Bash($PY scripts/md2docx.py:*)" "Bash($PY scripts/directive.py:*)" \
    "mcp__plugin_telegram_telegram__reply" "mcp__plugin_telegram_telegram__react" \
    "mcp__plugin_telegram_telegram__edit_message" "mcp__plugin_telegram_telegram__download_attachment" \
    "Agent" "Skill"
}
EOF
source ~/.zshrc
```

> 아침 브리핑과 자동 수집은 이 실행 파일들과 상관없이 동작해요 (파이썬 프로그램을 직접 예약 실행).

---

## 7. 부록 — 처음 설정에 필요한 것 미리 받아 두기

'처음 시작하기' 중에 비서가 같은 내용을 안내하지만, 미리 해 두면 설정이 훨씬 빨라요.
받은 값(토큰·키)은 **어디에도 붙여넣지 말고** 그대로 두세요. 설정할 때 비서가 여는 **설정 창**에만 넣어요.

### A. 휴대폰 질문용 봇 만들기 (3분, 휴대폰만 있으면 돼요)
봇은 휴대폰에서 비서에게 질문하는 **나만의 대화 상대**예요. 텔레그램 공식 봇 'BotFather' 에게 말을 걸어 만들어요.

1. 텔레그램 앱 위쪽 **검색**에 `BotFather` 를 입력해요.
   - 이름 옆에 **파란 체크(✔)** 가 있는 계정을 고르세요. 비슷한 이름의 가짜 계정이 있어요.
2. 대화방 아래 **시작(START)** 을 눌러요.
3. 입력창에 `/newbot` 을 입력하고 보내요.
4. **봇 이름**을 물어보면 아무 이름이나 보내요. 대화방 제목으로 보이는 이름이에요.
   - 예: `김상무 비서`
5. **봇 아이디**를 물어보면 **영문으로, 끝이 `bot` 으로 끝나게** 보내요.
   - 예: `kim_assistant_bot`
   - `Sorry, this username is already taken` 이 나오면 남이 이미 쓰는 아이디예요. 숫자를 붙여 다시 보내요 (예: `kim_assistant_2026_bot`).
6. `Done! Congratulations…` 메시지가 오면 성공이에요. 메시지 중간의 **`Use this token to access the HTTP API:`** 아래 긴 줄(숫자:영문, 예 `1234567890:AAH…`)이 **토큰**이에요.
   - 이 메시지는 지우지 말고 두세요. 설정할 때 이 토큰을 복사해서 설정 창에 넣어요.
   - 컴퓨터로 옮기기 쉬운 방법: 컴퓨터 브라우저에서 **https://web.telegram.org** 로 로그인 → BotFather 대화방에서 토큰 복사

⚠ 토큰은 봇의 열쇠예요. 다른 사람에게 보내거나 채팅창(비서 창 포함)에 붙여넣지 마세요.
유출된 것 같으면 BotFather 에게 `/revoke` 를 보내 새 토큰을 받으면 예전 토큰은 못 쓰게 돼요.
봇은 **사람마다 따로** 만들어요. 다른 사람이 만든 봇을 같이 쓰면 한쪽에서만 동작해요.

### B. 텔레그램 '앱 정보' 받기 (5분, 컴퓨터 브라우저)
비서가 **내 계정으로 대화방 메시지를 읽기** 위해 필요한 두 값(api_id, api_hash)이에요.

1. 컴퓨터 브라우저로 **https://my.telegram.org** 에 들어가요.
2. 휴대폰 번호를 `+82` 로 시작하게 입력해요 (010-1234-5678 → `+821012345678`) → **Next**
3. 휴대폰 **텔레그램 앱**의 'Telegram'(파란 체크) 대화방으로 확인 코드가 와요 (문자 아님). 그대로 입력 → **Sign In**
4. **API development tools** 를 눌러요.
5. 처음이면 양식이 나와요:
   - App title: `AIBiz Reader` · Short name: `aibizreader` (영문 소문자+숫자, 띄어쓰기 없이)
   - URL: 비워 둠 · Platform: **Desktop** · Description: `personal message reader`
   - **Create application**
6. **App api_id**(숫자)와 **App api_hash**(32글자)가 보이면 성공이에요. 이 화면을 열어 둔 채로 설정을 시작하세요.

막히면: "ERROR" 창이 뜨면 VPN·광고 차단을 끄고 다른 브라우저(크롬 시크릿 창)로 다시 해 보세요. Short name 을 더 독특하게 바꾸면 되는 경우도 많아요.

### C. 회의록용 Google AI 키 받기 (3분, 컴퓨터 브라우저)
회의 녹음을 글로 바꾸는 데 써요.

1. **https://aistudio.google.com/apikey** 에 Google 계정으로 로그인해요.
2. **Create API key** → `AIza…` 로 시작하는 키를 복사해요.
3. **꼭 해 주세요 — 결제 설정**: 같은 화면의 **Set up billing** 에서 카드를 등록해요. 무료로 쓰면 녹음이 Google AI 개선에 쓰일 수 있어요. 결제를 설정하면 쓰이지 않고, 비용은 1시간 회의에 몇백 원 수준이에요.

---

### 관리자 메모 (배포하는 사람용)
- 셋업 당일 순서·준비물: [SETUP_CHECKLIST.md](SETUP_CHECKLIST.md)
- 개인 정보(`secrets/`, `data/`, `wiki/`, `minutes/`, `briefings/`, `logs/`, `config/`)는 `.gitignore` 로 제외. 받는 사람은 자기 계정으로 새로 설정해요.
- `.claude/settings.json` 의 `enabledPlugins` 로 폴더를 열면 텔레그램 플러그인 설치를 권해요.
- 봇은 사람마다 따로 만들어야 해요 (같은 봇을 두 컴퓨터에서 동시에 못 씀).
- Mac 실행 권한은 git 에 기록되어 있어요. 새 `.command` 파일을 추가하면 `git update-index --chmod=+x <파일>`.
- 구성: 스킬 `.claude/skills/` (getting-started, tg-sync, tg-bot, kb-build, kb-ask, meeting-minutes, morning-briefing), 에이전트 `.claude/agents/` (kb-builder, minutes-writer, briefing-writer), 프로그램 `scripts/`. 개발 원칙은 [CLAUDE.md](CLAUDE.md).
