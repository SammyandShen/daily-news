"""
generate_with_claude_code.py

调用本机的 Claude Code (claude -p) 生成新闻讲解。
关键点：claude -p "提示词" 是 headless 模式，会用你的 Pro 订阅而不是 API key。

工作流程：
  1. 读 docs/_candidates.json（fetch_news.py 已经抓好的 5 条候选新闻）
  2. 对每条新闻，把"原始标题+摘要"作为提示词，让 Claude Code 生成结构化 JSON
  3. 把所有结果合并到 docs/news.json
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from json_repair import repair_json
except ImportError:
    repair_json = None

ROOT = Path(__file__).parent.parent
CANDIDATES = ROOT / "docs" / "_candidates.json"
OUTPUT = ROOT / "docs" / "news.json"
MAX_DAYS = 30

LEVEL = os.environ.get("LEVEL", "B2")

# 重要：禁用 ANTHROPIC_API_KEY，强制走 Pro 订阅
# 如果你 shell 里设置了这个变量，会让 Claude Code 走 API 计费
ENV_FOR_CLAUDE = {**os.environ}
ENV_FOR_CLAUDE.pop("ANTHROPIC_API_KEY", None)

PROMPT_TEMPLATE = """你是一位专业的英语教学助理，正在为一位 {level} 级别的中国学习者制作每日英语新闻精读材料。学习者关注科技、商业和经济领域。

请基于下面这条新闻，生成结构化输出。**只输出一个合法的 JSON 对象，不要任何说明文字、不要 markdown 代码块标记、不要 ```json 包裹**。

新闻标题: {title}
新闻摘要: {summary}
来源: {source}
分类: {category} (tech=科技, biz=商业, econ=经济)

严格按以下 JSON 结构输出：

{{
  "headlineEn": "改写后的精炼英文标题（如果原标题已经精炼可保留），不超过 18 词",
  "headlineCn": "对应的中文标题，简洁地道，不超过 30 字",
  "summaryEn": "用 60-90 词扩写的英文摘要，{level} 难度，包含关键事实和'为何重要'",
  "summaryCn": "对应的中文摘要，70-130 字，自然流畅",
  "excerpt": "约 30-60 词的英文摘录，可基于原始 summary 改写以方便阅读，但语气要像真实新闻片段",
  "vocab": [
    {{
      "word": "词或短语",
      "pos": "词性，如 v. / n. / adj. / phrase / phrasal v.",
      "meaning": "中文释义 + 简短的用法说明（说清楚为什么这个词比同义词更值得学，例如它的语域、隐喻、搭配习惯）",
      "etymology": "词源 30-80 字：来源语言（拉丁/希腊/古英语/法语等）+ 原义 + 语义演变路径。短语类词条若无明显词源可写『短语/复合词，无独立词源』",
      "morphology": "构词拆解 30-80 字：前缀 + 词根 + 后缀分解，附 2-3 个同词根/同前缀的英语词（帮助横向扩展）。若是不可拆解的简单词，写出常见派生词（如名词→动词→形容词形式）",
      "mnemonic": "记忆窍门 30-80 字：用具体画面、类比、谐音、易混词对比等帮助快速记忆。要够鲜活、够具体，能在脑中形成画面",
      "exampleEn": "一句使用该词的英文例句，主题贴近商业/科技/经济，{level} 难度",
      "exampleCn": "对应的中文翻译"
    }}
  ]
}}

要求：
1. vocab 数组**正好 5 项**
2. 选词标准：财经/科技英语里高频但教科书少教的搭配、商业语境的隐喻、容易混用的近义词差异。避免超基础词（如 important / good）和过于罕见的词。
3. 例句要紧扣商业/科技/经济语境
4. 中文释义要点出「为什么这个词值得学」
5. **etymology / morphology / mnemonic 三字段必须填，不能省略，不能写成 null 或空字符串**。即使是简单常见词也要努力挖掘记忆点
6. 严格输出合法 JSON，不要任何额外内容
7. 中文内容里不要使用直引号 " "，改用书名号《》或角引号「」，否则会破坏 JSON 格式"""


def collect_used_words() -> set:
    """从现有 news.json 收集所有已选过的词汇（小写归一）"""
    if not OUTPUT.exists():
        return set()
    try:
        with open(OUTPUT, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set()
    used = set()
    for day_data in data.get("days", {}).values():
        for story in day_data.get("stories", []):
            for v in story.get("vocab", []) or []:
                w = (v.get("word") or "").strip().lower()
                # 跳过失败兜底占位符
                if w and "生成失败" not in w and not w.startswith("（"):
                    used.add(w)
    return used


def call_claude_code(candidate: dict, retries: int = 2, exclude_words: set | None = None) -> dict | None:
    """调用 claude -p 生成内容。失败时重试 1 次。exclude_words 是已选过、需避免重复的词汇集合。"""
    prompt = PROMPT_TEMPLATE.format(
        level=LEVEL,
        title=candidate["title"],
        summary=candidate["summary"],
        source=candidate["source"],
        category=candidate["category"],
    )
    if exclude_words:
        # 按字母排序便于 Claude 扫描；过多时只保留最近 500 个
        excl = sorted(exclude_words)[:500]
        prompt += (
            "\n\n**避免与历史重复**：以下词汇/短语在过往新闻中已选过，请优先挑选不在此列表中的新词。"
            "只有当这条新闻的核心概念恰好就是其中某个词时，才可保留该词。\n"
            + ", ".join(excl)
        )

    for attempt in range(retries):
        try:
            # claude -p 是 headless 模式，--output-format json 让它返回结构化输出
            # 但我们要的是 Claude 生成内容里的 JSON，所以用纯文本模式更直接
            result = subprocess.run(
                ["claude", "-p", prompt, "--output-format", "json"],
                env=ENV_FOR_CLAUDE,
                capture_output=True,
                text=True,
                timeout=240,  # 4 分钟超时（带历史词汇排除清单后 prompt 略长，留足余量）
                check=True,
            )
            # --output-format json 把 Claude 的回复放在 result 字段，已正确转义
            outer = json.loads(result.stdout)
            text = outer.get("result", "").strip()

            # 剥掉可能的 markdown 代码块标记
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
            text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)

            # 找到第一个 { 到最后一个 } 之间的内容
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                if repair_json:
                    fixed = repair_json(text, return_objects=True)
                    if isinstance(fixed, dict):
                        return fixed
                raise
        except subprocess.TimeoutExpired:
            print(f"    ⏱ Timeout (attempt {attempt + 1})")
        except subprocess.CalledProcessError as e:
            print(f"    ❌ claude exit code {e.returncode}: {e.stderr[:200]}")
        except json.JSONDecodeError as e:
            print(f"    ⚠️ JSON parse failed (attempt {attempt + 1}): {e}")
            print(f"       Got: {text[:200]}...")
        except Exception as e:
            print(f"    ❌ Unexpected error: {e}")

        if attempt < retries - 1:
            print(f"    🔁 Retrying...")

    return None


def template_fallback(candidate: dict) -> dict:
    """Claude Code 调用失败时的兜底"""
    return {
        "headlineEn": candidate["title"],
        "headlineCn": "（生成失败 · 见下方摘要）",
        "summaryEn": candidate["summary"][:400] or candidate["title"],
        "summaryCn": "（自动生成失败 · 请查看日志，或手动重跑 daily-update.sh）",
        "excerpt": candidate["summary"][:300] or candidate["title"],
        "vocab": [
            {
                "word": "（自动生成失败）",
                "pos": "—",
                "meaning": "Claude Code 调用失败。请检查 logs/ 目录下的日志，确认 claude 命令可用且已登录 Pro 订阅。",
                "exampleEn": "Run `claude login` and `daily-update.sh` again to retry.",
                "exampleCn": "运行 claude login 重新登录后再次执行 daily-update.sh。",
            }
        ],
    }


def build_story(candidate: dict, idx: int, date_str: str, exclude_words: set | None = None) -> dict:
    print(f"  [{idx + 1}/5] {candidate['title'][:60]}...")
    content = call_claude_code(candidate, exclude_words=exclude_words)
    if content is None:
        print(f"        ⚠️ 生成失败，使用兜底内容")
        content = template_fallback(candidate)
    else:
        print(f"        ✅ 生成成功")
    # 确保每条 vocab 都有完整字段（兼容旧的生成结果）
    vocab_list = (content.get("vocab") or [])[:5]
    for v in vocab_list:
        v.setdefault("etymology", "")
        v.setdefault("morphology", "")
        v.setdefault("mnemonic", "")
    return {
        "id": f"{date_str.replace('-', '')}-{idx + 1}",
        "category": candidate["category"],
        "sourceName": candidate["source"],
        "sourceUrl": candidate["url"],
        "headlineEn": content.get("headlineEn", candidate["title"]),
        "headlineCn": content.get("headlineCn", ""),
        "summaryEn": content.get("summaryEn", ""),
        "summaryCn": content.get("summaryCn", ""),
        "excerpt": content.get("excerpt", ""),
        "vocab": vocab_list,
    }


def load_existing() -> dict:
    if OUTPUT.exists():
        try:
            with open(OUTPUT, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"days": {}}


def prune_old(days: dict) -> dict:
    sorted_keys = sorted(days.keys(), reverse=True)
    return {k: days[k] for k in sorted_keys[:MAX_DAYS]}


def label_for(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return f"{d.month}月{d.day}日 ({weekdays[d.weekday()]})"


def main():
    if not CANDIDATES.exists():
        print("❌ _candidates.json not found. Run fetch_news.py first.")
        sys.exit(1)

    with open(CANDIDATES, encoding="utf-8") as f:
        bundle = json.load(f)

    date_str = bundle["date"]
    candidates = bundle["candidates"]
    print(f"📰 Generating content for {date_str} ({len(candidates)} stories)")

    if not candidates:
        print("⚠️ No candidates today, skipping")
        return

    # 收集历史已选词汇，并在生成过程中逐条累加，避免同一天内 5 条故事互相重复
    used_words = collect_used_words()
    print(f"📚 历史已选词汇 {len(used_words)} 个，将作为排除清单")
    stories = []
    for i, c in enumerate(candidates):
        story = build_story(c, i, date_str, exclude_words=used_words)
        stories.append(story)
        # 把这条故事新选的词追加进排除集，给下一条用
        for v in story.get("vocab", []):
            w = (v.get("word") or "").strip().lower()
            if w and "生成失败" not in w and not w.startswith("（"):
                used_words.add(w)

    existing = load_existing()
    days = existing.get("days", {})
    days[date_str] = {"label": label_for(date_str), "stories": stories}
    days = prune_old(days)

    final = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "level": LEVEL,
        "days": days,
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Wrote {len(stories)} stories for {date_str}")
    print(f"📚 Total days kept: {len(days)}")

    # 清理临时文件
    CANDIDATES.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
