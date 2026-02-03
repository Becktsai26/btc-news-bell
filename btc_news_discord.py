import os
from pathlib import Path
import requests
import feedparser
from email.utils import parsedate_to_datetime
from datetime import datetime
from google import genai
from dotenv import load_dotenv

# ====== Config ======
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))
RSS_URL = os.environ.get(
    "NEWS_RSS_URL",
    "https://news.google.com/rss/search?q=site:blocktempo.com+(BTC+OR+%E6%AF%94%E7%89%B9%E5%B9%A3)+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not DISCORD_WEBHOOK_URL:
    raise RuntimeError("Missing DISCORD_WEBHOOK_URL. Check LineNotify/.env file.")
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY. Check LineNotify/.env file.")

# ====== Helpers ======
def chunk_text(text, max_len=1800):
    chunks = []
    buf = []
    total = 0
    for line in text.splitlines():
        if total + len(line) + 1 > max_len and buf:
            chunks.append("\n".join(buf))
            buf = [line]
            total = len(line) + 1
        else:
            buf.append(line)
            total += len(line) + 1
    if buf:
        chunks.append("\n".join(buf))
    return chunks

def fetch_today_items():
    feed = feedparser.parse(RSS_URL)
    tz = datetime.now().astimezone().tzinfo
    today = datetime.now(tz).date()

    items = []
    for e in feed.entries:
        published = e.get("published") or e.get("updated")
        dt = parsedate_to_datetime(published).astimezone(tz) if published else None
        if dt and dt.date() != today:
            continue

        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        source = ""
        if isinstance(e.get("source"), dict):
            source = e["source"].get("title") or ""
        items.append((title, source, link))

    return items[:30]

def summarize_with_gemini(items):
    if not items:
        return "今日沒有抓到 BTC 相關新聞。"

    lines = [f"- {t} | {s} | {l}" for t, s, l in items]

    prompt = f"""你是新聞彙整助手。請用繁體中文整理「今日 BTC 相關新聞」。
請遵守：
1) 先給一句總結（不超過 20 字）
2) 最多 8 則重點，每行格式：標題 — 一句話摘要 — 來源 — 連結
3) 全文不超過 1000 字

以下是今日新聞清單（標題 | 來源 | 連結）：
{chr(10).join(lines)}
"""

    client = genai.Client()
    last_err = None
    for _ in range(3):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            return resp.text.strip()
        except Exception as e:
            last_err = e
    raise last_err

def discord_send(text):
    for chunk in chunk_text(text):
        payload = {"content": chunk}
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=30)
        r.raise_for_status()

def main():
    items = fetch_today_items()
    summary = summarize_with_gemini(items)
    discord_send(summary)

if __name__ == "__main__":
    main()
