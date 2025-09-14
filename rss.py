import feedparser
import requests
import re
import time
import subprocess
from pathlib import Path
from typing import Optional, Tuple

# --- Config ---
acc = "YUY_IX"
RSS_URL = f"http://localhost:8080/YUY_IX/rss" # hardcoded bc it got mad when i put the acc string in here????
POLL_INTERVAL_SECONDS = 60  # 1 minute
CACHE_FILE = Path("last_seen_id.txt")  # store numeric tweet ID only
POST_ENDPOINT = "http://localhost:3000/"
CURL_BIN = "curl"  
POST_ON_FIRST_RUN = False  

UA = {"User-Agent": "rss-watcher/1.0 (+local)"}

ID_RE = re.compile(r"/status/(\d+)", re.IGNORECASE)
SKIP_TITLE_RE = re.compile(r"^(RT\b|R to\s)", re.IGNORECASE)

def extract_id(raw_link: str) -> Optional[int]:
    m = ID_RE.search(raw_link or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None

def normalize_link(tweet_id: int) -> str:
    # Use lowercase "status" (X/Twitter format)
    return f"https://x.com/{acc}/status/{tweet_id}"

def read_last_seen_id() -> Optional[int]:
    try:
        return int(CACHE_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None

def write_last_seen_id(tweet_id: int) -> None:
    CACHE_FILE.write_text(str(tweet_id), encoding="utf-8")

def fetch_feed(url: str):
    resp = requests.get(url, headers=UA, timeout=20)
    resp.raise_for_status()
    feed = feedparser.parse(resp.text.lstrip())
    if getattr(feed, "bozo", 0) == 1:
        raise RuntimeError(f"RSS parse error: {feed.bozo_exception}")
    return feed

def entry_pub_ts(entry) -> float:
    """
    Return a sortable timestamp (epoch seconds) from entry if available,
    else 0. feedparser sets 'published_parsed' or 'updated_parsed' as time.struct_time.
    """
    t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if t:
        # Convert struct_time to epoch
        import calendar, time as _time
        return calendar.timegm(t)
    return 0.0

def pick_newest_eligible(feed, last_id: Optional[int]) -> Optional[Tuple[str, int, str]]:
    """
    Return (title, tweet_id, published_str) for the newest eligible entry with id > last_id.
    Eligibility: title NOT starting with RT / R to .
    Sort by published time desc fallback by tweet id desc if times equal/missing.
    """
    items = []
    for e in feed.entries:
        title = (e.get("title") or "").strip()
        if SKIP_TITLE_RE.match(title):
            continue
        tid = extract_id(e.get("link", ""))
        if tid is None:
            continue
        items.append((title, tid, e.get("published", ""), entry_pub_ts(e)))

    if not items:
        return None

    # Sort: primary by timestamp desc secondary by id desc
    items.sort(key=lambda x: (x[3], x[1]), reverse=True)

    # Find first strictly newer than last_id (or any if last_id is None)
    for title, tid, pub, _ts in items:
        if last_id is None or tid > last_id:
            return (title, tid, pub)

    return None

def post_with_curl(link: str):
    cmd = [
        CURL_BIN, "-X", "POST", POST_ENDPOINT,
        "-H", "Content-Type: text/plain",
        "--data", link
    ]
    subprocess.run(cmd, check=True)

def main():
    print("Watcher started. Press Ctrl+C to stop.")
    primed = False

    while True:
        try:
            feed = fetch_feed(RSS_URL)
            last_id = read_last_seen_id()
            result = pick_newest_eligible(feed, last_id)

            if last_id is None and not primed:
                # On very first run set cache to current newest eligible (if any)
                if result:
                    _, tid, _pub = result
                    write_last_seen_id(tid)
                    print(f"Primed cache with id {tid}. POST_ON_FIRST_RUN={POST_ON_FIRST_RUN}")
                    if POST_ON_FIRST_RUN:
                        link = normalize_link(tid)
                        post_with_curl(link)
                        print(f"Posted (first run): {link}")
                else:
                    print("No eligible entries to prime.")
                primed = True

            else:
                if result is None:
                    do = 1 #me soooo lazy
                    #print("No new eligible post.")
                else:
                    title, tid, pub = result
                    if last_id is None or tid > last_id:
                        link = normalize_link(tid)
                        print(f"New post detected (id {tid} > {last_id}): {title}\n -> {link}\nPublished: {pub}")
                        try:
                            post_with_curl(link)
                            print("Posted via curl.")
                            write_last_seen_id(tid)
                        except subprocess.CalledProcessError as e:
                            print(f"curl failed: {e}")
                    else:
                        print("Eligible post found but not newer than cache.")
        except KeyboardInterrupt:
            print("\nStopping watcher.")
            break
        except Exception as e:
            print(f"Error: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
