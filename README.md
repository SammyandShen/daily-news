# 📰 Daily English News · macOS 版

为 B2 英语学习者每天自动推送 5 条科技/商业/经济资讯，含中英双语简介、原文摘录、5 个重点词汇/表达 + 例句。支持收藏、标签、Markdown 导出。

**完全免费** —— 用你已有的 Claude Code Pro 订阅本机生成内容，不需要 API key，不需要服务器，前端通过 GitHub Pages 永久托管。

---

## 🎯 整体工作原理

```
你的 Mac（每天 7:00 自动唤醒并执行）
    │
    ├─ ① 抓 9 个免费 RSS 源的新闻，按关键词打分挑出 5 条
    │
    ├─ ② 调用 claude -p（你的 Pro 订阅）生成中英双语讲解和词汇
    │
    └─ ③ git push → GitHub Pages 自动更新
                    │
                    ▼
              你访问固定网址查看
              https://你的GitHub用户名.github.io/daily-news/
              (收藏数据保存在浏览器，永久不丢)
```

**为什么用 macOS launchd 而不是 GitHub Actions：** 因为 Claude Code Pro 订阅认证在你本地 Mac 上，云端 Actions 没法用你的订阅。launchd 是 macOS 原生的"cron 替代品"，比 cron 更可靠：电脑睡眠时跳过的任务，唤醒后会自动补跑。

---

## 📦 部署步骤（全部完成约 15 分钟）

### 第 0 步：前提检查

打开 **终端**（Spotlight 搜 Terminal），逐条运行下面三条命令，每条都应有输出：

```bash
which claude     # 应输出 claude 命令的路径
claude --version # 应输出版本号
git --version    # 应输出 git 版本
python3 --version # 应输出 Python 版本（macOS 自带）
```

如果 `claude` 命令找不到：
```bash
npm install -g @anthropic-ai/claude-code
claude login   # 用你的 Pro 账号登录（一次性）
```

### 第 1 步：放置项目

把 `daily-news-mac` 整个文件夹放到你的家目录下，并改名为 `daily-news`：

```bash
# 假设 zip 解压后在 ~/Downloads/daily-news-mac
mv ~/Downloads/daily-news-mac ~/daily-news
cd ~/daily-news
```

### 第 2 步：装 Python 依赖

```bash
pip3 install -r scripts/requirements.txt
```

如果提示 `error: externally-managed-environment`（macOS 14+ 常见），改用：
```bash
pip3 install --user -r scripts/requirements.txt
# 或者用虚拟环境
python3 -m venv .venv && source .venv/bin/activate && pip install -r scripts/requirements.txt
```

### 第 3 步：在 GitHub 上创建仓库

1. 登录 [github.com](https://github.com) → New repository
2. 仓库名：`daily-news`（**必须用这个名**，要不要改后面的网址会乱）
3. 选 **Public**
4. **不要**勾选 "Initialize with README"
5. 点 Create

### 第 4 步：把项目推到 GitHub

回到终端（仍在 `~/daily-news` 目录）：

```bash
git init
git add .
git commit -m "Initial commit"

# 把 YOUR_USERNAME 替换成你的 GitHub 用户名
git remote add origin https://github.com/YOUR_USERNAME/daily-news.git
git branch -M main
git push -u origin main
```

如果是第一次用 GitHub CLI 或推送，可能需要登录授权（Mac 弹窗会引导你完成）。

### 第 5 步：启用 GitHub Pages

1. 在 GitHub 仓库页 → **Settings** → 左侧 **Pages**
2. **Source** 选 `Deploy from a branch`
3. **Branch** 选 `main`，文件夹选 `/docs`
4. 点 **Save**
5. 等 1-2 分钟，刷新页面，会显示一个网址：
   `https://YOUR_USERNAME.github.io/daily-news/`

**这就是你的应用永久访问地址。** Mac/iPhone 浏览器都能开，加到主屏幕即可。

### 第 6 步：先手动跑一次测试

```bash
cd ~/daily-news
bash daily-update.sh
```

第一次跑预计需要 1-3 分钟（Claude Code 生成 5 条新闻的内容）。看到 "🎉 完成" 就成了。

如果出错，看错误信息，常见两种：
- **claude 命令找不到** → 看第 0 步
- **git push 失败** → 检查 GitHub 仓库地址和登录状态

### 第 7 步：安装定时任务

```bash
bash install-launchd.sh
```

输出 "✅ 定时任务已加载" 即成功。从此每天早上 7:00 自动跑。

---

## 🛠 日常运维命令

```bash
cd ~/daily-news

# 立即手动跑一次（不等 7:00）
bash install-launchd.sh test

# 查看任务状态 + 最近日志
bash install-launchd.sh status

# 看今天的详细日志
tail -f logs/$(date +%Y-%m-%d).log

# 卸载定时任务
bash install-launchd.sh remove
```

---

## ⚙️ 自定义

### 改难度（A2 / B1 / B2 / C1 / C2）
编辑 `daily-update.sh`，找到这一行：
```bash
LEVEL="B2"
```

### 改运行时间
编辑 `launchd/com.user.daily-news.plist`，找到：
```xml
<key>Hour</key>
<integer>7</integer>
```
改完后重装：
```bash
bash install-launchd.sh remove
bash install-launchd.sh install
```

### 改主题方向 / RSS 源
编辑 `scripts/fetch_news.py` 里的 `RSS_SOURCES` 和 `KEYWORDS`。

### 加旁路通知（推送到手机）
脚本最后已经加了 macOS 系统通知。如果想推到 iPhone，可以再加一行调用 [Pushover](https://pushover.net) / [Bark](https://github.com/Finb/Bark)（自己留意接入）。

---

## 🐛 常见问题

**Q: 7:00 时电脑在睡眠，会漏跑吗？**
A: 不会。`launchd` 的 `StartCalendarInterval` 在唤醒后会自动补跑（这是它比 cron 强的地方）。

**Q: 如果电脑关机过夜呢？**
A: 那确实会漏。次日开机后手动跑一次：`bash install-launchd.sh test`。或者在系统设置 → 节能里开"插电时不睡眠"。

**Q: Pro 订阅每天用一次会不会触发限流？**
A: 5 条新闻 ≈ 5 次 Claude 对话，对 Pro 套餐来说微不足道（Pro 每 5 小时窗口允许大量对话）。

**Q: 我手机上想看怎么办？**
A: Safari 打开 `https://YOUR_USERNAME.github.io/daily-news/` → 分享 → "添加到主屏幕"，会变成一个像 App 一样的图标。

**Q: 收藏的词在 Mac 浏览器和手机能同步吗？**
A: 默认不能（每个浏览器自己存）。前端有"💾 备份 JSON"和"📂 从 JSON 恢复"按钮，可以手动跨设备同步。

**Q: 想看老的某天的新闻？**
A: 左侧日期栏自动显示最近 30 天。再往前的不会保留，但可以从 git 历史里找回 `docs/news.json` 的旧版本。

**Q: 我笔记本带去外地用，会有问题吗？**
A: 不会，只要联网+开机，定时任务正常跑。只要有网就能 git push。

---

## 📂 文件结构

```
daily-news/
├── daily-update.sh                      # 主脚本（每天跑一次）
├── install-launchd.sh                   # 定时任务安装/卸载
├── launchd/
│   └── com.user.daily-news.plist        # macOS 定时任务模板
├── scripts/
│   ├── fetch_news.py                    # RSS 抓取 + 关键词筛选
│   ├── generate_with_claude_code.py     # 调用 claude -p 生成内容
│   └── requirements.txt
├── docs/                                # → GitHub Pages 部署目录
│   ├── index.html                       # 前端 SPA
│   └── news.json                        # 数据（每天追加）
├── logs/                                # 每日运行日志（自动生成）
├── .gitignore
└── README.md
```

## 📝 License

MIT
