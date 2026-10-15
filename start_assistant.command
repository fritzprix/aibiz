#!/bin/bash
# Mac 용 업무 비서 시작 (Finder 에서 더블클릭)
# --channels : 휴대폰(텔레그램 봇) 메시지를 이 창으로 받음
# --permission-mode acceptEdits / --allowedTools : 휴대폰 질문에 답할 때 승인 창 때문에 멈추지 않도록
#   비서 전용 프로그램(scripts/)과 텔레그램 답장 기능만 미리 허용. 그 밖의 명령은 여전히 승인을 물음.
cd "$(dirname "$0")" || exit 1
printf '\033]0;업무 비서\007'
export PATH="$HOME/.local/bin:$PATH"
if ! command -v claude >/dev/null 2>&1; then
  echo "[문제] Claude Code 가 설치되어 있지 않아요. README.md 의 '1. 설치' 를 먼저 해 주세요."
  read -r -p "Enter 를 누르면 창이 닫혀요..." _
  exit 1
fi
PY=.venv/bin/python
exec claude --channels plugin:telegram@claude-plugins-official --permission-mode acceptEdits --allowedTools \
  "Bash($PY scripts/tg_sync.py:*)" "Bash($PY scripts/transcribe.py:*)" "Bash($PY scripts/digest.py:*)" \
  "Bash($PY scripts/briefing.py:*)" "Bash($PY scripts/md2docx.py:*)" "Bash($PY scripts/directive.py:*)" \
  "mcp__plugin_telegram_telegram__reply" "mcp__plugin_telegram_telegram__react" \
  "mcp__plugin_telegram_telegram__edit_message" "mcp__plugin_telegram_telegram__download_attachment" \
  "Agent" "Skill"
