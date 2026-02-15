# PDF 显示问题修复说明

## 问题描述

上传的 PDF 文件无法正常显示，原因是：
1. 中文文件名经过 `secure_filename()` 处理后，扩展名丢失
2. 浏览器无法识别正确的 MIME 类型

## 修复内容

### 1. 新增 `get_safe_filename()` 函数

```python
def get_safe_filename(original_filename):
    """生成安全的文件名，保留扩展名"""
    # 获取文件扩展名
    if '.' in original_filename:
        ext = original_filename.rsplit('.', 1)[1].lower()
    else:
        ext = ''

    # 使用 secure_filename 处理文件名
    safe_name = secure_filename(original_filename)

    # 如果 secure_filename 导致文件名为空或丢失扩展名，使用 UUID
    if not safe_name or '.' not in safe_name:
        safe_name = f"{uuid.uuid4().hex}.{ext}"

    return safe_name
```

**功能**：
- 先提取文件扩展名
- 使用 `secure_filename()` 处理文件名
- 如果扩展名丢失，使用 UUID 生成新文件名并保留扩展名

### 2. 改进文件访问路由

```python
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """访问上传的文件"""
    # 根据文件扩展名设置正确的 MIME 类型
    mimetype = None
    if filename.lower().endswith('.pdf'):
        mimetype = 'application/pdf'
    elif filename.lower().endswith(('.jpg', '.jpeg')):
        mimetype = 'image/jpeg'
    elif filename.lower().endswith('.png'):
        mimetype = 'image/png'
    elif filename.lower().endswith('.gif'):
        mimetype = 'image/gif'
    elif filename.lower().endswith('.webp'):
        mimetype = 'image/webp'

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, mimetype=mimetype)
```

**功能**：
- 根据文件扩展名自动设置正确的 MIME 类型
- 确保浏览器能正确识别和显示文件

## 测试验证

应用已重启，现在可以：

1. **重新上传 PDF 文件**
   - 文件名会被正确处理
   - 扩展名会被保留
   - 浏览器能正确显示 PDF

2. **测试中文文件名**
   - 中文文件名会被转换为 UUID
   - 扩展名会被保留
   - 例如：`测试文档.pdf` → `a1b2c3d4e5f6.pdf`

3. **访问已上传的文件**
   - 图片文件：直接在浏览器中显示
   - PDF 文件：在浏览器中打开 PDF 查看器

## 访问地址

应用运行在：http://localhost:5000

请重新测试 PDF 文件上传功能！
