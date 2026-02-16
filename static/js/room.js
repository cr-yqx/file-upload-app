"use strict";

const roomSlug = document.body.dataset.roomSlug;
const roomName = document.body.dataset.roomName;

const authSection = document.getElementById("authSection");
const workspace = document.getElementById("workspace");
const authForm = document.getElementById("authForm");
const uploadForm = document.getElementById("uploadForm");
const fileInput = document.getElementById("fileInput");
const filePickerButton = document.getElementById("filePickerButton");
const filePickerName = document.getElementById("filePickerName");
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

const pdfReaderModal = document.getElementById("pdfReaderModal");
const pdfReaderBackdrop = document.getElementById("pdfReaderBackdrop");
const pdfReaderTitle = document.getElementById("pdfReaderTitle");
const pdfReaderSubtitle = document.getElementById("pdfReaderSubtitle");
const closePdfReaderButton = document.getElementById("closePdfReaderButton");
const pdfPrevPageButton = document.getElementById("pdfPrevPageButton");
const pdfNextPageButton = document.getElementById("pdfNextPageButton");
const pdfPageInfo = document.getElementById("pdfPageInfo");
const pdfZoomSelect = document.getElementById("pdfZoomSelect");
const pdfCanvasContainer = document.getElementById("pdfCanvasContainer");
const pdfPageStage = document.getElementById("pdfPageStage");
const pdfCanvas = document.getElementById("pdfCanvas");
const pdfTextLayer = document.getElementById("pdfTextLayer");
const pdfHighlightLayer = document.getElementById("pdfHighlightLayer");
const pdfSelectionHint = document.getElementById("pdfSelectionHint");
const pageLevelCommentButton = document.getElementById("pageLevelCommentButton");

const lineThreadsTabButton = document.getElementById("lineThreadsTabButton");
const generalCommentsTabButton = document.getElementById("generalCommentsTabButton");
const lineThreadsPanel = document.getElementById("lineThreadsPanel");
const generalCommentsPanel = document.getElementById("generalCommentsPanel");
const lineSelectionComposer = document.getElementById("lineSelectionComposer");
const lineSelectionQuote = document.getElementById("lineSelectionQuote");
const lineSelectionInput = document.getElementById("lineSelectionInput");
const lineSelectionSubmitButton = document.getElementById("lineSelectionSubmitButton");
const lineSelectionCancelButton = document.getElementById("lineSelectionCancelButton");
const lineThreadsEmpty = document.getElementById("lineThreadsEmpty");
const lineThreadsList = document.getElementById("lineThreadsList");
const readerGeneralCommentList = document.getElementById("readerGeneralCommentList");
const readerGeneralCommentForm = document.getElementById("readerGeneralCommentForm");
const readerGeneralCommentInput = document.getElementById("readerGeneralCommentInput");
const readerGeneralCommentSubmit = document.getElementById("readerGeneralCommentSubmit");

const state = {
  isAuthorized: document.body.dataset.authorized === "true",
  viewer: { has_profile: false, nickname: "", viewer_token: "", is_owner: false },
  filters: { onlyStarred: false, onlyUnread: false, uploaderToken: "" },
  files: [],
  collaborators: [],
  selectedFileId: null,
  comments: [],
  commentsAfterId: 0,
  newCommentCount: 0,
  discussion: { status: "idle", ended_at: null, summary_version: 0, is_owner: false },
  discussionSummary: null,
  lastSummaryRenderKey: "",
  pollers: { presence: null, room: null, comments: null, discussion: null, readerThreads: null },
  reader: {
    open: false,
    fileId: null,
    pdfDoc: null,
    pageNumber: 1,
    totalPages: 1,
    zoom: 1,
    hasTextLayer: false,
    textIndexMap: { text: "", nodes: [] },
    threads: [],
    selectedThreadId: null,
    selectedAnchor: null,
    renderNonce: 0,
  },
};

let pdfWorkerConfigured = false;

function setAuthorized(next) { state.isAuthorized = next; authSection.hidden = next; workspace.hidden = !next; }
function setLoading(v) { loading.hidden = !v; }
function syncBodyScrollLock() {
  const lock = (nicknameModal && !nicknameModal.hidden) || (pdfReaderModal && !pdfReaderModal.hidden);
  document.body.style.overflow = lock ? "hidden" : "";
}
function showMessage(text, type = "error") {
  globalMessage.hidden = false;
  globalMessage.className = `message ${type}`;
  globalMessage.textContent = text;
}
function hideMessage() { globalMessage.hidden = true; globalMessage.className = "message"; globalMessage.textContent = ""; }
function setButtonLoading(button, loadingState, label = "处理中...") {
  if (!button) return;
  if (loadingState) {
    if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
    button.textContent = label;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
  }
}
function stopAllPollers() { Object.keys(state.pollers).forEach((k) => { if (state.pollers[k]) { clearInterval(state.pollers[k]); state.pollers[k] = null; } }); }
function handleAuthExpired() { stopAllPollers(); closePdfReader(); setAuthorized(false); showMessage("房间授权已过期，请重新输入口令。"); }

async function requestJson(url, options = {}) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false) {
    const error = new Error(data.message || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function normalizeWhitespace(v) { return String(v || "").replace(/\s+/g, " ").trim(); }
function formatTimestamp(v) { return (v || "").replace("T", " ").replace("Z", ""); }
function getSelectedFile() { return state.files.find((x) => x.id === state.selectedFileId) || null; }
function getFileById(id) { return state.files.find((x) => x.id === id) || null; }
function summaryStatusLabel(status) { if (status === "pending") return "排队中"; if (status === "running") return "处理中"; if (status === "done") return "已完成"; if (status === "failed") return "失败"; return "无需摘要"; }
function requireProfile(hint) { if (state.viewer.has_profile) return true; showMessage(`请先设置昵称再进行${hint}。`, "info"); openNicknameModal(); return false; }
function copyTextFallback(value) {
  const input = document.createElement("textarea"); input.value = value; input.style.position = "fixed"; input.style.opacity = "0";
  document.body.appendChild(input); input.select(); document.execCommand("copy"); document.body.removeChild(input);
}
function updateSelectedFileNameLabel() {
  const f = fileInput?.files?.[0];
  filePickerName.textContent = f ? f.name : "未选择文件";
  filePickerName.title = f ? f.name : "未选择文件";
}
function openNicknameModal() { nicknameInput.value = state.viewer.nickname || ""; nicknameModal.hidden = false; syncBodyScrollLock(); }
function closeNicknameModal() { nicknameModal.hidden = true; syncBodyScrollLock(); }

function renderSummary(file) {
  const wrapper = document.createElement("section");
  wrapper.className = "summary";
  if (file.type !== "pdf") { wrapper.innerHTML = "<p>图片文件无需摘要。</p>"; return wrapper; }
  if (file.summary_status === "done" && file.summary_json) {
    const summary = file.summary_json;
    wrapper.innerHTML = `<h4>AI 摘要</h4><p>一句话：${summary.one_line_summary || ""}</p><h4>关键点</h4><ul>${(summary.key_points || []).map((p) => `<li>${p}</li>`).join("")}</ul><p>关键词：${(summary.keywords || []).join(" / ")}</p><h4>行动建议</h4><ul>${(summary.suggested_actions || []).map((p) => `<li>${p}</li>`).join("")}</ul>`;
    return wrapper;
  }
  if (file.summary_status === "failed") { wrapper.innerHTML = `<p>摘要生成失败：${file.summary_error || "未知错误"}</p>`; return wrapper; }
  wrapper.innerHTML = "<p>摘要生成中，请稍候...</p>";
  return wrapper;
}
function updateMetrics() {
  metricTotal.textContent = `文件 ${state.files.length}`;
  metricStarred.textContent = `星标 ${state.files.filter((x) => x.collab?.starred_by_me).length}`;
  metricUnread.textContent = `未读 ${state.files.filter((x) => !x.collab?.read_by_me).length}`;
}

function renderMyUploadShortcuts() {
  myUploadShortcuts.innerHTML = "";
  const me = state.collaborators.find((x) => x.is_me);
  if (!me || !me.recent_uploads?.length) {
    myUploadShortcuts.innerHTML = '<p class="tips">暂无我的上传文件。</p>';
    return;
  }
  me.recent_uploads.forEach((item) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `file-icon-chip ${state.selectedFileId === item.id ? "active" : ""}`;
    chip.textContent = item.type === "pdf" ? "PDF" : "IMG";
    chip.title = item.original_name || "文件";
    chip.addEventListener("click", () => onUploaderFileSelect(me.viewer_token, item.id));
    myUploadShortcuts.appendChild(chip);
  });
}

function updateViewerSection() {
  viewerNicknameValue.textContent = state.viewer.has_profile ? state.viewer.nickname : "未设置昵称";
  renderMyUploadShortcuts();
}

function createFileCard(file) {
  const card = document.createElement("article");
  card.className = "file-card";
  if (state.selectedFileId === file.id) card.classList.add("selected");

  card.innerHTML = `
    <div class="file-card-head">
      <div>
        <h3>${file.original_name || file.filename}</h3>
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
      <span class="collab-metric">划线 ${file.collab?.line_thread_count || 0}</span>
      <span class="collab-metric">星标 ${file.collab?.star_count || 0}</span>
      <span class="collab-metric">已读 ${file.collab?.read_count || 0}</span>
    </div>
  `;
  card.appendChild(renderSummary(file));

  const actions = document.createElement("div");
  actions.className = "file-actions";

  const viewBtn = document.createElement("button");
  viewBtn.type = "button";
  viewBtn.className = "btn-secondary";
  viewBtn.textContent = file.type === "pdf" ? "打开阅读器" : "查看文件";
  viewBtn.addEventListener("click", () => {
    selectFile(file.id);
    if (file.type === "pdf") {
      openPdfReader(file.id).catch((error) => {
        if (error.status === 401) handleAuthExpired();
        else showMessage(error.message || "打开阅读器失败。");
      });
    } else {
      window.open(file.url, "_blank", "noopener,noreferrer");
    }
  });
  actions.appendChild(viewBtn);

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
  readBtn.textContent = file.collab?.read_by_me ? "标记未读" : "标记已读";
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
  const pdfFiles = files.filter((x) => x.type === "pdf");
  const imageFiles = files.filter((x) => x.type === "image");
  pdfCatalogList.innerHTML = "";
  imageCatalogList.innerHTML = "";
  const appendChip = (file, container) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `file-icon-chip ${state.selectedFileId === file.id ? "active" : ""}`;
    chip.textContent = file.original_name || file.filename;
    chip.title = file.original_name || file.filename;
    chip.addEventListener("click", () => selectFile(file.id));
    container.appendChild(chip);
  };
  pdfFiles.forEach((f) => appendChip(f, pdfCatalogList));
  imageFiles.forEach((f) => appendChip(f, imageCatalogList));
}

function renderFileList() {
  const visible = state.files.filter((file) => {
    if (state.filters.onlyStarred && !file.collab?.starred_by_me) return false;
    if (state.filters.onlyUnread && file.collab?.read_by_me) return false;
    return true;
  });
  fileList.innerHTML = "";
  if (visible.length === 0) {
    emptyState.hidden = false;
  } else {
    emptyState.hidden = true;
    visible.forEach((f) => fileList.appendChild(createFileCard(f)));
  }
  renderCatalog(visible);
}

function onUploaderFileSelect(uploaderToken, fileId) {
  state.filters.uploaderToken = uploaderToken || "";
  uploaderFilterSelect.value = state.filters.uploaderToken;
  loadFiles(true).then(() => selectFile(fileId)).catch((error) => {
    if (error.status === 401) handleAuthExpired();
    else showMessage(error.message || "筛选失败。");
  });
}

function renderUploaderFilterOptions() {
  const prev = state.filters.uploaderToken;
  uploaderFilterSelect.innerHTML = '<option value="">全部协作者</option>';
  state.collaborators.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.viewer_token;
    opt.textContent = p.is_me ? `${p.nickname}（我）` : p.nickname;
    uploaderFilterSelect.appendChild(opt);
  });
  uploaderFilterSelect.value = prev || "";
}

function renderCollaborators() {
  collaboratorPriorityRow.innerHTML = "";
  collaboratorList.innerHTML = "";
  const others = state.collaborators.filter((x) => !x.is_me);
  others.filter((x) => x.upload_count > 0).forEach((p) => collaboratorPriorityRow.appendChild(createUploaderCard(p, true)));
  others.filter((x) => x.upload_count <= 0).forEach((p) => collaboratorList.appendChild(createUploaderCard(p, false)));
  renderUploaderFilterOptions();
  renderMyUploadShortcuts();
}

function createUploaderCard(participant, priority = false) {
  const wrap = document.createElement("article");
  wrap.className = `uploader-card ${priority ? "priority" : ""}`;
  if (state.filters.uploaderToken === participant.viewer_token) wrap.classList.add("active");
  wrap.innerHTML = `<div class="uploader-card-header"><span class="uploader-avatar">${(participant.nickname || "?")[0] || "?"}</span><div class="uploader-identity"><strong>${participant.nickname || "匿名协作者"}</strong><span class="uploader-status ${participant.is_online ? "online" : "offline"}">${participant.is_online ? "在线" : "离线"}</span></div></div>`;
  const filesRow = document.createElement("div");
  filesRow.className = "uploader-files";
  (participant.recent_uploads || []).forEach((item) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `file-icon-chip ${state.selectedFileId === item.id ? "active" : ""}`;
    chip.textContent = item.type === "pdf" ? "PDF" : "IMG";
    chip.title = item.original_name || "文件";
    chip.addEventListener("click", (e) => { e.stopPropagation(); onUploaderFileSelect(participant.viewer_token, item.id); });
    filesRow.appendChild(chip);
  });
  if (participant.extra_upload_count > 0) {
    const more = document.createElement("span");
    more.className = "file-icon-chip extra-count";
    more.textContent = `+${participant.extra_upload_count}`;
    filesRow.appendChild(more);
  }
  if (!filesRow.childElementCount) {
    const empty = document.createElement("span");
    empty.className = "uploader-empty";
    empty.textContent = "暂无上传";
    filesRow.appendChild(empty);
  }
  wrap.appendChild(filesRow);
  wrap.addEventListener("click", () => onUploaderFileSelect(participant.viewer_token, null));
  return wrap;
}
function renderComments() {
  commentList.innerHTML = "";
  if (!state.selectedFileId) {
    commentFileMeta.textContent = "请先选择一个文件。";
    commentInput.disabled = true;
    submitCommentButton.disabled = true;
    renderReaderGeneralComments();
    return;
  }
  const selected = getSelectedFile();
  commentFileMeta.textContent = selected ? `当前文件：${selected.original_name || selected.filename}` : "当前文件不可用";
  commentInput.disabled = !state.viewer.has_profile;
  submitCommentButton.disabled = !state.viewer.has_profile;

  if (!state.comments.length) {
    commentList.innerHTML = '<p class="tips">暂无评论，写下第一条观点吧。</p>';
    renderReaderGeneralComments();
    return;
  }

  state.comments.forEach((comment) => {
    const item = document.createElement("article");
    item.className = "comment-item";
    item.innerHTML = `<div class="comment-item-head"><strong>${comment.nickname}</strong><span>${formatTimestamp(comment.created_at)}</span></div><p>${comment.content}</p>`;
    commentList.appendChild(item);
  });
  renderReaderGeneralComments();
}

function renderReaderGeneralComments() {
  if (!readerGeneralCommentList) return;
  readerGeneralCommentList.innerHTML = "";
  if (!state.selectedFileId) {
    readerGeneralCommentList.innerHTML = '<p class="tips">请先选择文件。</p>';
    return;
  }
  if (!state.comments.length) {
    readerGeneralCommentList.innerHTML = '<p class="tips">暂无通用评论。</p>';
    return;
  }
  state.comments.forEach((comment) => {
    const item = document.createElement("article");
    item.className = "comment-item";
    item.innerHTML = `<div class="comment-item-head"><strong>${comment.nickname}</strong><span>${formatTimestamp(comment.created_at)}</span></div><p>${comment.content}</p>`;
    readerGeneralCommentList.appendChild(item);
  });
}

function renderDiscussionSummary() {
  endDiscussionButton.hidden = !state.discussion?.is_owner;
  const status = state.discussion?.status || "idle";
  discussionStatusText.textContent = status === "running" ? "讨论总结生成中，正在自动刷新..." : status === "done" ? "讨论总结已生成，后续新评论会继续重算。" : status === "failed" ? "讨论总结生成失败，可重新触发。" : "讨论尚未结束。";

  const version = state.discussionSummary?.version || 0;
  const updatedAt = state.discussionSummary?.updated_at || "";
  const renderKey = `${version}::${updatedAt}`;
  if (state.lastSummaryRenderKey === renderKey) return;
  state.lastSummaryRenderKey = renderKey;

  discussionSummaryContainer.innerHTML = "";
  const payload = state.discussionSummary?.summary_json;
  if (!payload?.by_commented_owner?.length) {
    discussionSummaryContainer.innerHTML = '<p class="summary-placeholder">讨论结束后，这里会按“被评论者”分组展示可认领总结。</p>';
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

      const normal = document.createElement("ul");
      (fileItem.comment_details || []).forEach((detail) => {
        const li = document.createElement("li");
        li.textContent = `${detail.commenter_nickname}：${detail.comment_content}`;
        normal.appendChild(li);
      });
      if (normal.childElementCount) card.appendChild(normal);

      const line = document.createElement("ul");
      (fileItem.line_feedback || []).forEach((fb) => {
        const li = document.createElement("li");
        const quote = normalizeWhitespace(fb.quote_text || "");
        li.textContent = quote ? `第 ${fb.page_number} 页引用：${quote}` : `第 ${fb.page_number} 页（页级评论）`;
        line.appendChild(li);
        (fb.comments || []).forEach((msg) => {
          const mi = document.createElement("li");
          mi.textContent = `- ${msg.commenter_nickname}：${msg.comment_content}`;
          line.appendChild(mi);
        });
      });
      if (line.childElementCount) card.appendChild(line);
    });

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
  try { await requestJson(`/api/rooms/${roomSlug}/presence`, { method: "POST" }); }
  catch (error) { if (error.status === 401) handleAuthExpired(); }
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
    if (!state.selectedFileId || !state.files.some((x) => x.id === state.selectedFileId)) {
      state.selectedFileId = state.files[0]?.id || null;
      state.commentsAfterId = 0;
      state.comments = [];
    }
    updateMetrics();
    renderFileList();
    renderDiscussionSummary();
    updateDiscussionPoller();
    await loadComments(true);
    await syncReaderAfterFileRefresh();
  } finally {
    if (!silent) setLoading(false);
  }
}

async function loadComments(reset = false) {
  if (!state.selectedFileId) { state.comments = []; state.commentsAfterId = 0; renderComments(); return; }
  const query = reset ? "" : `?after_id=${state.commentsAfterId || 0}`;
  const data = await requestJson(`/api/rooms/${roomSlug}/files/${state.selectedFileId}/comments${query}`);
  const list = data.comments || [];
  if (reset) { state.comments = list; state.newCommentCount = 0; newCommentBadge.hidden = true; }
  else if (list.length > 0) { state.comments.push(...list); state.newCommentCount += list.length; newCommentBadge.hidden = false; newCommentBadge.textContent = `有新评论 +${state.newCommentCount}`; }
  state.commentsAfterId = data.cursor?.after_id || state.commentsAfterId;
  renderComments();
}

async function loadDiscussionSummary(force = false) {
  if (!state.isAuthorized) return;
  if (!force && !state.discussion?.ended_at) return;
  const data = await requestJson(`/api/rooms/${roomSlug}/discussion/summary`);
  state.discussion = data.discussion || state.discussion;
  state.discussionSummary = data.summary || null;
  renderDiscussionSummary();
  updateDiscussionPoller();
}

function updateDiscussionPoller() {
  if (state.pollers.discussion) { clearInterval(state.pollers.discussion); state.pollers.discussion = null; }
  if (!state.discussion?.ended_at) return;
  const ms = state.discussion.status === "running" ? 3000 : 10000;
  state.pollers.discussion = setInterval(() => loadDiscussionSummary().catch((e) => { if (e.status === 401) handleAuthExpired(); }), ms);
}

function startPollers() {
  stopAllPollers();
  state.pollers.presence = setInterval(() => sendPresence(), 30000);
  state.pollers.room = setInterval(async () => {
    try { await Promise.all([loadCollaborators(), loadFiles(true)]); }
    catch (error) { if (error.status === 401) handleAuthExpired(); }
  }, 5000);
  state.pollers.comments = setInterval(() => loadComments(false).catch((e) => { if (e.status === 401) handleAuthExpired(); }), 2000);
  updateDiscussionPoller();
  if (state.reader.open) startReaderThreadsPoller();
}

function selectFile(fileId) {
  state.selectedFileId = fileId;
  state.newCommentCount = 0;
  newCommentBadge.hidden = true;
  renderFileList();
  loadComments(true).catch((e) => { if (e.status === 401) handleAuthExpired(); });
}

async function initializeWorkspace() {
  await fetchProfile();
  await sendPresence();
  await Promise.all([loadCollaborators(), loadFiles(), loadDiscussionSummary(true)]);
  if (!state.viewer.has_profile) openNicknameModal();
  startPollers();
}

async function toggleFileStar(file) {
  if (!requireProfile("星标")) return;
  await requestJson(`/api/rooms/${roomSlug}/files/${file.id}/star`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ starred: !file.collab?.starred_by_me }) });
  await loadFiles(true);
}
async function toggleFileRead(file) {
  if (!requireProfile("已读")) return;
  await requestJson(`/api/rooms/${roomSlug}/files/${file.id}/read`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ read: !file.collab?.read_by_me }) });
  await loadFiles(true);
}
async function deleteFile(file) {
  const ok = window.confirm(`确认删除“${file.original_name || file.filename}”？`);
  if (!ok) return;
  await requestJson(`/api/rooms/${roomSlug}/files/${file.id}`, { method: "DELETE" });
  showMessage("文件已删除。", "success");
  if (state.reader.open && state.reader.fileId === file.id) closePdfReader();
  await loadFiles();
}
function ensurePdfJsReady() {
  if (!window.pdfjsLib) throw new Error("PDF.js 未加载，无法打开阅读器。");
  if (!pdfWorkerConfigured) {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js";
    pdfWorkerConfigured = true;
  }
}
function setReaderModalVisible(visible) { pdfReaderModal.hidden = !visible; syncBodyScrollLock(); }
function clearPdfLayers() { pdfTextLayer.innerHTML = ""; pdfHighlightLayer.innerHTML = ""; }
function setPdfLoading(loadingState) {
  pdfCanvasContainer.classList.toggle("loading", !!loadingState);
  pdfPrevPageButton.disabled = loadingState;
  pdfNextPageButton.disabled = loadingState;
  pdfZoomSelect.disabled = loadingState;
}
function updateReaderPageInfo() {
  pdfPageInfo.textContent = `${state.reader.pageNumber} / ${state.reader.totalPages}`;
  pdfPrevPageButton.disabled = state.reader.pageNumber <= 1;
  pdfNextPageButton.disabled = state.reader.pageNumber >= state.reader.totalPages;
}
function resetReaderState() {
  state.reader.pdfDoc = null;
  state.reader.fileId = null;
  state.reader.pageNumber = 1;
  state.reader.totalPages = 1;
  state.reader.zoom = 1;
  state.reader.hasTextLayer = false;
  state.reader.textIndexMap = { text: "", nodes: [] };
  state.reader.threads = [];
  state.reader.selectedThreadId = null;
  state.reader.selectedAnchor = null;
  state.reader.renderNonce += 1;
  lineThreadsList.innerHTML = "";
  lineThreadsEmpty.hidden = false;
  lineSelectionComposer.hidden = true;
  lineSelectionInput.value = "";
  pdfZoomSelect.value = "1";
  pdfPageInfo.textContent = "1 / 1";
  clearPdfLayers();
}
function closePdfReader() {
  if (!state.reader.open) return;
  if (state.pollers.readerThreads) { clearInterval(state.pollers.readerThreads); state.pollers.readerThreads = null; }
  state.reader.open = false;
  resetReaderState();
  setReaderModalVisible(false);
}

function setReaderTab(tab) {
  const useGeneral = tab === "general";
  lineThreadsTabButton.classList.toggle("active", !useGeneral);
  generalCommentsTabButton.classList.toggle("active", useGeneral);
  lineThreadsPanel.hidden = useGeneral;
  generalCommentsPanel.hidden = !useGeneral;
  if (useGeneral) renderReaderGeneralComments();
}

function buildTextIndexMap() {
  const walker = document.createTreeWalker(pdfTextLayer, NodeFilter.SHOW_TEXT, null);
  const nodes = [];
  let text = "";
  let node = walker.nextNode();
  while (node) {
    const value = node.textContent || "";
    if (value) {
      const start = text.length;
      text += value;
      nodes.push({ node, start, end: text.length });
    }
    node = walker.nextNode();
  }
  return { text, nodes };
}

function resolveCharPosition(offset) {
  const nodes = state.reader.textIndexMap.nodes || [];
  for (const entry of nodes) {
    if (offset <= entry.end) {
      const local = Math.max(0, Math.min((entry.node.textContent || "").length, offset - entry.start));
      return { node: entry.node, offset: local };
    }
  }
  if (!nodes.length) return null;
  const last = nodes[nodes.length - 1];
  return { node: last.node, offset: (last.node.textContent || "").length };
}

function buildRangeFromOffsets(start, end) {
  const s = resolveCharPosition(start);
  const e = resolveCharPosition(end);
  if (!s || !e) return null;
  const range = document.createRange();
  range.setStart(s.node, s.offset);
  range.setEnd(e.node, e.offset);
  return range;
}

function clearHighlights() { pdfHighlightLayer.innerHTML = ""; }
function drawHighlight(range) {
  clearHighlights();
  if (!range) return;
  const stage = pdfPageStage.getBoundingClientRect();
  Array.from(range.getClientRects()).forEach((rect) => {
    if (rect.width < 2 || rect.height < 2) return;
    const h = document.createElement("div");
    h.className = "pdf-highlight";
    h.style.left = `${rect.left - stage.left}px`;
    h.style.top = `${rect.top - stage.top}px`;
    h.style.width = `${rect.width}px`;
    h.style.height = `${rect.height}px`;
    pdfHighlightLayer.appendChild(h);
  });
}

function findThreadOffsets(thread) {
  const text = state.reader.textIndexMap.text || "";
  if (!text) return null;
  if (Number.isInteger(thread.quote_start) && Number.isInteger(thread.quote_end) && thread.quote_end > thread.quote_start) {
    return { start: thread.quote_start, end: thread.quote_end };
  }
  const quote = String(thread.quote_text || "");
  if (!quote) return null;
  const idx = text.indexOf(quote);
  if (idx < 0) return null;
  return { start: idx, end: idx + quote.length };
}

function highlightSelectedThread() {
  const thread = state.reader.threads.find((x) => x.id === state.reader.selectedThreadId);
  if (!thread || !state.reader.hasTextLayer) { clearHighlights(); return; }
  const offsets = findThreadOffsets(thread);
  if (!offsets) { clearHighlights(); return; }
  const range = buildRangeFromOffsets(offsets.start, offsets.end);
  drawHighlight(range);
}

function renderLineThreads() {
  lineThreadsList.innerHTML = "";
  if (!state.reader.threads.length) {
    lineThreadsEmpty.hidden = false;
    lineThreadsEmpty.textContent = "本页暂无划线线程。";
    clearHighlights();
    return;
  }
  lineThreadsEmpty.hidden = true;

  state.reader.threads.forEach((thread) => {
    const item = document.createElement("article");
    item.className = `line-thread-item ${thread.id === state.reader.selectedThreadId ? "active" : ""}`;
    item.innerHTML = `<div class="line-thread-meta"><span>第 ${thread.page_number} 页</span><span>${formatTimestamp(thread.updated_at || thread.created_at)}</span></div><p class="line-thread-quote">${normalizeWhitespace(thread.quote_text) || "页级评论（无高亮文本）"}</p>`;

    const messages = document.createElement("div");
    messages.className = "line-thread-messages";
    (thread.messages || []).forEach((msg) => {
      const block = document.createElement("article");
      block.className = "line-thread-message";
      block.innerHTML = `<div class="line-thread-message-head"><strong>${msg.nickname}</strong><span>${formatTimestamp(msg.created_at)}${msg.edited_at ? "（已编辑）" : ""}</span></div><p>${msg.content}</p>`;
      if (msg.is_mine && !msg.is_deleted) {
        const actions = document.createElement("div");
        actions.className = "line-thread-message-actions";
        const edit = document.createElement("button"); edit.type = "button"; edit.className = "mini-btn"; edit.textContent = "编辑";
        edit.addEventListener("click", (e) => {
          e.stopPropagation();
          editLineComment(msg).catch((error) => {
            if (error.status === 401) handleAuthExpired();
            else showMessage(error.message || "编辑失败。");
          });
        });
        const del = document.createElement("button"); del.type = "button"; del.className = "mini-btn"; del.textContent = "删除";
        del.addEventListener("click", (e) => {
          e.stopPropagation();
          deleteLineComment(msg).catch((error) => {
            if (error.status === 401) handleAuthExpired();
            else showMessage(error.message || "删除失败。");
          });
        });
        actions.appendChild(edit); actions.appendChild(del); block.appendChild(actions);
      }
      messages.appendChild(block);
    });
    item.appendChild(messages);

    const replyRow = document.createElement("div");
    replyRow.className = "line-thread-reply";
    const input = document.createElement("textarea");
    input.maxLength = 300;
    input.placeholder = state.viewer.has_profile ? "回复该线程..." : "请先设置昵称";
    input.disabled = !state.viewer.has_profile;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn-secondary";
    button.textContent = "回复";
    button.disabled = !state.viewer.has_profile;
    button.addEventListener("click", (e) => {
      e.stopPropagation();
      submitLineThreadReply(thread.id, input, button).catch((error) => {
        if (error.status === 401) handleAuthExpired();
        else showMessage(error.message || "回复失败。");
      });
    });
    replyRow.appendChild(input); replyRow.appendChild(button);
    item.appendChild(replyRow);

    item.addEventListener("click", () => { state.reader.selectedThreadId = thread.id; renderLineThreads(); highlightSelectedThread(); });
    lineThreadsList.appendChild(item);
  });
  highlightSelectedThread();
}

async function loadLineThreads(resetSelection = false) {
  if (!state.reader.open || !state.reader.fileId) return;
  const data = await requestJson(`/api/rooms/${roomSlug}/files/${state.reader.fileId}/line-threads?page=${state.reader.pageNumber}`);
  state.reader.threads = data.threads || [];
  if (resetSelection || !state.reader.threads.some((x) => x.id === state.reader.selectedThreadId)) {
    state.reader.selectedThreadId = state.reader.threads[0]?.id || null;
  }
  renderLineThreads();
}

function startReaderThreadsPoller() {
  if (state.pollers.readerThreads) clearInterval(state.pollers.readerThreads);
  state.pollers.readerThreads = setInterval(() => loadLineThreads(false).catch((e) => { if (e.status === 401) handleAuthExpired(); }), 2000);
}

function updateSelectionHint() {
  if (state.reader.hasTextLayer) {
    pdfSelectionHint.textContent = "拖动选择文本可发起划线评论。";
    pageLevelCommentButton.hidden = true;
  } else {
    pdfSelectionHint.textContent = "当前页没有文本层，可发起页级评论。";
    pageLevelCommentButton.hidden = false;
  }
}

async function renderPdfPage(resetThreads = false) {
  if (!state.reader.pdfDoc) return;
  const nonce = ++state.reader.renderNonce;
  setPdfLoading(true);
  try {
    const page = await state.reader.pdfDoc.getPage(state.reader.pageNumber);
    if (nonce !== state.reader.renderNonce) return;
    const viewport = page.getViewport({ scale: state.reader.zoom });
    pdfCanvas.width = Math.ceil(viewport.width);
    pdfCanvas.height = Math.ceil(viewport.height);
    pdfCanvas.style.width = `${viewport.width}px`;
    pdfCanvas.style.height = `${viewport.height}px`;
    pdfPageStage.style.width = `${viewport.width}px`;
    pdfPageStage.style.height = `${viewport.height}px`;
    clearPdfLayers();
    await page.render({ canvasContext: pdfCanvas.getContext("2d", { alpha: false }), viewport }).promise;
    const content = await page.getTextContent();
    if (nonce !== state.reader.renderNonce) return;
    state.reader.hasTextLayer = (content.items || []).some((i) => normalizeWhitespace(i.str).length > 0);
    if (state.reader.hasTextLayer) {
      await window.pdfjsLib.renderTextLayer({ textContentSource: content, container: pdfTextLayer, viewport, textDivs: [], enhanceTextSelection: true }).promise;
    }
    state.reader.textIndexMap = buildTextIndexMap();
    updateReaderPageInfo();
    updateSelectionHint();
    await loadLineThreads(resetThreads);
  } finally {
    setPdfLoading(false);
  }
}

async function openPdfReader(fileId) {
  const file = getFileById(fileId);
  if (!file || file.type !== "pdf") return;
  ensurePdfJsReady();
  state.selectedFileId = file.id;
  renderFileList();
  await loadComments(true);

  state.reader.open = true;
  state.reader.fileId = file.id;
  state.reader.zoom = Number.parseFloat(pdfZoomSelect.value || "1") || 1;
  state.reader.pageNumber = 1;
  state.reader.selectedAnchor = null;
  state.reader.selectedThreadId = null;

  pdfReaderTitle.textContent = file.original_name || file.filename;
  pdfReaderSubtitle.textContent = "可划选文本并创建线程评论";
  setReaderTab("line");
  setReaderModalVisible(true);

  const task = window.pdfjsLib.getDocument({ url: file.url, withCredentials: true });
  state.reader.pdfDoc = await task.promise;
  state.reader.totalPages = state.reader.pdfDoc.numPages || 1;
  await renderPdfPage(true);
  startReaderThreadsPoller();
}

async function syncReaderAfterFileRefresh() {
  if (!state.reader.open) return;
  const selected = getSelectedFile();
  if (!selected || selected.type !== "pdf") { closePdfReader(); return; }
  if (selected.id !== state.reader.fileId) await openPdfReader(selected.id);
  renderReaderGeneralComments();
}
function selectionBelongsToPdf(range) {
  if (!range) return false;
  const node = range.commonAncestorContainer;
  if (node === pdfTextLayer) return true;
  if (node.nodeType === Node.TEXT_NODE) return pdfTextLayer.contains(node.parentNode);
  return pdfTextLayer.contains(node);
}
function clearWindowSelection() { const sel = window.getSelection(); if (sel) sel.removeAllRanges(); }

function buildAnchorFromSelection(text) {
  const clean = normalizeWhitespace(text);
  const full = state.reader.textIndexMap.text || "";
  if (!clean || !full) return { page_number: state.reader.pageNumber, quote_text: clean, quote_prefix: "", quote_suffix: "", quote_start: null, quote_end: null };
  const idx = full.indexOf(text);
  if (idx < 0) {
    const nIdx = normalizeWhitespace(full).indexOf(clean);
    if (nIdx < 0) return { page_number: state.reader.pageNumber, quote_text: clean, quote_prefix: "", quote_suffix: "", quote_start: null, quote_end: null };
    return { page_number: state.reader.pageNumber, quote_text: clean, quote_prefix: normalizeWhitespace(full).slice(Math.max(0, nIdx - 30), nIdx), quote_suffix: normalizeWhitespace(full).slice(nIdx + clean.length, nIdx + clean.length + 30), quote_start: null, quote_end: null };
  }
  return { page_number: state.reader.pageNumber, quote_text: text, quote_prefix: full.slice(Math.max(0, idx - 30), idx), quote_suffix: full.slice(idx + text.length, idx + text.length + 30), quote_start: idx, quote_end: idx + text.length };
}

function openSelectionComposer(anchor) {
  state.reader.selectedAnchor = anchor;
  lineSelectionQuote.textContent = normalizeWhitespace(anchor.quote_text) ? `引用：${normalizeWhitespace(anchor.quote_text)}` : `第 ${anchor.page_number} 页（页级评论）`;
  lineSelectionComposer.hidden = false;
}

function cancelSelectionComposer(resetHighlight = true) {
  lineSelectionComposer.hidden = true;
  lineSelectionInput.value = "";
  state.reader.selectedAnchor = null;
  if (resetHighlight) highlightSelectedThread();
}

function capturePdfSelection() {
  if (!state.reader.open || !state.reader.hasTextLayer) return;
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return;
  const range = selection.getRangeAt(0);
  if (!selectionBelongsToPdf(range)) return;
  const text = selection.toString();
  if (!normalizeWhitespace(text)) return;
  openSelectionComposer(buildAnchorFromSelection(text));
  drawHighlight(range);
}

async function submitLineSelectionThread() {
  if (!state.reader.open || !state.reader.fileId) return;
  if (!requireProfile("划线评论")) return;
  const content = normalizeWhitespace(lineSelectionInput.value);
  if (!content) { showMessage("评论内容不能为空。"); return; }
  const anchor = state.reader.selectedAnchor || { page_number: state.reader.pageNumber, quote_text: "", quote_prefix: "", quote_suffix: "", quote_start: null, quote_end: null };
  setButtonLoading(lineSelectionSubmitButton, true, "发布中...");
  try {
    await requestJson(`/api/rooms/${roomSlug}/files/${state.reader.fileId}/line-threads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_number: anchor.page_number, quote_text: anchor.quote_text || "", quote_prefix: anchor.quote_prefix || "", quote_suffix: anchor.quote_suffix || "", quote_start: anchor.quote_start, quote_end: anchor.quote_end, content }),
    });
    cancelSelectionComposer(true);
    clearWindowSelection();
    await Promise.all([loadLineThreads(true), loadFiles(true), loadCollaborators(), loadDiscussionSummary(true)]);
    showMessage("划线线程已发布。", "success");
  } finally {
    setButtonLoading(lineSelectionSubmitButton, false);
  }
}

async function submitLineThreadReply(threadId, input, button) {
  if (!requireProfile("划线回复")) return;
  const content = normalizeWhitespace(input.value);
  if (!content) { showMessage("回复不能为空。"); return; }
  setButtonLoading(button, true, "发布中...");
  try {
    await requestJson(`/api/rooms/${roomSlug}/line-threads/${threadId}/messages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content }) });
    input.value = "";
    await Promise.all([loadLineThreads(false), loadFiles(true), loadCollaborators(), loadDiscussionSummary(true)]);
  } finally {
    setButtonLoading(button, false);
  }
}

async function editLineComment(comment) {
  const draft = window.prompt("编辑评论", comment.raw_content || comment.content || "");
  if (draft === null) return;
  const content = normalizeWhitespace(draft);
  if (!content) { showMessage("评论不能为空。"); return; }
  await requestJson(`/api/rooms/${roomSlug}/line-comments/${comment.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content }) });
  await Promise.all([loadLineThreads(false), loadFiles(true), loadDiscussionSummary(true)]);
}

async function deleteLineComment(comment) {
  if (!window.confirm("确认删除该条划线评论？")) return;
  await requestJson(`/api/rooms/${roomSlug}/line-comments/${comment.id}`, { method: "DELETE" });
  await Promise.all([loadLineThreads(false), loadFiles(true), loadDiscussionSummary(true)]);
}

async function postGeneralComment(content) {
  if (!state.selectedFileId) { showMessage("请先选择一个文件。"); return; }
  if (!requireProfile("评论")) return;
  const normalized = normalizeWhitespace(content);
  if (!normalized) { showMessage("评论不能为空。"); return; }
  await requestJson(`/api/rooms/${roomSlug}/files/${state.selectedFileId}/comments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: normalized }) });
  state.newCommentCount = 0;
  newCommentBadge.hidden = true;
  await Promise.all([loadComments(true), loadFiles(true), loadCollaborators(), loadDiscussionSummary(true)]);
}

authForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage();
  const passcode = document.getElementById("authPasscode")?.value || "";
  const submit = authForm.querySelector('button[type="submit"]');
  try {
    setButtonLoading(submit, true, "验证中...");
    await requestJson(`/api/rooms/${roomSlug}/auth`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ passcode }) });
    setAuthorized(true);
    showMessage(`房间 ${roomName} 已解锁。`, "success");
    await initializeWorkspace();
  } catch (error) {
    showMessage(error.message || "解锁失败。");
  } finally {
    setButtonLoading(submit, false);
  }
});

uploadForm?.addEventListener("submit", async (event) => {
  event.preventDefault(); hideMessage();
  if (!requireProfile("上传")) return;
  const selected = fileInput.files?.[0];
  if (!selected) { showMessage("请先选择文件。"); return; }
  const formData = new FormData(); formData.append("file", selected);
  try {
    setButtonLoading(uploadButton, true, "上传中...");
    const data = await requestJson(`/api/rooms/${roomSlug}/upload`, { method: "POST", body: formData });
    fileInput.value = ""; updateSelectedFileNameLabel();
    state.selectedFileId = data.file?.id || state.selectedFileId;
    showMessage(`上传成功：${data.file?.original_name || selected.name}`, "success");
    await Promise.all([loadFiles(), loadCollaborators()]);
  } catch (error) {
    if (error.status === 401) { handleAuthExpired(); return; }
    showMessage(error.message || "上传失败。");
  } finally {
    setButtonLoading(uploadButton, false);
  }
});

refreshButton?.addEventListener("click", async () => {
  try { await Promise.all([loadFiles(), loadCollaborators(), loadDiscussionSummary(true)]); showMessage("已刷新。", "success"); }
  catch (error) { if (error.status === 401) handleAuthExpired(); else showMessage(error.message || "刷新失败。"); }
});

copyRoomLinkButton?.addEventListener("click", async () => {
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(shareLink.href);
    else copyTextFallback(shareLink.href);
    showMessage("房间链接已复制。", "success");
  } catch (error) {
    showMessage(error.message || "复制失败。");
  }
});

filePickerButton?.addEventListener("click", () => fileInput?.click());
fileInput?.addEventListener("change", () => updateSelectedFileNameLabel());
editNicknameButton?.addEventListener("click", () => openNicknameModal());
nicknameSkipButton?.addEventListener("click", () => closeNicknameModal());

nicknameForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const nickname = normalizeWhitespace(nicknameInput.value);
  if (nickname.length < 2 || nickname.length > 20) { showMessage("昵称长度需在 2 到 20 个字符之间。"); return; }
  try {
    setButtonLoading(nicknameSubmitButton, true, "保存中...");
    await requestJson(`/api/rooms/${roomSlug}/profile`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nickname }) });
    closeNicknameModal();
    await Promise.all([fetchProfile(), loadCollaborators(), loadFiles()]);
    showMessage("昵称已保存。", "success");
  } catch (error) {
    if (error.status === 401) handleAuthExpired(); else showMessage(error.message || "昵称保存失败。");
  } finally {
    setButtonLoading(nicknameSubmitButton, false);
  }
});
commentForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setButtonLoading(submitCommentButton, true, "发布中...");
    await postGeneralComment(commentInput.value);
    commentInput.value = "";
  } catch (error) {
    if (error.status === 401) handleAuthExpired(); else showMessage(error.message || "评论发布失败。");
  } finally {
    setButtonLoading(submitCommentButton, false);
  }
});

readerGeneralCommentForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setButtonLoading(readerGeneralCommentSubmit, true, "发布中...");
    await postGeneralComment(readerGeneralCommentInput.value);
    readerGeneralCommentInput.value = "";
  } catch (error) {
    if (error.status === 401) handleAuthExpired(); else showMessage(error.message || "评论发布失败。");
  } finally {
    setButtonLoading(readerGeneralCommentSubmit, false);
  }
});

endDiscussionButton?.addEventListener("click", async () => {
  try {
    setButtonLoading(endDiscussionButton, true, "处理中...");
    const data = await requestJson(`/api/rooms/${roomSlug}/discussion/end`, { method: "POST" });
    state.discussion = data.discussion || state.discussion;
    renderDiscussionSummary();
    updateDiscussionPoller();
    showMessage("讨论已结束，正在生成总结...", "success");
    await loadDiscussionSummary(true);
  } catch (error) {
    if (error.status === 401) handleAuthExpired(); else showMessage(error.message || "结束讨论失败。");
  } finally {
    setButtonLoading(endDiscussionButton, false);
  }
});

uploaderFilterSelect?.addEventListener("change", async () => {
  state.filters.uploaderToken = uploaderFilterSelect.value || "";
  await loadFiles();
});
onlyStarredToggle?.addEventListener("change", () => { state.filters.onlyStarred = onlyStarredToggle.checked; renderFileList(); });
onlyUnreadToggle?.addEventListener("change", () => { state.filters.onlyUnread = onlyUnreadToggle.checked; renderFileList(); });
clearFiltersButton?.addEventListener("click", async () => {
  state.filters.onlyStarred = false;
  state.filters.onlyUnread = false;
  state.filters.uploaderToken = "";
  onlyStarredToggle.checked = false;
  onlyUnreadToggle.checked = false;
  uploaderFilterSelect.value = "";
  await loadFiles();
});
newCommentBadge?.addEventListener("click", () => { state.newCommentCount = 0; newCommentBadge.hidden = true; });

closePdfReaderButton?.addEventListener("click", () => closePdfReader());
pdfReaderBackdrop?.addEventListener("click", () => closePdfReader());
lineThreadsTabButton?.addEventListener("click", () => setReaderTab("line"));
generalCommentsTabButton?.addEventListener("click", () => setReaderTab("general"));
pdfPrevPageButton?.addEventListener("click", () => changeReaderPage(state.reader.pageNumber - 1));
pdfNextPageButton?.addEventListener("click", () => changeReaderPage(state.reader.pageNumber + 1));
pdfZoomSelect?.addEventListener("change", () => changeReaderZoom(pdfZoomSelect.value));
lineSelectionSubmitButton?.addEventListener("click", () => submitLineSelectionThread().catch((e) => { if (e.status === 401) handleAuthExpired(); else showMessage(e.message || "发布划线线程失败。"); }));
lineSelectionCancelButton?.addEventListener("click", () => { cancelSelectionComposer(true); clearWindowSelection(); });
pageLevelCommentButton?.addEventListener("click", () => {
  openSelectionComposer({ page_number: state.reader.pageNumber, quote_text: "", quote_prefix: "", quote_suffix: "", quote_start: null, quote_end: null });
  lineSelectionInput.focus();
});
pdfTextLayer?.addEventListener("mouseup", () => setTimeout(() => capturePdfSelection(), 0));
pdfTextLayer?.addEventListener("keyup", () => setTimeout(() => capturePdfSelection(), 0));

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (state.reader.open) { closePdfReader(); return; }
    if (nicknameModal && !nicknameModal.hidden) closeNicknameModal();
  }
});

window.addEventListener("beforeunload", () => stopAllPollers());

function changeReaderPage(nextPage) {
  if (!state.reader.pdfDoc) return;
  const target = Math.max(1, Math.min(nextPage, state.reader.totalPages));
  if (target === state.reader.pageNumber) return;
  state.reader.pageNumber = target;
  renderPdfPage(true).catch((e) => showMessage(e.message || "翻页失败。"));
}
function changeReaderZoom(value) {
  if (!state.reader.pdfDoc) return;
  const zoom = Number.parseFloat(String(value));
  if (!Number.isFinite(zoom) || zoom <= 0) return;
  state.reader.zoom = zoom;
  renderPdfPage(false).catch((e) => showMessage(e.message || "缩放失败。"));
}

updateSelectedFileNameLabel();
setAuthorized(state.isAuthorized);
if (state.isAuthorized) {
  initializeWorkspace().catch((error) => {
    if (error.status === 401) handleAuthExpired();
    else showMessage(error.message || "初始化失败。");
  });
}
