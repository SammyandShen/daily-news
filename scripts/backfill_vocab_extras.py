"""
backfill_vocab_extras.py

给历史 news.json 中所有词汇补上 etymology / morphology / mnemonic 三个字段。
工作流程：
  1. 读 docs/news.json
  2. 遍历每天每个 story 的 vocab，挑出还没有这三个字段（或为空）的词汇
  3. 一次性把同一个 story 内缺字段的词汇打包发给 claude -p，节省调用次数
  4. 写回 docs/news.json（增量保存，断点续传安全）

用法：
  python3 scripts/backfill_vocab_extras.py            # 跑全部
  LIMIT=10 python3 scripts/backfill_vocab_extras.py   # 只处理 10 个词汇（试运行）
  DATE=2026-05-20 python3 scripts/backfill_vocab_extras.py  # 只处理某一天
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from json_repair import repair_json
except ImportError:
    repair_json = None

ROOT = Path(__file__).parent.parent
NEWS_FILE = ROOT / "docs" / "news.json"

LIMIT = int(os.environ.get("LIMIT", "0"))  # 0 = 不限
TARGET_DATE = os.environ.get("DATE", "")

ENV_FOR_CLAUDE = {**os.environ}
ENV_FOR_CLAUDE.pop("ANTHROPIC_API_KEY", None)

PROMPT = """你是一位专业英语词汇学家。下面给你一组英语单词或短语，请为每一个补充三段记忆辅助信息。

输入是一个 JSON 数组，每项包含 word（词）和 meaning（中文释义供你参考）：
{items_json}

请输出一个 JSON 数组，长度与输入完全相同，按相同顺序返回。每项格式：

{{
  "word": "原词，与输入一致",
  "etymology": "词源 30-80 字：来源语言（拉丁/希腊/古英语/法语等）+ 原义 + 语义演变。短语类无独立词源可写『复合词/短语，无独立词源』",
  "morphology": "构词拆解 30-80 字：前缀 + 词根 + 后缀分解，附 2-3 个同根/同前缀英语词帮助横向扩展。不可拆解的简单词写出常见派生形式",
  "mnemonic": "记忆窍门 30-80 字：具体画面/类比/谐音/易混词对比，要鲜活、能形成画面"
}}

严格要求：
1. 只输出合法 JSON 数组，不要 markdown 标记、不要说明文字
2. 三个字段都必填，不能为空字符串或 null
3. 中文里不要使用直引号 " "，改用《》或「」
4. 数组长度和输入完全一致，顺序一致"""


def call_claude(items: list) -> list | None:
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    prompt = PROMPT.format(items_json=items_json)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            env=ENV_FOR_CLAUDE,
            capture_output=True,
            text=True,
            timeout=180,
            check=True,
        )
        outer = json.loads(result.stdout)
        text = outer.get("result", "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if repair_json:
                fixed = repair_json(text, return_objects=True)
                if isinstance(fixed, list):
                    return fixed
            raise
    except subprocess.TimeoutExpired:
        print("    ⏱ Timeout")
    except subprocess.CalledProcessError as e:
        print(f"    ❌ claude exit {e.returncode}: {e.stderr[:200]}")
    except Exception as e:
        print(f"    ❌ Error: {e}")
    return None


def needs_backfill(v: dict) -> bool:
    return not (v.get("etymology") and v.get("morphology") and v.get("mnemonic"))


def main():
    if not NEWS_FILE.exists():
        print("❌ news.json not found")
        sys.exit(1)

    with open(NEWS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    days = data.get("days", {})
    if TARGET_DATE:
        if TARGET_DATE not in days:
            print(f"❌ {TARGET_DATE} not in news.json")
            sys.exit(1)
        date_keys = [TARGET_DATE]
    else:
        # 按日期倒序处理（先补最近的）
        date_keys = sorted(days.keys(), reverse=True)

    processed_words = 0
    total_to_process = sum(
        sum(1 for s in days[d].get("stories", []) for v in s.get("vocab", []) if needs_backfill(v))
        for d in date_keys
    )
    print(f"📊 共发现 {total_to_process} 个待回填词汇，分布在 {len(date_keys)} 天")
    if LIMIT:
        print(f"⚠️ LIMIT={LIMIT}，本次最多处理 {LIMIT} 个词")

    for date in date_keys:
        stories = days[date].get("stories", [])
        for s_idx, story in enumerate(stories):
            vocab_list = story.get("vocab", [])
            # 找出需要补的下标
            pending_idx = [i for i, v in enumerate(vocab_list) if needs_backfill(v)]
            if not pending_idx:
                continue

            if LIMIT and processed_words >= LIMIT:
                print(f"🛑 达到 LIMIT={LIMIT}，停止")
                break

            # 截到 LIMIT
            if LIMIT:
                remaining = LIMIT - processed_words
                pending_idx = pending_idx[:remaining]

            items = [
                {"word": vocab_list[i]["word"], "meaning": vocab_list[i].get("meaning", "")}
                for i in pending_idx
            ]
            words_preview = ", ".join(v["word"] for v in items[:3]) + (" …" if len(items) > 3 else "")
            print(f"\n📅 {date} · story {s_idx + 1} · 补 {len(items)} 个词：{words_preview}")

            result = call_claude(items)
            if not result or not isinstance(result, list):
                print(f"    ⚠️ 调用失败，跳过这个 story")
                continue

            # 按顺序合并回去
            if len(result) != len(items):
                print(f"    ⚠️ 返回 {len(result)} 项 ≠ 输入 {len(items)} 项，按位置尽量合并")
            for j, vi in enumerate(pending_idx):
                if j >= len(result):
                    break
                r = result[j]
                if not isinstance(r, dict):
                    continue
                vocab_list[vi]["etymology"] = r.get("etymology", "") or vocab_list[vi].get("etymology", "")
                vocab_list[vi]["morphology"] = r.get("morphology", "") or vocab_list[vi].get("morphology", "")
                vocab_list[vi]["mnemonic"] = r.get("mnemonic", "") or vocab_list[vi].get("mnemonic", "")

            # 每个 story 处理完就写回，断点续传安全
            with open(NEWS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"    ✅ 已保存")
            processed_words += len(pending_idx)

        if LIMIT and processed_words >= LIMIT:
            break

    print(f"\n🎉 完成！本次回填了 {processed_words} 个词汇")


if __name__ == "__main__":
    main()
