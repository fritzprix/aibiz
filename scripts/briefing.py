"""아침 브리핑 자동 실행·전송.

명령:
  auto                        (예약 실행용) 새 메시지 수집 → Claude 로 위키 반영+브리핑 작성 → 텔레그램 전송
  send <요약.txt> [--attach 전체.md]   봇으로 보내기
  schedule [--time 07:30] [--days weekdays|daily]   자동 실행 켜기
  unschedule                  자동 실행 끄기
  status                      예약 상태와 마지막 결과

Claude 는 화면 없이(claude -p) 실행되고, 이 컴퓨터에 켜져 있는 비서 창의 봇 연결과 충돌하지 않게
텔레그램 플러그인을 끈 채로 실행합니다. 전송은 봇 주소로 직접 보냅니다.
"""
import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tg_sync as T  # noqa: E402

ROOT = T.ROOT
CONFIG_FILE = ROOT / "config" / "briefing.json"
STATUS_FILE = ROOT / "data" / "state" / "briefing_status.json"
OUT_DIR = ROOT / "briefings"
LOG = ROOT / "logs" / "briefing.log"
PY = ROOT / ".venv" / ("Scripts/python.exe" if T.IS_WIN else "bin/python")
TASK_NAME = "AIDev-MorningBriefing"
MAC_LABEL = "com.aidev.morningbriefing"
MAC_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"
DEFAULT = {"time": "07:30", "days": "weekdays", "claude_path": None}
DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def cfg():
    c = T.load_json(CONFIG_FILE, None)
    if c is None:
        c = dict(DEFAULT)
        T.save_json(CONFIG_FILE, c)
    for k, v in DEFAULT.items():
        c.setdefault(k, v)
    return c


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    print(msg, flush=True)


# ---------- 텔레그램 전송 ----------

def recipients():
    token, access = T.bot_status()
    return token, [str(x) for x in (access.get("allowFrom") or [])]


def tg_call(token, method, fields, file_field=None, file_path=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    if file_path:
        b = uuid.uuid4().hex
        body = bytearray()
        for k, v in fields.items():
            body += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        name = Path(file_path).name
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{name}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n").encode()
        body += Path(file_path).read_bytes() + f"\r\n--{b}--\r\n".encode()
        req = urllib.request.Request(url, data=bytes(body), headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    else:
        req = urllib.request.Request(url, data=json.dumps(fields).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def chunks(text, limit=3900):
    out, cur = [], ""
    for para in text.split("\n\n"):
        if len(cur) + len(para) + 2 > limit and cur:
            out.append(cur)
            cur = ""
        while len(para) > limit:
            out.append(para[:limit])
            para = para[limit:]
        cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out


def send(text, attach=None):
    token, to = recipients()
    if not token or not to:
        raise RuntimeError("휴대폰 질문용 봇이 연결·등록되어 있지 않아 텔레그램으로 보낼 수 없어요. (tg-bot 설정 필요)")
    for chat in to:
        for part in chunks(text):
            tg_call(token, "sendMessage", {"chat_id": chat, "text": part, "disable_web_page_preview": True})
        if attach and Path(attach).exists():
            tg_call(token, "sendDocument", {"chat_id": chat}, "document", attach)
    return len(to)


def cmd_send(a):
    try:
        n = send(Path(a.text).read_text(encoding="utf-8"), a.attach)
    except Exception as e:
        print(f"❌ 보내지 못했어요: {e}")
        return 1
    print(f"✅ {n}명에게 보냈어요.")
    return 0


# ---------- 자동 실행 ----------

def find_claude(c):
    p = c.get("claude_path")
    if p and Path(p).exists():
        return p
    p = shutil.which("claude") or shutil.which("claude.exe") or shutil.which("claude.cmd")
    for guess in (Path.home() / ".local" / "bin" / ("claude.exe" if T.IS_WIN else "claude"),):
        if not p and guess.exists():
            p = str(guess)
    if p and p.lower().endswith((".cmd", ".bat")):  # npm 설치: 인자 따옴표가 깨지지 않게 실제 실행 파일 사용
        exe = Path(p).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if exe.exists():
            p = str(exe)
    return p


def allowed_tools():
    py = ".venv/Scripts/python.exe" if T.IS_WIN else ".venv/bin/python"
    tools = ["Read", "Grep", "Glob", "Write", "Edit", "Agent", "Skill"]
    for s in ("digest.py", "md2docx.py"):
        tools += [f"Bash({py} scripts/{s}:*)", f"Bash(./{py} scripts/{s}:*)"]
    return ",".join(tools)


def write_status(ok, msg, **kw):
    T.save_json(STATUS_FILE, {"ok": ok, "message": msg, "at": datetime.now().isoformat(timespec="seconds"), **kw})


def cmd_auto(a):
    c = cfg()
    today = datetime.now().strftime("%Y-%m-%d")
    full, short = OUT_DIR / f"{today}.md", OUT_DIR / f"{today}.telegram.txt"
    log("=== 아침 브리핑 시작")
    r = subprocess.run([str(PY), str(ROOT / "scripts" / "tg_sync.py"), "sync"], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    log("수집: " + (r.stdout.strip().splitlines() or ["(출력 없음)"])[-1])
    claude = find_claude(c)
    if not claude:
        return fail("Claude Code 를 찾지 못했어요. (설치 위치가 바뀌었을 수 있어요)")
    env = dict(os.environ)
    env["TELEGRAM_STATE_DIR"] = str(ROOT / "data" / "state" / "headless_telegram")  # 비서 창의 봇 연결을 건드리지 않음
    empty_mcp = ROOT / "data" / "state" / "empty_mcp.json"
    T.save_json(empty_mcp, {"mcpServers": {}})
    cmd = [claude, "-p", "/morning-briefing auto", "--allowedTools", allowed_tools(),
           "--strict-mcp-config", "--mcp-config", str(empty_mcp)]
    log("Claude 실행: 위키 반영 + 브리핑 작성")
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=a.timeout * 60)
    except subprocess.TimeoutExpired:
        return fail(f"브리핑 작성이 {a.timeout}분 안에 끝나지 않았어요.")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "logs" / "briefing_claude_last.log").write_text((r.stdout or "") + "\n--- stderr ---\n" + (r.stderr or ""),
                                                             encoding="utf-8")
    log(f"Claude 종료 (코드 {r.returncode}, {int(time.time() - t0)}초)")
    if not short.exists() or not full.exists():
        return fail("브리핑 파일이 만들어지지 않았어요. (logs/briefing_claude_last.log 참고)")
    try:
        n = send(short.read_text(encoding="utf-8"), full)
    except Exception as e:
        return fail(f"브리핑은 만들었지만 텔레그램 전송에 실패했어요: {e}", alert=False)
    subprocess.run([str(PY), str(ROOT / "scripts" / "digest.py"), "commit", "briefing"], cwd=ROOT,
                   capture_output=True)
    write_status(True, f"{n}명에게 전송", file=full.relative_to(ROOT).as_posix())
    log(f"✅ 완료: {n}명에게 전송")
    return 0


def fail(msg, alert=True):
    log("❌ " + msg)
    write_status(False, msg)
    subprocess.run([str(PY), str(ROOT / "scripts" / "digest.py"), "release", "briefing"], cwd=ROOT,
                   capture_output=True)
    if alert:
        try:
            send(f"⚠ 오늘 아침 브리핑을 만들지 못했어요.\n이유: {msg}\n\n컴퓨터의 비서 창에서 \"브리핑 다시 해줘\" 라고 하면 다시 만들어요.")
        except Exception:
            pass
    return 1


# ---------- 예약 ----------

def cmd_schedule(a):
    c = cfg()
    if a.time:
        c["time"] = a.time
    if a.days:
        c["days"] = a.days
    claude = find_claude(c)
    if not claude:
        print("Claude Code 위치를 찾지 못했어요. 먼저 Claude Code 를 설치해 주세요.")
        return 1
    c["claude_path"] = claude
    T.save_json(CONFIG_FILE, c)
    hh, mm = (int(x) for x in c["time"].split(":"))
    days = DAYS_EN[:5] if c["days"] == "weekdays" else DAYS_EN
    if T.IS_WIN:
        script = f"""
$a = New-ScheduledTaskAction -Execute '{T.VENV_BG_PY}' -Argument '"{Path(__file__).resolve()}" auto' -WorkingDirectory '{ROOT}'
$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek {','.join(days)} -At '{hh:02d}:{mm:02d}'
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun
Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $a -Trigger $t -Settings $s -Description 'AIDev: 아침 브리핑' -Force | Out-Null
"""
        code, out, err = T.ps(script)
        if code != 0:
            print("예약에 실패했어요.\n" + err[-800:])
            return 1
    else:
        from xml.sax.saxutils import escape as x
        wd = range(1, 6) if c["days"] == "weekdays" else range(0, 7)
        cal = "".join(f"<dict><key>Weekday</key><integer>{d}</integer><key>Hour</key><integer>{hh}</integer>"
                      f"<key>Minute</key><integer>{mm}</integer></dict>" for d in wd)
        MAC_PLIST.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["launchctl", "unload", str(MAC_PLIST)], capture_output=True)
        MAC_PLIST.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{MAC_LABEL}</string>
  <key>ProgramArguments</key><array><string>{x(str(PY))}</string><string>{x(str(Path(__file__).resolve()))}</string><string>auto</string></array>
  <key>WorkingDirectory</key><string>{x(str(ROOT))}</string>
  <key>StartCalendarInterval</key><array>{cal}</array>
  <key>StandardOutPath</key><string>{x(str(ROOT / 'logs' / 'briefing.out.log'))}</string>
  <key>StandardErrorPath</key><string>{x(str(ROOT / 'logs' / 'briefing.err.log'))}</string>
</dict></plist>
""", encoding="utf-8")
        r = subprocess.run(["launchctl", "load", "-w", str(MAC_PLIST)], capture_output=True, text=True)
        if r.returncode != 0:
            print("예약에 실패했어요.\n" + (r.stderr or "")[-800:])
            return 1
    label = "평일" if c["days"] == "weekdays" else "매일"
    print(f"✅ {label} {hh:02d}:{mm:02d} 에 아침 브리핑을 보내도록 예약했어요. (컴퓨터가 켜져 있어야 해요)")
    return 0


def cmd_unschedule(a):
    if T.IS_WIN:
        T.ps(f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false")
    else:
        subprocess.run(["launchctl", "unload", "-w", str(MAC_PLIST)], capture_output=True)
        MAC_PLIST.unlink(missing_ok=True)
    print("아침 브리핑 자동 실행을 껐어요.")
    return 0


def cmd_status(a):
    c = cfg()
    if T.IS_WIN:
        code, out, _ = T.ps(f"(Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction Stop | Get-ScheduledTaskInfo)"
                            ".NextRunTime.ToString('yyyy-MM-dd HH:mm')")
        sched = out if code == 0 and out else None
    else:
        sched = "켜짐" if MAC_PLIST.exists() else None
    print(f"예약: {('켜짐 — 다음 ' + sched) if sched else '꺼짐'} ({'평일' if c['days'] == 'weekdays' else '매일'} {c['time']})")
    st = T.load_json(STATUS_FILE, None)
    print("마지막 결과: " + (f"{st['at']} {'✅' if st['ok'] else '❌'} {st['message']}" if st else "아직 없음"))
    token, to = recipients()
    print(f"받는 사람: {len(to)}명" if token and to else "받는 사람: 없음 (봇 연결·등록 필요)")
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    au = sub.add_parser("auto")
    au.add_argument("--timeout", type=int, default=90, help="Claude 작성 제한 시간(분)")
    s = sub.add_parser("send")
    s.add_argument("text")
    s.add_argument("--attach")
    sc = sub.add_parser("schedule")
    sc.add_argument("--time")
    sc.add_argument("--days", choices=["weekdays", "daily"])
    sub.add_parser("unschedule")
    sub.add_parser("status")
    a = p.parse_args()
    return {"auto": cmd_auto, "send": cmd_send, "schedule": cmd_schedule, "unschedule": cmd_unschedule,
            "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
