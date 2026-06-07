# 部署到 Render（傻瓜式步骤）

Render 从 GitHub 仓库部署，所以分两大步：**① 把代码推到 GitHub → ② 在 Render 上连接它**。

---

## 第一步：把代码推到 GitHub

### 1. 确认装了 Git
在 PowerShell 里运行：
```powershell
git --version
```
如果报错，去 https://git-scm.com/download/win 下载安装后重开终端。

### 2. 进入项目目录
```powershell
cd "C:\Users\olivi\OneDrive\Desktop\ASTON\求职\应用设计\parent-check"
```

### 3. 初始化并提交
```powershell
git init
git add .
git commit -m "Parent Check: bilingual scam/health checker"
```

### 4. 在 GitHub 上建一个空仓库
- 打开 https://github.com/new
- 仓库名填 `parent-check`，选 **Public**（公开）
- **不要**勾选 "Add a README"（你已经有了）
- 点 Create repository

### 5. 把本地代码推上去
GitHub 建完会显示你的仓库地址，把下面两行里的 `你的用户名` 换成你的：
```powershell
git remote add origin https://github.com/你的用户名/parent-check.git
git branch -M main
git push -u origin main
```
（第一次推送会让你登录 GitHub，照提示来即可。）

---

## 第二步：在 Render 上部署

### 1. 注册 Render
- 打开 https://render.com → Get Started → **用 GitHub 账号登录**（最省事）

### 2. 用 Blueprint 一键部署（推荐）
因为项目里已经有 `render.yaml`，Render 能自动读懂配置：
- 点右上角 **New +** → **Blueprint**
- 选中你刚推上去的 `parent-check` 仓库 → **Connect**
- Render 会读到 `render.yaml`，显示要创建的服务 → 点 **Apply**
- 等几分钟，状态变成 **Live** 就成功了

> 如果不想用 Blueprint，也可以 New + → **Web Service**，手动填：
> - Build Command: `pip install -r requirements.txt`
> - Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT`
> - Environment → 加一个变量 `SECRET_KEY`，值随便填一长串随机字符

### 3. 拿到公开网址
部署成功后，Render 给你一个网址，形如：
```
https://parent-check.onrender.com
```
**这就是任何人都能打开的公开链接**——发给家人、写进简历/领英都行。

---

## 上线后要知道的 3 件事（免费档的限制）

1. **会"睡觉"**：免费服务 15 分钟没人访问就休眠，下次打开要等约 30 秒"冷启动"。录 demo 或发给别人前，先自己打开一下唤醒它。

2. **历史记录会被清空**：Render 免费档的硬盘是临时的，每次**重新部署或重启**，`parent_check.db` 会被重置（历史清零）。做演示完全够用；要永久保存就得换成托管数据库（如 Render 的 PostgreSQL，或 Supabase/Neon）。

3. **目前所有人共用一份历史**：没有登录系统，任何人点"历史"都能看到别人输入过的内容。做 demo 没问题，但要真正公开给陌生人长期用，需要加用户隔离（账号或 session）。

---

## 更新代码后怎么重新部署
以后改了代码，只要再推一次 GitHub，Render 会**自动重新部署**：
```powershell
git add .
git commit -m "说明这次改了什么"
git push
```
