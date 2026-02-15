# 文件上传系统

基于 Python Flask + 原生 HTML/JS 的文件上传功能。

## 功能特性

- ✅ 支持图片格式：JPG, JPEG, PNG, GIF, WEBP
- ✅ 支持 PDF 文件
- ✅ 单文件大小限制：10MB
- ✅ 实时上传进度显示
- ✅ 前后端双重文件验证
- ✅ 安全文件名处理
- ✅ 美观的用户界面

## 项目结构

```
skill_test/
├── app.py                 # Flask 主应用
├── uploads/              # 文件存储目录
├── static/
│   ├── css/
│   │   └── style.css    # 样式文件
│   └── js/
│       └── upload.js    # 上传逻辑
└── templates/
    └── index.html       # 上传页面
```

## 安装依赖

```bash
pip install flask
```

## 运行应用

```bash
python app.py
```

应用将在 `http://localhost:5000` 启动。

## 使用说明

1. 打开浏览器访问 `http://localhost:5000`
2. 点击"选择文件"按钮选择要上传的文件
3. 系统会自动验证文件类型和大小
4. 点击"上传文件"按钮开始上传
5. 上传过程中会显示实时进度
6. 上传成功后会显示文件信息和访问链接

## 技术栈

- **后端**: Python Flask
- **前端**: 原生 HTML/CSS/JavaScript
- **文件处理**: Werkzeug (Flask 内置)

## 安全特性

- 使用 `secure_filename()` 防止路径遍历攻击
- 前后端双重文件类型验证
- 文件大小限制保护
- 仅允许特定文件扩展名

## 测试场景

- [x] 上传合法图片文件（< 10MB）
- [x] 上传合法 PDF 文件（< 10MB）
- [x] 尝试上传超过 10MB 的文件（应被拒绝）
- [x] 尝试上传不支持的文件类型（应被拒绝）
- [x] 验证进度条显示
- [x] 验证上传成功后的文件访问
