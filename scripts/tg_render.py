"""수집한 원본(JSONL)을 검색·읽기 쉬운 마크다운으로 정리 (규칙 기반, Claude 사용 안 함).

결과 구조:
  data/raw/<chat_id>/<YYYY-MM>.jsonl        원본 (월별, 덧붙이기만 함 — 다시 만들 때의 근거)
  data/text/<종류>/<방이름>__<chat_id>/
      _index.md                             방 요약 (날짜별 메시지 수, 주요 참여자)
      <YYYY-MM-DD>.md                       하루치 대화 (메시지 1개 = 1줄)
  data/daily/<YYYY-MM-DD>.md                그날 대화가 있었던 방 목록
  data/chats.md                             전체 방 목록

한 줄 형식:  HH:MM [#메시지번호] 보낸사람 ↪#답장대상: 내용 (첨부)
"""
import json
import os
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
TEXT = ROOT / "data" / "text"
DAILY = ROOT / "data" / "daily"
CHATS_MD = ROOT / "data" / "chats.md"
CACHE_FILE = ROOT / "data" / "state" / "text_index.json"

KIND_DIR = {"private": "private", "group": "group", "channel": "channel", "bot": "other", "saved": "other"}
KIND_KO = {"private": "1:1 대화", "group": "그룹", "channel": "채널", "bot": "봇", "saved": "저장한 메시지"}
MEDIA_KO = {"photo": "사진", "video": "동영상", "voice": "음성메시지", "audio": "오디오", "link": "링크 미리보기", "file": "파일"}
WEEK = "월화수목금토일"
SESSION_GAP_MIN = 60  # 이 시간 이상 대화가 끊기면 새 단락
GENERATED_NOTE = "<!-- 자동 생성 파일: 직접 고치지 마세요. 다음 수집 때 덮어써집니다. -->"


# ---------- 원본 (JSONL) ----------

def read_jsonl(p):
    rows = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # 쓰다 끊긴 줄
    except FileNotFoundError:
        pass
    return rows


def append_rows(cid, rows):
    """원본을 월별 파일에 덧붙이고, 바뀐 (방, 날짜) 목록을 돌려줌."""
    by_month = {}
    for r in rows:
        by_month.setdefault(r["date"][:7], []).append(r)
    d = RAW / cid
    d.mkdir(parents=True, exist_ok=True)
    for ym, rs in by_month.items():
        with open(d / f"{ym}.jsonl", "a", encoding="utf-8") as f:
            for r in rs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {(cid, r["date"][:10]) for r in rows}


def migrate_flat():
    """예전 형식(data/raw/<id>.jsonl 한 파일)을 월별 폴더로 옮김."""
    n = 0
    for p in list(RAW.glob("*.jsonl")):
        rows = read_jsonl(p)
        if rows:
            append_rows(p.stem, rows)
        p.unlink()
        n += 1
    return n


def chat_rows(cid, month=None):
    files = [RAW / cid / f"{month}.jsonl"] if month else sorted((RAW / cid).glob("*.jsonl"))
    seen = {}
    for p in files:
        for r in read_jsonl(p):
            seen[r["id"]] = r  # 같은 메시지가 두 번 저장돼도 하나로
    return sorted(seen.values(), key=lambda r: r["id"])


# ---------- 마크다운 ----------

def slug(title):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title or "")
    s = "".join(ch for ch in s if ord(ch) <= 0xFFFF)  # 이모지 제거 (경로 문제 방지)
    s = re.sub(r"\s+", "_", s.strip()).strip("._")
    return s[:40] or "이름없음"


def chat_dir(cid, meta):
    want = TEXT / KIND_DIR.get(meta.get("type"), "other") / f"{slug(meta.get('title'))}__{cid}"
    for old in TEXT.glob(f"*/*__{cid}"):
        if old != want:  # 방 이름이 바뀐 경우 폴더 이름도 따라감
            want.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old, want)
        break
    want.mkdir(parents=True, exist_ok=True)
    return want


def one_line(text):
    return re.sub(r"\s*\r?\n\s*", " ⏎ ", (text or "").strip())


def media_ko(m):
    if not m:
        return None
    if m.startswith("file:"):
        return f"파일: {m[5:]}"
    return MEDIA_KO.get(m, m)


def fmt_line(r, kind):
    head = f"{r['date'][11:16]} [#{r['id']}]"
    if kind != "channel":
        head += f" {r.get('sender') or '?'}" + (" (나)" if r.get("out") else "")
    if r.get("reply_to"):
        head += f" ↪#{r['reply_to']}"
    extras = [x for x in ("전달됨" if r.get("forwarded") else None, media_ko(r.get("media"))) if x]
    body = one_line(r.get("text"))
    tail = f" ({', '.join(extras)})" if extras else ""
    return f"{head}: {body}{tail}".rstrip()


def md_link(text, path):
    """방 이름의 [ ] 와 경로의 ( ) 때문에 링크가 깨지지 않게."""
    t = (text or "").replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    return f"[{t}](<{path}>)"


def yaml_str(s):
    return json.dumps(s or "", ensure_ascii=False)


def top_people(rows, kind, n):
    if kind == "channel":
        return []
    c = Counter((r.get("sender") or "?") for r in rows)
    return c.most_common(n)


def render_day(cid, day, meta, folder):
    kind = meta.get("type")
    rows = [r for r in chat_rows(cid, day[:7]) if r["date"][:10] == day]
    out = folder / f"{day}.md"
    if not rows:
        out.unlink(missing_ok=True)
        return None
    people = top_people(rows, kind, 10)
    wd = WEEK[date.fromisoformat(day).weekday()]
    lines = [
        "---",
        f"chat: {yaml_str(meta.get('title'))}",
        f"chat_id: {yaml_str(cid)}",
        f"type: {kind}",
        f"date: {day}",
        f"messages: {len(rows)}",
        f"first_id: {rows[0]['id']}",
        f"last_id: {rows[-1]['id']}",
        f"participants: [{', '.join(yaml_str(p) for p, _ in people)}]",
        "---",
        GENERATED_NOTE,
        f"# {meta.get('title')} · {day} ({wd}) · {KIND_KO.get(kind, kind)}",
    ]
    session, prev = [], None
    for r in sorted(rows, key=lambda r: (r["date"], r["id"])):
        t = datetime.fromisoformat(r["date"])
        if prev is not None and (t - prev).total_seconds() > SESSION_GAP_MIN * 60:
            lines += flush_session(session, kind)
            session = []
        session.append(r)
        prev = t
    lines += flush_session(session, kind)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"count": len(rows), "people": [p for p, _ in people[:3]]}


def flush_session(rows, kind):
    if not rows:
        return []
    return ["", f"## {rows[0]['date'][11:16]}~{rows[-1]['date'][11:16]} ({len(rows)}건)"] + [fmt_line(r, kind) for r in rows]


def render_chat_index(cid, meta, folder, cache):
    kind = meta.get("type")
    rows = chat_rows(cid)
    days = {}
    for r in rows:
        days.setdefault(r["date"][:10], []).append(r)
    entry = {
        "title": meta.get("title"), "type": kind, "dir": folder.relative_to(ROOT).as_posix(),
        "total": len(rows), "first": min(days) if days else None, "last": max(days) if days else None,
        "days": {d: [len(rs), [p for p, _ in top_people(rs, kind, 3)]] for d, rs in days.items()},
    }
    cache[cid] = entry
    people = top_people(rows, kind, 15)
    lines = [
        "---",
        f"chat: {yaml_str(meta.get('title'))}",
        f"chat_id: {yaml_str(cid)}",
        f"type: {kind}",
        f"username: {yaml_str(meta.get('username'))}",
        f"messages: {entry['total']}",
        f"first_date: {entry['first']}",
        f"last_date: {entry['last']}",
        "---",
        GENERATED_NOTE,
        f"# {meta.get('title')} ({KIND_KO.get(kind, kind)})",
        "",
    ]
    if people:
        lines += ["주요 참여자: " + ", ".join(f"{p}({n})" for p, n in people), ""]
    lines += ["| 날짜 | 메시지 | 주요 참여자 |", "|---|---:|---|"]
    for d in sorted(days, reverse=True):
        n, ps = entry["days"][d]
        lines.append(f"| [{d}]({d}.md) | {n} | {', '.join(ps)} |")
    (folder / "_index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_daily(day, cache):
    items = []
    for cid, e in cache.items():
        if day in e["days"]:
            n, ps = e["days"][day]
            items.append((n, e, cid, ps))
    out = DAILY / f"{day}.md"
    if not items:
        out.unlink(missing_ok=True)
        return
    DAILY.mkdir(parents=True, exist_ok=True)
    items.sort(key=lambda x: -x[0])
    wd = WEEK[date.fromisoformat(day).weekday()]
    lines = [GENERATED_NOTE, f"# {day} ({wd}) — 대화가 있었던 방 {len(items)}개, 메시지 {sum(i[0] for i in items)}건", ""]
    for n, e, cid, ps in items:
        who = f" — {', '.join(ps)}" if ps else ""
        link = md_link(e["title"], f"../text/{e['dir'].split('data/text/', 1)[1]}/{day}.md")
        lines.append(f"- {link} · {KIND_KO.get(e['type'], e['type'])} · {n}건{who}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_chats_md(cache):
    rows = sorted(cache.values(), key=lambda e: (e["last"] or ""), reverse=True)
    lines = [GENERATED_NOTE, f"# 채팅방 목록 ({len(rows)}개, 메시지가 있는 방만)", "",
             "| 방 | 종류 | 메시지 | 처음 | 마지막 |", "|---|---|---:|---|---|"]
    for e in rows:
        title = md_link(e["title"], f"{e['dir'].split('data/', 1)[1]}/_index.md").replace("|", "\\|")
        lines.append(f"| {title} | {KIND_KO.get(e['type'], e['type'])} "
                     f"| {e['total']} | {e['first']} | {e['last']} |")
    CHATS_MD.parent.mkdir(parents=True, exist_ok=True)
    CHATS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_cache():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, CACHE_FILE)


def render(touched, state_chats):
    """바뀐 (방, 날짜)만 다시 만듦."""
    cache = load_cache()
    by_chat = {}
    for cid, day in touched:
        by_chat.setdefault(cid, set()).add(day)
    for cid, days in by_chat.items():
        meta = state_chats.get(cid) or {"title": cid, "type": "group"}
        folder = chat_dir(cid, meta)
        for d in sorted(days):
            render_day(cid, d, meta, folder)
        render_chat_index(cid, meta, folder, cache)
    for d in sorted({d for _, d in touched}):
        render_daily(d, cache)
    render_chats_md(cache)
    save_cache(cache)
    return len(by_chat)


def render_all(state_chats):
    migrate_flat()
    touched = set()
    for d in RAW.iterdir() if RAW.exists() else []:
        if d.is_dir():
            touched |= {(d.name, r["date"][:10]) for r in chat_rows(d.name)}
    return render(touched, state_chats)


def remove_chat(cid):
    """방 하나의 원본·문서를 모두 지움 (제외 + --purge)."""
    import shutil

    shutil.rmtree(RAW / cid, ignore_errors=True)
    for d in TEXT.glob(f"*/*__{cid}"):
        shutil.rmtree(d, ignore_errors=True)
    cache = load_cache()
    e = cache.pop(cid, None)
    if e:
        for day in e["days"]:
            render_daily(day, cache)
        render_chats_md(cache)
        save_cache(cache)
