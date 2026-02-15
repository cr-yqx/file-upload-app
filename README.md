# AI 学习资料房间（Flask + PostgreSQL）

这是一个可分享的文件上传应用，支持“房间口令访问 + PDF 自动摘要 + 异步任务轮询”。

## 核心能力

- 房间模式：创建房间、口令验证、分享链接
- 文件上传：支持 JPG/JPEG/PNG/GIF/WEBP/PDF，单文件默认 10MB
- 文件管理：列表展示、查看、删除
- AI 摘要：上传 PDF 后异步生成摘要（OpenAI）
- 任务状态：`queued/running/done/failed` 轮询
- 协作互动：匿名昵称、评论、星标、已读、文件协作指标
- 兼容旧接口：`/upload`、`/api/files`、`/files` 映射到默认房间 `demo` 并返回 `deprecated`

## 技术栈

- Flask + Flask-SQLAlchemy
- PostgreSQL（元数据）
- 本地后台线程（异步摘要任务）
- OpenAI API（摘要生成）
- Railway（部署）

## 项目结构

```text
.
├─ app.py
├─ Procfile
├─ requirements.txt
├─ .env.example
├─ templates/
│  ├─ room_entry.html
│  └─ room.html
├─ static/
│  ├─ css/
│  │  ├─ rooms.css
│  │  └─ room.css
│  └─ js/
│     ├─ rooms.js
│     └─ room.js
├─ scripts/
│  ├─ smoke_test.py
│  ├─ post_deploy_check.py
│  └─ daily_report.py
└─ tests/
   └─ test_rooms_api.py
```

## 本地运行

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 配置环境变量（可复制 `.env.example`）

```bash
set DATABASE_URL=postgresql://...
set OPENAI_API_KEY=sk-...
set OPENAI_BASE_URL=https://api.openai.com/v1
```

3. 启动 Web

```bash
python app.py
```

4. 访问页面

- 入口页：`http://localhost:5000/`
- 房间页：`http://localhost:5000/r/<room_slug>`

## Railway 部署要点

- Web 进程：`web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- 必须挂载 Volume 到 `/app/uploads`
- 需要配置 PostgreSQL、OpenAI Key
- 可选配置 `OPENAI_BASE_URL`（默认 `https://api.openai.com/v1`，用于代理/中转服务）
- 使用第三方中转时，`OPENAI_MODEL` 必须填该服务 `/v1/models` 返回的真实模型 ID，不能填展示名

## API 概览

### 新接口

- `POST /api/rooms` 创建房间
- `POST /api/rooms/<room_slug>/auth` 房间鉴权
- `GET /api/rooms/<room_slug>/profile` 获取当前会话昵称状态
- `POST /api/rooms/<room_slug>/profile` 设置/更新昵称
- `POST /api/rooms/<room_slug>/upload` 上传文件
- `GET /api/rooms/<room_slug>/files` 获取文件列表
- `GET /api/rooms/<room_slug>/jobs/<job_id>` 查询摘要任务
- `DELETE /api/rooms/<room_slug>/files/<file_id>` 删除文件
- `GET /api/rooms/<room_slug>/files/<file_id>/comments` 获取最近评论
- `POST /api/rooms/<room_slug>/files/<file_id>/comments` 新增评论
- `PUT /api/rooms/<room_slug>/files/<file_id>/star` 星标/取消星标
- `PUT /api/rooms/<room_slug>/files/<file_id>/read` 标记已读/未读

### 兼容接口（Deprecated）

- `POST /upload`
- `GET /api/files`
- `DELETE /api/files/<filename>`
- `GET /files`

## 自动化工作流

- CI + Railway：`.github/workflows/ci-and-railway.yml`
- 每日统计：`.github/workflows/daily-metrics-report.yml`

需要配置的 GitHub Secrets：

- `RAILWAY_DEPLOY_HOOK`
- `APP_BASE_URL`
- `DATABASE_URL`
- `DAILY_REPORT_WEBHOOK`（可选）

## 冒烟检查脚本

```bash
python scripts/smoke_test.py --base-url https://your-app.up.railway.app
```

## 验收建议

- 创建房间 + 错误口令返回 401
- 上传图片可展示，不触发摘要
- 上传 PDF 后 1 分钟内有终态（done/failed）
- 删除文件后 URL 404，列表同步更新
- `/api/files` 返回 `deprecated: true`
