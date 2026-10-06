#!/usr/bin/env python3
"""海外ニュース朝刊ダイジェスト

feeds.yaml の海外無料RSSを取得し、直近の記事をセクション別にまとめた
HTML(docs/index.html と docs/archive/YYYY-MM-DD.html)を生成する。

任意の環境変数:
  GEMINI_API_KEY   … 設定すると見出しの日本語訳とセクション要約を付ける(Google AI Studio の無料枠)
  GEMINI_MODEL     … 既定 gemini-3.5-flash-lite
  SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / MAIL_TO … 設定するとHTMLメールで送信
  DISCORD_WEBHOOK / SLACK_WEBHOOK … 設定するとページURLを通知
  PAGE_URL         … 通知に載せる公開ページURL(GitHub Pages など)
"""
import html
import json
import os
import re
import smtplib
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

import feedparser
import requests
import yaml

JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (compatible; KaigaiNewsDigest/1.0; personal RSS reader)"
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs"


def load_config():
    return yaml.safe_load((ROOT / "feeds.yaml").read_text(encoding="utf-8"))


def clean(text, limit=220):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def entry_time(e):
    for key in ("published_parsed", "updated_parsed"):
        t = e.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch(feed, since):
    try:
        r = requests.get(feed["url"], headers={"User-Agent": UA}, timeout=25)
        r.raise_for_status()
        parsed = feedparser.parse(r.content)
    except Exception as ex:  # 1ソースの失敗で全体を止めない
        return feed, [], f"{type(ex).__name__}: {ex}"
    items = []
    kws = [k.lower() for k in feed.get("keywords", [])]
    for e in parsed.entries[:120]:
        t = entry_time(e)
        if t is None or t < since:
            continue
        title = clean(e.get("title"), 200)
        summary = clean(e.get("summary") or e.get("description"))
        if not title:
            continue
        if kws and not any(k in (title + " " + summary).lower() for k in kws):
            continue
        items.append({"title": title, "summary": summary, "link": e.get("link", ""),
                      "time": t, "source": feed["name"], "weight": feed.get("weight", 1)})
    items.sort(key=lambda x: x["time"], reverse=True)
    return feed, items[: feed.get("max", 5)], None


def score(item, priorities):
    s = item["weight"] * 10
    text = " " + item["title"].lower() + " "
    for p in priorities:
        if any(w in text for w in p["words"]):
            s += p["boost"] * 5
    age_h = (datetime.now(timezone.utc) - item["time"]).total_seconds() / 3600
    return s - age_h * 0.2


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())[:60]


# ---------- 任意: Gemini 無料枠で日本語化 ----------
def gemini_enrich(sections):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return
    model = os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash-lite"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    for sec in sections:
        if not sec["items"]:
            continue
        lines = "\n".join(f"{i}. [{it['source']}] {it['title']} — {it['summary'][:160]}"
                          for i, it in enumerate(sec["items"]))
        prompt = (
            "以下は海外ニュースの見出し一覧です。JSONのみで返してください。\n"
            '形式: {"summary": "このセクションの要点を日本語で3行以内(箇条書き・各行「・」始まり)",'
            ' "titles": ["各見出しの自然な日本語訳(番号順・同じ件数)"]}\n'
            "事実は見出しと抜粋にある内容だけを使い、推測を加えないこと。\n\n" + lines)
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
        for attempt in range(3):
            try:
                r = requests.post(url, params={"key": key}, json=body, timeout=60)
                if r.status_code == 429:
                    time.sleep(20)
                    continue
                r.raise_for_status()
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                data = json.loads(txt)
                sec["ai_summary"] = data.get("summary", "")
                for it, ja in zip(sec["items"], data.get("titles", [])):
                    it["title_ja"] = ja
                break
            except Exception as ex:
                print(f"[gemini] {sec['title']}: {ex}", file=sys.stderr)
                time.sleep(5)
        time.sleep(4)  # 無料枠のレート制限対策


# ---------- HTML ----------
CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif;
max-width:860px;margin:0 auto;padding:16px;color:#1d1d1f;background:#fafaf7;line-height:1.55}
h1{font-size:1.45rem;margin:.2em 0}.meta{color:#666;font-size:.85rem}
nav{position:sticky;top:0;background:#fafaf7;padding:6px 0;border-bottom:1px solid #ddd;font-size:.85rem}
nav a{margin-right:10px;text-decoration:none;color:#0b57d0;white-space:nowrap}
h2{font-size:1.15rem;margin-top:1.6em;border-left:5px solid #0b57d0;padding-left:8px}
.ai{background:#eef3fd;border-radius:8px;padding:8px 12px;white-space:pre-line;font-size:.92rem}
.item{padding:9px 0;border-bottom:1px solid #e6e6e6}
.item a{font-weight:600;color:#111;text-decoration:none}.item a:hover{text-decoration:underline}
.ja{display:block;color:#1967d2;font-size:.95rem}.src{color:#888;font-size:.78rem}
.sum{color:#444;font-size:.86rem;margin-top:2px}.empty{color:#999;font-size:.9rem}
.err{color:#a33;font-size:.8rem}
@media (prefers-color-scheme:dark){body,nav{background:#141414;color:#e8e8e8}.item a{color:#f2f2f2}
.sum{color:#bbb}.ai{background:#1d2738}.item{border-color:#333}.ja{color:#8ab4f8}}
"""


def render(sections, errors, now_jst, window_h):
    out = [f"<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>海外ニュース朝刊 {now_jst:%Y-%m-%d}</title><style>{CSS}</style></head><body>",
           f"<h1>🌍 海外ニュース朝刊 {now_jst:%Y年%m月%d日(%a)}</h1>",
           f"<div class='meta'>生成 {now_jst:%H:%M} JST/直近{window_h}時間/"
           f"{sum(len(s['items']) for s in sections)}件</div><nav>"]
    out += [f"<a href='#{s['id']}'>{html.escape(s['title'])}</a>" for s in sections]
    out.append("</nav>")
    for s in sections:
        out.append(f"<h2 id='{s['id']}'>{html.escape(s['title'])}</h2>")
        if s.get("ai_summary"):
            out.append(f"<div class='ai'>{html.escape(s['ai_summary'])}</div>")
        if not s["items"]:
            out.append("<div class='empty'>新着なし</div>")
        for it in s["items"]:
            t = it["time"].astimezone(JST)
            ja = f"<span class='ja'>{html.escape(it['title_ja'])}</span>" if it.get("title_ja") else ""
            out.append(
                f"<div class='item'>{ja}<a href='{html.escape(it['link'])}' target='_blank' rel='noopener'>"
                f"{html.escape(it['title'])}</a><div class='src'>{html.escape(it['source'])}・{t:%m/%d %H:%M}</div>"
                f"<div class='sum'>{html.escape(it['summary'])}</div></div>")
    if errors:
        out.append("<h2>⚠ 取得できなかった情報源</h2>")
        out += [f"<div class='err'>{html.escape(n)}: {html.escape(e)}</div>" for n, e in errors]
    out.append("</body></html>")
    return "\n".join(out).replace("(Mon)", "(月)").replace("(Tue)", "(火)").replace("(Wed)", "(水)") \
        .replace("(Thu)", "(木)").replace("(Fri)", "(金)").replace("(Sat)", "(土)").replace("(Sun)", "(日)")


def notify(page_html, now_jst):
    subject = f"海外ニュース朝刊 {now_jst:%Y-%m-%d}"
    if os.environ.get("SMTP_USER") and os.environ.get("MAIL_TO"):
        msg = MIMEText(page_html, "html", "utf-8")
        msg["Subject"], msg["From"], msg["To"] = subject, os.environ["SMTP_USER"], os.environ["MAIL_TO"]
        with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", 587))) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
        print("mail sent")
    page = os.environ.get("PAGE_URL", "")
    text = f"📰 {subject} ができました {page}".strip()
    if os.environ.get("DISCORD_WEBHOOK"):
        requests.post(os.environ["DISCORD_WEBHOOK"], json={"content": text}, timeout=20)
    if os.environ.get("SLACK_WEBHOOK"):
        requests.post(os.environ["SLACK_WEBHOOK"], json={"text": text}, timeout=20)


def main():
    cfg = load_config()
    now = datetime.now(timezone.utc)
    now_jst = now.astimezone(JST)
    window_h = cfg.get("monday_window_hours", 74) if now_jst.weekday() == 0 else cfg.get("window_hours", 26)
    since = now - timedelta(hours=window_h)

    jobs = [(sec, f) for sec in cfg["sections"] for f in sec["feeds"]]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda j: (j[0]["id"],) + fetch(j[1], since), jobs))

    errors, seen, sections = [], set(), []
    for sec in cfg["sections"]:
        items = []
        for sid, feed, its, err in results:
            if sid != sec["id"]:
                continue
            if err:
                errors.append((feed["name"], err))
            for it in its:
                k = norm_title(it["title"])
                if k not in seen:
                    seen.add(k)
                    items.append(it)
        items.sort(key=lambda x: score(x, cfg.get("priority_keywords", [])), reverse=True)
        sections.append({"id": sec["id"], "title": sec["title"], "items": items})

    gemini_enrich(sections)
    page = render(sections, errors, now_jst, window_h)
    (OUT / "archive").mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    (OUT / "archive" / f"{now_jst:%Y-%m-%d}.html").write_text(page, encoding="utf-8")
    print(f"items={sum(len(s['items']) for s in sections)} errors={len(errors)}")
    for n, e in errors:
        print(f"  ! {n}: {e}")
    if "--no-notify" not in sys.argv:
        notify(page, now_jst)


if __name__ == "__main__":
    main()
