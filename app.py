from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import os
import uuid

app = Flask(__name__)

# 配置
UPLOAD_FOLDER = 'uploads'
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf'}

# MIME 类型映射
MIME_TYPES = {
    'pdf': 'application/pdf',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'webp': 'image/webp'
}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """处理文件上传"""
    # 检查是否有文件
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有选择文件'}), 400

    file = request.files['file']

    # 检查文件名是否为空
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'}), 400

    # 检查文件类型
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': '不支持的文件类型，仅支持图片和PDF'}), 400

    # 安全处理文件名，保留扩展名
    filename = get_safe_filename(file.filename)

    # 保存文件
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # 获取文件大小
    file_size = os.path.getsize(filepath)

    # 返回成功响应
    return jsonify({
        'success': True,
        'message': '文件上传成功',
        'filename': filename,
        'size': file_size,
        'url': f'/uploads/{filename}'
    })


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """访问上传的文件"""
    # 获取文件扩展名并设置 MIME 类型
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    mimetype = MIME_TYPES.get(ext)

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, mimetype=mimetype)


if __name__ == '__main__':
    # 开发环境
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    # 生产环境（Railway 会使用 gunicorn）
    # 确保上传目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
