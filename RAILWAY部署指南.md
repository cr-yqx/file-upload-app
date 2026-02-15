# Railway 部署指南

## 准备工作 ✅

所有部署配置文件已准备完成：
- ✅ `Procfile` - Railway 启动配置
- ✅ `runtime.txt` - Python 版本指定
- ✅ `requirements.txt` - 依赖包（已添加 gunicorn）
- ✅ `.gitignore` - Git 忽略文件
- ✅ `app.py` - 已支持生产环境

---

## 部署步骤

### 1. 创建 Git 仓库

```bash
# 初始化 Git 仓库
git init

# 添加所有文件
git add .

# 提交
git commit -m "Initial commit: File upload application"
```

### 2. 推送到 GitHub

```bash
# 在 GitHub 创建新仓库后
git remote add origin https://github.com/你的用户名/仓库名.git
git branch -M main
git push -u origin main
```

### 3. 部署到 Railway

#### 方式 A：通过 Railway 网站（推荐）

1. 访问 [Railway.app](https://railway.app/)
2. 点击 "Start a New Project"
3. 选择 "Deploy from GitHub repo"
4. 授权 GitHub 并选择您的仓库
5. Railway 会自动检测 Python 项目并部署
6. 等待部署完成（约 2-3 分钟）

#### 方式 B：通过 Railway CLI

```bash
# 安装 Railway CLI
npm i -g @railway/cli

# 登录
railway login

# 初始化项目
railway init

# 部署
railway up
```

### 4. 配置环境变量（可选）

在 Railway 项目设置中添加：
- `FLASK_ENV=production`
- `MAX_FILE_SIZE=10485760` （如需自定义）

### 5. 获取部署 URL

部署完成后，Railway 会提供一个 URL，例如：
- `https://your-app-name.up.railway.app`

---

## 重要说明

### 文件存储问题

⚠️ **Railway 的文件系统是临时的**，每次重新部署时 `uploads/` 目录会被清空。

**解决方案**：

#### 选项 1：使用云存储（推荐生产环境）
- AWS S3
- 阿里云 OSS
- 腾讯云 COS
- Cloudinary（图片专用）

#### 选项 2：使用 Railway Volumes（持久化存储）
在 Railway 项目设置中：
1. 进入 "Volumes" 标签
2. 创建新 Volume
3. 挂载路径：`/app/uploads`

#### 选项 3：仅用于演示
如果只是演示项目，可以接受文件临时存储。

---

## 测试部署

部署成功后，访问您的 Railway URL：
1. 测试文件上传功能
2. 验证进度条显示
3. 测试 PDF 和图片显示

---

## 常见问题

### Q: 部署失败怎么办？
A: 查看 Railway 的部署日志，通常是依赖安装问题。

### Q: 上传文件后找不到？
A: 检查是否配置了 Volume，或考虑使用云存储。

### Q: 如何更新应用？
A: 推送新代码到 GitHub，Railway 会自动重新部署。

### Q: 如何绑定自定义域名？
A: 在 Railway 项目设置的 "Domains" 中添加。

---

## 成本估算

**Railway 免费额度**：
- $5 免费额度/月
- 约可运行 500 小时
- 适合小型项目和演示

**超出后**：
- 按使用量计费
- 约 $0.000463/分钟
- 月费约 $20-30（持续运行）

---

## 下一步

1. 初始化 Git 仓库
2. 推送到 GitHub
3. 在 Railway 部署
4. 测试功能
5. （可选）配置云存储

**需要帮助执行这些步骤吗？**
