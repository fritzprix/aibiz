#!/bin/bash
# Mac 용 설정 창 (Finder 에서 더블클릭 = 텔레그램 연결)
# 사용: ./setup.command [telegram|bot|gemini]
cd "$(dirname "$0")" || exit 1
case "${1:-telegram}" in
  bot)    CMD=(scripts/tg_sync.py bot-setup);  TITLE="휴대폰 질문용 봇 연결" ;;
  gemini) CMD=(scripts/transcribe.py setup);   TITLE="회의록 전사(Gemini) 설정" ;;
  *)      CMD=(scripts/tg_sync.py setup);      TITLE="텔레그램 연결 설정" ;;
esac
printf '\033]0;%s\007' "$TITLE"

finish() { echo; read -r -p "Enter 를 누르면 창이 닫혀요..." _; exit "${1:-0}"; }

find_py() {
  for c in python3.13 python3.12 python3.11 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$c" >/dev/null 2>&1 &&
       "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      PY="$c"; return 0
    fi
  done
  return 1
}

if [ ! -x .venv/bin/python ]; then
  if ! find_py; then
    echo "파이썬이 없어서 설치할게요..."
    if command -v brew >/dev/null 2>&1; then
      brew install python@3.12
    else
      xcode-select --install >/dev/null 2>&1
      echo "[안내] 화면에 '개발자 도구 설치' 창이 뜨면 '설치'를 누르세요."
      echo "       설치가 끝나면 이 파일을 다시 더블클릭해 주세요."
      finish 1
    fi
    find_py || { echo "[문제] 파이썬을 설치하지 못했어요. Claude 에게 \"파이썬을 못 찾는대\" 라고 알려 주세요."; finish 1; }
  fi
  echo "처음 한 번만 필요한 준비를 하고 있어요. 1~2분 걸려요..."
  "$PY" -m venv .venv || { echo "[문제] 준비에 실패했어요. Claude 에게 이 창의 문구를 알려 주세요."; finish 1; }
fi

if ! .venv/bin/python -c 'import telethon, google.genai, docx, imageio_ffmpeg' 2>/dev/null; then
  echo "필요한 프로그램을 설치하고 있어요. 처음엔 몇 분 걸릴 수 있어요..."
  .venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt ||
    { echo "[문제] 프로그램 설치에 실패했어요. 인터넷 연결을 확인한 뒤 Claude 에게 \"설치에 실패했대\" 라고 알려 주세요."; finish 1; }
fi

.venv/bin/python "${CMD[@]}"
finish $?
