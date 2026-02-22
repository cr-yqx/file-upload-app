# 项目启动方式与使用文档

本文档基于当前代码实现（`app.py`）整理，适用于本地开发与 Railway 部署。

## 1. 项目简介

这是一个基于 Flask 的“会议协作文件房间”应用，支持：

- 创建房间 + 口令进入
- 匿名昵称协作
- 文件上传（`JPG/JPEG/PNG/GIF/WEBP/PDF/DOC/DOCX`）
- PDF/DOCX 自动摘要（异步任务）
- 全文评论与划线评论
- 协作者、星标、已读、会议总结

## 2. 环境准备

建议环境：

- Python `3.11.x`（仓库 `runtime.txt` 为 `python-3.11.11`）
- 可用的 `pip`
- 可选：PostgreSQL（本地不配也可先用 SQLite）

安装依赖：

```powershell
pip install -r requirements.txt
```

## 3. 环境变量配置

可复制 `.env.example` 作为参考。关键变量如下：

### 必填（建议）

- `SECRET_KEY`：Flask 会话密钥
- `OPENAI_API_KEY`：AI 摘要调用密钥

### 常用

- `DATABASE_URL`：默认 `sqlite:///app.db`
  - 若用 PostgreSQL，支持填 `postgresql://...`，代码会自动转为 `postgresql+psycopg://...`
- `UPLOAD_FOLDER`：默认 `uploads`
- `MAX_FILE_SIZE`：默认 `10485760`（10MB）
- `OPENAI_MODEL`：默认 `gpt-4o-mini`
- `OPENAI_BASE_URL`：默认 `https://api.openai.com/v1`

### 摘要任务相关

- `SUMMARY_MAX_TEXT_CHARS`：默认 `20000`
- `SUMMARY_MIN_TEXT_CHARS`：默认 `80`
- `SUMMARY_MAX_ATTEMPTS`：默认 `2`
- `SUMMARY_RETRY_DELAY_SECONDS`：默认 `3`

### 房间/协作相关

- `DEFAULT_ROOM_SLUG`：默认 `demo`
- `DEFAULT_ROOM_NAME`：默认 `Demo Room`
- `DEFAULT_ROOM_PASSCODE`：默认 `demo1234`
- `DISCUSSION_RECOMPUTE_MIN_SECONDS`：默认 `30`
- `ONLINE_WINDOW_SECONDS`：默认 `90`
- `PRESENCE_HEARTBEAT_SECONDS`：默认 `30`

## 4. 本地启动

### 4.1 启动命令

```powershell
python app.py
```

默认监听：`http://127.0.0.1:5000`

### 4.2 首次启动会发生什么

- 自动创建上传目录（`UPLOAD_FOLDER`）
- 自动建表（`db.create_all()`）
- 自动执行轻量 schema 升级
- 自动确保默认房间存在（`DEFAULT_ROOM_SLUG`）

### 4.3 快速自检

打开健康检查：

- `http://127.0.0.1:5000/health`

应返回：

- `success: true`
- `status: ok`
- `counts.rooms/files/jobs`

## 5. 生产启动（Railway / Gunicorn）

仓库 `Procfile` 当前内容：

```procfile
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

部署建议：

- 配置 `DATABASE_URL`（推荐 PostgreSQL）
- 配置 `OPENAI_API_KEY`
- 挂载持久化存储目录到 `/app/uploads`（对应 `UPLOAD_FOLDER`）

## 6. 页面使用流程（推荐）

### 6.1 进入入口页

- `GET /`

可创建房间或进入已有房间。

### 6.2 创建房间

- 填写房间名、房间标识（可选）、口令
- 创建成功后得到分享链接：`/r/<room_slug>`

### 6.3 房间鉴权

- 访问房间页后输入口令完成授权

### 6.4 设置协作昵称

- 在房间内先设置昵称（2~20 字）
- 部分操作（如上传）要求先有昵称

### 6.5 上传文件

- 支持扩展名：`jpg/jpeg/png/gif/webp/pdf/doc/docx`
- 单文件默认上限 10MB

摘要行为：

- `pdf/docx`：自动进入摘要任务（`pending -> running -> done/failed`）
- `doc`：不自动摘要（会提示建议转 `docx`）
- 图片：不摘要

### 6.6 评论与协作

- 右侧“文件评论”支持全文评论
- 阅读器中支持划线评论（PDF/DOCX）
- 可进行星标、已读、协作者筛选

### 6.7 会议总结

- 房主可触发“结束讨论并生成总结”
- 总结会按当前实现结构展示并可持续重算

## 7. API 使用要点（核心）

常用接口：

- `POST /api/rooms` 创建房间
- `POST /api/rooms/<room_slug>/auth` 鉴权
- `GET/POST /api/rooms/<room_slug>/profile` 获取/设置昵称
- `POST /api/rooms/<room_slug>/upload` 上传文件
- `GET /api/rooms/<room_slug>/files` 文件列表
- `GET /api/rooms/<room_slug>/jobs/<job_id>` 摘要任务状态
- `POST /api/rooms/<room_slug>/discussion/end` 结束讨论
- `GET /api/rooms/<room_slug>/discussion/summary` 获取总结

兼容旧接口（deprecated）：

- `POST /upload`
- `GET /api/files`
- `GET /files`

## 8. 自动化检查脚本

### 8.1 冒烟测试

```powershell
python scripts/smoke_test.py --base-url https://your-app.up.railway.app
```

### 8.2 部署后检查并生成报告

```powershell
python scripts/post_deploy_check.py --base-url https://your-app.up.railway.app --report-file post_deploy_report.md
```

## 9. 常见问题排查

### 9.1 PowerShell 下 `&&` 报错

Windows PowerShell 不支持 `&&`，改用分号：

```powershell
pip install -r requirements.txt; pytest -q
```

### 9.2 摘要失败

优先检查：

- `OPENAI_API_KEY` 是否正确
- `OPENAI_BASE_URL` 与 `OPENAI_MODEL` 是否匹配服务端（尤其第三方网关）
- 上传文件是否文本可提取（扫描件可能文本不足）

### 9.3 500/502 或页面打不开

优先看：

- `/health` 是否为 `success: true`
- Railway `Deploy Logs` / `HTTP Logs` 是否有导入错误或环境变量缺失
- 数据库连接串是否正确

---

如需给团队演示，建议先做一次完整流程演练：创建房间 -> 设置昵称 -> 上传 PDF/DOCX -> 评论 -> 结束讨论 -> 查看总结。
