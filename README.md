# Weekly Spending Report — Setup Guide

## 一、安装依赖

```bash
pip3 install requests plotly kaleido
```

> `kaleido` 是 Plotly 导出 PNG 图片必须的。

---

## 二、Notion 配置

### 1. 创建 Integration
1. 访问 https://www.notion.so/my-integrations
2. 点击 **New integration**，命名随意（比如 "Spending Report"）
3. 权限选 **Read content**，workspace 选你的
4. 创建后复制 **Internal Integration Token** → 填入脚本 `NOTION_TOKEN`

### 2. 共享数据库给 Integration
1. 打开你的 Notion 支出数据库页面
2. 右上角 `···` → **Connections** → 找到你的 integration → 点击 Connect
3. 复制数据库 URL 中的 ID：
   - URL 格式：`https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...`
   - `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 这一段（32位）就是 Database ID
   - 填入脚本 `NOTION_DATABASE_ID`

### 3. 确认字段名称
脚本默认字段名：`Date`, `Amount`, `Type`, `Description`
如果你的 Notion 字段名不一样，修改脚本顶部的：
```python
FIELD_DATE = "Date"
FIELD_AMOUNT = "Amount"
FIELD_TYPE = "Type"
FIELD_DESCRIPTION = "Description"
```

---

## 三、Gmail 配置

> 必须使用 **App Password**，不能用 Gmail 登录密码。

1. 访问 Google 账号 → 安全 → 两步验证（先开启）
2. 搜索 "App passwords" → 创建，名称随意
3. 复制生成的 16 位密码 → 填入脚本 `GMAIL_APP_PASSWORD`
4. 确认 `GMAIL_SENDER = "isyumj@gmail.com"`

---

## 四、测试运行

```bash
cd ~/spending_report
python3 spending_report.py
```

如果一切正常，你应该看到：
```
📡 Fetching Notion data...
   142 transactions loaded
📅 Report week: 2026-04-27 → 2026-05-03
🎨 Generating charts...
📧 Sending email...
✅ Report sent to ['isyumj@gmail.com', 'HaochenLucas@gmail.com']
```

---

## 五、设置每周一自动运行（macOS launchd）

### 1. 编辑 plist 文件
打开 `com.haochenjoyce.weeklyspending.plist`，修改两处：
- `python3` 路径：运行 `which python3` 查看你的路径
- 脚本绝对路径：改成实际路径，比如 `/Users/haochen/spending_report/spending_report.py`

### 2. 安装到 launchd
```bash
# 复制 plist 到 LaunchAgents 目录
cp com.haochenjoyce.weeklyspending.plist ~/Library/LaunchAgents/

# 加载（注册定时任务）
launchctl load ~/Library/LaunchAgents/com.haochenjoyce.weeklyspending.plist
```

### 3. 验证是否注册成功
```bash
launchctl list | grep haochenjoyce
```
看到输出说明已注册。

### 4. 手动触发一次测试
```bash
launchctl start com.haochenjoyce.weeklyspending
```

### 5. 查看日志
```bash
cat /tmp/spending_report.log        # 正常输出
cat /tmp/spending_report_error.log  # 错误信息
```

---

## 六、常见问题

**Q: Mac 关机了周一没跑怎么办？**  
A: launchd 不会补跑。建议周一上班前开机即可。如果需要绝对可靠，可以改用 GitHub Actions（免费，云端跑），但需要把 token 存到 GitHub Secrets。告诉我，我可以帮你配。

**Q: 图表显示空白？**  
A: 确认 `kaleido` 安装成功：`python3 -c "import kaleido; print('ok')"`

**Q: Amount 字段有 $ 符号解析失败？**  
A: 检查 Notion 里 Amount 字段类型是 **Number** 还是 **Text**。如果是 Text，需要修改 `parse_transaction` 中的解析逻辑：
```python
amount_raw = props[FIELD_AMOUNT]["rich_text"][0]["plain_text"]
amount = float(amount_raw.replace("$", "").replace(",", ""))
```

---

## 文件结构

```
spending_report/
├── spending_report.py                    # 主脚本
├── com.haochenjoyce.weeklyspending.plist # macOS 定时任务配置
└── README.md                             # 本文件
```
