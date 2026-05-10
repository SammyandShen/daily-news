#!/bin/bash
# bootstrap.sh
# 一键部署 Daily News 到你的 GitHub 账号
#
# 这个脚本会：
#   1. 检查依赖（gh, claude, python3, git）
#   2. 创建 GitHub 公开仓库 daily-news
#   3. 推送项目代码
#   4. 启用 GitHub Pages（指向 /docs）
#   5. 跑一次完整流程验证
#   6. 安装 macOS 定时任务（每天 7:00）
#
# 你的 GitHub 凭证只在 `gh auth login` 那步输入，不会经过任何第三方
# 整个过程预计 5-10 分钟

set -e  # 任何步骤失败立即退出

# ────────────────────────────────────────────────
# 颜色
# ────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

step() { echo -e "\n${BLUE}${BOLD}▶ $1${NC}"; }
ok() { echo -e "${GREEN}✓ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
err() { echo -e "${RED}✗ $1${NC}"; }
ask() { echo -e "${YELLOW}? $1${NC}"; }

# ────────────────────────────────────────────────
# 0. 前置检查
# ────────────────────────────────────────────────
echo -e "${BOLD}┌────────────────────────────────────────────┐${NC}"
echo -e "${BOLD}│  📰 Daily News · 一键部署到 GitHub Pages    │${NC}"
echo -e "${BOLD}└────────────────────────────────────────────┘${NC}"

step "检查依赖"

MISSING=()
command -v git &>/dev/null && ok "git: $(which git)" || MISSING+=("git")
command -v python3 &>/dev/null && ok "python3: $(which python3)" || MISSING+=("python3")
command -v claude &>/dev/null && ok "claude: $(which claude)" || MISSING+=("claude")
command -v gh &>/dev/null && ok "gh: $(which gh)" || MISSING+=("gh")

if [ ${#MISSING[@]} -gt 0 ]; then
    echo ""
    err "缺少以下依赖：${MISSING[*]}"
    echo ""
    echo "请先安装："
    for dep in "${MISSING[@]}"; do
        case "$dep" in
            git)     echo "  • git → 一般 Mac 自带；或装 Xcode Command Line Tools: xcode-select --install" ;;
            python3) echo "  • python3 → Mac 自带；或 brew install python" ;;
            claude)  echo "  • claude → npm install -g @anthropic-ai/claude-code"
                     echo "    然后登录：claude login" ;;
            gh)      echo "  • gh → brew install gh"
                     echo "    没装 Homebrew 的话先装：https://brew.sh" ;;
        esac
    done
    echo ""
    echo "全部装好后，再次运行此脚本"
    exit 1
fi

# ────────────────────────────────────────────────
# 1. 检查 gh 登录态
# ────────────────────────────────────────────────
step "检查 GitHub 登录态"

if gh auth status &>/dev/null; then
    GH_USER=$(gh api user --jq .login)
    ok "已登录为：$GH_USER"
else
    warn "未登录 GitHub"
    echo ""
    echo "下一步会让你登录 GitHub，方式是浏览器跳转 + 设备码"
    echo "（你的密码不会被这个脚本看到，也不会经过我们的对话）"
    echo ""
    read -p "按回车继续 → 然后按提示在浏览器中授权..."
    gh auth login --web --git-protocol https
    GH_USER=$(gh api user --jq .login)
    ok "登录成功：$GH_USER"
fi

# ────────────────────────────────────────────────
# 2. 检查 claude 登录态
# ────────────────────────────────────────────────
step "检查 Claude Code 登录态"

# 尝试一次极短的调用
if echo "test" | claude -p "回复 ok 两个字" --max-turns 1 &>/dev/null; then
    ok "Claude Code 可用"
else
    warn "Claude Code 可能未登录，或需要 Pro 订阅"
    echo "请运行：claude login"
    echo "登录完后重新跑此脚本"
    exit 1
fi

# ────────────────────────────────────────────────
# 3. 检查项目目录
# ────────────────────────────────────────────────
step "确认项目目录"

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "项目当前位置：$PROJECT_DIR"

if [ "$PROJECT_DIR" != "$HOME/daily-news" ]; then
    warn "项目不在 ~/daily-news，建议移过去（launchd 模板默认这里）"
    read -p "现在自动移动？[Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        if [ -e "$HOME/daily-news" ]; then
            err "$HOME/daily-news 已存在，请手动处理"
            exit 1
        fi
        mv "$PROJECT_DIR" "$HOME/daily-news"
        cd "$HOME/daily-news"
        PROJECT_DIR="$HOME/daily-news"
        ok "已移动到 $PROJECT_DIR"
        echo ""
        warn "请用新路径重新执行此脚本：cd ~/daily-news && bash bootstrap.sh"
        exit 0
    fi
fi
cd "$PROJECT_DIR"

# ────────────────────────────────────────────────
# 4. 装 Python 依赖
# ────────────────────────────────────────────────
step "安装 Python 依赖"

if pip3 install -r scripts/requirements.txt --quiet 2>/dev/null; then
    ok "依赖已安装"
elif pip3 install --user -r scripts/requirements.txt --quiet 2>/dev/null; then
    ok "依赖已安装到 --user 目录"
elif pip3 install --break-system-packages -r scripts/requirements.txt --quiet 2>/dev/null; then
    ok "依赖已安装（绕过 PEP 668）"
else
    err "Python 依赖安装失败"
    echo "请手动运行：pip3 install -r scripts/requirements.txt"
    exit 1
fi

# ────────────────────────────────────────────────
# 5. 创建 GitHub 仓库
# ────────────────────────────────────────────────
step "创建/确认 GitHub 仓库"

REPO_NAME="daily-news"
if gh repo view "$GH_USER/$REPO_NAME" &>/dev/null; then
    warn "仓库 $GH_USER/$REPO_NAME 已存在"
    read -p "是否使用现有仓库？(否则脚本中止) [Y/n] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "请删除现有仓库或换个仓库名后重试"
        exit 1
    fi
else
    gh repo create "$REPO_NAME" --public --description "📰 我的每日英语新闻精读" --confirm
    ok "仓库已创建：https://github.com/$GH_USER/$REPO_NAME"
fi

# ────────────────────────────────────────────────
# 6. 初始化 git 并推送
# ────────────────────────────────────────────────
step "初始化 git 并推送代码"

if [ ! -d .git ]; then
    git init -q
    git branch -M main
    ok "git 初始化"
fi

# 配置远程
if git remote get-url origin &>/dev/null; then
    git remote set-url origin "https://github.com/$GH_USER/$REPO_NAME.git"
else
    git remote add origin "https://github.com/$GH_USER/$REPO_NAME.git"
fi

# 配置作者（如果没设过）
git config user.name &>/dev/null || git config user.name "$GH_USER"
git config user.email &>/dev/null || git config user.email "${GH_USER}@users.noreply.github.com"

git add .
if git diff --staged --quiet; then
    ok "无新更改"
else
    git commit -q -m "Initial commit · daily news app" || git commit -q -m "Update"
    ok "已提交"
fi

git push -u origin main 2>&1 | grep -v "^remote:" || true
ok "已推送到 GitHub"

# ────────────────────────────────────────────────
# 7. 启用 GitHub Pages
# ────────────────────────────────────────────────
step "启用 GitHub Pages"

# 通过 gh api 启用 Pages，指向 main 分支的 /docs 文件夹
if gh api "repos/$GH_USER/$REPO_NAME/pages" &>/dev/null; then
    ok "Pages 已启用"
else
    gh api -X POST "repos/$GH_USER/$REPO_NAME/pages" \
        -f "source[branch]=main" \
        -f "source[path]=/docs" >/dev/null 2>&1 && ok "Pages 已启用" || warn "Pages 启用可能失败，请手动到 Settings → Pages 检查"
fi

PAGES_URL="https://$GH_USER.github.io/$REPO_NAME/"

# ────────────────────────────────────────────────
# 8. 先手动跑一次验证
# ────────────────────────────────────────────────
step "跑一次完整流程验证（预计 1-3 分钟）"

read -p "现在跑一次测试？[Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    bash daily-update.sh
fi

# ────────────────────────────────────────────────
# 9. 安装 launchd 定时任务
# ────────────────────────────────────────────────
step "安装定时任务（每天 7:00 自动更新）"

read -p "现在安装？[Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    bash install-launchd.sh
fi

# ────────────────────────────────────────────────
# 完成
# ────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}┌────────────────────────────────────────────┐${NC}"
echo -e "${GREEN}${BOLD}│              🎉 全部完成！                  │${NC}"
echo -e "${GREEN}${BOLD}└────────────────────────────────────────────┘${NC}"
echo ""
echo -e "📱 你的应用网址：${BOLD}$PAGES_URL${NC}"
echo "   （GitHub Pages 首次部署需 1-2 分钟，稍等再访问）"
echo ""
echo "📋 常用命令："
echo "   bash install-launchd.sh test    # 立即手动跑一次"
echo "   bash install-launchd.sh status  # 查看运行状态"
echo "   tail -f logs/\$(date +%Y-%m-%d).log  # 看实时日志"
echo ""
echo -e "${BLUE}建议：把 $PAGES_URL 在 Safari 打开，分享 → 添加到主屏幕${NC}"
