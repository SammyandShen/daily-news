#!/bin/bash
# daily-update.sh
# 每天定时跑这一个脚本即可：抓新闻 → 调 Claude Code 生成讲解 → push 到 GitHub
# 所有日志输出到 logs/ 目录，方便排查

set -e  # 任何一步失败立即退出

# ============================================
# 配置区（你可以改）
# ============================================
PROJECT_DIR="$HOME/Documents/CC/daily-news"        # 你把项目放在哪里
CLAUDE_CMD="claude"                    # Claude Code 命令名（默认就是 claude）
PYTHON_CMD="python3"                   # Python 命令名
GIT_BRANCH="main"                      # 推送到哪个分支
LEVEL="B2"                             # 学习者难度

# ============================================
# 不需要改的部分
# ============================================
LOG_DIR="$PROJECT_DIR/logs"
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/$TODAY.log"

mkdir -p "$LOG_DIR"

# 同时输出到日志和终端
exec > >(tee -a "$LOG_FILE") 2>&1

echo "================================================"
echo "🚀 Daily News Update · $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"

cd "$PROJECT_DIR"

# 加载用户的 PATH（launchd 启动时 PATH 极简，需要补全）
# 这样才能找到 claude / python3 / git
set +e
source "$HOME/.zshrc" 2>/dev/null
source "$HOME/.bash_profile" 2>/dev/null
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"

# 检查依赖
echo ""
echo "📋 检查依赖..."
if ! command -v "$CLAUDE_CMD" &> /dev/null; then
    echo "❌ 找不到 claude 命令"
    echo "   请确认 Claude Code 已安装：npm install -g @anthropic-ai/claude-code"
    echo "   并已用 Pro 订阅登录：claude login"
    exit 1
fi
if ! command -v "$PYTHON_CMD" &> /dev/null; then
    echo "❌ 找不到 python3 命令"
    exit 1
fi
echo "✅ claude: $(which $CLAUDE_CMD)"
echo "✅ python: $(which $PYTHON_CMD)"

# Step 1: 抓 RSS，筛选候选新闻
echo ""
echo "📡 Step 1/3: 抓取 RSS 新闻源..."
"$PYTHON_CMD" scripts/fetch_news.py

# Step 2: 调 Claude Code 生成中英双语讲解
echo ""
echo "🤖 Step 2/3: 调用 Claude Code 生成讲解（用你的 Pro 订阅，不消耗 API 额度）..."
"$PYTHON_CMD" scripts/generate_with_claude_code.py

# Step 2.5: 自动重试失败条目（最多 2 轮）
echo ""
echo "🔁 检查并重试失败条目..."
"$PYTHON_CMD" scripts/retry_failed.py

# Step 3: 提交并推送
echo ""
echo "📤 Step 3/3: 推送到 GitHub..."
if [[ -n $(git status --porcelain docs/news.json) ]]; then
    git add docs/news.json
    git commit -m "📰 Update news for $TODAY"
    git push origin "$GIT_BRANCH"
    echo "✅ 推送成功，GitHub Pages 将在 1-2 分钟后更新"
else
    echo "ℹ️ news.json 没有变化，跳过提交"
fi

echo ""
echo "🎉 完成！日志保存在 $LOG_FILE"

# 顺手发个 macOS 通知（可选）
osascript -e "display notification \"今日 5 条资讯已更新\" with title \"📰 Daily News\" sound name \"Glass\"" 2>/dev/null || true
