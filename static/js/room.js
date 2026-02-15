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
const myUploadShortcuts = document.getElementById("myUploadShortcuts");
const editNicknameButton = document.getElementById("editNicknameButton");
const onlyStarredToggle = document.getElementById("onlyStarredToggle");
const onlyUnreadToggle = document.getElementById("onlyUnreadToggle");
const uploaderFilterSelect = document.getElementById("uploaderFilterSelect");
const clearFiltersButton = document.getElementById("clearFiltersButton");

const endDiscussionButton = document.getElementById("endDiscussionButton");
const discussionStatusText = document.getElementById("discussionStatusText");
const discussionSummaryContainer = document.getElementById("discussionSummaryContainer");

const collaboratorPriorityRow = document.getElementById("collaboratorPriorityRow");
const collaboratorList = document.getElementById("collaboratorList");
const pdfCatalogList = document.getElementById("pdfCatalogList");
const imageCatalogList = document.getElementById("imageCatalogList");

const commentFileMeta = document.getElementById("commentFileMeta");
const commentList = document.getElementById("commentList");
const commentForm = document.getElementById("commentForm");
const commentInput = document.getElementById("commentInput");
const submitCommentButton = document.getElementById("submitCommentButton");
const newCommentBadge = document.getElementById("newCommentBadge");

const nicknameModal = document.getElementById("nicknameModal");
const nicknameForm = document.getElementById("nicknameForm");
const nicknameInput = document.getElementById("nicknameInput");
const nicknameSubmitButton = document.getElementById("nicknameSubmitButton");
const nicknameSkipButton = document.getElementById("nicknameSkipButton");

const state = {
    isAuthorized: document.body.dataset.authorized === "true",
    viewer: {has_profile: false, nickname: "", viewer_token: "", is_owner: false},
    filters: {onlyStarred: false, onlyUnread: false, uploaderToken: ""},
    files: [],
    collaborators: [],
    selectedFileId: null,
    comments: [],
    commentsAfterId: 0,
    newCommentCount: 0,
    discussion: {status: "idle", ended_at: null, summary_version: 0, is_owner: false},
    discussionSummary: null,
    pollers: {presence: null, room: null, comments: null, discussion: null},
};

function setAuthorized(nextAuthorized) {
    state.isAuthorized = nextAuthorized;
    authSection.hidden = nextAuthorized;
    workspace.hidden = !nextAuthorized;
}

function setLoading(isLoading) {
    loading.hidden = !isLoading;
}

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

function setButtonLoading(button, isLoading, label = "处理中...") {
    if (!button) return;
    if (isLoading) {
        button.dataset.originalText = button.textContent;
        button.textContent = label;
        button.disabled = true;
        return;
    }
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
}

function stopAllPollers() {
    Object.keys(state.pollers).forEach((key) => {
        if (state.pollers[key]) {
            clearInterval(state.pollers[key]);
            state.pollers[key] = null;
        }
    });
}

function handleAuthExpired() {
    stopAllPollers();
    setAuthorized(false);
    showMessage("房间授权已过期，请重新输入口令。");
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

async function copyText(value) {
    if (!value) throw new Error("没有可复制的内容。");
    if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        return;
    }
    const input = document.createElement("textarea");
    input.value = value;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    document.body.removeChild(input);
}

function openNicknameModal() {
    nicknameInput.value = state.viewer.nickname || "";
    nicknameModal.hidden = false;
    document.body.style.overflow = "hidden";
}

function closeNicknameModal() {
    nicknameModal.hidden = true;
    document.body.style.overflow = "";
}

function requireProfile(actionHint) {
    if (state.viewer.has_profile) return true;
    showMessage(`请先设置昵称再进行${actionHint}。`, "info");
    openNicknameModal();
    return false;
}

function summaryStatusLabel(status) {
    if (status === "pending") return "排队中";
    if (status === "running") return "处理中";
    if (status === "done") return "已完成";
    if (status === "failed") return "失败";
    return "无需摘要";
}

function updateMetrics() {
    metricTotal.textContent = `文件 ${state.files.length}`;
    metricStarred.textContent = `星标 ${state.files.filter((item) => item.collab?.starred_by_me).length}`;
    metricUnread.textContent = `未读 ${state.files.filter((item) => !item.collab?.read_by_me).length}`;
}

function updateViewerSection() {
    viewerNicknameValue.textContent = state.viewer.has_profile ? state.viewer.nickname : "未设置昵称";
    renderMyUploadShortcuts();
}

function applyClientFilters(files) {
    return files.filter((file) => {
        if (state.filters.onlyStarred && !file.collab?.starred_by_me) return false;
        if (state.filters.onlyUnread && file.collab?.read_by_me) return false;
        return true;
    });
}

function renderSummary(file) {
    const wrapper = document.createElement("section");
    wrapper.className = "summary";

    if (file.type !== "pdf") {
        wrapper.innerHTML = "<p>图片文件无需摘要。</p>";
        return wrapper;
    }

    if (file.summary_status === "done" && file.summary_json) {
        const summary = file.summary_json;
        wrapper.innerHTML = `
            <h4>AI 摘要</h4>
            <p>一句话：${summary.one_line_summary}</p>
            <h4>关键点</h4>
            <ul>${(summary.key_points || []).map((point) => `<li>${point}</li>`).join("")}</ul>
            <p>关键词：${(summary.keywords || []).join(" / ")}</p>
            <h4>建议行动</h4>
            <ul>${(summary.suggested_actions || []).map((point) => `<li>${point}</li>`).join("")}</ul>
        `;
        return wrapper;
    }

    if (file.summary_status === "failed") {
        wrapper.innerHTML = `<p>摘要生成失败：${file.summary_error || "未知错误"}</p>`;
        return wrapper;
    }

    wrapper.innerHTML = "<p>摘要生成中，请稍候...</p>";
    return wrapper;
}

function getSelectedFile() {
    return state.files.find((item) => item.id === state.selectedFileId) || null;
}

function createFileCard(file) {
    const card = document.createElement("article");
    card.className = "file-card";
    if (state.selectedFileId === file.id) card.classList.add("selected");

    const title = file.original_name || file.filename;
    card.innerHTML = `
        <div class="file-card-head">
            <div>
                <h3>${title}</h3>
                <div class="file-meta">
                    <span>上传者：${file.uploader_nickname || "未命名上传者"}</span>
                    <span>大小：${file.size_mb} MB</span>
                    <span>时间：${file.modified}</span>
                    <span>类型：${String(file.type || "").toUpperCase()}</span>
                </div>
            </div>
            <span class="badge ${file.summary_status}">摘要状态：${summaryStatusLabel(file.summary_status)}</span>
        </div>
        <div class="collab-section">
            <span class="collab-metric">评论 ${file.collab?.comment_count || 0}</span>
            <span class="collab-metric">星标 ${file.collab?.star_count || 0}</span>
            <span class="collab-metric">已读 ${file.collab?.read_count || 0}</span>
        </div>
    `;
    card.appendChild(renderSummary(file));

    const actions = document.createElement("div");
    actions.className = "file-actions";

    const viewLink = document.createElement("a");
    viewLink.href = file.url;
    viewLink.target = "_blank";
    viewLink.rel = "noopener noreferrer";
    viewLink.textContent = "查看文件";
    actions.appendChild(viewLink);

    const commentBtn = document.createElement("button");
    commentBtn.type = "button";
    commentBtn.className = "btn-secondary";
    commentBtn.textContent = "查看评论";
    commentBtn.addEventListener("click", () => selectFile(file.id));
    actions.appendChild(commentBtn);

    const starBtn = document.createElement("button");
    starBtn.type = "button";
    starBtn.className = "btn-secondary";
    starBtn.textContent = file.collab?.starred_by_me ? "取消星标" : "设为星标";
    starBtn.disabled = !state.viewer.has_profile;
    starBtn.addEventListener("click", () => toggleFileStar(file));
    actions.appendChild(starBtn);

    const readBtn = document.createElement("button");
    readBtn.type = "button";
    readBtn.className = "btn-secondary";
    readBtn.textContent = file.collab?.read_by_me ? "标为未读" : "标为已读";
    readBtn.disabled = !state.viewer.has_profile;
    readBtn.addEventListener("click", () => toggleFileRead(file));
    actions.appendChild(readBtn);

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "danger";
    deleteBtn.textContent = "删除文件";
    deleteBtn.addEventListener("click", () => deleteFile(file));
    actions.appendChild(deleteBtn);

    card.appendChild(actions);
    return card;
}

function renderCatalog(files) {
    const pdfFiles = files.filter((item) => item.type === "pdf");
    const imageFiles = files.filter((item) => item.type === "image");
    pdfCatalogList.innerHTML = "";
    imageCatalogList.innerHTML = "";

    const appendChip = (file, container) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = `file-icon-chip ${state.selectedFileId === file.id ? "active" : ""}`.trim();
        chip.textContent = file.original_name || file.filename;
        chip.title = file.original_name || file.filename;
        chip.addEventListener("click", () => selectFile(file.id));
        container.appendChild(chip);
    };

    pdfFiles.forEach((file) => appendChip(file, pdfCatalogList));
    imageFiles.forEach((file) => appendChip(file, imageCatalogList));
}

function renderFileList() {
    const visibleFiles = applyClientFilters(state.files);
    fileList.innerHTML = "";
    if (visibleFiles.length === 0) {
        emptyState.hidden = false;
    } else {
        emptyState.hidden = true;
        visibleFiles.forEach((file) => fileList.appendChild(createFileCard(file)));
    }
    renderCatalog(visibleFiles);
}

function onUploaderFileSelect(uploaderToken, fileId) {
    state.filters.uploaderToken = uploaderToken;
    uploaderFilterSelect.value = uploaderToken;
    state.selectedFileId = fileId;
    loadFiles();
}

function createUploaderPill(participant, priority = false) {
    const wrap = document.createElement("div");
    wrap.className = `uploader-pill ${priority ? "priority" : ""}`.trim();
    if (state.filters.uploaderToken === participant.viewer_token) wrap.classList.add("active");
    wrap.title = participant.is_online ? "在线" : "离线";

    const text = document.createElement("span");
    text.textContent = `${participant.is_online ? "●" : "○"} ${participant.nickname}`;
    wrap.appendChild(text);
    wrap.addEventListener("click", () => {
        state.filters.uploaderToken = participant.viewer_token;
        uploaderFilterSelect.value = participant.viewer_token;
        loadFiles();
    });

    (participant.recent_uploads || []).forEach((item) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "file-icon-chip";
        chip.textContent = item.type === "pdf" ? "PDF" : "IMG";
        chip.title = item.original_name;
        chip.addEventListener("click", (event) => {
            event.stopPropagation();
            onUploaderFileSelect(participant.viewer_token, item.id);
        });
        wrap.appendChild(chip);
    });
    if (participant.extra_upload_count > 0) {
        const extra = document.createElement("span");
        extra.className = "file-icon-chip";
        extra.textContent = `+${participant.extra_upload_count}`;
        wrap.appendChild(extra);
    }
    return wrap;
}

function renderUploaderFilterOptions() {
    const previous = state.filters.uploaderToken;
    uploaderFilterSelect.innerHTML = '<option value="">全部协作者</option>';
    state.collaborators.forEach((participant) => {
        const option = document.createElement("option");
        option.value = participant.viewer_token;
        option.textContent = participant.is_me ? `${participant.nickname}（我）` : participant.nickname;
        uploaderFilterSelect.appendChild(option);
    });
    uploaderFilterSelect.value = previous || "";
}

function renderMyUploadShortcuts() {
    myUploadShortcuts.innerHTML = "";
    const me = state.collaborators.find((item) => item.is_me);
    if (!me || !me.recent_uploads?.length) {
        myUploadShortcuts.innerHTML = '<p class="tips">暂无我的上传文件快捷入口。</p>';
        return;
    }
    me.recent_uploads.forEach((item) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "file-icon-chip";
        chip.textContent = item.type === "pdf" ? "PDF" : "IMG";
        chip.title = item.original_name;
        chip.addEventListener("click", () => onUploaderFileSelect(me.viewer_token, item.id));
        myUploadShortcuts.appendChild(chip);
    });
}

function renderCollaborators() {
    collaboratorPriorityRow.innerHTML = "";
    collaboratorList.innerHTML = "";
    const others = state.collaborators.filter((item) => !item.is_me);
    others.filter((item) => item.upload_count > 0).forEach((item) => {
        collaboratorPriorityRow.appendChild(createUploaderPill(item, true));
    });
    others.filter((item) => item.upload_count <= 0).forEach((item) => {
        collaboratorList.appendChild(createUploaderPill(item, false));
    });
    renderUploaderFilterOptions();
    renderMyUploadShortcuts();
}

function renderComments() {
    commentList.innerHTML = "";
    if (!state.selectedFileId) {
        commentFileMeta.textContent = "请先选择一个文件。";
        commentInput.disabled = true;
        submitCommentButton.disabled = true;
        return;
    }
    const selectedFile = getSelectedFile();
    commentFileMeta.textContent = selectedFile ? `当前文件：${selectedFile.original_name || selectedFile.filename}` : "当前文件不可用";
    commentInput.disabled = !state.viewer.has_profile;
    submitCommentButton.disabled = !state.viewer.has_profile;

    if (!state.comments.length) {
        commentList.innerHTML = '<p class="tips">暂无评论，写下第一条观点吧。</p>';
        return;
    }
    state.comments.forEach((comment) => {
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

function renderDiscussionSummary() {
    endDiscussionButton.hidden = !state.discussion?.is_owner;
    const status = state.discussion?.status || "idle";
    discussionStatusText.textContent =
        status === "running" ? "讨论总结生成中，正在实时刷新..." :
        status === "done" ? "讨论总结已生成，后续新评论会节流重算。" :
        status === "failed" ? "讨论总结生成失败，可再次尝试结束讨论。" :
        "讨论尚未结束。";

    discussionSummaryContainer.innerHTML = "";
    const payload = state.discussionSummary?.summary_json;
    if (!payload?.by_commented_owner?.length) {
        discussionSummaryContainer.innerHTML = '<p class="summary-placeholder">讨论结束后，这里会按被评论者分组展示可认领总结。</p>';
        return;
    }

    payload.by_commented_owner.forEach((group) => {
        const card = document.createElement("article");
        card.className = "summary-group";
        card.innerHTML = `<h4>被评论者：${group.owner_nickname}</h4>`;
        (group.files || []).forEach((fileItem) => {
            const title = document.createElement("p");
            title.innerHTML = `<strong>文件：</strong>${fileItem.file_name}`;
            card.appendChild(title);
            const ul = document.createElement("ul");
            (fileItem.comment_details || []).forEach((detail) => {
                const li = document.createElement("li");
                li.textContent = `${detail.commenter_nickname}：${detail.comment_content}`;
                ul.appendChild(li);
            });
            card.appendChild(ul);
        });
        const actionsTitle = document.createElement("p");
        actionsTitle.innerHTML = "<strong>待认领事项：</strong>";
        card.appendChild(actionsTitle);
        const actions = document.createElement("ul");
        (group.claimable_actions || []).forEach((action) => {
            const li = document.createElement("li");
            li.textContent = action;
            actions.appendChild(li);
        });
        card.appendChild(actions);
        discussionSummaryContainer.appendChild(card);
    });
}

async function fetchProfile() {
    const data = await requestJson(`/api/rooms/${roomSlug}/profile`);
    state.viewer = data.viewer || state.viewer;
    state.discussion = data.discussion || state.discussion;
    updateViewerSection();
    renderDiscussionSummary();
}

async function sendPresence() {
    if (!state.isAuthorized) return;
    try {
        await requestJson(`/api/rooms/${roomSlug}/presence`, {method: "POST"});
    } catch (error) {
        if (error.status === 401) handleAuthExpired();
    }
}

async function loadCollaborators() {
    if (!state.isAuthorized) return;
    const data = await requestJson(`/api/rooms/${roomSlug}/collaborators`);
    state.collaborators = data.collaborators || [];
    renderCollaborators();
}

async function loadFiles(silent = false) {
    if (!state.isAuthorized) return;
    if (!silent) setLoading(true);

    const params = new URLSearchParams();
    if (state.filters.uploaderToken) params.set("uploader_token", state.filters.uploaderToken);
    if (state.selectedFileId) params.set("selected_file_id", String(state.selectedFileId));

    try {
        const data = await requestJson(`/api/rooms/${roomSlug}/files?${params.toString()}`);
        state.files = data.files || [];
        state.discussion = data.discussion || state.discussion;
        updateMetrics();
        if (!state.selectedFileId || !state.files.some((item) => item.id === state.selectedFileId)) {
            state.selectedFileId = state.files[0]?.id || null;
            state.commentsAfterId = 0;
            state.comments = [];
        }
        renderFileList();
        renderDiscussionSummary();
        await loadComments(true);
    } finally {
        if (!silent) setLoading(false);
    }
}

async function loadComments(reset = false) {
    if (!state.selectedFileId) {
        state.comments = [];
        state.commentsAfterId = 0;
        renderComments();
        return;
    }
    const query = reset ? "" : `?after_id=${state.commentsAfterId || 0}`;
    const data = await requestJson(`/api/rooms/${roomSlug}/files/${state.selectedFileId}/comments${query}`);
    const list = data.comments || [];

    if (reset) {
        state.comments = list;
        state.newCommentCount = 0;
        newCommentBadge.hidden = true;
    } else if (list.length > 0) {
        state.comments.push(...list);
        state.newCommentCount += list.length;
        newCommentBadge.hidden = false;
        newCommentBadge.textContent = `有新评论 +${state.newCommentCount}`;
    }
    state.commentsAfterId = data.cursor?.after_id || state.commentsAfterId;
    renderComments();
}

async function loadDiscussionSummary() {
    if (!state.isAuthorized || !state.discussion?.ended_at) return;
    const data = await requestJson(`/api/rooms/${roomSlug}/discussion/summary`);
    state.discussion = data.discussion || state.discussion;
    state.discussionSummary = data.summary || null;
    renderDiscussionSummary();
    updateDiscussionPoller();
}

function updateDiscussionPoller() {
    if (state.pollers.discussion) {
        clearInterval(state.pollers.discussion);
        state.pollers.discussion = null;
    }
    if (!state.discussion?.ended_at) return;
    const intervalMs = state.discussion.status === "running" ? 3000 : 10000;
    state.pollers.discussion = setInterval(() => {
        loadDiscussionSummary().catch((error) => {
            if (error.status === 401) handleAuthExpired();
        });
    }, intervalMs);
}

function startPollers() {
    stopAllPollers();
    state.pollers.presence = setInterval(() => sendPresence(), 30000);
    state.pollers.room = setInterval(async () => {
        try {
            await Promise.all([loadCollaborators(), loadFiles(true)]);
        } catch (error) {
            if (error.status === 401) handleAuthExpired();
        }
    }, 5000);
    state.pollers.comments = setInterval(() => {
        loadComments(false).catch((error) => {
            if (error.status === 401) handleAuthExpired();
        });
    }, 2000);
    updateDiscussionPoller();
}

function selectFile(fileId) {
    state.selectedFileId = fileId;
    state.newCommentCount = 0;
    newCommentBadge.hidden = true;
    renderFileList();
    loadComments(true).catch((error) => {
        if (error.status === 401) handleAuthExpired();
    });
}

async function initializeWorkspace() {
    await fetchProfile();
    await sendPresence();
    await Promise.all([loadCollaborators(), loadFiles(), loadDiscussionSummary()]);
    if (!state.viewer.has_profile) openNicknameModal();
    startPollers();
}

async function toggleFileStar(file) {
    if (!requireProfile("星标")) return;
    await requestJson(`/api/rooms/${roomSlug}/files/${file.id}/star`, {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({starred: !file.collab?.starred_by_me}),
    });
    await loadFiles(true);
}

async function toggleFileRead(file) {
    if (!requireProfile("已读状态")) return;
    await requestJson(`/api/rooms/${roomSlug}/files/${file.id}/read`, {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({read: !file.collab?.read_by_me}),
    });
    await loadFiles(true);
}

async function deleteFile(file) {
    const confirmed = window.confirm(`确认删除“${file.original_name || file.filename}”？`);
    if (!confirmed) return;
    await requestJson(`/api/rooms/${roomSlug}/files/${file.id}`, {method: "DELETE"});
    showMessage("文件已删除。", "success");
    await loadFiles();
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
    if (!requireProfile("上传")) return;
    const selectedFile = fileInput.files?.[0];
    if (!selectedFile) {
        showMessage("请先选择文件。");
        return;
    }
    const formData = new FormData();
    formData.append("file", selectedFile);
    try {
        setButtonLoading(uploadButton, true, "上传中...");
        const data = await requestJson(`/api/rooms/${roomSlug}/upload`, {method: "POST", body: formData});
        fileInput.value = "";
        state.selectedFileId = data.file?.id || state.selectedFileId;
        showMessage(`上传成功：${data.file?.original_name || selectedFile.name}`, "success");
        await Promise.all([loadFiles(), loadCollaborators()]);
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
    try {
        await Promise.all([loadFiles(), loadCollaborators(), loadDiscussionSummary()]);
    } catch (error) {
        if (error.status === 401) handleAuthExpired();
        else showMessage(error.message);
    }
});

copyRoomLinkButton?.addEventListener("click", async () => {
    try {
        await copyText(shareLink.href);
        showMessage("房间链接已复制。", "success");
    } catch (error) {
        showMessage(error.message || "复制失败。");
    }
});

editNicknameButton?.addEventListener("click", () => openNicknameModal());
nicknameSkipButton?.addEventListener("click", () => closeNicknameModal());

nicknameForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
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
        closeNicknameModal();
        await Promise.all([fetchProfile(), loadCollaborators(), loadFiles()]);
        showMessage("昵称已保存。", "success");
    } catch (error) {
        if (error.status === 401) handleAuthExpired();
        else showMessage(error.message);
    } finally {
        setButtonLoading(nicknameSubmitButton, false);
    }
});

commentForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.selectedFileId) {
        showMessage("请先选择一个文件。");
        return;
    }
    if (!requireProfile("评论")) return;
    const content = commentInput.value.trim();
    if (!content) {
        showMessage("评论不能为空。");
        return;
    }
    try {
        setButtonLoading(submitCommentButton, true, "发布中...");
        await requestJson(`/api/rooms/${roomSlug}/files/${state.selectedFileId}/comments`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({content}),
        });
        commentInput.value = "";
        newCommentBadge.hidden = true;
        state.newCommentCount = 0;
        await Promise.all([loadComments(true), loadFiles(true), loadCollaborators(), loadDiscussionSummary()]);
        showMessage("评论已发布。", "success");
    } catch (error) {
        if (error.status === 401) handleAuthExpired();
        else showMessage(error.message);
    } finally {
        setButtonLoading(submitCommentButton, false);
    }
});

endDiscussionButton?.addEventListener("click", async () => {
    try {
        setButtonLoading(endDiscussionButton, true, "处理中...");
        await requestJson(`/api/rooms/${roomSlug}/discussion/end`, {method: "POST"});
        showMessage("讨论已结束，正在生成总结...", "success");
        await loadDiscussionSummary();
    } catch (error) {
        if (error.status === 401) handleAuthExpired();
        else showMessage(error.message);
    } finally {
        setButtonLoading(endDiscussionButton, false);
    }
});

uploaderFilterSelect?.addEventListener("change", async () => {
    state.filters.uploaderToken = uploaderFilterSelect.value || "";
    await loadFiles();
});
onlyStarredToggle?.addEventListener("change", () => {
    state.filters.onlyStarred = onlyStarredToggle.checked;
    renderFileList();
});
onlyUnreadToggle?.addEventListener("change", () => {
    state.filters.onlyUnread = onlyUnreadToggle.checked;
    renderFileList();
});
clearFiltersButton?.addEventListener("click", async () => {
    state.filters.onlyStarred = false;
    state.filters.onlyUnread = false;
    state.filters.uploaderToken = "";
    onlyStarredToggle.checked = false;
    onlyUnreadToggle.checked = false;
    uploaderFilterSelect.value = "";
    await loadFiles();
});
newCommentBadge?.addEventListener("click", () => {
    state.newCommentCount = 0;
    newCommentBadge.hidden = true;
});

window.addEventListener("beforeunload", () => stopAllPollers());

setAuthorized(state.isAuthorized);
if (state.isAuthorized) {
    initializeWorkspace().catch((error) => {
        if (error.status === 401) handleAuthExpired();
        else showMessage(error.message);
    });
}
