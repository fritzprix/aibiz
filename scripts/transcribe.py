"""회의 녹음 → 전사 (Google Gemini 사용).

명령:
  setup                    Gemini API 키 설정 (대화형 창에서)
  doctor                   키·모델·연결 점검
  run <녹음파일> [--title]  전사 → data/transcripts/<날짜>_<이름>.md

긴 녹음은 15분 단위로 잘라 전사하고 시간을 이어 붙입니다.
중간에 끊겨도 다시 실행하면 끝난 구간은 건너뜁니다.
"""
import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
KEY_FILE = ROOT / "secrets" / "gemini.json"
CONFIG_FILE = ROOT / "config" / "meeting.json"
WORK = ROOT / "data" / "audio" / "work"
TRANSCRIPTS = ROOT / "data" / "transcripts"
DEFAULT_CONFIG = {"model": "auto", "chunk_minutes": 5}
MIN_CHARS_PER_MIN = 120   # 말소리가 있는 구간인데 1분당 이보다 적게 받아 적으면 '중간에 끊김'으로 봄
MIN_SPLIT_SEC = 60
MODEL_CACHE = ROOT / "data" / "state" / "gemini_model.json"


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def load_config():
    cfg = load_json(CONFIG_FILE, None)
    if cfg is None:
        cfg = dict(DEFAULT_CONFIG)
        save_json(CONFIG_FILE, cfg)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def load_key():
    k = load_json(KEY_FILE, {})
    if os.environ.get("GEMINI_API_KEY"):
        k = {**k, "api_key": os.environ["GEMINI_API_KEY"]}
    return k


# ---------- 오류를 쉬운 말로 ----------

def explain(e):
    """(코드, 쉬운 설명)"""
    try:
        from google.genai import errors
    except ImportError:
        return "E-NO-LIB", "필요한 프로그램이 설치되지 않았어요."
    if isinstance(e, errors.APIError):
        msg = f"{getattr(e, 'status', '')} {getattr(e, 'message', '')} {e}"
        code = getattr(e, "code", 0)
        if "API_KEY_INVALID" in msg or "API key not valid" in msg or "API key expired" in msg:
            return "E-GEMINI-BAD-KEY", "API 키가 틀렸거나 만료됐어요. AI Studio 에서 키를 다시 복사하거나 새로 만들어 주세요."
        if "location is not supported" in msg.lower() or "User location" in msg:
            return "E-GEMINI-REGION", "지금 위치(또는 VPN)에서 이 서비스를 쓸 수 없다고 해요. VPN 을 끄거나, AI Studio 에서 결제 계정을 연결해 주세요."
        if code == 429 or "RESOURCE_EXHAUSTED" in msg:
            return "E-GEMINI-QUOTA", "사용 한도를 넘었어요. 무료 등급이면 한도가 작아요. 잠시 뒤 다시 하거나, 결제 계정을 연결하면 한도가 커져요."
        if code == 403 or "PERMISSION_DENIED" in msg:
            return "E-GEMINI-PERMISSION", "이 키로는 권한이 없대요. AI Studio 에서 새 키를 만들어 다시 설정해 주세요."
        if code == 404 or "NOT_FOUND" in msg:
            return "E-GEMINI-MODEL", "지정한 AI 모델을 찾을 수 없어요. 설정의 model 을 auto 로 두면 알아서 골라요."
        if code and code >= 500:
            return "E-GEMINI-SERVER", "Google 쪽 일시적인 문제예요. 잠시 뒤 다시 하면 대부분 해결돼요."
        return "E-GEMINI-OTHER", f"Gemini 오류 ({code}): {getattr(e, 'message', e)}"
    if isinstance(e, (OSError, ConnectionError)) or "Connect" in type(e).__name__ or "Timeout" in type(e).__name__:
        return "E-NETWORK", "인터넷에 연결되지 않았어요. 연결을 확인해 주세요."
    return "E-UNKNOWN", f"예상하지 못한 문제: {type(e).__name__}: {e}"


# ---------- 모델 ----------

def client_for(key):
    from google import genai
    return genai.Client(api_key=key)


def pick_model(client, cfg, refresh=False):
    """설정이 auto 면 쓸 수 있는 최신 'flash' 모델을 고름 (모델 이름이 바뀌어도 동작하도록)."""
    if cfg.get("model") and cfg["model"] != "auto":
        return cfg["model"]
    cache = load_json(MODEL_CACHE, {})
    if cache.get("model") and not refresh and time.time() - cache.get("at", 0) < 7 * 86400:
        return cache["model"]
    best = None
    for m in client.models.list():
        name = (m.name or "").removeprefix("models/")
        actions = getattr(m, "supported_actions", None) or []
        if actions and "generateContent" not in actions:
            continue
        mm = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash(-preview.*|-\d{3})?", name)
        if not mm:
            continue
        rank = (float(mm.group(1)), 0 if mm.group(2) and "preview" in mm.group(2) else 1, -len(name))
        if best is None or rank > best[0]:
            best = (rank, name)
    model = best[1] if best else "gemini-2.5-flash"
    save_json(MODEL_CACHE, {"model": model, "at": time.time()})
    return model


# ---------- setup ----------

def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        raise KeyboardInterrupt


def cmd_setup(args):
    print("=" * 60)
    print(" 회의 녹음 전사용 Gemini API 키 설정")
    print(" 키는 이 컴퓨터에만 저장되고, 채팅창이나 외부로 보내지지 않아요.")
    print("=" * 60)
    try:
        from google import genai  # noqa: F401
    except ImportError:
        print("\n⚠ 필요한 프로그램이 설치되지 않았어요. Claude 에게 '설치가 안 됐대'라고 알려 주세요.")
        return 1
    try:
        print("\nAI Studio 에서 복사한 API 키를 붙여넣어 주세요. (보통 AIza 로 시작하는 39글자)")
        print("  붙여넣기는 마우스 오른쪽 클릭 또는 Ctrl+V")
        while True:
            k = re.sub(r"\s", "", ask("  API 키 ▶ ")).strip("'\"")
            if not k:
                continue
            if not k.startswith("AIza") or len(k) != 39:
                print(f"  (모양이 보통과 달라요: {len(k)}글자. 일단 확인해 볼게요)")
            print("  확인 중...")
            try:
                c = client_for(k)
                model = pick_model(c, {"model": "auto"}, refresh=True)
                c.models.generate_content(model=model, contents="1+1=? 숫자만")
                break
            except Exception as e:
                code, text = explain(e)
                print(f"  ⚠ {text}")
                if code in ("E-GEMINI-REGION", "E-NETWORK"):
                    return 1
        print(f"  ✅ 키가 정상이에요. 사용할 AI 모델: {model}")
        print("\n중요: 무료 등급에서는 보낸 녹음이 Google 의 서비스 개선에 쓰일 수 있어요.")
        print("  AI Studio 에서 '결제 설정(Set up billing)'을 해 두면 유료 등급이 되어 학습에 쓰이지 않아요.")
        paid = ask("  결제 설정을 하셨나요? (y = 했음 / n = 안 했음·모름): ").lower() in ("y", "yes", "예", "네", "ㅛ")
        save_json(KEY_FILE, {"api_key": k, "paid_tier": paid, "saved": datetime.now().isoformat(timespec="seconds")})
        print("\n✅ 저장했어요." + ("" if paid else " (무료 등급으로 기록했어요. 회의록을 만들 때마다 한 번 더 확인할게요.)"))
        print("이 창을 닫고 Claude 에게 '다 했어' 라고 말해 주세요.")
        return 0
    except KeyboardInterrupt:
        print("\n\n중단했어요.")
        return 1


# ---------- doctor ----------

def cmd_doctor(args):
    out = []

    def add(ok, code, title, detail=""):
        out.append((ok, code, title, detail))

    try:
        from google import genai  # noqa: F401
        import imageio_ffmpeg  # noqa: F401
        add(True, None, "필요한 프로그램 설치됨")
        lib = True
    except ImportError:
        add(False, "E-NO-LIB", "필요한 프로그램이 아직 설치되지 않았어요", "Claude 가 설치를 진행하면 돼요.")
        lib = False
    k = load_key()
    if not k.get("api_key"):
        add(False, "E-GEMINI-NO-KEY", "Gemini API 키가 아직 없어요", "AI Studio 에서 키를 만들고 설정 창에 넣어야 해요.")
    elif lib and not args.offline:
        try:
            c = client_for(k["api_key"])
            model = pick_model(c, load_config(), refresh=True)
            c.models.generate_content(model=model, contents="1+1=? 숫자만")
            add(True, None, f"Gemini 연결 정상 (모델: {model})")
        except Exception as e:
            add(False, *explain(e))
    else:
        add(True, None, "Gemini API 키 있음 (실제 확인 생략)")
    if k.get("api_key"):
        add(bool(k.get("paid_tier")), "E-GEMINI-FREE-TIER",
            "유료 등급(결제 설정됨)" if k.get("paid_tier") else "무료 등급으로 설정됨",
            "" if k.get("paid_tier") else "무료 등급에서는 녹음이 Google 서비스 개선에 쓰일 수 있어요. 민감한 회의라면 결제 설정을 권해요.")
    print("회의록(전사) 점검 결과")
    print("-" * 40)
    for ok, code, title, detail in out:
        print(("✅ " if ok else "❌ ") + title + (f"  [{code}]" if not ok and code else ""))
        if detail:
            print("    " + detail)
    fails = [o for o in out if not o[0]]
    print("-" * 40)
    print("모두 정상이에요." if not fails else f"해결할 문제 {len(fails)}개")
    return 0 if not fails else 1


# ---------- 전사 ----------

def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration_sec(path):
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        raise ValueError("녹음 파일을 읽을 수 없어요. 파일이 손상됐거나 소리 파일이 아닐 수 있어요.")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def cut(src, dst, start, length):
    subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(length),
                    "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", str(dst)], check=True)


def hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def parse_ts(s):
    parts = [int(x) for x in re.findall(r"\d+", s or "0")][-3:]
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec


PROMPT = """다음은 회의 녹음의 일부입니다 (전체 {n}구간 중 {i}번째, 이 구간 길이 {mins}).
처음부터 **끝까지** 들리는 그대로 빠짐없이 받아 적으세요. 구간 끝까지 다 적기 전에 멈추지 마세요.

규칙
- 요약·생략·의역 금지. "음", "어" 같은 군더더기만 생략 가능. 말한 언어 그대로 (영어는 영어로).
- 한 항목은 길어야 30초 분량(약 300자). 한 사람이 길게 말하면 여러 항목으로 나누고 각각 start 를 적을 것.
- 영어 용어·회사명·제품명은 들리는 대로 원어로 표기.
- 말하는 사람이 바뀔 때마다 항목 하나. start 는 이 구간 시작 기준 "MM:SS".
- 화자는 목소리로 구분해 "화자1", "화자2" … 로 표기. 대화 중 이름·직함이 확실히 드러나면 그것을 써도 됨 (예: "김상무").
- 앞 구간과 같은 사람은 같은 표기를 유지.
- 알아들을 수 없는 부분은 [불명확].
- 말소리가 없으면 빈 목록.
{context}"""


def mean_volume(path):
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else 0.0


def looks_short(utts, length):
    """받아 적은 분량이 구간 길이에 비해 너무 적거나, 시각이 구간 중간에서 멈췄는지."""
    chars = sum(len(u.get("text") or "") for u in utts)
    last = max((parse_ts(u.get("start")) for u in utts), default=0)
    return chars < MIN_CHARS_PER_MIN * length / 60 or (length > 90 and last < length * 0.6)


def transcribe_span(client, model, src, work, tag, start, length, i, n, context, depth=0):
    """구간 하나를 전사. 결과가 모자라면 한 번 더 요청하고, 그래도 모자라면 반으로 나눠 다시."""
    mp3 = work / f"{tag}.mp3"
    cut(src, mp3, start, length)
    try:
        if mean_volume(mp3) < -50:  # 거의 무음
            return []
        span = f"{int(length // 60)}분 {int(length % 60)}초"
        best = None
        for attempt in range(2):
            utts = transcribe_chunk(client, model, mp3, i, n, span, context)
            if best is None or sum(len(u.get("text") or "") for u in utts) > sum(len(u.get("text") or "") for u in best):
                best = utts
            if not looks_short(utts, length):
                return utts
        if length / 2 < MIN_SPLIT_SEC or depth >= 2:
            return best
        half = length / 2
        print(f"    (받아 적은 양이 부족해서 반으로 나눠 다시 전사)", flush=True)
        a = transcribe_span(client, model, src, work, tag + "a", start, half, i, n, context, depth + 1)
        b = transcribe_span(client, model, src, work, tag + "b", start + half, length - half, i, n, context, depth + 1)
        return a + [dict(u, start=hms(half + parse_ts(u.get("start")))) for u in b]
    finally:
        mp3.unlink(missing_ok=True)


def recorded_at(src):
    """파일 이름에서 녹음 날짜·시각 찾기 (예: 260430_083802, 20260430_0838, 2026-04-30). 없으면 파일 시각."""
    name = src.stem
    m = re.search(r"(?<!\d)(\d{2})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})?(?!\d)", name)
    if m:
        y, mo, d, h, mi = (int(x) for x in m.groups()[:5])
        try:
            return datetime(2000 + y, mo, d, h, mi)
        except ValueError:
            pass
    m = re.search(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})(?:[_\- T]?(\d{2})[:._-]?(\d{2}))?", name)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4) or 0), int(m.group(5) or 0))
        except ValueError:
            pass
    return datetime.fromtimestamp(src.stat().st_mtime)


def transcribe_chunk(client, model, path, i, n, mins, context):
    from google.genai import types

    prompt = PROMPT.format(i=i, n=n, mins=mins, context=context)
    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {"start": {"type": "STRING"}, "speaker": {"type": "STRING"}, "text": {"type": "STRING"}},
            "required": ["start", "speaker", "text"],
        },
    }
    base = dict(temperature=0, max_output_tokens=65536, response_mime_type="application/json", response_schema=schema)
    data = Path(path).read_bytes()
    parts = [types.Part.from_bytes(data=data, mime_type="audio/mp3"), prompt]
    no_thinking = True  # 전사엔 '생각' 단계가 필요 없음 → 비용·시간 절약 (지원 안 하는 모델이면 끔)
    last = None
    for attempt in range(4):
        cfg = dict(base)
        if no_thinking:
            cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        try:
            r = client.models.generate_content(model=model, contents=parts, config=types.GenerateContentConfig(**cfg))
            return json.loads(r.text)
        except json.JSONDecodeError as e:
            last = e  # 답이 중간에 끊김 → 다시
        except Exception as e:
            code, _ = explain(e)
            last = e
            if code in ("E-GEMINI-BAD-KEY", "E-GEMINI-PERMISSION", "E-GEMINI-REGION"):
                raise
            if code == "E-GEMINI-OTHER" and no_thinking:
                no_thinking = False
                continue
            time.sleep(10 * (attempt + 1))
    raise last


def cmd_run(args):
    src = Path(args.audio).expanduser()
    if not src.exists():
        print(f"❌ 파일을 찾을 수 없어요: {src}")
        return 1
    k = load_key()
    if not k.get("api_key"):
        print("❌ Gemini API 키가 아직 설정되지 않았어요. [E-GEMINI-NO-KEY]")
        return 1
    cfg = load_config()
    try:
        total = duration_sec(src)
    except Exception as e:
        print(f"❌ {e}")
        return 1
    chunk = int(cfg["chunk_minutes"]) * 60
    n = max(1, int((total + chunk - 1) // chunk))
    stem = re.sub(r'[<>:"/\\|?*\s]+', "_", src.stem)[:50]
    work = WORK / f"{stem}_c{chunk}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        client = client_for(k["api_key"])
        model = pick_model(client, cfg)
    except Exception as e:
        code, text = explain(e)
        print(f"❌ {text} [{code}]")
        return 1
    print(f"녹음 길이 {hms(total)} → {n}구간으로 나눠 전사해요. (모델: {model})")
    lines, speakers = [], []
    for i in range(n):
        part_json = work / f"part_{i:03d}.json"
        start = i * chunk
        if part_json.exists():
            utts = load_json(part_json, [])
            print(f"  [{i + 1}/{n}] 이미 끝난 구간 — 건너뜀")
        else:
            length = min(chunk, total - start)
            context = ""
            if args.speakers:
                context += ("\n참석자 (알려진 이름): " + args.speakers +
                            "\n목소리·호칭·자기소개로 누구인지 판단되면 이 이름을 화자로 쓰고, 확실하지 않으면 화자번호를 쓸 것.")
            if lines:
                context += "\n앞 구간 화자: " + ", ".join(speakers) + "\n앞 구간 마지막 발화:\n" + "\n".join(lines[-6:])
            print(f"  [{i + 1}/{n}] 전사 중...", flush=True)
            try:
                utts = transcribe_span(client, model, src, work, f"part_{i:03d}", start, length, i + 1, n, context)
            except Exception as e:
                code, text = explain(e)
                print(f"❌ {i + 1}번째 구간에서 멈췄어요: {text} [{code}]")
                print("   다시 실행하면 끝난 구간은 건너뛰고 이어서 해요.")
                return 1
            save_json(part_json, utts)
        for u in utts:
            sp = (u.get("speaker") or "?").strip()
            if sp not in speakers:
                speakers.append(sp)
            text = re.sub(r"\s*\n\s*", " ", (u.get("text") or "").strip())
            if text:
                lines.append(f"[{hms(start + parse_ts(u.get('start')))}] {sp}: {text}")
    title = args.title or src.stem
    when = datetime.fromisoformat(args.date) if args.date else recorded_at(src)
    day = when.strftime("%Y-%m-%d")
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    out = TRANSCRIPTS / f"{day}_{stem}.md"
    head = [
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"source: {json.dumps(src.name, ensure_ascii=False)}",
        f"recorded: {when:%Y-%m-%d %H:%M} ({'월화수목금토일'[when.weekday()]})",
        f"duration: {hms(total)}",
        f"engine: gemini/{model}",
        f"speakers: [{', '.join(json.dumps(s, ensure_ascii=False) for s in speakers)}]",
        f"utterances: {len(lines)}",
        "---",
        f"# 전사: {title}",
        "",
    ]
    out.write_text("\n".join(head + lines) + "\n", encoding="utf-8")
    print(f"✅ 전사 완료: 발화 {len(lines)}개, 화자 {len(speakers)}명")
    print(f"TRANSCRIPT: {out.relative_to(ROOT).as_posix()}")
    return 0


def main():
    p = argparse.ArgumentParser(description="회의 녹음 전사 (Gemini)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    d = sub.add_parser("doctor")
    d.add_argument("--offline", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("audio")
    r.add_argument("--title")
    r.add_argument("--speakers", help="참석자 이름 (쉼표로 구분). 화자 구분 정확도가 올라감")
    r.add_argument("--date", help="녹음 날짜 (예: 2026-04-30 08:38). 비우면 파일 이름·시각에서 찾음")
    a = p.parse_args()
    return {"setup": cmd_setup, "doctor": cmd_doctor, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
