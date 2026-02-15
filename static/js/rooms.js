const createRoomForm = document.getElementById("createRoomForm");
const joinRoomForm = document.getElementById("joinRoomForm");
const createResult = document.getElementById("createResult");
const globalMessage = document.getElementById("globalMessage");
const defaultRoomSlug = document.body.dataset.defaultRoomSlug || "demo";

const quickDemoButton = document.getElementById("quickDemoButton");
const sharePreview = document.getElementById("sharePreview");
const copyShareButton = document.getElementById("copyShareButton");

function showGlobalMessage(text, type = "error") {
    globalMessage.hidden = false;
    globalMessage.className = `message ${type}`;
    globalMessage.textContent = text;
}

function clearGlobalMessage() {
    globalMessage.hidden = true;
    globalMessage.textContent = "";
    globalMessage.className = "message";
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

function normalizeSlug(rawValue) {
    return String(rawValue || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9-]+/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "");
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

async function requestJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));

    if (!response.ok || data.success === false) {
        throw new Error(data.message || `Request failed (${response.status})`);
    }

    return data;
}

createRoomForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearGlobalMessage();
    createResult.hidden = true;

    const name = document.getElementById("createRoomName").value.trim();
    const slug = normalizeSlug(document.getElementById("createRoomSlug").value);
    const passcode = document.getElementById("createRoomPasscode").value;

    if (!name) {
        showGlobalMessage("请输入房间名称。");
        return;
    }
    if (passcode.trim().length < 4) {
        showGlobalMessage("房间口令至少 4 位。");
        return;
    }

    const submitButton = createRoomForm.querySelector('button[type="submit"]');

    try {
        setButtonLoading(submitButton, true, "创建中...");

        const payload = {name, passcode};
        if (slug) {
            payload.slug = slug;
        }

        const data = await requestJson("/api/rooms", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload),
        });

        createResult.hidden = false;
        createResult.innerHTML = `
            <p>房间创建成功：<strong>${data.room.name}</strong></p>
            <p>分享链接：<a href="${data.share_url}" target="_blank" rel="noopener noreferrer">${data.share_url}</a></p>
            <p>0.9 秒后自动进入房间...</p>
        `;

        setTimeout(() => {
            window.location.href = `/r/${data.room.slug}`;
        }, 900);
    } catch (error) {
        showGlobalMessage(error.message);
    } finally {
        setButtonLoading(submitButton, false);
    }
});

joinRoomForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearGlobalMessage();

    const rawSlug = document.getElementById("joinRoomSlug").value;
    const slug = normalizeSlug(rawSlug);
    const passcode = document.getElementById("joinRoomPasscode").value;

    if (!slug) {
        showGlobalMessage("请输入正确的房间标识。");
        return;
    }

    const submitButton = joinRoomForm.querySelector('button[type="submit"]');

    try {
        setButtonLoading(submitButton, true, "验证中...");

        await requestJson(`/api/rooms/${slug}/auth`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({passcode}),
        });

        window.location.href = `/r/${slug}`;
    } catch (error) {
        showGlobalMessage(error.message);
    } finally {
        setButtonLoading(submitButton, false);
    }
});

quickDemoButton?.addEventListener("click", () => {
    const slugInput = document.getElementById("joinRoomSlug");
    slugInput.value = defaultRoomSlug;
    slugInput.dispatchEvent(new Event("input", {bubbles: true}));
    showGlobalMessage("已填充默认房间标识，输入口令后即可进入。", "info");
});

copyShareButton?.addEventListener("click", async () => {
    clearGlobalMessage();
    try {
        await copyText(sharePreview?.value || "");
        showGlobalMessage("分享链接已复制。", "success");
    } catch (error) {
        showGlobalMessage(error.message || "复制失败，请手动复制链接。");
    }
});

document.getElementById("joinRoomSlug").value = defaultRoomSlug;
