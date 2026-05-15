import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from dateutil import tz
import feedparser
import yaml

DB_PATH = "news.db"
OUT_DIR = "out"
LATEST_JSON = os.path.join(OUT_DIR, "latest.json")
LATEST_TXT = os.path.join(OUT_DIR, "latest.txt")
ALL_JSONL = os.path.join(OUT_DIR, "articles.jsonl")

SEOUL_TZ = tz.gettz("Asia/Seoul")

def load_config(path="news_config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def ensure_dirs():
    os.makedirs(OUT_DIR, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            guid TEXT UNIQUE,
            title TEXT,
            link TEXT,
            summary TEXT,
            published_utc TEXT,
            fetched_utc TEXT,
            is_used INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn

def make_guid(entry):
    # 우선순위: entry.id > entry.guid > entry.link > title+published 해시
    candidates = [
        getattr(entry, "id", None),
        getattr(entry, "guid", None),
        getattr(entry, "link", None)
    ]
    for c in candidates:
        if c: 
            return c
    basis = f"{getattr(entry,'title','')}_{getattr(entry,'published','')}"
    return hashlib.sha256(basis.encode("utf-8", "ignore")).hexdigest()

def to_iso_utc(entry):
    # feedparser의 published_parsed → ISO UTC
    if getattr(entry, "published_parsed", None):
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    else:
        dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    return dt.isoformat()

def filter_by_keywords(title, summary, include, exclude):
    text = f"{title} {summary}".lower()
    if include:
        if not any(k.lower() in text for k in include):
            return False
    if exclude:
        if any(k.lower() in text for k in exclude):
            return False
    return True

def save_latest_files(rec):
    # latest.json
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    # latest.txt (다음 단계에서 바로 프롬프트로 쓰기 쉬움)
    seoul_dt = datetime.fromisoformat(rec["published_utc"]).astimezone(SEOUL_TZ)
    lines = [
        f"[{rec['source']}] {rec['title']}",
        f"링크: {rec['link']}",
        f"발행(서울): {seoul_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"요약: {rec['summary'] or ''}".strip()
    ]
    with open(LATEST_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    # 누적 로그(JSON Lines)
    with open(ALL_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def fetch_once(cfg, conn):
    include = cfg.get("include_keywords") or []
    exclude = cfg.get("exclude_keywords") or []
    feeds = cfg.get("feeds") or []
    new_count = 0

    for feed in feeds:
        name = feed["name"]
        url = feed["url"]
        print(f"[*] Fetching: {name} | {url}")
        d = feedparser.parse(url)

        for entry in d.entries:
            guid = make_guid(entry)
            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            published_utc = to_iso_utc(entry)
            fetched_utc = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

            if not filter_by_keywords(title, summary, include, exclude):
                continue

            # DB Insert (중복 무시)
            try:
                conn.execute(
                    "INSERT INTO articles (source, guid, title, link, summary, published_utc, fetched_utc) VALUES (?,?,?,?,?,?,?)",
                    (name, guid, title, link, summary, published_utc, fetched_utc)
                )
                conn.commit()
                new_count += 1
                rec = {
                    "source": name,
                    "guid": guid,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published_utc": published_utc,
                    "fetched_utc": fetched_utc
                }
                save_latest_files(rec)  # 가장 최근 건을 최신 파일로 갱신
                print(f"  [+] New: {title}")
            except sqlite3.IntegrityError:
                # 이미 본 기사
                conn.rollback()
                pass

    print(f"[*] Cycle done. New articles: {new_count}")
    return new_count

def main():
    ensure_dirs()
    cfg = load_config()
    conn = init_db()
    interval = int(cfg.get("poll_seconds", 30))
    print(f"Started news collector | interval={interval}s | DB={DB_PATH} | OUT={OUT_DIR}")

    while True:
        try:
            fetch_once(cfg, conn)
        except Exception as e:
            print("[!] Error in fetch cycle:", e)
        time.sleep(interval)

if __name__ == "__main__":
    main()
