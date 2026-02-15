// 获取 DOM 元素
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const progressContainer = document.getElementById('progressContainer');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');
const message = document.getElementById('message');
const fileInfo = document.getElementById('fileInfo');
const resultContainer = document.getElementById('resultContainer');
const resultInfo = document.getElementById('resultInfo');

// 常量
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ALLOWED_TYPES = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp', 'application/pdf'];
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf'];

// 文件选择事件
fileInput.addEventListener('change', function() {
    const file = this.files[0];

    if (!file) {
        uploadBtn.disabled = true;
        fileInfo.innerHTML = '';
        return;
    }

    // 验证文件大小
    if (file.size > MAX_FILE_SIZE) {
        showMessage('文件大小超过 10MB 限制', 'error');
        uploadBtn.disabled = true;
        fileInfo.innerHTML = '';
        return;
    }

    // 验证文件类型
    const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(fileExtension)) {
        showMessage('不支持的文件类型，仅支持图片和 PDF', 'error');
        uploadBtn.disabled = true;
        fileInfo.innerHTML = '';
        return;
    }

    // 显示文件信息
    const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2);
    fileInfo.innerHTML = `
        <strong>已选择文件：</strong>${file.name}<br>
        <strong>文件大小：</strong>${fileSizeMB} MB<br>
        <strong>文件类型：</strong>${file.type || '未知'}
    `;

    uploadBtn.disabled = false;
    hideMessage();
    resultContainer.style.display = 'none';
});

// 上传按钮点击事件
uploadBtn.addEventListener('click', function() {
    const file = fileInput.files[0];

    if (!file) {
        showMessage('请先选择文件', 'error');
        return;
    }

    uploadFile(file);
});

// 上传文件函数
function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();

    // 上传进度事件
    xhr.upload.addEventListener('progress', function(e) {
        if (e.lengthComputable) {
            const percentComplete = Math.round((e.loaded / e.total) * 100);
            updateProgress(percentComplete);
        }
    });

    // 上传完成事件
    xhr.addEventListener('load', function() {
        if (xhr.status === 200) {
            const response = JSON.parse(xhr.responseText);
            if (response.success) {
                showMessage(response.message, 'success');
                showResult(response);
                resetUpload();
            } else {
                showMessage(response.message, 'error');
                hideProgress();
            }
        } else {
            const response = JSON.parse(xhr.responseText);
            showMessage(response.message || '上传失败', 'error');
            hideProgress();
        }
    });

    // 上传错误事件
    xhr.addEventListener('error', function() {
        showMessage('网络错误，上传失败', 'error');
        hideProgress();
    });

    // 发送请求
    xhr.open('POST', '/upload', true);
    xhr.send(formData);

    // 显示进度条
    showProgress();
    uploadBtn.disabled = true;
}

// 更新进度条
function updateProgress(percent) {
    progressBar.style.width = percent + '%';
    progressText.textContent = percent + '%';
}

// 显示进度条
function showProgress() {
    progressContainer.style.display = 'block';
    updateProgress(0);
}

// 隐藏进度条
function hideProgress() {
    progressContainer.style.display = 'none';
}

// 显示消息
function showMessage(text, type) {
    message.textContent = text;
    message.className = 'message ' + type;
    message.style.display = 'block';
}

// 隐藏消息
function hideMessage() {
    message.style.display = 'none';
}

// 显示上传结果
function showResult(data) {
    const fileSizeMB = (data.size / (1024 * 1024)).toFixed(2);
    resultInfo.innerHTML = `
        <p><strong>文件名：</strong>${data.filename}</p>
        <p><strong>文件大小：</strong>${fileSizeMB} MB</p>
        <p><strong>访问地址：</strong><a href="${data.url}" target="_blank">${data.url}</a></p>
    `;
    resultContainer.style.display = 'block';
}

// 重置上传
function resetUpload() {
    fileInput.value = '';
    fileInfo.innerHTML = '';
    uploadBtn.disabled = true;
    hideProgress();
}
