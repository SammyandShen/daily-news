"""
fetch_news.py
从主流英语媒体的免费 RSS 源抓取当日新闻，
按"科技 / 商业 / 经济"主题打分排序，挑出 STORIES_PER_DAY 条候选写入临时文件。
"""

import feedparser
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 免费 RSS 源（无需 API Key、无需登录）
RSS_SOURCES = [
    # 科技
    {"name": "TechCrunch",      "url": "https://techcrunch.com/feed/",                              "cat_hint": "tech"},
    {"name": "The Verge",       "url": "https://www.theverge.com/rss/index.xml",                    "cat_hint": "tech"},
    {"name": "Ars Technica",    "url": "https://feeds.arstechnica.com/arstechnica/index",           "cat_hint": "tech"},
    {"name": "Wired",           "url": "https://www.wired.com/feed/rss",                            "cat_hint": "tech"},
    # 商业 / 经济
    {"name": "Reuters Business","url": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best", "cat_hint": "biz"},
    {"name": "BBC Business",    "url": "https://feeds.bbci.co.uk/news/business/rss.xml",            "cat_hint": "biz"},
    {"name": "CNBC Top News",   "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",     "cat_hint": "biz"},
    {"name": "MarketWatch",     "url": "https://feeds.marketwatch.com/marketwatch/topstories/",     "cat_hint": "econ"},
    # 通用财经科技
    {"name": "Financial Times", "url": "https://www.ft.com/rss/home",                               "cat_hint": "biz"},
]

# 关键词权重：命中越多，故事越值得选
KEYWORDS = {
    "tech": [
        "AI", "artificial intelligence", "OpenAI", "Anthropic", "Google", "Meta", "Apple",
        "Microsoft", "Nvidia", "chip", "semiconductor", "data center", "cloud", "model",
        "robot", "autonomous", "quantum", "cybersecurity", "breach", "startup",
    ],
    "biz": [
        "earnings", "IPO", "acquisition", "merger", "valuation", "funding", "revenue",
        "profit", "layoff", "CEO", "stock", "shareholder", "deal", "partnership",
    ],
    "econ": [
        "Fed", "Federal Reserve", "rate", "inflation", "GDP", "jobless", "unemployment",
        "tariff", "trade", "recession", "stagflation", "central bank", "treasury",
        "oil", "Brent", "crude", "yield",
    ],
}

# 排除噪音
NEGATIVE_KEYWORDS = [
    "horoscope", "celebrity", "kardashian", "review of", "trailer",
    "video game release", "spoiler",
]

OUTPUT = Path(__file__).parent.parent / "docs" / "_candidates.json"
NEWS_JSON = Path(__file__).parent.parent / "docs" / "news.json"
LOOKBACK_HOURS = 36  # 只看过去 36 小时的新闻
DEDUP_DAYS = 7       # 过去 N 天选过的故事不再选
STORIES_PER_DAY = 3  # 每天几条故事：tech 1 + biz 1 + econ 1


def normalize_title(t: str) -> str:
    """归一化标题用于精确去重：小写 + 折叠所有非字母数字为空格"""
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def collect_recent_stories():
    """从 news.json 收集过去 DEDUP_DAYS 天的 URL 和归一化标题"""
    if not NEWS_JSON.exists():
        return set(), set()
    try:
        with open(NEWS_JSON, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set(), set()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=DEDUP_DAYS)).strftime("%Y-%m-%d")
    urls, titles = set(), set()
    for date_str, day_data in data.get("days", {}).items():
        if date_str < cutoff_date:
            continue
        for story in day_data.get("stories", []):
            url = (story.get("sourceUrl") or "").strip()
            title = (story.get("headlineEn") or "").strip()
            if url:
                urls.add(url)
            if title:
                titles.add(normalize_title(title))
    return urls, titles


def score_entry(title: str, summary: str) -> dict:
    """给一条新闻按主题打分，返回 {category: score}"""
    text = (title + " " + summary).lower()
    scores = {}
    for cat, kws in KEYWORDS.items():
        scores[cat] = sum(1 for kw in kws if kw.lower() in text)
    # 减去负面关键词
    if any(neg in text for neg in NEGATIVE_KEYWORDS):
        for cat in scores:
            scores[cat] -= 5
    return scores


def normalize_date(entry) -> datetime | None:
    """解析 RSS 条目的发布时间，返回带时区的 datetime"""
    for k in ("published_parsed", "updated_parsed"):
        t = entry.get(k)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def clean_summary(s: str) -> str:
    """剥掉 HTML 标签，限制长度"""
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:500]


def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)
    candidates = []

    recent_urls, recent_titles = collect_recent_stories()
    print(f"📚 过去 {DEDUP_DAYS} 天已用过的故事：URL {len(recent_urls)} 条 · 标题 {len(recent_titles)} 条")

    skipped_dup = 0
    for src in RSS_SOURCES:
        print(f"Fetching {src['name']}...")
        try:
            feed = feedparser.parse(src["url"])
        except Exception as e:
            print(f"  ⚠️ Failed: {e}")
            continue

        for entry in feed.entries[:30]:  # 每源最多看 30 条
            pub = normalize_date(entry)
            if pub and pub < cutoff:
                continue
            title = entry.get("title", "").strip()
            summary = clean_summary(entry.get("summary", ""))
            if not title:
                continue

            # 去重：URL 完全相同 或 归一化标题相同
            url = (entry.get("link") or "").strip()
            if url and url in recent_urls:
                skipped_dup += 1
                continue
            if normalize_title(title) in recent_titles:
                skipped_dup += 1
                continue

            scores = score_entry(title, summary)
            best_cat = max(scores, key=scores.get)
            best_score = scores[best_cat]
            if best_score < 1:
                continue

            candidates.append({
                "title": title,
                "summary": summary,
                "url": entry.get("link", ""),
                "source": src["name"],
                "published": pub.isoformat() if pub else None,
                "category": best_cat,
                "score": best_score,
            })

    # 在每个分类内按分数排序，挑出 top 候选
    by_cat = {"tech": [], "biz": [], "econ": []}
    for c in sorted(candidates, key=lambda x: -x["score"]):
        if len(by_cat[c["category"]]) < 3:  # 每类最多 3 条候选
            by_cat[c["category"]].append(c)

    # 拼成最终 STORIES_PER_DAY 条：每类各 1 条，保持多样性
    final = (by_cat["tech"][:1] + by_cat["biz"][:1] + by_cat["econ"][:1])
    if len(final) < STORIES_PER_DAY:
        # 某个分类候选不够 → 用剩余的按分数填
        leftover = sorted(candidates, key=lambda x: -x["score"])
        for c in leftover:
            if c not in final and len(final) < STORIES_PER_DAY:
                final.append(c)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # 用本地日期（daily-update.sh 在中国时间 07:00 触发；用 UTC 会滞后一天）
    local_date = datetime.now().strftime("%Y-%m-%d")
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"date": local_date, "candidates": final}, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved {len(final)} candidates as {local_date} → {OUTPUT} (跳过重复 {skipped_dup} 条)")


if __name__ == "__main__":
    main()
