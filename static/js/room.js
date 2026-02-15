const roomSlug = document.body.dataset.roomSlug;
const roomName = document.body.dataset.roomName;

const authSection = document.getElementById("authSection");
const workspace = document.getElementById("workspace");
const authForm = document.getElementById("authForm");
const uploadForm = document.getElementById("uploadForm");
const fileInput = document.getElementById("fileInput");
const uploadButton = document.getElementById("uploadButton");
const refreshButton = document.getElementById("refreshButton");
const fileList = document.getElementById("fileList");
const loading = document.getElementById("loading");
const emptyState = document.getElementById("emptyState");
const globalMessage = document.getElementById("globalMessage");

const shareLink = document.getElementById("shareLink");
const copyRoomLinkButton = document.getElementById("copyRoomLinkButton");

const metricTotal = document.getElementById("metricTotal");
const metricStarred = document.getElementById("metricStarred");
const metricUnread = document.getElementById("metricUnread");

const viewerNicknameValue = document.getElementById("viewerNicknameValue");
const editNicknameButton = document.getElementById("editNicknameButton");

const onlyStarredToggle = document.getElementById("onlyStarredToggle");
const onlyUnreadToggle = document.getElementById("onlyUnreadToggle");
const clearFiltersButton = document.getElementById("clearFiltersButton");

const nicknameModal = document.getElementById("nicknameModal");
const nicknameForm = document.getElementById("nicknameForm");
const nicknameInput = document.getElementById("nicknameInput");
const nicknameSubmitButton = document.getElementById("nicknameSubmitButton");
const nicknameSkipButton = document.getElementById("nicknameSkipButton");

const commentDrawer = document.getElementById("commentDrawer");
const closeCommentDrawerButton = document.getElementById("closeCommentDrawerButton");
const commentFileMeta = document.getElementById("commentFileMeta");
const commentList = document.getElementById("commentList");
const commentForm = document.getElementById("commentForm");
const commentInput = document.getElementById("commentInput");
const submitCommentButton = document.getElementById("submitCommentButton");

const state = {
    isAuthorized: document.body.dataset.authorized === "true",
    files: [],
    viewer: {
        has_profile: false,
        nickname: "",
    },
    metrics: {
        total_files: 0,
        starred_files: 0,
        unread_files: 0,
    },
    filters: {
        onlyStarred: false,
        onlyUnread: false,
    },
    activeCommentFileId: null,
    pollers: new Map(),
};

function showMessage(text, type = "error") {
    globalMessage.hidden = false;
    globalMessage.className = `message ${type}`;
    globalMessage.textContent = text;
}

function hideMessage() {
    globalMessage.hidden = true;
    globalMessage.className = "message";
    globalMessage.textContent = "";
}

function setLoading(isLoading) {
    loading.hidden = !isLoading;
}

function setButtonLoading(button, isLoading, label = "处理中...") {
    if (!button) {
        return;
    }
    if (isLoading) {
        button.dataset.originalText = button.textContent;
        button.textContent = label;
        button.disabled = true;
        return;
    }
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
}

function setAuthorized(nextAuthorized) {
    state.isAuthorized = nextAuthorized;
    authSection.hidden = nextAuthorized;
    workspace.hidden = !nextAuthorized;
    if (!nextAuthorized) {
        closeNicknameModal();
        closeCommentDrawer();
    }
}

function handleAuthExpired() {
    stopAllPollers();
    setAuthorized(false);
    showMessage("房间授权已过期，请重新输入口令。");
}

function stopAllPollers() {
    for (const timer of state.pollers.values()) {
        clearInterval(timer);
    }
    state.pollers.clear();
}

async function copyText(value) {
    if (!value) {
        throw new Error("没有可复制的内容。");
    }
    if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        return;
    }
    const fallback = document.createElement("textarea");
    fallback.value = value;
    fallback.style.position = "fixed";
    fallback.style.opacity = "0";
    document.body.appendChild(fallback);
    fallback.select();
    document.execCommand("copy");
    document.body.removeChild(fallback);
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

function summaryStatusLabel(status) {
    switch (status) {
        case "pending":
            return "排队中";
        case "running":
            return "处理中";
        case "done":
            return "已完成";
        case "failed":
            return "失败";
        default:
            return "无需摘要";
    }
}

function applyFilters(files) {
    return files.filter((file) => {
        if (state.filters.onlyStarred && !file.collab?.starred_by_me) {
            return false;
        }
        if (state.filters.onlyUnread && file.collab?.read_by_me) {
            return false;
        }
        return true;
    });
}

function updateViewerBlock() {
    if (state.viewer.has_profile) {
        viewerNicknameValue.textContent = state.viewer.nickname;
        editNicknameButton.textContent = "修改昵称";
        return;
    }
    viewerNicknameValue.textContent = "未设置昵称";
    editNicknameButton.textContent = "设置昵称";
}

function updateMetricsBlock() {
    metricTotal.textContent = `文件 ${state.metrics.total_files || 0}`;
    metricStarred.textContent = `星标 ${state.metrics.starred_files || 0}`;
    metricUnread.textContent = `未读 ${state.metrics.unread_files || 0}`;
}

function openNicknameModal(forceFocus = true) {
    nicknameInput.value = state.viewer.nickname || "";
    nicknameModal.hidden = false;
    document.body.style.overflow = "hidden";
    if (forceFocus) {
        setTimeout(() => nicknameInput.focus(), 20);
    }
}

function closeNicknameModal() {
    nicknameModal.hidden = true;
    document.body.style.overflow = "";
}

function requireProfile(actionHint) {
    if (state.viewer.has_profile) {
        return true;
    }
    showMessage(`请先设置昵称再进行${actionHint}。`, "info");
    openNicknameModal();
    return false;
}

function renderSummary(file) {
    const wrapper = document.createElement("section");
    wrapper.className = "summary";

    if (file.type !== "pdf") {
        wrapper.innerHTML = '<p class="summary-text">图片文件无需摘要。</p>';
        return wrapper;
    }

    if (file.summary_status === "done" && file.summary_json) {
        const summary = file.summary_json;
        wrapper.innerHTML = "";

        const title = document.createElement("h4");
        title.textContent = "AI 摘要";
        wrapper.appendChild(title);

        const oneLine = document.createElement("p");
        oneLine.textContent = `一句话：${summary.one_line_summary}`;
        wrapper.appendChild(oneLine);

        const keyPointsTitle = document.createElement("h4");
        keyPointsTitle.textContent = "关键点";
        wrapper.appendChild(keyPointsTitle);

        const keyPoints = document.createElement("ul");
        (summary.key_points || []).forEach((point) => {
            const li = document.createElement("li");
            li.textContent = point;
            keyPoints.appendChild(li);
        });
        wrapper.appendChild(keyPoints);

        const keywords = document.createElement("p");
        keywords.textContent = `关键词：${(summary.keywords || []).join(" / ")}`;
        wrapper.appendChild(keywords);

        const actionsTitle = document.createElement("h4");
        actionsTitle.textContent = "建议行动";
        wrapper.appendChild(actionsTitle);

        const actions = document.createElement("ul");
        (summary.suggested_actions || []).forEach((action) => {
            const li = document.createElement("li");
            li.textContent = action;
            actions.appendChild(li);
        });
        wrapper.appendChild(actions);
        return wrapper;
    }

    if (file.summary_status === "failed") {
        wrapper.innerHTML = `<p class="summary-text">摘要生成失败：${file.summary_error || "未知错误"}</p>`;
        return wrapper;
    }

    wrapper.innerHTML = '<p class="summary-text">摘要生成中，请稍候...</p>';
    return wrapper;
}

function ensurePolling(file) {
    if (!file.summary_job_id) {
        return;
    }

    if (!["pending", "running"].includes(file.summary_status)) {
        const staleTimer = state.pollers.get(file.summary_job_id);
        if (staleTimer) {
            clearInterval(staleTimer);
            state.pollers.delete(file.summary_job_id);
        }
        return;
    }

    if (state.pollers.has(file.summary_job_id)) {
        return;
    }

    const timer = setInterval(async () => {
        try {
            const data = await requestJson(`/api/rooms/${roomSlug}/jobs/${file.summary_job_id}`);
            if (["done", "failed"].includes(data.job.status)) {
                clearInterval(timer);
                state.pollers.delete(file.summary_job_id);
                await loadFiles();
            }
        } catch (error) {
            clearInterval(timer);
            state.pollers.delete(file.summary_job_id);
            if (error.status === 401) {
                handleAuthExpired();
            }
        }
    }, 2000);

    state.pollers.set(file.summary_job_id, timer);
}

function createFileCard(file, index) {
    const card = document.createElement("article");
    card.className = "file-card";
    card.style.animationDelay = `${index * 40}ms`;

    const cardHead = document.createElement("div");
    cardHead.className = "file-card-head";

    const titleBlock = document.createElement("div");
    const name = document.createElement("h3");
    name.textContent = file.original_name || file.filename;
    titleBlock.appendChild(name);

    const meta = document.createElement("div");
    meta.className = "file-meta";
    meta.innerHTML = `
        <span>大小：${file.size_mb} MB</span>
        <span>时间：${file.modified}</span>
        <span>类型：${String(file.type || "").toUpperCase()}</span>
    `;
    titleBlock.appendChild(meta);

    const badge = document.createElement("span");
    badge.className = `badge ${file.summary_status}`;
    badge.textContent = `摘要状态：${summaryStatusLabel(file.summary_status)}`;

    cardHead.appendChild(titleBlock);
    cardHead.appendChild(badge);
    card.appendChild(cardHead);

    const collabSection = document.createElement("section");
    collabSection.className = "collab-section";

    const collabMetrics = document.createElement("div");
    collabMetrics.className = "collab-metrics";
    collabMetrics.innerHTML = `
        <span>评论 ${file.collab?.comment_count || 0}</span>
        <span>星标 ${file.collab?.star_count || 0}</span>
        <span>已读 ${file.collab?.read_count || 0}</span>
    `;

    const collabActions = document.createElement("div");
    collabActions.className = "collab-actions";

    const starButton = document.createElement("button");
    starButton.type = "button";
    starButton.className = `btn-secondary btn-star ${file.collab?.starred_by_me ? "active" : ""}`.trim();
    starButton.textContent = file.collab?.starred_by_me ? "取消星标" : "设为星标";
    starButton.disabled = !state.viewer.has_profile;
    starButton.addEventListener("click", () => toggleFileStar(file));

    const readButton = document.createElement("button");
    readButton.type = "button";
    readButton.className = `btn-secondary btn-read ${file.collab?.read_by_me ? "active" : ""}`.trim();
    readButton.textContent = file.collab?.read_by_me ? "标为未读" : "标为已读";
    readButton.disabled = !state.viewer.has_profile;
    readButton.addEventListener("click", () => toggleFileRead(file));

    const commentButton = document.createElement("button");
    commentButton.type = "button";
    commentButton.className = "btn-secondary";
    commentButton.textContent = `评论 (${file.collab?.comment_count || 0})`;
    commentButton.disabled = !state.viewer.has_profile;
    commentButton.addEventListener("click", () => openCommentDrawer(file));

    collabActions.appendChild(starButton);
    collabActions.appendChild(readButton);
    collabActions.appendChild(commentButton);

    collabSection.appendChild(collabMetrics);
    collabSection.appendChild(collabActions);
    card.appendChild(collabSection);

    card.appendChild(renderSummary(file));

    const fileActions = document.createElement("div");
    fileActions.className = "file-actions";

    const viewLink = document.createElement("a");
    viewLink.href = file.url;
    viewLink.target = "_blank";
    viewLink.rel = "noopener noreferrer";
    viewLink.textContent = "查看文件";

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "danger";
    deleteButton.textContent = "删除文件";
    deleteButton.addEventListener("click", () => deleteFile(file));

    fileActions.appendChild(viewLink);
    fileActions.appendChild(deleteButton);
    card.appendChild(fileActions);

    ensurePolling(file);
    return card;
}

function renderFiles() {
    const visibleFiles = applyFilters(state.files);
    fileList.innerHTML = "";

    if (visibleFiles.length === 0) {
        emptyState.hidden = false;
    } else {
        emptyState.hidden = true;
        visibleFiles.forEach((file, index) => {
            fileList.appendChild(createFileCard(file, index));
        });
    }

    if (state.activeCommentFileId) {
        const currentFile = state.files.find((item) => item.id === state.activeCommentFileId);
        if (!currentFile) {
            closeCommentDrawer();
        } else {
            commentFileMeta.textContent = currentFile.original_name || currentFile.filename;
        }
    }
}

async function fetchProfile() {
    if (!state.isAuthorized) {
        return;
    }
    const data = await requestJson(`/api/rooms/${roomSlug}/profile`);
    state.viewer = data.viewer || {has_profile: false, nickname: ""};
    updateViewerBlock();
}

async function loadFiles() {
    if (!state.isAuthorized) {
        return;
    }

    setLoading(true);
    hideMessage();

    try {
        const data = await requestJson(`/api/rooms/${roomSlug}/files`);
        state.files = data.files || [];
        state.metrics = data.metrics || state.metrics;
        state.viewer = data.viewer || state.viewer;
        updateViewerBlock();
        updateMetricsBlock();
        renderFiles();
    } catch (error) {
        if (error.status === 401) {
            handleAuthExpired();
            return;
        }
        showMessage(error.message);
    } finally {
        setLoading(false);
    }
}

async function initializeWorkspace() {
    try {
        await fetchProfile();
        if (!state.viewer.has_profile) {
            openNicknameModal(false);
        }
    } catch (error) {
        if (error.status === 401) {
            handleAuthExpired();
            return;
        }
        showMessage(error.message);
    }
    await loadFiles();
}

async function deleteFile(file) {
    const confirmed = window.confirm(`删除文件会同时删除摘要结果，确认删除 “${file.original_name || file.filename}” 吗？`);
    if (!confirmed) {
        return;
    }

    try {
        await requestJson(`/api/rooms/${roomSlug}/files/${file.id}`, {
            method: "DELETE",
        });
        showMessage("文件已删除。", "success");
        await loadFiles();
    } catch (error) {
        if (error.status === 401) {
            handleAuthExpired();
            return;
        }
        showMessage(error.message);
    }
}

async function toggleFileStar(file) {
    if (!requireProfile("星标")) {
        return;
    }

    try {
        await requestJson(`/api/rooms/${roomSlug}/files/${file.id}/star`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({starred: !file.collab?.starred_by_me}),
        });
        await loadFiles();
    } catch (error) {
        if (error.status === 401) {
            handleAuthExpired();
            return;
        }
        showMessage(error.message);
    }
}

async function toggleFileRead(file) {
    if (!requireProfile("已读状态")) {
        return;
    }

    try {
        await requestJson(`/api/rooms/${roomSlug}/files/${file.id}/read`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({read: !file.collab?.read_by_me}),
        });
        await loadFiles();
    } catch (error) {
        if (error.status === 401) {
            handleAuthExpired();
            return;
        }
        showMessage(error.message);
    }
}

function renderComments(comments) {
    commentList.innerHTML = "";
    if (!comments || comments.length === 0) {
        const empty = document.createElement("p");
        empty.className = "summary-text";
        empty.textContent = "暂无评论，写下第一条观点吧。";
        commentList.appendChild(empty);
        return;
    }

    comments.forEach((comment) => {
        const item = document.createElement("article");
        item.className = "comment-item";
        item.innerHTML = `
            <div class="comment-item-head">
                <strong>${comment.nickname}</strong>
                <span>${comment.created_at.replace("T", " ").replace("Z", "")}</span>
            </div>
            <p>${comment.content}</p>
        `;
        commentList.appendChild(item);
    });
}

async function loadComments(fileId) {
    try {
        const data = await requestJson(`/api/rooms/${roomSlug}/files/${fileId}/comments`);
        renderComments(data.comments || []);
    } catch (error) {
        if (error.status === 401) {
            handleAuthExpired();
            return;
        }
        showMessage(error.message);
    }
}

async function openCommentDrawer(file) {
    if (!requireProfile("评论")) {
        return;
    }
    state.activeCommentFileId = file.id;
    commentFileMeta.textContent = file.original_name || file.filename;
    commentList.innerHTML = "";
    commentInput.value = "";
    commentDrawer.hidden = false;
    await loadComments(file.id);
}

function closeCommentDrawer() {
    state.activeCommentFileId = null;
    commentDrawer.hidden = true;
}

authForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideMessage();

    const passcode = document.getElementById("authPasscode").value;
    const submitButton = authForm.querySelector('button[type="submit"]');

    try {
        setButtonLoading(submitButton, true, "验证中...");
        await requestJson(`/api/rooms/${roomSlug}/auth`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({passcode}),
        });

        setAuthorized(true);
        showMessage(`房间 ${roomName} 已解锁。`, "success");
        await initializeWorkspace();
    } catch (error) {
        showMessage(error.message);
    } finally {
        setButtonLoading(submitButton, false);
    }
});

uploadForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideMessage();

    const selectedFile = fileInput.files?.[0];
    if (!selectedFile) {
        showMessage("请先选择文件。");
        return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
        setButtonLoading(uploadButton, true, "上传中...");
        const data = await requestJson(`/api/rooms/${roomSlug}/upload`, {
            method: "POST",
            body: formData,
        });
        const fileName = data.file?.original_name || data.file?.filename || selectedFile.name;
        showMessage(`上传成功：${fileName}`, "success");
        fileInput.value = "";
        await loadFiles();
    } catch (error) {
        if (error.status === 401) {
            handleAuthExpired();
            return;
        }
        showMessage(error.message);
    } finally {
        setButtonLoading(uploadButton, false);
    }
});

refreshButton?.addEventListener("click", async () => {
    await loadFiles();
});

copyRoomLinkButton?.addEventListener("click", async () => {
    hideMessage();
    try {
        await copyText(shareLink.href);
        showMessage("房间链接已复制。", "success");
    } catch (error) {
        showMessage(error.message || "复制失败，请手动复制。");
    }
});

editNicknameButton?.addEventListener("click", () => {
    openNicknameModal();
});

nicknameSkipButton?.addEventListener("click", () => {
    closeNicknameModal();
});

nicknameForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideMessage();

    const nickname = nicknameInput.value.trim();
    if (nickname.length < 2 || nickname.length > 20) {
        showMessage("昵称长度需在 2 到 20 个字符之间。");
        return;
    }

    try {
        setButtonLoading(nicknameSubmitButton, true, "保存中...");
        await requestJson(`/api/rooms/${roomSlug}/profile`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({nickname}),
        });

        state.viewer = {
            has_profile: true,
            nickname,
        };
        updateViewerBlock();
        closeNicknameModal();
        showMessage("昵称已保存。", "success");
        await loadFiles();
    } catch (error) {
        if (error.status === 401) {
            handleAuthExpired();
            return;
        }
        showMessage(error.message);
    } finally {
        setButtonLoading(nicknameSubmitButton, false);
    }
});

commentForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideMessage();

    if (!state.activeCommentFileId) {
        showMessage("未选择评论文件。");
        return;
    }
    if (!requireProfile("评论")) {
        return;
    }

    const content = commentInput.value.trim();
    if (!content) {
        showMessage("评论不能为空。");
        return;
    }
    if (content.length > 300) {
        showMessage("评论不能超过 300 字。");
        return;
    }

    try {
        setButtonLoading(submitCommentButton, true, "发布中...");
        await requestJson(`/api/rooms/${roomSlug}/files/${state.activeCommentFileId}/comments`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({content}),
        });

        commentInput.value = "";
        await Promise.all([loadComments(state.activeCommentFileId), loadFiles()]);
        showMessage("评论已发布。", "success");
    } catch (error) {
        if (error.status === 401) {
            handleAuthExpired();
            return;
        }
        showMessage(error.message);
    } finally {
        setButtonLoading(submitCommentButton, false);
    }
});

closeCommentDrawerButton?.addEventListener("click", () => {
    closeCommentDrawer();
});

commentDrawer?.addEventListener("click", (event) => {
    if (event.target === commentDrawer) {
        closeCommentDrawer();
    }
});

onlyStarredToggle?.addEventListener("change", () => {
    state.filters.onlyStarred = onlyStarredToggle.checked;
    renderFiles();
});

onlyUnreadToggle?.addEventListener("change", () => {
    state.filters.onlyUnread = onlyUnreadToggle.checked;
    renderFiles();
});

clearFiltersButton?.addEventListener("click", () => {
    state.filters.onlyStarred = false;
    state.filters.onlyUnread = false;
    onlyStarredToggle.checked = false;
    onlyUnreadToggle.checked = false;
    renderFiles();
});

window.addEventListener("beforeunload", () => {
    stopAllPollers();
});

setAuthorized(state.isAuthorized);
if (state.isAuthorized) {
    initializeWorkspace();
}
