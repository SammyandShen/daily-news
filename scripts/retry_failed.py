"""
retry_failed.py

检查 docs/news.json 中今天的失败条目，自动重试，最多 2 轮。
由 daily-update.sh 在 generate_with_claude_code.py 之后调用。
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "docs" / "news.json"
MAX_ROUNDS = 2

sys.path.insert(0, str(ROOT / "scripts"))
from generate_with_claude_code import call_claude_code

TODAY = os.environ.get("TODAY", date.today().isoformat())


def get_failed(stories):
    return [(i, s) for i, s in enumerate(stories) if "生成失败" in s.get("headlineCn", "")]


def main():
    if not OUTPUT.exists():
        print("  ⚠️ news.json 不存在，跳过")
        return

    with open(OUTPUT, encoding="utf-8") as f:
        data = json.load(f)

    if TODAY not in data.get("days", {}):
        print(f"  ℹ️ 今天 ({TODAY}) 无数据，跳过")
        return

    stories = data["days"][TODAY]["stories"]
    failed = get_failed(stories)

    if not failed:
        print("  ✅ 今天没有失败条目")
        return

    print(f"  发现 {len(failed)} 条失败，开始重试...")

    for round_num in range(1, MAX_ROUNDS + 1):
        failed = get_failed(stories)
        if not failed:
            break
        print(f"  第 {round_num} 轮重试（{len(failed)} 条）...")
        for idx, s in failed:
            candidate = {
                "title": s["headlineEn"],
                "summary": s["summaryEn"],
                "source": s["sourceName"],
                "url": s["sourceUrl"],
                "category": s["category"],
            }
            print(f"    [{idx}] {candidate['title'][:60]}...")
            content = call_claude_code(candidate)
            if content:
                stories[idx].update({
                    "headlineCn": content.get("headlineCn", ""),
                    "summaryEn": content.get("summaryEn", s["headlineEn"]),
                    "summaryCn": content.get("summaryCn", ""),
                    "excerpt": content.get("excerpt", ""),
                    "vocab": (content.get("vocab") or [])[:5],
                })
                print(f"        ✅ {content.get('headlineCn', '')[:30]}")
                with open(OUTPUT, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                print(f"        ❌ 仍然失败")

    still_failed = get_failed(stories)
    if still_failed:
        print(f"  ⚠️ 仍有 {len(still_failed)} 条未能修复")
    else:
        print(f"  ✅ 全部重试成功")


if __name__ == "__main__":
    main()
