#!/bin/bash
# install-launchd.sh
# 一键安装 macOS 定时任务（每天 7:00 自动更新新闻）
#
# 用法：
#   bash install-launchd.sh        # 安装
#   bash install-launchd.sh test   # 立即手动跑一次（不安装定时）
#   bash install-launchd.sh status # 查看是否在运行
#   bash install-launchd.sh remove # 卸载

set -e

USERNAME=$(whoami)
PROJECT_DIR="$HOME/daily-news"
PLIST_NAME="com.user.daily-news"
PLIST_RETRY_NAME="com.user.daily-news-retry"
PLIST_SOURCE="$PROJECT_DIR/launchd/$PLIST_NAME.plist"
PLIST_RETRY_SOURCE="$PROJECT_DIR/launchd/$PLIST_RETRY_NAME.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
PLIST_RETRY_DEST="$HOME/Library/LaunchAgents/$PLIST_RETRY_NAME.plist"

case "${1:-install}" in
    install)
        echo "📦 安装定时任务..."

        # 检查项目目录
        if [ ! -d "$PROJECT_DIR" ]; then
            echo "❌ 找不到项目目录 $PROJECT_DIR"
            echo "   请先把 daily-news 项目克隆/解压到 $HOME/daily-news"
            exit 1
        fi

        mkdir -p "$HOME/Library/LaunchAgents"

        # 安装 7:00 主任务
        sed "s|USERNAME|$USERNAME|g" "$PLIST_SOURCE" > "$PLIST_DEST"
        launchctl unload "$PLIST_DEST" 2>/dev/null || true
        launchctl load "$PLIST_DEST"
        echo "✅ 07:00 主任务已加载"

        # 安装 12:00 重试任务
        sed "s|USERNAME|$USERNAME|g" "$PLIST_RETRY_SOURCE" > "$PLIST_RETRY_DEST"
        launchctl unload "$PLIST_RETRY_DEST" 2>/dev/null || true
        launchctl load "$PLIST_RETRY_DEST"
        echo "✅ 12:00 重试任务已加载"

        chmod +x "$PROJECT_DIR/daily-update.sh"

        echo ""
        echo "⏰ 每天 07:00 生成新闻，12:00 自动重试失败条目"
        echo "📋 查看状态：bash install-launchd.sh status"
        ;;

    test)
        echo "🧪 立即手动跑一次..."
        cd "$PROJECT_DIR"
        bash daily-update.sh
        ;;

    status)
        echo "📊 任务状态："
        if launchctl list | grep -q "$PLIST_NAME"; then
            launchctl list | grep "$PLIST_NAME"
            echo ""
            echo "✅ 任务已加载"
            echo ""
            echo "最近一次执行日志："
            LATEST_LOG=$(ls -t "$PROJECT_DIR/logs/"*.log 2>/dev/null | head -1)
            if [ -n "$LATEST_LOG" ]; then
                echo "($LATEST_LOG)"
                tail -20 "$LATEST_LOG"
            else
                echo "（还没有日志，明早 7:00 后查看）"
            fi
        else
            echo "❌ 任务未加载，运行 'bash install-launchd.sh install' 安装"
        fi
        ;;

    remove)
        echo "🗑 卸载定时任务..."
        launchctl unload "$PLIST_DEST" 2>/dev/null && echo "✅ 主任务已卸载" || echo "ℹ️ 主任务未在运行"
        rm -f "$PLIST_DEST"
        launchctl unload "$PLIST_RETRY_DEST" 2>/dev/null && echo "✅ 重试任务已卸载" || echo "ℹ️ 重试任务未在运行"
        rm -f "$PLIST_RETRY_DEST"
        echo "项目文件夹和日志保留，可以手动删除：rm -rf $PROJECT_DIR"
        ;;

    *)
        echo "用法："
        echo "  bash install-launchd.sh         # 安装定时任务"
        echo "  bash install-launchd.sh test    # 立即手动跑一次"
        echo "  bash install-launchd.sh status  # 查看运行状态"
        echo "  bash install-launchd.sh remove  # 卸载"
        exit 1
        ;;
esac
