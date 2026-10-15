"""텔레그램 메시지 수집기.

내 텔레그램 계정으로 로그인해서, 내가 참여한 채팅방의 메시지를 '읽기만' 해서
data/raw/ 에 저장합니다. 메시지를 보내거나 지우는 기능은 없습니다.

명령:
  setup                 처음 연결 (대화형 창에서 실행)
  doctor                연결 상태 점검 + 문제 해결 안내
  sync                  새 메시지 가져오기
  chats                 채팅방 목록과 수집 여부 보기
  exclude add|remove    수집 제외 목록 관리
  schedule / unschedule 자동 수집 켜기/끄기
"""
import argparse
import asyncio
import getpass
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tg_render  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / "secrets"
CRED_FILE = SECRETS / "telegram.json"
SESSION = SECRETS / "telegram"  # Telethon이 .session 을 붙임
SESSION_FILE = SECRETS / "telegram.session"
CONFIG_FILE = ROOT / "config" / "telegram.json"
RAW = ROOT / "data" / "raw"
STATE_DIR = ROOT / "data" / "state"
STATE_FILE = STATE_DIR / "tg_sync_state.json"
STATUS_FILE = STATE_DIR / "tg_sync_status.json"
LOCK_FILE = STATE_DIR / "tg_sync.lock"
LOG_FILE = ROOT / "logs" / "tg_sync.log"
IS_WIN = sys.platform == "win32"
VENV_BG_PY = ROOT / ".venv" / ("Scripts/pythonw.exe" if IS_WIN else "bin/python")  # 창 없이 실행되는 파이썬
TASK_NAME = "AIDev-TelegramSync"  # Windows 작업 스케줄러 이름
MAC_LABEL = "com.aidev.telegramsync"
MAC_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"
LOCK_STALE_SEC = 2 * 3600
TELEGRAM_SERVICE_ID = 777000  # 로그인 코드가 오는 공식 'Telegram' 대화방 — 절대 수집하지 않음

DEFAULT_CONFIG = {
    "backfill_days": 30,
    "backfill_days_per_chat": {},
    "exclude": [],
    "skip_bots": True,
    "skip_saved_messages": True,
    "max_messages_per_chat_per_run": 3000,
}

log = logging.getLogger("tg_sync")


# ---------- 공통 ----------

def setup_logging():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    h = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_config():
    cfg = load_json(CONFIG_FILE, None)
    if cfg is None:
        cfg = dict(DEFAULT_CONFIG)
        save_json(CONFIG_FILE, cfg)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def now_local():
    return datetime.now().astimezone()


class Busy(Exception):
    pass


def pid_alive(pid):
    """그 프로그램이 아직 실행 중인지 (창을 X 로 닫으면 잠금이 남으므로 확인 필요)."""
    if not pid:
        return False
    if IS_WIN:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class Lock:
    """동시에 두 번 실행되지 않게 막는 잠금 (로그인 정보 파일이 한 번에 하나만 열릴 수 있음)."""

    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"owner": self.owner, "pid": os.getpid(), "at": time.time()}, f)
                return self
            except FileExistsError:
                info = load_json(LOCK_FILE, {})
                if time.time() - info.get("at", 0) > LOCK_STALE_SEC or not pid_alive(info.get("pid")):
                    LOCK_FILE.unlink(missing_ok=True)
                    continue
                raise Busy(info.get("owner", "?"))
        raise Busy("?")

    def __exit__(self, *a):
        LOCK_FILE.unlink(missing_ok=True)


BUSY_TEXT = {
    "sync": "지금 메시지를 가져오는 중",
    "setup": "설정 창이 열려 있는 중",
    "doctor": "점검 중",
    "chats": "채팅방 목록을 읽는 중",
    "fetch": "녹음 파일을 내려받는 중",
}


def check_creds(c):
    """저장된 인증 정보가 올바른 모양인지 확인. 문제 목록(쉬운 말)을 돌려줌."""
    problems = []
    api_id = str(c.get("api_id", "")).strip()
    api_hash = str(c.get("api_hash", "")).strip()
    if not api_id:
        problems.append("api_id 가 비어 있어요.")
    elif not api_id.isdigit():
        problems.append("api_id 는 숫자로만 되어 있어야 해요.")
    if not api_hash:
        problems.append("api_hash 가 비어 있어요.")
    elif not re.fullmatch(r"[0-9a-f]{32}", api_hash):
        problems.append("api_hash 는 영문 소문자(a~f)와 숫자로 된 32글자여야 해요.")
    return problems


def make_client(creds):
    from telethon import TelegramClient

    SECRETS.mkdir(parents=True, exist_ok=True)
    return TelegramClient(
        str(SESSION),
        int(creds["api_id"]),
        creds["api_hash"],
        device_model="AIDev 메시지 수집기",
        system_version="Windows",
        app_version="1.0",
        flood_sleep_threshold=120,
    )


# ---------- setup (대화형) ----------

def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        raise KeyboardInterrupt


def ask_yes(prompt, default=True):
    v = ask(prompt + (" (Y/n): " if default else " (y/N): ")).lower()
    if not v:
        return default
    return v in ("y", "yes", "ㅛ", "예", "네", "응")


def prompt_api_id():
    print("\n[1/2] api_id 입력")
    print("  my.telegram.org 화면의 'App api_id' 옆에 있는 숫자예요. (예: 1234567)")
    while True:
        v = re.sub(r"\s", "", ask("  api_id 를 붙여넣고 Enter ▶ "))
        if v.isdigit() and 3 <= len(v) <= 12:
            return v
        if not v:
            print("  ⚠ 아무것도 입력되지 않았어요. 붙여넣기는 마우스 오른쪽 클릭 또는 Ctrl+V 입니다.")
        elif re.fullmatch(r"[0-9a-fA-F]{32}", v):
            print("  ⚠ 이건 api_hash 같아요. api_id 는 숫자로만 된 짧은 값이에요. 'App api_id' 쪽 값을 넣어 주세요.")
        else:
            print("  ⚠ api_id 는 숫자로만 되어 있어요. 앞뒤에 다른 글자가 같이 복사되지 않았는지 확인해 주세요.")


def prompt_api_hash():
    print("\n[2/2] api_hash 입력")
    print("  'App api_hash' 옆에 있는 32글자 값이에요. (영문+숫자 섞임)")
    while True:
        v = re.sub(r"\s", "", ask("  api_hash 를 붙여넣고 Enter ▶ ")).lower()
        if re.fullmatch(r"[0-9a-f]{32}", v):
            return v
        if not v:
            print("  ⚠ 아무것도 입력되지 않았어요.")
        elif v.isdigit():
            print("  ⚠ 숫자만 있네요. 이건 api_id 같아요. 'App api_hash' 쪽 값을 넣어 주세요.")
        else:
            print(f"  ⚠ 글자 수가 {len(v)}개예요. 32글자여야 해요. 일부만 복사됐거나 다른 값이 섞인 것 같아요.")


def normalize_phone(v):
    d = re.sub(r"[\s\-\(\)\.]", "", v)
    if d.startswith("00"):
        d = "+" + d[2:]
    if d.startswith("+"):
        rest = d[1:]
    elif d.startswith("0"):  # 010-... 같은 한국 번호로 간주
        rest = "82" + d[1:]
    else:
        rest = d
    if not rest.isdigit() or not 8 <= len(rest) <= 15:
        return None
    return "+" + rest


def prompt_phone():
    print("\n휴대폰 번호 입력")
    print("  텔레그램에 가입한 번호예요. 010-1234-5678 처럼 그냥 입력해도 돼요.")
    while True:
        p = normalize_phone(ask("  휴대폰 번호 ▶ "))
        if not p:
            print("  ⚠ 번호 모양이 이상해요. 숫자만 다시 입력해 주세요. (해외 번호는 +국가번호 로 시작)")
            continue
        if ask_yes(f"  {p} 이 번호가 맞나요?"):
            return p


async def password_step(client):
    from telethon import errors, functions

    hint = ""
    try:
        pw = await client(functions.account.GetPasswordRequest())
        hint = pw.hint or ""
    except Exception:
        pass
    print("\n이 계정은 '2단계 인증 비밀번호'가 걸려 있어요.")
    print("  텔레그램 설정 > 개인정보 및 보안 > 2단계 인증 에서 직접 정한 비밀번호예요.")
    if hint:
        print(f"  (설정해 둔 힌트: {hint})")
    print("  ※ 입력해도 화면에 글자가 안 보이는 게 정상이에요. 다 치고 Enter 를 누르세요.")
    for _ in range(5):
        try:
            p = getpass.getpass("  2단계 비밀번호 ▶ ")
        except EOFError:
            raise KeyboardInterrupt
        if not p:
            continue
        try:
            await client.sign_in(password=p)
            return True
        except errors.PasswordHashInvalidError:
            print("  ⚠ 비밀번호가 틀렸어요. 대소문자/한영 전환 상태를 확인하고 다시 입력해 주세요.")
        except errors.FloodWaitError as e:
            print(f"  ⚠ 너무 여러 번 시도해서 텔레그램이 잠시 막았어요. {wait_text(e.seconds)} 뒤에 다시 해 주세요.")
            return False
    print("  ⚠ 5번 틀렸어요. 비밀번호가 기억나지 않으면 텔레그램 앱에서 재설정할 수 있어요.")
    return False


def wait_text(sec):
    if sec >= 3600:
        return f"약 {sec // 3600}시간 {sec % 3600 // 60}분"
    if sec >= 60:
        return f"약 {sec // 60}분"
    return f"{sec}초"


async def interactive_login(creds):
    """결과: 'ok' / 'bad_api' / 'abort'"""
    from telethon import errors

    client = make_client(creds)
    try:
        await client.connect()
    except (OSError, ConnectionError):
        print("\n⚠ 텔레그램 서버에 연결하지 못했어요. 인터넷 연결(또는 회사 방화벽/VPN)을 확인해 주세요.")
        return "abort"
    try:
        try:
            if await client.is_user_authorized():
                me = await client.get_me()
                print(f"\n✅ 이미 연결되어 있어요: {display_name(me)}")
                return "ok"
        except errors.ApiIdInvalidError:
            return "bad_api"

        while True:
            phone = prompt_phone()
            try:
                await client.send_code_request(phone)
                break
            except errors.ApiIdInvalidError:
                return "bad_api"
            except errors.PhoneNumberInvalidError:
                print("  ⚠ 텔레그램이 이 번호를 인식하지 못했어요. 번호를 다시 확인해 주세요.")
            except errors.PhoneNumberBannedError:
                print("  ⚠ 이 번호는 텔레그램에서 이용이 제한된 상태예요. 텔레그램 앱에서 먼저 확인이 필요해요.")
                return "abort"
            except (errors.FloodWaitError, errors.PhoneNumberFloodError) as e:
                sec = getattr(e, "seconds", 0)
                print(f"  ⚠ 짧은 시간에 너무 많이 시도해서 텔레그램이 잠시 막았어요. {wait_text(sec) if sec else '한참'} 뒤에 다시 해 주세요.")
                return "abort"

        print("\n인증 코드 입력")
        print("  방금 휴대폰 텔레그램 앱의 'Telegram' 공식 대화방(파란 체크)으로 숫자 코드가 왔어요.")
        print("  (앱이 없으면 문자로 올 수도 있어요.) 그 숫자를 입력하세요.")
        print("  ※ 이 코드는 절대 다른 사람이나 채팅창에 알려주지 마세요. 여기 창에만 입력하세요.")
        logged_in = False
        for _ in range(5):
            code = re.sub(r"\D", "", ask("  인증 코드 ▶ "))
            if not code:
                continue
            try:
                await client.sign_in(phone=phone, code=code)
                logged_in = True
                break
            except errors.PhoneCodeInvalidError:
                print("  ⚠ 코드가 틀렸어요. 가장 최근에 온 코드인지 확인하고 다시 입력해 주세요.")
            except errors.PhoneCodeExpiredError:
                print("  ⚠ 코드 유효시간이 지났어요. 새 코드를 보낼게요.")
                await client.send_code_request(phone)
            except errors.SessionPasswordNeededError:
                logged_in = await password_step(client)
                break
            except errors.PhoneNumberUnoccupiedError:
                print("  ⚠ 이 번호로 가입된 텔레그램 계정이 없어요. 번호를 확인해 주세요.")
                return "abort"
            except errors.FloodWaitError as e:
                print(f"  ⚠ 너무 여러 번 시도해서 잠시 막혔어요. {wait_text(e.seconds)} 뒤에 다시 해 주세요.")
                return "abort"
        if not logged_in:
            return "abort"
        me = await client.get_me()
        print(f"\n✅ 연결 성공! {display_name(me)} 계정으로 로그인했어요.")
        print("  텔레그램 앱에 '새 기기 로그인' 알림이 올 수 있어요. 기기 이름이 'AIDev 메시지 수집기'면 이 프로그램이에요.")
        return "ok"
    finally:
        await client.disconnect()


def cmd_setup(args):
    print("=" * 60)
    print(" 텔레그램 연결 설정")
    print(" 여기 입력하는 정보는 이 컴퓨터에만 저장되고, 채팅창이나 외부로 보내지지 않아요.")
    print(" 언제든 창을 닫으면 중단돼요. 중간에 멈춰도 처음부터 다시 하면 됩니다.")
    print("=" * 60)
    try:
        with Lock("setup"):
            while True:
                creds = load_json(CRED_FILE, {})
                if creds and not check_creds(creds) and ask_yes("\n이전에 입력한 api_id/api_hash 를 그대로 쓸까요?"):
                    pass
                else:
                    if creds and check_creds(creds):
                        print("\n저장된 정보에 문제가 있어서 다시 입력받을게요: " + " ".join(check_creds(creds)))
                    creds = {"api_id": prompt_api_id(), "api_hash": prompt_api_hash()}
                    save_json(CRED_FILE, creds)
                    print("  저장했어요.")
                result = asyncio.run(interactive_login(creds))
                if result == "bad_api":
                    print("\n⚠ 텔레그램이 api_id/api_hash 를 거절했어요.")
                    print("  두 값이 서로 짝이 맞지 않거나 잘못 복사된 경우예요.")
                    print("  my.telegram.org 화면에서 두 값을 다시 복사해서 입력해 주세요.")
                    CRED_FILE.unlink(missing_ok=True)
                    SESSION_FILE.unlink(missing_ok=True)
                    continue
                break
    except Busy as b:
        print(f"\n⚠ 지금 {BUSY_TEXT.get(str(b), '다른 작업이 실행 중')}이에요. 1~2분 뒤에 다시 열어 주세요.")
        return 1
    except KeyboardInterrupt:
        print("\n\n중단했어요. 다시 하려면 설정 창을 다시 열면 됩니다.")
        return 1
    except sqlite3.OperationalError:
        print("\n⚠ 로그인 정보 파일을 다른 프로그램이 쓰고 있어요. 잠시 뒤 다시 열어 주세요.")
        return 1
    if result == "ok":
        print("\n🎉 설정이 끝났어요. 이 창을 닫고 Claude 에게 '다 했어' 라고 말해 주세요.")
        return 0
    print("\n설정을 끝내지 못했어요. 이 창의 안내 문구를 Claude 에게 알려 주시면 도와드릴게요.")
    print("(인증 코드나 비밀번호는 알려주지 마세요.)")
    return 1


# ---------- bot-setup (휴대폰으로 질문하는 봇 연결, 대화형) ----------

def bot_state_dir():
    d = os.environ.get("TELEGRAM_STATE_DIR")
    if d:
        return Path(d)
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "channels" / "telegram"


def check_bot_token(token):
    """텔레그램에 토큰을 확인. (ok, 봇 아이디 또는 쉬운 말 오류)"""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("ok"):
            return True, "@" + data["result"]["username"]
        return False, "텔레그램이 이 토큰을 인정하지 않았어요."
    except urllib.error.HTTPError as e:
        if e.code in (401, 404):
            return False, "토큰이 틀렸거나 폐기된 토큰이에요. BotFather 에서 다시 복사해 주세요."
        return False, f"텔레그램 응답 오류({e.code})예요. 잠시 뒤 다시 해 주세요."
    except (urllib.error.URLError, OSError):
        return False, "텔레그램 서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요."


def cmd_bot_setup(args):
    print("=" * 60)
    print(" 텔레그램 봇 연결 (휴대폰으로 비서에게 질문하기)")
    print(" 봇 토큰은 이 컴퓨터에만 저장되고, 채팅창이나 외부로 보내지지 않아요.")
    print("=" * 60)
    print("\nBotFather 가 준 '토큰'을 붙여넣어 주세요.")
    print("  모양: 숫자:영문숫자 (예: 1234567890:AAH...)  — 붙여넣기는 마우스 오른쪽 클릭 또는 Ctrl+V")
    try:
        while True:
            t = re.sub(r"\s", "", ask("  봇 토큰 ▶ "))
            if not t:
                continue
            t = t.removeprefix("bot")  # 'bot123:...' 처럼 앞에 붙여 복사한 경우
            if not re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{30,}", t):
                if ":" not in t:
                    print("  ⚠ 가운데 ':' 이 없어요. BotFather 메시지의 'Use this token' 아래 한 줄 전체를 복사해 주세요.")
                else:
                    print("  ⚠ 토큰 모양이 이상해요. 일부만 복사됐거나 다른 글자가 섞인 것 같아요.")
                continue
            print("  확인 중...")
            ok, info = check_bot_token(t)
            if ok:
                break
            print("  ⚠ " + info)
    except KeyboardInterrupt:
        print("\n\n중단했어요.")
        return 1
    d = bot_state_dir()
    d.mkdir(parents=True, exist_ok=True)
    env = d / ".env"
    lines = []
    if env.exists():
        lines = [x for x in env.read_text(encoding="utf-8").splitlines() if not x.startswith("TELEGRAM_BOT_TOKEN=")]
    lines.append(f"TELEGRAM_BOT_TOKEN={t}")
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(env, 0o600)
    except OSError:
        pass
    print(f"\n✅ 봇 {info} 연결 정보를 저장했어요.")
    print("\n다음 할 일:")
    print("  1. 이 창을 닫고, 업무 비서(Claude) 창도 닫았다가 'start_assistant' 로 다시 여세요.")
    print(f"  2. 휴대폰 텔레그램에서 {info} 를 검색해 아무 메시지나 보내세요.")
    print("  3. 봇이 6글자 코드를 답장하면, 그 코드를 Claude 에게 알려 주세요. (이 코드는 알려줘도 괜찮아요)")
    return 0


def bot_status():
    """(토큰 있음?, 봇 아이디 또는 None, 허용된 사람 수, 정책)"""
    d = bot_state_dir()
    token = None
    env = d / ".env"
    if env.exists():
        for x in env.read_text(encoding="utf-8").splitlines():
            if x.startswith("TELEGRAM_BOT_TOKEN="):
                token = x.split("=", 1)[1].strip()
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or token
    access = load_json(d / "access.json", {})
    return token, access


# ---------- sync ----------

def display_name(e):
    from telethon.tl.types import User

    if e is None:
        return None
    if isinstance(e, User):
        n = " ".join(x for x in (e.first_name, e.last_name) if x)
        return n or (e.username and "@" + e.username) or str(e.id)
    return getattr(e, "title", None) or str(getattr(e, "id", ""))


def chat_kind(d):
    from telethon.tl.types import Channel, User

    e = d.entity
    if isinstance(e, User):
        if e.is_self:
            return "saved"
        if e.bot:
            return "bot"
        return "private"
    if isinstance(e, Channel) and e.broadcast:
        return "channel"
    return "group"


KIND_KO = {"private": "1:1 대화", "group": "그룹", "channel": "채널", "bot": "봇", "saved": "저장한 메시지",
           "assistant": "비서 대화방"}


def skip_reason(d, kind, cfg):
    cid = str(d.id)
    if d.id == TELEGRAM_SERVICE_ID or getattr(d.entity, "id", None) == TELEGRAM_SERVICE_ID:
        return "텔레그램 공식 알림방(로그인 코드 보호)"
    if any(str(x.get("id")) == cid for x in cfg["exclude"]):
        return "제외 목록"
    if kind == "bot" and cfg["skip_bots"]:
        return "봇 대화"
    if kind == "saved" and cfg["skip_saved_messages"]:
        return "저장한 메시지"
    return None


def media_kind(m):
    if m.voice:
        return "voice"
    if m.audio:
        return "audio"
    if m.video:
        return "video"
    if m.photo:
        return "photo"
    if m.document:
        name = m.file.name if m.file else None
        return f"file:{name}" if name else "file"
    if m.web_preview:
        return "link"
    return None


def forward_origin(m):
    """전달된 메시지의 원래 보낸 사람·시각 (상위 임원 지시 파악용)."""
    f = m.fwd_from
    if not f:
        return None, None
    name = getattr(f, "from_name", None) or getattr(f, "post_author", None)
    if not name:
        try:
            ent = m.forward.sender or m.forward.chat if m.forward else None
            name = display_name(ent) if ent else None
        except Exception:
            name = None
    if not name and getattr(f, "from_id", None) is not None:
        pid = f.from_id
        name = str(getattr(pid, "user_id", None) or getattr(pid, "channel_id", None) or getattr(pid, "chat_id", ""))
    when = f.date.astimezone().isoformat(timespec="seconds") if getattr(f, "date", None) else None
    return name, when


def to_row(m, cid, title, kind):
    sender = display_name(m.sender) if m.sender else (m.post_author or title)
    top = getattr(m.reply_to, "reply_to_top_id", None) if m.reply_to else None
    fwd_name, fwd_date = forward_origin(m)
    return {
        "id": m.id,
        "date": m.date.astimezone().isoformat(timespec="seconds"),
        "chat_id": cid,
        "chat": title,
        "chat_type": kind,
        "sender_id": m.sender_id,
        "sender": sender,
        "out": bool(m.out),
        "text": m.message or "",
        "reply_to": m.reply_to_msg_id,
        "thread_top": top,
        "forwarded": bool(m.fwd_from),
        "fwd_from": fwd_name,
        "fwd_date": fwd_date,
        "media": media_kind(m),
    }


ASSISTANT_CACHE = STATE_DIR / "assistant_bot.json"


def assistant_bot_username():
    """내 비서 봇의 아이디 (봇 대화방은 '비서 대화방'으로 따로 수집 — 상위 지시·답장 감지용)."""
    token, _ = bot_status()
    if not token:
        return None
    cache = load_json(ASSISTANT_CACHE, {})
    key = token.split(":")[0]
    if cache.get("key") == key and cache.get("username"):
        return cache["username"]
    ok, info = check_bot_token(token)
    if not ok:
        return cache.get("username")
    save_json(ASSISTANT_CACHE, {"key": key, "username": info.lstrip("@")})
    return info.lstrip("@")


class NeedLogin(Exception):
    pass


async def do_sync(cfg, creds, only_bot=False, bot_username=None):
    from telethon import errors

    client = make_client(creds)
    await client.connect()
    summary = {"chats_checked": 0, "chats_with_new": 0, "new_messages": 0, "skipped": 0, "problems": [],
               "assistant_new": 0}
    touched = set()
    bot_un = (bot_username or "").lower()
    try:
        if not await client.is_user_authorized():
            raise NeedLogin()
        state = load_json(STATE_FILE, {"chats": {}})
        chats = state.setdefault("chats", {})
        me = await client.get_me()
        state["me"] = {"id": me.id, "name": display_name(me), "username": me.username,
                       "first_name": me.first_name, "last_name": me.last_name}
        cap = int(cfg["max_messages_per_chat_per_run"])
        async for d in client.iter_dialogs():
            kind = chat_kind(d)
            if kind == "bot" and bot_un and (getattr(d.entity, "username", "") or "").lower() == bot_un:
                kind = "assistant"  # 내 비서 봇과의 대화방
            if only_bot and kind != "assistant":
                continue
            cid = str(d.id)
            if skip_reason(d, kind, cfg):
                summary["skipped"] += 1
                continue
            summary["chats_checked"] += 1
            st = chats.get(cid, {})
            last = st.get("last_id")
            top = d.message.id if d.message else 0  # 채팅방 목록에 이미 들어 있는 '마지막 메시지 번호'
            if kind == "assistant" and not last:
                last = top  # 비서 대화방은 지난 대화를 가져오지 않음 — 지금부터 새로 오는 것만
                chats[cid] = {"title": d.name, "type": kind, "username": getattr(d.entity, "username", None),
                              "last_id": last, "last_checked": now_local().isoformat(timespec="seconds"),
                              "raw": f"data/raw/{cid}/"}
                save_json(STATE_FILE, state)
                continue
            if last and top <= last:
                continue  # 새 메시지 없음 → 텔레그램에 따로 묻지 않음
            try:
                if last:
                    it = client.iter_messages(d.entity, min_id=last, reverse=True, limit=cap)
                else:
                    days = int(cfg["backfill_days_per_chat"].get(cid, cfg["backfill_days"]))
                    since = datetime.now(timezone.utc) - timedelta(days=days)
                    it = client.iter_messages(d.entity, offset_date=since, reverse=True, limit=cap)
                rows, max_id = [], last or 0
                async for m in it:
                    max_id = max(max_id, m.id)
                    if m.action:  # 입장/퇴장 같은 시스템 알림
                        continue
                    if not m.message and not m.media:
                        continue
                    rows.append(to_row(m, cid, d.name, kind))
            except errors.FloodWaitError as e:
                summary["problems"].append(f"텔레그램이 속도 제한을 걸어서 이번엔 여기까지만 가져왔어요 ({wait_text(e.seconds)} 대기 필요). 다음 실행 때 이어서 가져와요.")
                break
            except (errors.ChannelPrivateError, errors.ChatAdminRequiredError, errors.ChannelInvalidError):
                summary["problems"].append(f"'{d.name}' 방은 더 이상 읽을 수 없어서 건너뛰었어요 (나갔거나 강퇴됨).")
                continue
            if not last and not max_id:
                max_id = top  # 처음인데 기간 안에 메시지가 없던 방 → 다음부터는 새 메시지만
            if rows:
                touched |= tg_render.append_rows(cid, rows)
                summary["chats_with_new"] += 1
                summary["new_messages"] += len(rows)
                if kind == "assistant":
                    summary["assistant_new"] += sum(1 for r in rows if r["out"])
            chats[cid] = {
                "title": d.name,
                "type": kind,
                "username": getattr(d.entity, "username", None),
                "last_id": max_id or last,
                "last_checked": now_local().isoformat(timespec="seconds"),
                "raw": f"data/raw/{cid}/",
            }
            save_json(STATE_FILE, state)  # 방 하나 끝날 때마다 저장 → 중간에 끊겨도 이어서 진행
        return summary, touched, chats
    finally:
        await client.disconnect()


def write_status(ok, code=None, message=None, summary=None, started=None):
    save_json(STATUS_FILE, {
        "ok": ok,
        "error_code": code,
        "message": message,
        "started": started,
        "finished": now_local().isoformat(timespec="seconds"),
        **(summary or {}),
    })


def cmd_sync(args):
    from telethon import errors

    started = now_local().isoformat(timespec="seconds")
    cfg = load_config()
    creds = load_json(CRED_FILE, {})
    if not creds or check_creds(creds):
        msg = "아직 텔레그램 연결 설정이 안 되어 있어요."
        write_status(False, "E-NO-CREDS", msg, started=started)
        print(msg)
        return 2
    try:
        with Lock("sync"):
            if tg_render.migrate_flat():
                log.info("migrated flat raw files to monthly folders")
            summary, touched, chats = asyncio.run(do_sync(cfg, creds, only_bot=args.only_bot,
                                                          bot_username=assistant_bot_username()))
            if touched:
                try:
                    tg_render.render(touched, chats)
                except Exception as e:  # 문서 정리가 실패해도 수집 결과는 보존
                    log.exception("render failed")
                    summary["problems"].append(f"읽기용 문서 정리 중 문제가 생겼어요 ({type(e).__name__}). 원본은 안전하게 저장됐어요.")
    except Busy as b:
        print(f"{BUSY_TEXT.get(str(b), '다른 작업이 실행 중')}이라 이번 수집은 건너뛰어요.")
        log.info("skip: busy (%s)", b)
        return 0
    except NeedLogin:
        msg = "텔레그램 로그인이 풀렸어요. 설정 창에서 다시 로그인해야 해요."
        write_status(False, "E-LOGGED-OUT", msg, started=started)
        log.error(msg)
        print(msg)
        return 3
    except errors.ApiIdInvalidError:
        msg = "api_id/api_hash 가 거절됐어요. 설정을 다시 해야 해요."
        write_status(False, "E-BAD-API", msg, started=started)
        log.error(msg)
        print(msg)
        return 3
    except (OSError, ConnectionError) as e:
        msg = "인터넷에 연결되지 않아 이번 수집을 못 했어요. 다음 실행 때 자동으로 다시 시도해요."
        write_status(False, "E-NETWORK", msg, started=started)
        log.error("%s (%s)", msg, e)
        print(msg)
        return 4
    except sqlite3.OperationalError as e:
        msg = "로그인 정보 파일이 다른 곳에서 열려 있어 이번 수집을 건너뛰었어요."
        write_status(False, "E-SESSION-LOCKED", msg, started=started)
        log.error("%s (%s)", msg, e)
        print(msg)
        return 4
    except Exception as e:
        log.exception("unexpected")
        write_status(False, "E-UNKNOWN", f"예상하지 못한 문제: {type(e).__name__}: {e}", started=started)
        print(f"예상하지 못한 문제가 생겼어요: {type(e).__name__}: {e}")
        return 5
    if not args.only_bot:
        write_status(True, summary=summary, started=started)
    log.info("sync ok: %s", summary)
    if summary.get("assistant_new") and not args.only_bot and not args.no_directive:
        try:  # 임원이 봇에게 새로 보낸 것(전달된 지시·답장·질문)이 있으면 처리 시작 (비서 창이 꺼져 있을 때만)
            import directive
            print("  " + directive.maybe_spawn())
        except Exception:
            log.exception("directive spawn failed")
    print(f"✅ 수집 완료: 채팅방 {summary['chats_checked']}개 확인, "
          f"{summary['chats_with_new']}개 방에서 새 메시지 {summary['new_messages']}건")
    for p in summary["problems"]:
        print("  ⚠ " + p)
    return 0


# ---------- chats / exclude ----------

async def list_dialogs(creds):
    client = make_client(creds)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise NeedLogin()
        out = []
        async for d in client.iter_dialogs():
            out.append({"id": str(d.id), "title": d.name, "kind": chat_kind(d), "_d": d})
        return out
    finally:
        await client.disconnect()


def cmd_chats(args):
    cfg = load_config()
    creds = load_json(CRED_FILE, {})
    state = load_json(STATE_FILE, {"chats": {}})["chats"]
    try:
        with Lock("chats"):
            ds = asyncio.run(list_dialogs(creds))
    except Busy as b:
        print(f"지금 {BUSY_TEXT.get(str(b), '다른 작업이 실행 중')}이에요. 잠시 뒤 다시 해 주세요.")
        return 1
    except NeedLogin:
        print("텔레그램 로그인이 필요해요. (doctor 로 점검해 보세요)")
        return 3
    counts = {}
    print(f"{'번호':>4}  {'수집':<4} {'종류':<8} 이름 (ID)")
    for i, x in enumerate(ds, 1):
        why = skip_reason(x["_d"], x["kind"], cfg)
        mark = "  ✗ " if why else "  ✓ "
        counts[x["kind"]] = counts.get(x["kind"], 0) + 1
        extra = f"  ← 제외: {why}" if why else ""
        got = " (수집됨)" if x["id"] in state else ""
        print(f"{i:>4}  {mark} {KIND_KO.get(x['kind'], x['kind']):<8} {x['title']} ({x['id']}){got}{extra}")
    print("\n합계: " + ", ".join(f"{KIND_KO.get(k, k)} {v}개" for k, v in counts.items()))
    return 0


def find_matches(query, candidates):
    q = query.strip()
    exact = [c for c in candidates if c["id"] == q]
    if exact:
        return exact
    same = [c for c in candidates if c["title"] == q]
    if same:
        return same
    return [c for c in candidates if q.lower() in (c["title"] or "").lower()]


def cmd_exclude(args):
    cfg = load_config()
    state = load_json(STATE_FILE, {"chats": {}})["chats"]
    if args.action == "list":
        if not cfg["exclude"]:
            print("제외 목록이 비어 있어요.")
        for x in cfg["exclude"]:
            print(f"- {x.get('title')} ({x.get('id')})")
        return 0
    if args.action == "remove":
        before = len(cfg["exclude"])
        hits = find_matches(args.query, [{"id": str(x["id"]), "title": x.get("title")} for x in cfg["exclude"]])
        if len(hits) != 1:
            print("제외 목록에서 딱 하나를 찾지 못했어요:" if hits else "제외 목록에 그런 방이 없어요.")
            for h in hits:
                print(f"- {h['title']} ({h['id']})")
            return 1
        cfg["exclude"] = [x for x in cfg["exclude"] if str(x["id"]) != hits[0]["id"]]
        save_json(CONFIG_FILE, cfg)
        print(f"'{hits[0]['title']}' 을(를) 다시 수집해요. (제외 {before}→{len(cfg['exclude'])}개)")
        return 0
    # add: 우선 수집 기록에서 찾고, 없으면 텔레그램에서 직접 목록을 읽음
    cands = [{"id": k, "title": v.get("title")} for k, v in state.items()]
    hits = find_matches(args.query, cands)
    if not hits:
        try:
            with Lock("chats"):
                ds = asyncio.run(list_dialogs(load_json(CRED_FILE, {})))
            hits = find_matches(args.query, [{"id": d["id"], "title": d["title"]} for d in ds])
        except (Busy, NeedLogin):
            pass
    if len(hits) != 1:
        print("어느 방인지 하나로 정해지지 않았어요:" if hits else f"'{args.query}' 에 해당하는 방을 찾지 못했어요.")
        for h in hits[:20]:
            print(f"- {h['title']} ({h['id']})")
        return 1
    h = hits[0]
    if not any(str(x["id"]) == h["id"] for x in cfg["exclude"]):
        cfg["exclude"].append({"id": h["id"], "title": h["title"]})
        save_json(CONFIG_FILE, cfg)
    print(f"'{h['title']}' 은(는) 이제 수집하지 않아요.")
    has_data = (RAW / h["id"]).exists()
    if args.purge and has_data:
        tg_render.remove_chat(h["id"])
        print("  이미 저장돼 있던 이 방의 메시지와 문서도 지웠어요.")
    elif has_data:
        print("  (이미 저장된 메시지는 남아 있어요. 지우려면 --purge 를 붙여 다시 실행)")
    return 0


AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma", ".amr", ".3gp",
             ".mp4", ".mov", ".webm", ".mkv", ".qta"}


def is_recording(m):
    if m.voice or m.audio or m.video or m.video_note:
        return True
    if m.document and m.file:
        mime = (m.file.mime_type or "").lower()
        ext = (m.file.ext or "").lower()
        return mime.startswith(("audio/", "video/")) or ext in AUDIO_EXT
    return False


async def do_fetch_media(creds, chat, hours, out_dir):
    client = make_client(creds)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise NeedLogin()
        entity = await client.get_entity(chat)
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        async for m in client.iter_messages(entity, limit=50):
            if m.date < since:
                break
            if m.out and is_recording(m):
                out_dir.mkdir(parents=True, exist_ok=True)
                name = (m.file.name if m.file and m.file.name else f"recording_{m.date.astimezone():%Y%m%d_%H%M}{m.file.ext or '.ogg'}")
                target = out_dir / name
                size_mb = (m.file.size or 0) / 1_048_576
                print(f"내려받는 중: {name} ({size_mb:.1f}MB)", flush=True)
                path = await m.download_media(file=str(target))
                return path
        return None
    finally:
        await client.disconnect()


def cmd_fetch_media(args):
    """봇이 받기엔 큰(20MB 초과) 녹음을 내 계정으로 직접 내려받음."""
    chat = args.chat
    if not chat:
        token, _ = bot_status()
        if not token:
            print("어느 대화방에서 가져올지 모르겠어요. (봇이 연결되어 있지 않음) --chat 으로 지정해 주세요.")
            return 1
        ok, info = check_bot_token(token)
        if not ok:
            print("봇 정보를 확인하지 못했어요: " + info)
            return 1
        chat = info  # @봇아이디
    try:
        with Lock("fetch"):
            path = asyncio.run(do_fetch_media(load_json(CRED_FILE, {}), chat, args.hours, ROOT / "data" / "audio"))
    except Busy as b:
        print(f"지금 {BUSY_TEXT.get(str(b), '다른 작업이 실행 중')}이에요. 1~2분 뒤 다시 해 주세요.")
        return 1
    except NeedLogin:
        print("내 계정 텔레그램 로그인이 필요해요. (tg-sync 설정)")
        return 3
    if not path:
        print(f"최근 {args.hours}시간 안에 {chat} 대화방에 내가 보낸 녹음 파일이 없어요.")
        return 1
    print(f"✅ 저장했어요.\nAUDIO: {Path(path).resolve().relative_to(ROOT).as_posix()}")
    return 0


def cmd_render(args):
    """원본에서 읽기용 문서를 전부 다시 만듦 (형식 변경 후 등)."""
    state = load_json(STATE_FILE, {"chats": {}})["chats"]
    try:
        with Lock("sync"):
            n = tg_render.render_all(state)
    except Busy as b:
        print(f"지금 {BUSY_TEXT.get(str(b), '다른 작업이 실행 중')}이에요. 잠시 뒤 다시 해 주세요.")
        return 1
    print(f"✅ 채팅방 {n}개의 읽기용 문서를 다시 만들었어요.")
    return 0


# ---------- schedule ----------

def ps(script):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def mac_plist(n):
    from xml.sax.saxutils import escape as x
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{MAC_LABEL}</string>
  <key>ProgramArguments</key><array>
    <string>{x(str(VENV_BG_PY))}</string><string>{x(str(Path(__file__).resolve()))}</string><string>sync</string>
  </array>
  <key>WorkingDirectory</key><string>{x(str(ROOT))}</string>
  <key>StartInterval</key><integer>{n * 60}</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{x(str(ROOT / 'logs' / 'schedule.out.log'))}</string>
  <key>StandardErrorPath</key><string>{x(str(ROOT / 'logs' / 'schedule.err.log'))}</string>
</dict></plist>
"""


def cmd_schedule(args):
    if not VENV_BG_PY.exists():
        print("필요한 프로그램(.venv)이 아직 설치되지 않았어요. 먼저 설치를 해야 해요.")
        return 1
    n = max(5, int(args.every))
    if not IS_WIN:
        MAC_PLIST.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["launchctl", "unload", str(MAC_PLIST)], capture_output=True)
        MAC_PLIST.write_text(mac_plist(n), encoding="utf-8")
        r = subprocess.run(["launchctl", "load", "-w", str(MAC_PLIST)], capture_output=True, text=True)
        if r.returncode != 0:
            print("자동 수집 등록에 실패했어요.")
            print((r.stderr or "")[-800:])
            return 1
        print(f"✅ 자동 수집을 켰어요. 이제 {n}분마다 새 메시지를 가져와요. (컴퓨터가 켜져 있고 로그인된 동안)")
        if any(part in ("Documents", "Desktop", "Downloads") for part in ROOT.parts):
            print("  ⚠ 이 폴더가 '문서/데스크탑/다운로드' 안에 있어서 Mac 보안 설정 때문에 자동 수집이 막힐 수 있어요.")
            print("    홈 폴더 바로 아래(예: ~/aibiz)로 옮기는 걸 권해요.")
        return 0
    script = f"""
$a = New-ScheduledTaskAction -Execute '{VENV_BG_PY}' -Argument '"{Path(__file__).resolve()}" sync' -WorkingDirectory '{ROOT}'
$t = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes {n})
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $a -Trigger $t -Settings $s -Description 'AIDev: 텔레그램 새 메시지 자동 수집' -Force | Out-Null
"""
    code, out, err = ps(script)
    if code != 0:
        print("자동 수집 등록에 실패했어요.")
        print(err[-800:])
        return 1
    print(f"✅ 자동 수집을 켰어요. 이제 {n}분마다 새 메시지를 가져와요. (컴퓨터가 켜져 있고 로그인된 동안)")
    return 0


def cmd_unschedule(args):
    if not IS_WIN:
        subprocess.run(["launchctl", "unload", "-w", str(MAC_PLIST)], capture_output=True)
        MAC_PLIST.unlink(missing_ok=True)
        print("자동 수집을 껐어요.")
        return 0
    code, out, err = ps(f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false")
    if code != 0 and "No MSFT_ScheduledTask" not in err and "찾을 수 없" not in err:
        print("자동 수집 해제에 실패했어요.")
        print(err[-800:])
        return 1
    print("자동 수집을 껐어요.")
    return 0


def schedule_info():
    if not IS_WIN:
        if not MAC_PLIST.exists():
            return None
        r = subprocess.run(["launchctl", "list", MAC_LABEL], capture_output=True, text=True)
        if r.returncode != 0:
            return None
        m = re.search(r'"LastExitStatus"\s*=\s*(-?\d+)', r.stdout)
        st = load_json(STATUS_FILE, {})
        return {"State": "Ready", "Last": st.get("finished", "-"), "Result": int(m.group(1)) if m else 0, "Next": "주기적으로"}
    code, out, err = ps(
        f"$t = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction Stop; $i = $t | Get-ScheduledTaskInfo; "
        "[pscustomobject]@{State=[string]$t.State; Last=$i.LastRunTime.ToString('yyyy-MM-dd HH:mm'); "
        "Result=$i.LastTaskResult; Next=$i.NextRunTime.ToString('yyyy-MM-dd HH:mm')} | ConvertTo-Json -Compress")
    if code != 0 or not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


# ---------- doctor ----------

def cmd_doctor(args):
    results = []  # (ok, code, title, detail)

    def add(ok, code, title, detail=""):
        results.append((ok, code, title, detail))

    add(sys.version_info >= (3, 9), "E-PYTHON", f"파이썬 {sys.version.split()[0]}",
        "" if sys.version_info >= (3, 9) else "파이썬 3.9 이상이 필요해요.")

    try:
        import telethon  # noqa: F401
        add(True, None, "필요한 프로그램 설치됨")
        lib_ok = True
    except ImportError:
        add(False, "E-NO-LIB", "필요한 프로그램이 아직 설치되지 않았어요", "설치 단계를 먼저 진행해야 해요.")
        lib_ok = False

    creds = load_json(CRED_FILE, None)
    if creds is None:
        add(False, "E-NO-CREDS", "텔레그램 인증 정보(api_id/api_hash)가 아직 없어요", "설정 창에서 입력해야 해요.")
        creds_ok = False
    else:
        probs = check_creds(creds)
        add(not probs, "E-BAD-CREDS", "인증 정보 모양 확인", " ".join(probs))
        creds_ok = not probs

    if not SESSION_FILE.exists():
        add(False, "E-NO-LOGIN", "텔레그램 로그인이 아직 안 되어 있어요", "설정 창에서 휴대폰 번호로 로그인해야 해요.")
    elif lib_ok and creds_ok and not args.offline:
        async def live():
            from telethon import errors
            client = make_client(creds)
            try:
                await asyncio.wait_for(client.connect(), 20)
            except (OSError, ConnectionError, asyncio.TimeoutError):
                return ("E-NETWORK", None)
            try:
                if not await client.is_user_authorized():
                    return ("E-LOGGED-OUT", None)
                return (None, display_name(await client.get_me()))
            except errors.ApiIdInvalidError:
                return ("E-BAD-API", None)
            except errors.AuthKeyUnregisteredError:
                return ("E-LOGGED-OUT", None)
            finally:
                await client.disconnect()
        try:
            with Lock("doctor"):
                code, name = asyncio.run(live())
            msgs = {
                "E-NETWORK": ("텔레그램 서버에 연결이 안 돼요", "인터넷 연결, 회사 방화벽, VPN 을 확인해 주세요."),
                "E-LOGGED-OUT": ("텔레그램 로그인이 풀렸어요", "휴대폰 텔레그램의 '기기' 목록에서 이 프로그램이 로그아웃됐을 수 있어요. 설정 창에서 다시 로그인하면 돼요."),
                "E-BAD-API": ("텔레그램이 api_id/api_hash 를 거절했어요", "값을 다시 복사해서 설정 창에서 입력해야 해요."),
            }
            if code:
                add(False, code, *msgs[code])
            else:
                add(True, None, f"텔레그램 연결 정상 — {name} 계정")
        except Busy as b:
            add(True, None, f"실시간 연결 확인은 건너뜀 ({BUSY_TEXT.get(str(b), '다른 작업 실행 중')})")
        except sqlite3.OperationalError:
            add(False, "E-SESSION-LOCKED", "로그인 정보 파일이 다른 곳에서 열려 있어요", "잠시 뒤 다시 점검해 주세요. 계속되면 설정 창이 열려 있지 않은지 확인하세요.")
    elif SESSION_FILE.exists():
        add(True, None, "로그인 정보 파일 있음 (실시간 확인 생략)")

    info = schedule_info()
    if info is None:
        add(False, "E-NO-SCHEDULE", "자동 수집이 꺼져 있어요", "켜면 정해진 간격마다 알아서 새 메시지를 가져와요.")
    else:
        bad = info.get("Result") not in (0, 267009, 267011, None)  # 0=성공, 267009=실행중, 267011=아직 실행 전
        add(not bad, "E-SCHEDULE-FAIL", f"자동 수집 켜짐 (마지막 {info.get('Last')}, 다음 {info.get('Next')})",
            f"마지막 자동 실행이 실패했어요 (코드 {info.get('Result')}). 아래 '최근 수집' 결과를 확인하세요." if bad else "")

    st = load_json(STATUS_FILE, None)
    if st:
        if st.get("ok"):
            add(True, None, f"최근 수집 {st.get('finished')}: 새 메시지 {st.get('new_messages', 0)}건 "
                            f"(채팅방 {st.get('chats_checked', 0)}개 확인)",
                " / ".join(st.get("problems") or []))
        else:
            add(False, st.get("error_code") or "E-UNKNOWN", f"최근 수집 실패 ({st.get('finished')})", st.get("message") or "")
    else:
        add(True, None, "아직 수집한 적 없음")

    if args.bot:
        token, access = bot_status()
        if not token:
            add(False, "E-BOT-NO-TOKEN", "휴대폰 질문용 봇이 아직 연결되지 않았어요", "BotFather 로 봇을 만들고 설정 창에 토큰을 넣어야 해요.")
        else:
            ok, info = check_bot_token(token) if not args.offline else (True, "(확인 생략)")
            add(ok, "E-BOT-BAD-TOKEN", f"봇 연결됨 {info}" if ok else "봇 토큰에 문제가 있어요", "" if ok else info)
            allowed = access.get("allowFrom") or []
            policy = access.get("dmPolicy", "pairing")
            if not allowed:
                add(False, "E-BOT-NOT-PAIRED", "아직 아무도 봇에 등록되지 않았어요", "휴대폰에서 봇에게 메시지를 보내고 받은 코드를 Claude 에게 알려 주세요.")
            elif policy != "allowlist":
                add(False, "E-BOT-OPEN", f"봇에 {len(allowed)}명 등록됨, 하지만 아직 잠기지 않았어요",
                    "모르는 사람도 등록 코드를 받을 수 있는 상태예요. 등록이 끝났으면 잠가야 해요.")
            else:
                add(True, None, f"봇 사용 가능 — {len(allowed)}명만 사용하도록 잠김")

    print("텔레그램 수집 점검 결과")
    print("-" * 40)
    for ok, code, title, detail in results:
        print(("✅ " if ok else "❌ ") + title + (f"  [{code}]" if not ok and code else ""))
        if detail:
            print("    " + detail)
    fails = [r for r in results if not r[0]]
    print("-" * 40)
    print("모두 정상이에요." if not fails else f"해결할 문제 {len(fails)}개 — 가장 위의 ❌ 부터 해결하면 돼요.")
    return 0 if not fails else 1


def main():
    setup_logging()
    p = argparse.ArgumentParser(description="텔레그램 메시지 수집기")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    d = sub.add_parser("doctor")
    d.add_argument("--offline", action="store_true", help="텔레그램에 실제로 접속하지 않고 점검")
    d.add_argument("--bot", action="store_true", help="휴대폰 질문용 봇 연결 상태도 점검")
    sub.add_parser("bot-setup")
    sy = sub.add_parser("sync")
    sy.add_argument("--only-bot", action="store_true", help="비서 봇 대화방만 (지시·답장 확인용, 몇 초)")
    sy.add_argument("--no-directive", action="store_true", help="수집 후 지시 처리를 시작하지 않음")
    sub.add_parser("chats")
    e = sub.add_parser("exclude")
    e.add_argument("action", choices=["add", "remove", "list"])
    e.add_argument("query", nargs="?", default="")
    e.add_argument("--purge", action="store_true", help="이미 저장된 그 방의 메시지도 삭제")
    s = sub.add_parser("schedule")
    s.add_argument("--every", type=int, default=30, help="몇 분마다 (기본 30)")
    sub.add_parser("unschedule")
    sub.add_parser("render")
    fm = sub.add_parser("fetch-media")
    fm.add_argument("--chat", help="대화방 (@아이디 또는 이름). 비우면 내 봇과의 대화방")
    fm.add_argument("--hours", type=int, default=24, help="최근 몇 시간 안의 파일 (기본 24)")
    a = p.parse_args()
    if a.cmd == "exclude" and a.action != "list" and not a.query:
        p.error("방 이름 또는 ID 를 적어 주세요.")
    return {
        "setup": cmd_setup, "bot-setup": cmd_bot_setup, "doctor": cmd_doctor, "sync": cmd_sync, "chats": cmd_chats,
        "exclude": cmd_exclude, "schedule": cmd_schedule, "unschedule": cmd_unschedule, "render": cmd_render,
        "fetch-media": cmd_fetch_media,
    }[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
