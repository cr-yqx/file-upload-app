const roomSlug = document.body.dataset.roomSlug;
const roomName = document.body.dataset.roomName;
let isAuthorized = document.body.dataset.authorized === 'true';

const authSection = document.getElementById('authSection');
const workspace = document.getElementById('workspace');
const authForm = document.getElementById('authForm');
const uploadForm = document.getElementById('uploadForm');
const fileInput = document.getElementById('fileInput');
const uploadButton = document.getElementById('uploadButton');
const refreshButton = document.getElementById('refreshButton');
const fileList = document.getElementById('fileList');
const loading = document.getElementById('loading');
const emptyState = document.getElementById('emptyState');
const globalMessage = document.getElementById('globalMessage');

const pollers = new Map();

function setAuthorized(nextAuthorized) {
    isAuthorized = nextAuthorized;
    authSection.hidden = nextAuthorized;
    workspace.hidden = !nextAuthorized;
}

function showMessage(text, type = 'error') {
    globalMessage.hidden = false;
    globalMessage.className = `message ${type}`;
    globalMessage.textContent = text;
}

function hideMessage() {
    globalMessage.hidden = true;
    globalMessage.textContent = '';
    globalMessage.className = 'message';
}

function setLoading(isLoading) {
    loading.hidden = !isLoading;
}

function stopAllPollers() {
    for (const intervalId of pollers.values()) {
        clearInterval(intervalId);
    }
    pollers.clear();
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));

    if (!response.ok || data.success === false) {
        const error = new Error(data.message || `Request failed (${response.status})`);
        error.status = response.status;
        throw error;
    }

    return data;
}

function renderSummary(file) {
    const wrapper = document.createElement('section');
    wrapper.className = 'summary';

    if (file.type !== 'pdf') {
        wrapper.innerHTML = '<p>图片文件无需摘要。</p>';
        return wrapper;
    }

    if (file.summary_status === 'done' && file.summary_json) {
        const summary = file.summary_json;
        wrapper.innerHTML = '';

        const title = document.createElement('h4');
        title.textContent = 'AI 摘要';
        wrapper.appendChild(title);

        const oneLine = document.createElement('p');
        oneLine.textContent = `一句话：${summary.one_line_summary}`;
        wrapper.appendChild(oneLine);

        const keyPointsTitle = document.createElement('h4');
        keyPointsTitle.textContent = '关键点';
        wrapper.appendChild(keyPointsTitle);
        const keyPoints = document.createElement('ul');
        (summary.key_points || []).forEach((point) => {
            const li = document.createElement('li');
            li.textContent = point;
            keyPoints.appendChild(li);
        });
        wrapper.appendChild(keyPoints);

        const keywords = document.createElement('p');
        keywords.textContent = `关键词：${(summary.keywords || []).join(' / ')}`;
        wrapper.appendChild(keywords);

        const actionsTitle = document.createElement('h4');
        actionsTitle.textContent = '建议行动';
        wrapper.appendChild(actionsTitle);
        const actions = document.createElement('ul');
        (summary.suggested_actions || []).forEach((action) => {
            const li = document.createElement('li');
            li.textContent = action;
            actions.appendChild(li);
        });
        wrapper.appendChild(actions);

        return wrapper;
    }

    if (file.summary_status === 'failed') {
        wrapper.innerHTML = `<p>摘要生成失败：${file.summary_error || '未知错误'}</p>`;
        return wrapper;
    }

    wrapper.innerHTML = '<p>摘要生成中，请稍候...</p>';
    return wrapper;
}

function summaryStatusLabel(status) {
    switch (status) {
        case 'pending':
            return '排队中';
        case 'running':
            return '处理中';
        case 'done':
            return '已完成';
        case 'failed':
            return '失败';
        default:
            return '无需摘要';
    }
}

function ensurePolling(file) {
    if (!file.summary_job_id) {
        return;
    }

    if (!['pending', 'running'].includes(file.summary_status)) {
        if (pollers.has(file.summary_job_id)) {
            clearInterval(pollers.get(file.summary_job_id));
            pollers.delete(file.summary_job_id);
        }
        return;
    }

    if (pollers.has(file.summary_job_id)) {
        return;
    }

    const intervalId = setInterval(async () => {
        try {
            const data = await requestJson(`/api/rooms/${roomSlug}/jobs/${file.summary_job_id}`);
            const status = data.job.status;

            if (status === 'done' || status === 'failed') {
                clearInterval(intervalId);
                pollers.delete(file.summary_job_id);
                loadFiles();
            }
        } catch (error) {
            clearInterval(intervalId);
            pollers.delete(file.summary_job_id);

            if (error.status === 401) {
                setAuthorized(false);
                showMessage('房间授权已过期，请重新输入口令。');
            }
        }
    }, 2000);

    pollers.set(file.summary_job_id, intervalId);
}

function createFileCard(file) {
    const card = document.createElement('article');
    card.className = 'file-card';

    const name = document.createElement('h3');
    name.textContent = file.original_name || file.filename;
    card.appendChild(name);

    const meta = document.createElement('div');
    meta.className = 'file-meta';
    meta.innerHTML = `
        <span>大小：${file.size_mb} MB</span>
        <span>时间：${file.modified}</span>
        <span>类型：${file.type.toUpperCase()}</span>
    `;
    card.appendChild(meta);

    const badge = document.createElement('span');
    badge.className = `badge ${file.summary_status}`;
    badge.textContent = `摘要状态：${summaryStatusLabel(file.summary_status)}`;
    card.appendChild(badge);

    card.appendChild(renderSummary(file));

    const actions = document.createElement('div');
    actions.className = 'file-actions';

    const viewLink = document.createElement('a');
    viewLink.href = file.url;
    viewLink.target = '_blank';
    viewLink.rel = 'noopener noreferrer';
    viewLink.textContent = '查看文件';

    const deleteButton = document.createElement('button');
    deleteButton.className = 'danger';
    deleteButton.textContent = '删除文件';
    deleteButton.addEventListener('click', () => deleteFile(file));

    actions.appendChild(viewLink);
    actions.appendChild(deleteButton);

    card.appendChild(actions);

    ensurePolling(file);

    return card;
}

async function loadFiles() {
    if (!isAuthorized) {
        return;
    }

    hideMessage();
    setLoading(true);

    try {
        const data = await requestJson(`/api/rooms/${roomSlug}/files`);
        const files = data.files || [];

        fileList.innerHTML = '';

        if (files.length === 0) {
            emptyState.hidden = false;
        } else {
            emptyState.hidden = true;
            files.forEach((file) => {
                fileList.appendChild(createFileCard(file));
            });
        }
    } catch (error) {
        if (error.status === 401) {
            setAuthorized(false);
            showMessage('房间授权已过期，请重新输入口令。');
        } else {
            showMessage(error.message);
        }
    } finally {
        setLoading(false);
    }
}

async function deleteFile(file) {
    const confirmed = window.confirm(`删除文件会同时删除摘要结果，确认删除 “${file.original_name || file.filename}” 吗？`);
    if (!confirmed) {
        return;
    }

    try {
        await requestJson(`/api/rooms/${roomSlug}/files/${file.id}`, {
            method: 'DELETE',
        });
        showMessage('文件已删除。', 'success');
        await loadFiles();
    } catch (error) {
        showMessage(error.message);
    }
}

authForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideMessage();

    const passcode = document.getElementById('authPasscode').value;
    const submitButton = authForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;

    try {
        await requestJson(`/api/rooms/${roomSlug}/auth`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ passcode }),
        });

        setAuthorized(true);
        showMessage(`房间 ${roomName} 已解锁。`, 'success');
        await loadFiles();
    } catch (error) {
        showMessage(error.message);
    } finally {
        submitButton.disabled = false;
    }
});

uploadForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideMessage();

    const selectedFile = fileInput.files?.[0];
    if (!selectedFile) {
        showMessage('请先选择文件。');
        return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);

    uploadButton.disabled = true;
    try {
        const data = await requestJson(`/api/rooms/${roomSlug}/upload`, {
            method: 'POST',
            body: formData,
        });

        const fileName = data.file?.original_name || data.file?.filename || selectedFile.name;
        showMessage(`上传成功：${fileName}`, 'success');
        fileInput.value = '';
        await loadFiles();
    } catch (error) {
        showMessage(error.message);
    } finally {
        uploadButton.disabled = false;
    }
});

refreshButton?.addEventListener('click', async () => {
    await loadFiles();
});

window.addEventListener('beforeunload', () => {
    stopAllPollers();
});

setAuthorized(isAuthorized);
if (isAuthorized) {
    loadFiles();
}
