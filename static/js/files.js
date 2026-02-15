// 页面加载时获取文件列表
document.addEventListener('DOMContentLoaded', function() {
    loadFiles();
});

// 获取 DOM 元素
const loading = document.getElementById('loading');
const message = document.getElementById('message');
const fileList = document.getElementById('fileList');
const emptyState = document.getElementById('emptyState');
const previewModal = document.getElementById('previewModal');
const previewContent = document.getElementById('previewContent');
const closeModal = document.querySelector('.close');

// 关闭模态框
closeModal.onclick = function() {
    previewModal.style.display = 'none';
    previewContent.innerHTML = '';
}

window.onclick = function(event) {
    if (event.target == previewModal) {
        previewModal.style.display = 'none';
        previewContent.innerHTML = '';
    }
}

// 加载文件列表
function loadFiles() {
    loading.style.display = 'block';
    fileList.innerHTML = '';
    emptyState.style.display = 'none';
    hideMessage();

    fetch('/api/files')
        .then(response => response.json())
        .then(data => {
            loading.style.display = 'none';

            if (data.success) {
                if (data.files.length === 0) {
                    emptyState.style.display = 'block';
                } else {
                    displayFiles(data.files);
                }
            } else {
                showMessage(data.message || '加载失败', 'error');
            }
        })
        .catch(error => {
            loading.style.display = 'none';
            showMessage('网络错误：' + error.message, 'error');
        });
}

// 显示文件列表
function displayFiles(files) {
    fileList.innerHTML = '';

    files.forEach(file => {
        const card = createFileCard(file);
        fileList.appendChild(card);
    });
}

// 创建文件卡片
function createFileCard(file) {
    const card = document.createElement('div');
    card.className = 'file-card';

    // 预览区域
    const preview = document.createElement('div');
    preview.className = 'file-preview';
    preview.onclick = () => previewFile(file);

    if (file.type === 'image') {
        const img = document.createElement('img');
        img.src = file.url;
        img.alt = file.filename;
        preview.appendChild(img);
    } else {
        const icon = document.createElement('div');
        icon.className = 'pdf-icon';
        icon.textContent = '📄';
        preview.appendChild(icon);
    }

    // 文件信息
    const info = document.createElement('div');
    info.className = 'file-info';
    info.innerHTML = `
        <div class="file-name">${file.filename}</div>
        <div class="file-meta">
            <div>大小：${file.size_mb} MB</div>
            <div>时间：${file.modified}</div>
        </div>
    `;

    // 操作按钮
    const actions = document.createElement('div');
    actions.className = 'file-actions';

    const viewBtn = document.createElement('a');
    viewBtn.href = file.url;
    viewBtn.target = '_blank';
    viewBtn.className = 'btn btn-view';
    viewBtn.textContent = '查看';

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-delete';
    deleteBtn.textContent = '删除';
    deleteBtn.onclick = () => deleteFile(file.filename);

    actions.appendChild(viewBtn);
    actions.appendChild(deleteBtn);

    card.appendChild(preview);
    card.appendChild(info);
    card.appendChild(actions);

    return card;
}

// 预览文件
function previewFile(file) {
    previewContent.innerHTML = '';

    if (file.type === 'image') {
        const img = document.createElement('img');
        img.src = file.url;
        img.alt = file.filename;
        previewContent.appendChild(img);
    } else {
        const iframe = document.createElement('iframe');
        iframe.src = file.url;
        previewContent.appendChild(iframe);
    }

    previewModal.style.display = 'block';
}

// 删除文件
function deleteFile(filename) {
    if (!confirm(`确定要删除文件 "${filename}" 吗？`)) {
        return;
    }

    fetch(`/api/files/${filename}`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showMessage('文件已删除', 'success');
            loadFiles();
        } else {
            showMessage(data.message || '删除失败', 'error');
        }
    })
    .catch(error => {
        showMessage('网络错误：' + error.message, 'error');
    });
}

// 显示消息
function showMessage(text, type) {
    message.textContent = text;
    message.className = 'message ' + type;
    message.style.display = 'block';

    setTimeout(() => {
        hideMessage();
    }, 3000);
}

// 隐藏消息
function hideMessage() {
    message.style.display = 'none';
}
