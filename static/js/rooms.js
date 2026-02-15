const createRoomForm = document.getElementById('createRoomForm');
const joinRoomForm = document.getElementById('joinRoomForm');
const createResult = document.getElementById('createResult');
const globalMessage = document.getElementById('globalMessage');
const defaultRoomSlug = document.body.dataset.defaultRoomSlug || 'demo';

function showGlobalMessage(text, type = 'error') {
    globalMessage.hidden = false;
    globalMessage.className = `message ${type}`;
    globalMessage.textContent = text;
}

function clearGlobalMessage() {
    globalMessage.hidden = true;
    globalMessage.textContent = '';
    globalMessage.className = 'message';
}

function normalizeSlug(rawValue) {
    return String(rawValue || '')
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9-]+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
}

async function requestJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));

    if (!response.ok || data.success === false) {
        throw new Error(data.message || `Request failed (${response.status})`);
    }

    return data;
}

createRoomForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearGlobalMessage();
    createResult.hidden = true;

    const name = document.getElementById('createRoomName').value.trim();
    const slug = normalizeSlug(document.getElementById('createRoomSlug').value);
    const passcode = document.getElementById('createRoomPasscode').value;

    const submitButton = createRoomForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;

    try {
        const payload = { name, passcode };
        if (slug) {
            payload.slug = slug;
        }

        const data = await requestJson('/api/rooms', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        createResult.hidden = false;
        createResult.innerHTML = `
            <p>房间创建成功：<strong>${data.room.name}</strong></p>
            <p>分享链接：<a href="${data.share_url}" target="_blank">${data.share_url}</a></p>
            <p>正在跳转到房间...</p>
        `;

        setTimeout(() => {
            window.location.href = `/r/${data.room.slug}`;
        }, 900);
    } catch (error) {
        showGlobalMessage(error.message);
    } finally {
        submitButton.disabled = false;
    }
});

joinRoomForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearGlobalMessage();

    const rawSlug = document.getElementById('joinRoomSlug').value;
    const slug = normalizeSlug(rawSlug);
    const passcode = document.getElementById('joinRoomPasscode').value;

    if (!slug) {
        showGlobalMessage('请先输入正确的房间标识。');
        return;
    }

    const submitButton = joinRoomForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;

    try {
        await requestJson(`/api/rooms/${slug}/auth`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ passcode }),
        });

        window.location.href = `/r/${slug}`;
    } catch (error) {
        showGlobalMessage(error.message);
    } finally {
        submitButton.disabled = false;
    }
});

document.getElementById('joinRoomSlug').value = defaultRoomSlug;
