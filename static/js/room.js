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
const wordCatalogList = document.getElementById("wordCatalogList");
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
const docxStage = document.getElementById("docxStage");
const docxContent = document.getElementById("docxContent");
const docxHighlightLayer = document.getElementById("docxHighlightLayer");
const docDowngradeNotice = document.getElementById("docDowngradeNotice");
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
    mode: null,
    fileId: null,
    pdfDoc: null,
    docxLoaded: false,
    loadingTask: null,
    pageNumber: 1,
    totalPages: 1,
    viewerScaleMode: "fit",
    userZoomFactor: 1,
    fitScale: 1,
    effectiveScale: 1,
    hasTextLayer: false,
    textIndexMap: { text: "", nodes: [] },
    threads: [],
    selectedThreadId: null,
    selectedAnchor: null,
    renderNonce: 0,
    resizeObserver: null,
    resizeDebounceTimer: null,
    selectionCaptureTimer: null,
    selectionWarnAt: 0,
    selectionWarnCode: "",
    pointerDownInPdf: false,
    pendingSelectionAnchor: null,
    renderTask: null,
    textLayerTask: null,
  },
};

let pdfWorkerConfigured = false;
const PDFJS_CDN_BASE = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105";
const READER_SELECTION_DEBOUNCE_MS = 80;
const MIN_LINE_SELECTION_CHARS = 2;
const DOCX_SUPPORTED_TYPES = new Set(["docx"]);
const READER_LINE_SUPPORTED_TYPES = new Set(["pdf", "docx"]);

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

async function ensureFileReadable(fileUrl) {
  let response;
  try {
    response = await fetch(fileUrl, {
      method: "HEAD",
      credentials: "same-origin",
    });
  } catch (_error) {
    const error = new Error("文件地址不可达，请刷新后重试。");
    error.status = 0;
    throw error;
  }

  if (response.status === 405 || response.status === 501) {
    return;
  }

  if (response.status === 401) {
    const error = new Error("房间授权过期，请重新输入口令。");
    error.status = 401;
    throw error;
  }
  if (response.status === 404) {
    const error = new Error("文件不存在或已删除。");
    error.status = 404;
    throw error;
  }
  if (!response.ok) {
    const error = new Error("文件地址不可达，请刷新后重试。");
    error.status = response.status;
    throw error;
  }
}

function normalizeWhitespace(v) { return String(v || "").replace(/\s+/g, " ").trim(); }
function formatTimestamp(v) { return (v || "").replace("T", " ").replace("Z", ""); }
function getSelectedFile() { return state.files.find((x) => x.id === state.selectedFileId) || null; }
function getFileById(id) { return state.files.find((x) => x.id === id) || null; }
function summaryStatusLabel(status) { if (status === "pending") return "排队中"; if (status === "running") return "处理中"; if (status === "done") return "已完成"; if (status === "failed") return "失败"; return "无需摘要"; }
function fileTypeLabel(fileType) {
  if (fileType === "pdf") return "PDF";
  if (fileType === "docx") return "DOCX";
  if (fileType === "doc") return "DOC";
  if (fileType === "image") return "IMG";
  return String(fileType || "").toUpperCase() || "FILE";
}
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
  if (file.type !== "pdf") {
    if (file.type === "doc" || file.type === "docx") {
      wrapper.innerHTML = "<p>Word 文件本期不自动生成摘要，可通过全文评论与划线评论沉淀讨论。</p>";
      return wrapper;
    }
    wrapper.innerHTML = "<p>图片文件无需摘要。</p>";
    return wrapper;
  }
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
    chip.textContent = fileTypeLabel(item.type);
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
  const supportsReader = file.type === "pdf" || file.type === "docx" || file.type === "doc";
  viewBtn.textContent = supportsReader ? "打开阅读器" : "查看文件";
  viewBtn.addEventListener("click", () => {
    selectFile(file.id);
    if (supportsReader) {
      openDocumentReader(file.id).catch((error) => {
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
  const wordFiles = files.filter((x) => x.type === "doc" || x.type === "docx");
  const imageFiles = files.filter((x) => x.type === "image");
  pdfCatalogList.innerHTML = "";
  wordCatalogList.innerHTML = "";
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
  wordFiles.forEach((f) => appendChip(f, wordCatalogList));
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
    chip.textContent = fileTypeLabel(item.type);
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
    readerGeneralCommentList.innerHTML = '<p class="tips">暂无全文评论。</p>';
    return;
  }
  state.comments.forEach((comment) => {
    const item = document.createElement("article");
    item.className = "comment-item";
    item.innerHTML = `<div class="comment-item-head"><strong>${comment.nickname}</strong><span>${formatTimestamp(comment.created_at)}</span></div><p>${comment.content}</p>`;
    readerGeneralCommentList.appendChild(item);
  });
}

function buildSummaryList(items, mapText, emptyText = "暂无内容。") {
  if (!Array.isArray(items) || items.length === 0) {
    const empty = document.createElement("p");
    empty.className = "tips";
    empty.textContent = emptyText;
    return empty;
  }
  const ul = document.createElement("ul");
  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = mapText(item);
    ul.appendChild(li);
  });
  return ul;
}

function normalizeSummaryActionKey(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .replace(/\s*([,，.。:：;；!！?？、])\s*/g, "$1")
    .trim();
}

function dedupeSummaryActionList(items, maxItems = 12) {
  const source = Array.isArray(items) ? items : [];
  const seen = new Set();
  const result = [];
  source.forEach((item) => {
    const text = String(item || "").trim();
    const key = normalizeSummaryActionKey(text);
    if (!key || seen.has(key) || result.length >= maxItems) return;
    seen.add(key);
    result.push(text);
  });
  return result;
}

function deriveFileActionBoard(fileItem, groupActions) {
  const fileName = String(fileItem.file_name || "").trim();
  const board = fileItem.action_board && typeof fileItem.action_board === "object" ? fileItem.action_board : {};
  let processing = dedupeSummaryActionList(board.processing, 6);
  let followUp = dedupeSummaryActionList(board.follow_up, 6);
  const consumed = new Set();
  const normalizedProcessingSet = new Set(processing.map((item) => normalizeSummaryActionKey(item)));
  const normalizedFollowUpSet = new Set(followUp.map((item) => normalizeSummaryActionKey(item)));
  const fullComments = Array.isArray(fileItem.full_comments) ? fileItem.full_comments : (Array.isArray(fileItem.comment_details) ? fileItem.comment_details : []);
  const lineComments = Array.isArray(fileItem.line_comments) ? fileItem.line_comments : (Array.isArray(fileItem.line_feedback) ? fileItem.line_feedback : []);

  const actionMatchesFile = (actionText) => {
    if (!fileName) return false;
    return actionText.includes(`《${fileName}》`) || actionText.includes(fileName);
  };

  if ((!processing.length || !followUp.length) && Array.isArray(groupActions)) {
    groupActions.forEach((rawAction) => {
      const action = String(rawAction || "").trim();
      const key = normalizeSummaryActionKey(action);
      if (!key || !actionMatchesFile(action)) return;
      if (action.startsWith("处理")) {
        if (!normalizedProcessingSet.has(key)) {
          processing.push(action);
          normalizedProcessingSet.add(key);
        }
        consumed.add(key);
      } else if (action.startsWith("跟进")) {
        if (!normalizedFollowUpSet.has(key)) {
          followUp.push(action);
          normalizedFollowUpSet.add(key);
        }
        consumed.add(key);
      }
    });
  }

  if (!processing.length) {
    lineComments.slice(0, 3).forEach((item) => {
      const quote = normalizeWhitespace(item.quote_text || "");
      if (!quote) return;
      const scope = item.source_type === "docx" ? `段落 ${item.segment_key || "-"}` : `第 ${item.page_number || 1} 页`;
      const action = `处理《${fileName || "该文件"}》${scope}引用：${quote.slice(0, 42)}`;
      const key = normalizeSummaryActionKey(action);
      if (!normalizedProcessingSet.has(key)) {
        processing.push(action);
        normalizedProcessingSet.add(key);
      }
    });
  }

  if (!followUp.length) {
    fullComments.slice(0, 3).forEach((item) => {
      const action = `跟进《${fileName || "该文件"}》全文评论：${String(item.comment_content || "").slice(0, 42)}`;
      const key = normalizeSummaryActionKey(action);
      if (!normalizedFollowUpSet.has(key)) {
        followUp.push(action);
        normalizedFollowUpSet.add(key);
      }
    });
  }

  if (!processing.length) {
    processing = [`处理《${fileName || "该文件"}》：补充结构化结论与负责人。`];
  }
  if (!followUp.length) {
    followUp = [`跟进《${fileName || "该文件"}》：暂无全文评论，建议会后补充。`];
  }

  processing = dedupeSummaryActionList(processing, 4);
  followUp = dedupeSummaryActionList(followUp, 4);
  processing.forEach((item) => consumed.add(normalizeSummaryActionKey(item)));
  followUp.forEach((item) => consumed.add(normalizeSummaryActionKey(item)));

  return { processing, followUp, consumed };
}

function renderDiscussionSummary() {
  const canEndDiscussion = Boolean(state.discussion?.is_owner || state.viewer?.is_owner || state.discussion?.owner_bound === false);
  endDiscussionButton.hidden = !canEndDiscussion;
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
    discussionSummaryContainer.innerHTML = '<p class="summary-placeholder">讨论结束后，这里会按“协作者”分组展示总结。</p>';
    return;
  }

  payload.by_commented_owner.forEach((group) => {
    const rawGroupActions = Array.isArray(group.claimable_actions) ? group.claimable_actions : [];
    const card = document.createElement("article");
    card.className = "summary-group";
    const ownerTitle = document.createElement("h4");
    ownerTitle.textContent = `${group.owner_nickname || "未命名上传者"}`;
    card.appendChild(ownerTitle);

    if (group.owner_summary) {
      const ownerNote = document.createElement("p");
      ownerNote.className = "summary-owner-note";
      ownerNote.textContent = String(group.owner_summary);
      card.appendChild(ownerNote);
    }

    (group.files || []).forEach((fileItem) => {
      const fileCard = document.createElement("section");
      fileCard.className = "summary-file-card";

      const fileTitle = document.createElement("p");
      fileTitle.className = "summary-file-title";
      fileTitle.textContent = `文件：${fileItem.file_name || "-"}`;
      fileCard.appendChild(fileTitle);

      const fullComments = fileItem.full_comments || fileItem.comment_details || [];
      const fullSection = document.createElement("section");
      fullSection.className = "summary-section";
      const fullTitle = document.createElement("h5");
      fullTitle.textContent = "全文评论";
      fullSection.appendChild(fullTitle);
      fullSection.appendChild(
        buildSummaryList(
          fullComments,
          (detail) => `${detail.commenter_nickname || "匿名"}：${detail.comment_content || ""}`,
          "暂无全文评论。"
        )
      );
      fileCard.appendChild(fullSection);

      const lineComments = fileItem.line_comments || fileItem.line_feedback || [];
      const lineSection = document.createElement("section");
      lineSection.className = "summary-section";
      const lineTitle = document.createElement("h5");
      lineTitle.textContent = "划线评论";
      lineSection.appendChild(lineTitle);
      lineSection.appendChild(
        buildSummaryList(
          lineComments,
          (fb) => {
            const quote = normalizeWhitespace(fb.quote_text || "");
            const scope = fb.source_type === "docx" ? `段落 ${fb.segment_key || "-"}` : `第 ${fb.page_number || 1} 页`;
            const messages = (fb.comments || [])
              .map((msg) => `${msg.commenter_nickname || "匿名"}：${msg.comment_content || ""}`)
              .join("；");
            if (quote) return `${scope} 引用「${quote}」${messages ? ` -> ${messages}` : ""}`;
            return `${scope}（无引用）${messages ? ` -> ${messages}` : ""}`;
          },
          "暂无划线评论。"
        )
      );
      fileCard.appendChild(lineSection);

      const divider = document.createElement("div");
      divider.className = "summary-divider";
      fileCard.appendChild(divider);

      const actionBoardResult = deriveFileActionBoard(fileItem, rawGroupActions);

      const board = document.createElement("section");
      board.className = "action-board";
      const processing = actionBoardResult.processing || [];
      const followUp = actionBoardResult.followUp || [];

      const processingCol = document.createElement("section");
      processingCol.className = "action-row processing-row";
      const processingTitle = document.createElement("h5");
      processingTitle.textContent = "处理";
      processingCol.appendChild(processingTitle);
      processingCol.appendChild(buildSummaryList(processing, (v) => String(v || ""), "暂无处理项。"));

      const boardDivider = document.createElement("div");
      boardDivider.className = "summary-divider";

      const followCol = document.createElement("section");
      followCol.className = "action-row followup-row";
      const followTitle = document.createElement("h5");
      followTitle.textContent = "跟进";
      followCol.appendChild(followTitle);
      followCol.appendChild(buildSummaryList(followUp, (v) => String(v || ""), "暂无跟进项。"));

      board.appendChild(processingCol);
      board.appendChild(boardDivider);
      board.appendChild(followCol);
      fileCard.appendChild(board);
      card.appendChild(fileCard);
    });
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
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = `${PDFJS_CDN_BASE}/pdf.worker.min.js`;
    pdfWorkerConfigured = true;
  }
}
function ensureDocxLibsReady() {
  if (!window.mammoth) throw new Error("Mammoth.js 未加载，无法打开 DOCX 阅读器。");
  if (!window.DOMPurify) throw new Error("DOMPurify 未加载，无法安全渲染 DOCX。");
}
function getStablePdfDocumentOptions(fileUrl) {
  return {
    url: fileUrl,
    withCredentials: true,
    disableRange: true,
    disableStream: true,
    disableAutoFetch: false,
    useSystemFonts: true,
    cMapUrl: `${PDFJS_CDN_BASE}/cmaps/`,
    cMapPacked: true,
    standardFontDataUrl: `${PDFJS_CDN_BASE}/standard_fonts/`,
  };
}
async function loadPdfDocumentStable(fileUrl) {
  if (state.reader.loadingTask?.destroy) {
    try {
      state.reader.loadingTask.destroy();
    } catch (_error) {
      // no-op
    }
  }
  const loadingTask = window.pdfjsLib.getDocument(getStablePdfDocumentOptions(fileUrl));
  state.reader.loadingTask = loadingTask;
  try {
    return await loadingTask.promise;
  } finally {
    if (state.reader.loadingTask === loadingTask) {
      state.reader.loadingTask = null;
    }
  }
}
function cancelReaderRenderTasks() {
  if (state.reader.renderTask?.cancel) {
    try {
      state.reader.renderTask.cancel();
    } catch (_error) {
      // no-op
    }
  }
  state.reader.renderTask = null;

  if (state.reader.textLayerTask?.cancel) {
    try {
      state.reader.textLayerTask.cancel();
    } catch (_error) {
      // no-op
    }
  }
  state.reader.textLayerTask = null;
}
function normalizePdfLoadError(error) {
  if (!error) return new Error("PDF 加载失败，请刷新后重试。");
  if (typeof error.status === "number" && error.status > 0) return error;
  const name = String(error.name || "");
  if (name === "MissingPDFException") return new Error("文件不存在或已删除。");
  if (name === "PasswordException") return new Error("该 PDF 受密码保护，暂不支持在线阅读。");
  if (name === "InvalidPDFException" || name === "FormatError") return new Error("PDF 解析失败，请重新上传文件后重试。");
  if (name === "UnexpectedResponseException") return new Error("PDF 读取失败，请稍后重试。");
  return new Error(error.message || "PDF 加载失败，请刷新后重试。");
}
async function awaitPdfTask(taskLike) {
  if (!taskLike) return;
  if (typeof taskLike.then === "function") {
    await taskLike;
    return;
  }
  if (taskLike.promise && typeof taskLike.promise.then === "function") {
    await taskLike.promise;
  }
}
function isTextLayerArgError(error) {
  const message = String(error?.message || "");
  return /textContent|textContentStream|textContentSource/i.test(message);
}
function createPdfTextContentStream(page) {
  if (!page || typeof page.streamTextContent !== "function") return null;
  try {
    return page.streamTextContent({ includeMarkedContent: true });
  } catch (_error) {
    return null;
  }
}

async function renderPdfTextLayer(page, content, viewport) {
  const optionsBase = {
    container: pdfTextLayer,
    viewport,
    textDivs: [],
    enhanceTextSelection: true,
  };

  const attempts = [
    { textContent: content },
    { textContentStream: createPdfTextContentStream(page) },
    { textContentSource: content },
  ];
  let lastError = null;

  for (const option of attempts) {
    const key = Object.keys(option)[0];
    const value = option[key];
    if (!value) continue;

    try {
      pdfTextLayer.innerHTML = "";
      state.reader.textLayerTask = window.pdfjsLib.renderTextLayer({
        ...optionsBase,
        [key]: value,
      });
      await awaitPdfTask(state.reader.textLayerTask);
      state.reader.textLayerTask = null;
      return;
    } catch (error) {
      state.reader.textLayerTask = null;
      lastError = error;
      if (!isTextLayerArgError(error)) throw error;
    }
  }

  if (window.pdfjsLib?.TextLayer) {
    const source = createPdfTextContentStream(page) || content;
    if (source) {
      const task = new window.pdfjsLib.TextLayer({
        textContentSource: source,
        container: pdfTextLayer,
        viewport,
      });
      state.reader.textLayerTask = task;
      await awaitPdfTask(task.render?.());
      state.reader.textLayerTask = null;
      return;
    }
  }

  throw lastError || new Error("PDF 文本层渲染失败。");
}
function setReaderModalVisible(visible) { pdfReaderModal.hidden = !visible; syncBodyScrollLock(); }
function clearReaderLayers() {
  pdfTextLayer.innerHTML = "";
  pdfHighlightLayer.innerHTML = "";
  docxHighlightLayer.innerHTML = "";
  docxContent.innerHTML = "";
}
function setReaderMode(mode) {
  state.reader.mode = mode;
  const isPdf = mode === "pdf";
  const isDocx = mode === "docx";
  const isDoc = mode === "doc";
  pdfPageStage.hidden = !isPdf;
  docxStage.hidden = !isDocx;
  docDowngradeNotice.hidden = !isDoc;
  pdfPrevPageButton.disabled = !isPdf;
  pdfNextPageButton.disabled = !isPdf;
  pdfZoomSelect.disabled = !isPdf;
}
function setPdfLoading(loadingState) {
  pdfCanvasContainer.classList.toggle("loading", !!loadingState);
  if (state.reader.mode !== "pdf") {
    pdfPrevPageButton.disabled = true;
    pdfNextPageButton.disabled = true;
    pdfZoomSelect.disabled = true;
    return;
  }
  if (loadingState) {
    pdfPrevPageButton.disabled = true;
    pdfNextPageButton.disabled = true;
  } else {
    updateReaderPageInfo();
  }
  pdfZoomSelect.disabled = loadingState;
}
function updateReaderPageInfo() {
  pdfPageInfo.textContent = `${state.reader.pageNumber} / ${state.reader.totalPages}`;
  pdfPrevPageButton.disabled = state.reader.pageNumber <= 1;
  pdfNextPageButton.disabled = state.reader.pageNumber >= state.reader.totalPages;
}
function getReaderContainerInnerWidth() {
  if (!pdfCanvasContainer) return 0;
  const styles = window.getComputedStyle(pdfCanvasContainer);
  const paddingLeft = Number.parseFloat(styles.paddingLeft || "0");
  const paddingRight = Number.parseFloat(styles.paddingRight || "0");
  return Math.max(0, pdfCanvasContainer.clientWidth - paddingLeft - paddingRight);
}
function stopReaderResizeObserver() {
  if (state.reader.resizeDebounceTimer) {
    clearTimeout(state.reader.resizeDebounceTimer);
    state.reader.resizeDebounceTimer = null;
  }
  if (state.reader.resizeObserver) {
    state.reader.resizeObserver.disconnect();
    state.reader.resizeObserver = null;
  }
}
function ensureReaderResizeObserver() {
  stopReaderResizeObserver();
  if (!window.ResizeObserver) return;
  state.reader.resizeObserver = new ResizeObserver(() => {
    if (!state.reader.open || state.reader.mode !== "pdf" || !state.reader.pdfDoc) return;
    if (state.reader.resizeDebounceTimer) clearTimeout(state.reader.resizeDebounceTimer);
    state.reader.resizeDebounceTimer = setTimeout(() => {
      state.reader.resizeDebounceTimer = null;
      renderPdfPage(false).catch((error) => {
        showMessage(error.message || "窗口变化后重绘失败。");
      });
    }, 120);
  });
  state.reader.resizeObserver.observe(pdfCanvasContainer);
}
function computeReaderScale(page) {
  const baseViewport = page.getViewport({ scale: 1 });
  const userFactor = Number.isFinite(state.reader.userZoomFactor) && state.reader.userZoomFactor > 0 ? state.reader.userZoomFactor : 1;
  let fitScale = 1;
  if (state.reader.viewerScaleMode === "fit") {
    const innerWidth = getReaderContainerInnerWidth();
    if (innerWidth > 0 && baseViewport.width > 0) {
      fitScale = innerWidth / baseViewport.width;
    }
  }
  state.reader.fitScale = Math.max(0.2, Math.min(fitScale, 6));
  state.reader.effectiveScale = Math.max(0.2, Math.min(state.reader.fitScale * userFactor, 6));
  return state.reader.effectiveScale;
}
function resetReaderState() {
  stopReaderResizeObserver();
  cancelReaderRenderTasks();
  if (state.reader.selectionCaptureTimer) {
    clearTimeout(state.reader.selectionCaptureTimer);
    state.reader.selectionCaptureTimer = null;
  }
  if (state.reader.loadingTask?.destroy) {
    try {
      state.reader.loadingTask.destroy();
    } catch (_error) {
      // no-op
    }
  }
  state.reader.loadingTask = null;
  state.reader.mode = null;
  state.reader.pdfDoc = null;
  state.reader.docxLoaded = false;
  state.reader.fileId = null;
  state.reader.pageNumber = 1;
  state.reader.totalPages = 1;
  state.reader.viewerScaleMode = "fit";
  state.reader.userZoomFactor = 1;
  state.reader.fitScale = 1;
  state.reader.effectiveScale = 1;
  state.reader.hasTextLayer = false;
  state.reader.textIndexMap = { text: "", nodes: [] };
  state.reader.threads = [];
  state.reader.selectedThreadId = null;
  state.reader.selectedAnchor = null;
  state.reader.selectionWarnAt = 0;
  state.reader.selectionWarnCode = "";
  state.reader.pointerDownInPdf = false;
  state.reader.pendingSelectionAnchor = null;
  state.reader.renderNonce += 1;
  lineThreadsList.innerHTML = "";
  lineThreadsEmpty.hidden = false;
  lineSelectionComposer.hidden = true;
  lineSelectionInput.value = "";
  pdfZoomSelect.value = "1";
  pdfPageInfo.textContent = "1 / 1";
  clearReaderLayers();
  setReaderMode(null);
}
function closePdfReader() {
  if (!state.reader.open) return;
  if (state.pollers.readerThreads) { clearInterval(state.pollers.readerThreads); state.pollers.readerThreads = null; }
  clearWindowSelection();
  state.reader.open = false;
  resetReaderState();
  setReaderModalVisible(false);
}

function setReaderTab(tab) {
  if (tab === "line" && !READER_LINE_SUPPORTED_TYPES.has(state.reader.mode || "")) {
    showMessage("当前文件类型不支持划线评论，请使用全文评论。", "info");
    return;
  }
  const useGeneral = tab === "general";
  lineThreadsTabButton.classList.toggle("active", !useGeneral);
  generalCommentsTabButton.classList.toggle("active", useGeneral);
  lineThreadsPanel.hidden = useGeneral;
  generalCommentsPanel.hidden = !useGeneral;
  if (useGeneral) renderReaderGeneralComments();
}

function getActiveTextContainer() {
  if (state.reader.mode === "docx") return docxContent;
  return pdfTextLayer;
}

function getActiveStageElement() {
  if (state.reader.mode === "docx") return docxStage;
  return pdfPageStage;
}

function buildTextIndexMap(container = null) {
  const host = container || getActiveTextContainer();
  const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT, null);
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

function getActiveHighlightLayer() {
  if (state.reader.mode === "docx") return docxHighlightLayer;
  return pdfHighlightLayer;
}

function clearHighlights() {
  pdfHighlightLayer.innerHTML = "";
  docxHighlightLayer.innerHTML = "";
}

function drawHighlight(range) {
  clearHighlights();
  if (!range) return;
  const stageEl = getActiveStageElement();
  const layer = getActiveHighlightLayer();
  const stage = stageEl.getBoundingClientRect();
  Array.from(range.getClientRects()).forEach((rect) => {
    if (rect.width < 2 || rect.height < 2) return;
    const h = document.createElement("div");
    h.className = "pdf-highlight";
    h.style.left = `${rect.left - stage.left}px`;
    h.style.top = `${rect.top - stage.top}px`;
    h.style.width = `${rect.width}px`;
    h.style.height = `${rect.height}px`;
    layer.appendChild(h);
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
    lineThreadsEmpty.textContent = state.reader.mode === "docx" ? "当前文档暂无划线评论。" : "本页暂无划线评论。";
    clearHighlights();
    return;
  }
  lineThreadsEmpty.hidden = true;

  state.reader.threads.forEach((thread) => {
    const item = document.createElement("article");
    item.className = `line-thread-item ${thread.id === state.reader.selectedThreadId ? "active" : ""}`;
    const scopeLabel = thread.source_type === "docx" ? `段落 ${thread.segment_key || "-"}` : `第 ${thread.page_number} 页`;
    item.innerHTML = `<div class="line-thread-meta"><span>${scopeLabel}</span><span>${formatTimestamp(thread.updated_at || thread.created_at)}</span></div><p class="line-thread-quote">${normalizeWhitespace(thread.quote_text) || "页级评论（无高亮文本）"}</p>`;

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
  const query = new URLSearchParams();
  if (state.reader.mode === "pdf") {
    query.set("page", String(state.reader.pageNumber));
  }
  const qs = query.toString();
  const url = qs
    ? `/api/rooms/${roomSlug}/files/${state.reader.fileId}/line-threads?${qs}`
    : `/api/rooms/${roomSlug}/files/${state.reader.fileId}/line-threads`;
  const data = await requestJson(url);
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
  if (state.reader.mode === "doc") {
    pdfSelectionHint.textContent = "`.doc` 当前仅支持全文评论。请转换为 `.docx` 以启用划线评论。";
    pageLevelCommentButton.hidden = true;
    return;
  }
  if (state.reader.hasTextLayer) {
    pdfSelectionHint.textContent = "拖动选择文本可发起划线评论。";
    pageLevelCommentButton.hidden = true;
  } else {
    if (state.reader.mode === "pdf") {
      pdfSelectionHint.textContent = "当前页无可选文本，已切换页级评论。";
      pageLevelCommentButton.hidden = false;
    } else {
      pdfSelectionHint.textContent = "当前文档暂无可选文本，可使用全文评论。";
      pageLevelCommentButton.hidden = true;
    }
  }
}

async function renderPdfPage(resetThreads = false) {
  if (!state.reader.pdfDoc) return;
  setReaderMode("pdf");
  const nonce = ++state.reader.renderNonce;
  setPdfLoading(true);
  try {
    cancelReaderRenderTasks();
    const page = await state.reader.pdfDoc.getPage(state.reader.pageNumber);
    if (nonce !== state.reader.renderNonce) return;

    const scale = computeReaderScale(page);
    const viewport = page.getViewport({ scale });
    const devicePixelRatio = Math.max(1, window.devicePixelRatio || 1);
    pdfCanvas.width = Math.ceil(viewport.width * devicePixelRatio);
    pdfCanvas.height = Math.ceil(viewport.height * devicePixelRatio);
    pdfCanvas.style.width = `${viewport.width}px`;
    pdfCanvas.style.height = `${viewport.height}px`;
    pdfPageStage.style.width = `${viewport.width}px`;
    pdfPageStage.style.height = `${viewport.height}px`;
    clearReaderLayers();

    const canvasContext = pdfCanvas.getContext("2d", { alpha: false });
    if (!canvasContext) throw new Error("浏览器不支持 PDF 画布渲染。");
    canvasContext.setTransform(1, 0, 0, 1, 0, 0);
    canvasContext.clearRect(0, 0, pdfCanvas.width, pdfCanvas.height);
    canvasContext.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    canvasContext.imageSmoothingEnabled = true;
    canvasContext.imageSmoothingQuality = "high";
    state.reader.renderTask = page.render({ canvasContext, viewport });
    await state.reader.renderTask.promise;
    state.reader.renderTask = null;

    const content = await page.getTextContent();
    if (nonce !== state.reader.renderNonce) return;
    state.reader.hasTextLayer = (content.items || []).some((i) => normalizeWhitespace(i.str).length > 0);
    if (state.reader.hasTextLayer) {
      await renderPdfTextLayer(page, content, viewport);
    }
    state.reader.textIndexMap = buildTextIndexMap(pdfTextLayer);
    updateReaderPageInfo();
    updateSelectionHint();
    await loadLineThreads(resetThreads);
  } catch (error) {
    const name = String(error?.name || "");
    const message = String(error?.message || "").toLowerCase();
    if (name === "RenderingCancelledException" || message.includes("rendering cancelled")) {
      return;
    }
    throw error;
  } finally {
    if (nonce === state.reader.renderNonce) {
      setPdfLoading(false);
    }
  }
}

function assignDocxSegments() {
  if (!docxContent) return;
  const segmentSelectors = "p,li,h1,h2,h3,h4,h5,h6,blockquote,pre,td,th";
  const segments = Array.from(docxContent.querySelectorAll(segmentSelectors))
    .filter((el) => normalizeWhitespace(el.textContent).length > 0);
  segments.forEach((el, index) => {
    el.dataset.segmentKey = `segment-${index + 1}`;
  });
}

async function renderDocxDocument(file, resetThreads = false) {
  ensureDocxLibsReady();
  const response = await fetch(file.url, { credentials: "same-origin" });
  if (!response.ok) {
    const error = new Error("DOCX 文件读取失败，请稍后重试。");
    error.status = response.status;
    throw error;
  }
  const arrayBuffer = await response.arrayBuffer();
  const result = await window.mammoth.convertToHtml({ arrayBuffer });
  const sanitized = window.DOMPurify.sanitize(result.value || "", {
    USE_PROFILES: { html: true },
  });
  clearReaderLayers();
  docxContent.innerHTML = sanitized;
  assignDocxSegments();
  state.reader.textIndexMap = buildTextIndexMap(docxContent);
  state.reader.hasTextLayer = normalizeWhitespace(docxContent.textContent).length > 0;
  state.reader.docxLoaded = true;
  state.reader.totalPages = 1;
  state.reader.pageNumber = 1;
  updateReaderPageInfo();
  updateSelectionHint();
  await loadLineThreads(resetThreads);
}

async function openDocumentReader(fileId) {
  const file = getFileById(fileId);
  if (!file || !["pdf", "docx", "doc"].includes(file.type)) return;
  await ensureFileReadable(file.url);
  state.selectedFileId = file.id;
  renderFileList();
  await loadComments(true);

  state.reader.open = true;
  state.reader.mode = file.type;
  state.reader.fileId = file.id;
  state.reader.viewerScaleMode = "fit";
  state.reader.userZoomFactor = Number.parseFloat(pdfZoomSelect.value || "1") || 1;
  state.reader.pageNumber = 1;
  state.reader.selectedAnchor = null;
  state.reader.pendingSelectionAnchor = null;
  state.reader.selectedThreadId = null;
  state.reader.hasTextLayer = false;
  state.reader.textIndexMap = { text: "", nodes: [] };
  setReaderMode(file.type);

  pdfReaderTitle.textContent = file.original_name || file.filename;
  pdfReaderSubtitle.textContent = file.type === "doc"
    ? "`.doc` 支持全文评论，划线评论请先转换为 `.docx`"
    : "可划选文本并创建划线评论";
  if (file.type === "doc") {
    setReaderTab("general");
  } else {
    setReaderTab("line");
  }
  setReaderModalVisible(true);

  try {
    if (file.type === "pdf") {
      ensurePdfJsReady();
      state.reader.pdfDoc = await loadPdfDocumentStable(file.url);
      state.reader.totalPages = state.reader.pdfDoc.numPages || 1;
      ensureReaderResizeObserver();
      await renderPdfPage(true);
    } else if (file.type === "docx") {
      state.reader.pdfDoc = null;
      stopReaderResizeObserver();
      await renderDocxDocument(file, true);
    } else {
      state.reader.pdfDoc = null;
      state.reader.docxLoaded = false;
      stopReaderResizeObserver();
      clearReaderLayers();
      state.reader.hasTextLayer = false;
      updateReaderPageInfo();
      updateSelectionHint();
      await loadLineThreads(true);
    }
    startReaderThreadsPoller();
  } catch (error) {
    closePdfReader();
    if (file.type === "pdf") {
      throw normalizePdfLoadError(error);
    }
    throw error;
  }
}

async function openPdfReader(fileId) {
  await openDocumentReader(fileId);
}

async function syncReaderAfterFileRefresh() {
  if (!state.reader.open) return;
  const selected = getSelectedFile();
  if (!selected || !["pdf", "docx", "doc"].includes(selected.type)) { closePdfReader(); return; }
  if (selected.id !== state.reader.fileId || selected.type !== state.reader.mode) await openDocumentReader(selected.id);
  renderReaderGeneralComments();
}
function nodeBelongsToReaderLayer(node) {
  const textLayer = getActiveTextContainer();
  if (!node || !textLayer) return false;
  if (node === textLayer) return true;
  if (node.nodeType === Node.TEXT_NODE) return textLayer.contains(node.parentNode);
  return textLayer.contains(node);
}
function maybeShowSelectionWarning(code, message) {
  const now = Date.now();
  if (state.reader.selectionWarnCode === code && now - state.reader.selectionWarnAt < 1200) return;
  state.reader.selectionWarnCode = code;
  state.reader.selectionWarnAt = now;
  showMessage(message, "info");
}
function schedulePdfSelectionCapture(trigger = "selectionchange") {
  if (!state.reader.open || !state.reader.hasTextLayer) return;
  if (!READER_LINE_SUPPORTED_TYPES.has(state.reader.mode || "")) return;
  if (trigger === "selectionchange" && !state.reader.pointerDownInPdf) return;
  if (state.reader.selectionCaptureTimer) clearTimeout(state.reader.selectionCaptureTimer);
  const waitMs = trigger === "pointerup" ? READER_SELECTION_DEBOUNCE_MS : READER_SELECTION_DEBOUNCE_MS + 20;
  state.reader.selectionCaptureTimer = setTimeout(() => {
    state.reader.selectionCaptureTimer = null;
    capturePdfSelection(trigger);
  }, waitMs);
}
function clearWindowSelection() { const sel = window.getSelection(); if (sel) sel.removeAllRanges(); }

function getRangeOffsetInLayer(range, boundary) {
  const offsetRange = document.createRange();
  const textLayer = getActiveTextContainer();
  offsetRange.selectNodeContents(textLayer);
  if (boundary === "start") {
    offsetRange.setEnd(range.startContainer, range.startOffset);
  } else {
    offsetRange.setEnd(range.endContainer, range.endOffset);
  }
  return offsetRange.toString().length;
}

function getRangeOffsetInContainer(range, container, boundary) {
  const offsetRange = document.createRange();
  offsetRange.selectNodeContents(container);
  if (boundary === "start") {
    offsetRange.setEnd(range.startContainer, range.startOffset);
  } else {
    offsetRange.setEnd(range.endContainer, range.endOffset);
  }
  return offsetRange.toString().length;
}

function findSegmentElement(node) {
  let current = node;
  if (current && current.nodeType === Node.TEXT_NODE) current = current.parentNode;
  while (current && current !== docxContent) {
    if (current.nodeType === Node.ELEMENT_NODE && current.dataset && current.dataset.segmentKey) {
      return current;
    }
    current = current.parentNode;
  }
  return null;
}

function getDocxSegmentAnchor(range) {
  if (state.reader.mode !== "docx") {
    return { segment_key: "", segment_start: null, segment_end: null, cross_segment: false };
  }
  const startSeg = findSegmentElement(range.startContainer);
  const endSeg = findSegmentElement(range.endContainer);
  if (!startSeg || !endSeg) {
    return { segment_key: "", segment_start: null, segment_end: null, cross_segment: false };
  }
  if (startSeg !== endSeg) {
    return { segment_key: "", segment_start: null, segment_end: null, cross_segment: true };
  }
  const segStart = getRangeOffsetInContainer(range, startSeg, "start");
  const segEnd = getRangeOffsetInContainer(range, startSeg, "end");
  return {
    segment_key: startSeg.dataset.segmentKey || "",
    segment_start: Number.isFinite(segStart) ? segStart : null,
    segment_end: Number.isFinite(segEnd) ? segEnd : null,
    cross_segment: false,
  };
}

function buildAnchorFromSelection(text) {
  const clean = normalizeWhitespace(text);
  const full = state.reader.textIndexMap.text || "";
  const mode = state.reader.mode || "pdf";
  const baseAnchor = {
    source_type: mode,
    anchor_scope: mode === "docx" ? "segment" : "text",
    segment_key: "",
    segment_start: null,
    segment_end: null,
  };
  if (!clean || !full) return {
    ...baseAnchor,
    page_number: state.reader.pageNumber,
    quote_text: clean,
    quote_prefix: "",
    quote_suffix: "",
    quote_start: null,
    quote_end: null,
    anchor_precision: "fallback",
  };
  const idx = full.indexOf(text);
  if (idx < 0) {
    const nIdx = normalizeWhitespace(full).indexOf(clean);
    if (nIdx < 0) return {
      ...baseAnchor,
      page_number: state.reader.pageNumber,
      quote_text: clean,
      quote_prefix: "",
      quote_suffix: "",
      quote_start: null,
      quote_end: null,
      anchor_precision: "fallback",
    };
    return {
      ...baseAnchor,
      page_number: state.reader.pageNumber,
      quote_text: clean,
      quote_prefix: normalizeWhitespace(full).slice(Math.max(0, nIdx - 30), nIdx),
      quote_suffix: normalizeWhitespace(full).slice(nIdx + clean.length, nIdx + clean.length + 30),
      quote_start: null,
      quote_end: null,
      anchor_precision: "fallback",
    };
  }
  return {
    ...baseAnchor,
    page_number: state.reader.pageNumber,
    quote_text: text,
    quote_prefix: full.slice(Math.max(0, idx - 30), idx),
    quote_suffix: full.slice(idx + text.length, idx + text.length + 30),
    quote_start: idx,
    quote_end: idx + text.length,
    anchor_precision: "fallback",
  };
}

function buildAnchorFromRange(range) {
  const text = range.toString();
  const clean = normalizeWhitespace(text);
  if (!clean) return buildAnchorFromSelection(text);
  const mode = state.reader.mode || "pdf";

  try {
    const start = getRangeOffsetInLayer(range, "start");
    const end = getRangeOffsetInLayer(range, "end");
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
      return buildAnchorFromSelection(text);
    }
    const segmentAnchor = getDocxSegmentAnchor(range);
    if (segmentAnchor.cross_segment) {
      maybeShowSelectionWarning("cross-segment", "请在同一段落内选择文本并评论。");
      return buildAnchorFromSelection(text);
    }
    const full = state.reader.textIndexMap.text || "";
    const safeStart = Math.max(0, Math.min(full.length, start));
    const safeEnd = Math.max(safeStart, Math.min(full.length, end));
    return {
      source_type: mode,
      anchor_scope: mode === "docx" ? "segment" : "text",
      page_number: state.reader.pageNumber,
      quote_text: text,
      quote_prefix: full.slice(Math.max(0, safeStart - 30), safeStart),
      quote_suffix: full.slice(safeEnd, Math.min(full.length, safeEnd + 30)),
      quote_start: safeStart,
      quote_end: safeEnd,
      segment_key: segmentAnchor.segment_key,
      segment_start: segmentAnchor.segment_start,
      segment_end: segmentAnchor.segment_end,
      anchor_precision: "exact",
    };
  } catch (_error) {
    return buildAnchorFromSelection(text);
  }
}

function openSelectionComposer(anchor, focusComposer = false) {
  setReaderTab("line");
  state.reader.selectedAnchor = anchor;
  if (normalizeWhitespace(anchor.quote_text)) {
    lineSelectionQuote.textContent = `引用：${normalizeWhitespace(anchor.quote_text)}`;
  } else if (anchor.source_type === "docx") {
    lineSelectionQuote.textContent = `段落 ${anchor.segment_key || "-"}（无引用，段落评论）`;
  } else {
    lineSelectionQuote.textContent = `第 ${anchor.page_number} 页（页级评论）`;
  }
  lineSelectionComposer.hidden = false;
  if (focusComposer) {
    try {
      lineSelectionInput.focus({ preventScroll: true });
    } catch (_error) {
      lineSelectionInput.focus();
    }
  }
}

function cancelSelectionComposer(resetHighlight = true) {
  lineSelectionComposer.hidden = true;
  lineSelectionInput.value = "";
  state.reader.selectedAnchor = null;
  if (resetHighlight) highlightSelectedThread();
}

function capturePdfSelection(trigger = "selectionchange") {
  if (!state.reader.open || !state.reader.hasTextLayer) return;
  if (!READER_LINE_SUPPORTED_TYPES.has(state.reader.mode || "")) return;
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return;
  const range = selection.getRangeAt(0);
  const startInside = nodeBelongsToReaderLayer(range.startContainer);
  const endInside = nodeBelongsToReaderLayer(range.endContainer);
  const activeLayer = getActiveTextContainer();
  if (!startInside || !endInside) {
    let mayCrossPage = startInside || endInside;
    if (!mayCrossPage && selection.containsNode && activeLayer) {
      try {
        mayCrossPage = selection.containsNode(activeLayer, true);
      } catch (_error) {
        mayCrossPage = false;
      }
    }
    if (mayCrossPage && trigger === "pointerup") {
      maybeShowSelectionWarning("cross-page", "请在单页内划线评论。");
    }
    return;
  }
  const text = selection.toString();
  const normalized = normalizeWhitespace(text);
  if (normalized.length < MIN_LINE_SELECTION_CHARS) {
    if (trigger === "pointerup") {
      maybeShowSelectionWarning("too-short", `至少选择 ${MIN_LINE_SELECTION_CHARS} 个字符后再评论。`);
    }
    return;
  }
  const anchor = buildAnchorFromRange(range);
  if (trigger === "selectionchange") {
    state.reader.pendingSelectionAnchor = anchor;
    drawHighlight(range);
    return;
  }

  const finalAnchor = state.reader.pendingSelectionAnchor || anchor;
  state.reader.pendingSelectionAnchor = null;
  if (state.reader.mode === "docx" && finalAnchor.anchor_scope === "segment" && !finalAnchor.segment_key) {
    maybeShowSelectionWarning("segment-missing", "请在同一段落内选择文本并评论。");
    return;
  }
  openSelectionComposer(finalAnchor, true);
  drawHighlight(range);
}

async function submitLineSelectionThread() {
  if (!state.reader.open || !state.reader.fileId) return;
  if (state.reader.mode === "doc") {
    showMessage("`.doc` 请先转换为 `.docx` 后再进行划线评论。", "info");
    return;
  }
  if (!requireProfile("划线评论")) return;
  const content = normalizeWhitespace(lineSelectionInput.value);
  if (!content) { showMessage("评论内容不能为空。"); return; }
  const anchor = state.reader.selectedAnchor || {
    source_type: state.reader.mode || "pdf",
    anchor_scope: state.reader.mode === "docx" ? "segment" : "page",
    page_number: state.reader.pageNumber,
    quote_text: "",
    quote_prefix: "",
    quote_suffix: "",
    quote_start: null,
    quote_end: null,
    segment_key: "",
    segment_start: null,
    segment_end: null,
  };
  if (state.reader.mode === "docx" && anchor.anchor_scope === "segment" && !anchor.segment_key) {
    showMessage("请选择同一段落中的文本后再发布划线评论。");
    return;
  }
  setButtonLoading(lineSelectionSubmitButton, true, "发布中...");
  try {
    await requestJson(`/api/rooms/${roomSlug}/files/${state.reader.fileId}/line-threads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_type: anchor.source_type || state.reader.mode || "pdf",
        anchor_scope: anchor.anchor_scope || (state.reader.mode === "docx" ? "segment" : "text"),
        page_number: anchor.page_number || 1,
        quote_text: anchor.quote_text || "",
        quote_prefix: anchor.quote_prefix || "",
        quote_suffix: anchor.quote_suffix || "",
        quote_start: anchor.quote_start,
        quote_end: anchor.quote_end,
        segment_key: anchor.segment_key || "",
        segment_start: anchor.segment_start,
        segment_end: anchor.segment_end,
        content,
      }),
    });
    cancelSelectionComposer(true);
    clearWindowSelection();
    await Promise.all([loadLineThreads(true), loadFiles(true), loadCollaborators(), loadDiscussionSummary(true)]);
    showMessage("划线评论已发布。", "success");
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
lineSelectionSubmitButton?.addEventListener("click", () => submitLineSelectionThread().catch((e) => { if (e.status === 401) handleAuthExpired(); else showMessage(e.message || "发布划线评论失败。"); }));
lineSelectionCancelButton?.addEventListener("click", () => { cancelSelectionComposer(true); clearWindowSelection(); });
pageLevelCommentButton?.addEventListener("click", () => {
  openSelectionComposer(
    {
      source_type: state.reader.mode || "pdf",
      anchor_scope: "page",
      page_number: state.reader.pageNumber,
      quote_text: "",
      quote_prefix: "",
      quote_suffix: "",
      quote_start: null,
      quote_end: null,
      segment_key: "",
      segment_start: null,
      segment_end: null,
    },
    true
  );
});
pdfTextLayer?.addEventListener("pointerdown", () => {
  state.reader.pointerDownInPdf = true;
});
pdfPageStage?.addEventListener("pointerdown", () => {
  state.reader.pointerDownInPdf = true;
});
docxContent?.addEventListener("pointerdown", () => {
  state.reader.pointerDownInPdf = true;
});
document.addEventListener("selectionchange", () => {
  schedulePdfSelectionCapture("selectionchange");
});
window.addEventListener("pointerup", () => {
  schedulePdfSelectionCapture("pointerup");
  state.reader.pointerDownInPdf = false;
});
window.addEventListener("pointercancel", () => {
  state.reader.pointerDownInPdf = false;
});

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
  state.reader.userZoomFactor = zoom;
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
