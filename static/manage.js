/* ===== Auth ===== */
const TOKEN = localStorage.getItem('adminToken');
const api = (url, opts = {}) => {
    opts.headers = { ...opts.headers, 'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json' };
    return fetch(url, opts).then(r => { if (r.status === 401) { logout(); throw new Error('unauthorized'); } return r.json(); });
};

function checkAuth() {
    if (!TOKEN) { location.href = '/static/login.html'; return; }
    api('/admin/status').catch(() => logout());
}

function logout() {
    localStorage.removeItem('adminToken');
    location.href = '/static/login.html';
}

/* ===== Toast ===== */
function showToast(msg, type = 'info') {
    const colors = { success: 'bg-green-600', error: 'bg-red-600', info: 'bg-gray-900' };
    const el = document.createElement('div');
    el.className = `fixed bottom-4 right-4 ${colors[type] || colors.info} text-white px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium z-[200] animate-slide-up`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; setTimeout(() => el.remove(), 300); }, 2000);
}

/* ===== Tabs ===== */
function switchTab(tab) {
    ['accounts', 'settings', 'chat'].forEach(t => {
        document.getElementById('panel' + t.charAt(0).toUpperCase() + t.slice(1)).classList.toggle('hidden', t !== tab);
        const btn = document.getElementById('tab' + t.charAt(0).toUpperCase() + t.slice(1));
        btn.classList.toggle('border-primary', t === tab);
        btn.classList.toggle('border-transparent', t !== tab);
        btn.classList.toggle('text-muted-foreground', t !== tab);
    });
    if (tab === 'settings') loadSettings();
    if (tab === 'accounts') loadAccounts();
    if (tab === 'chat') loadChatModels();
}

/* ===== Accounts ===== */
let _accounts = [];

function loadAccounts() {
    api('/admin/accounts').then(d => {
        _accounts = d.accounts || [];
        const s = d.stats || {};
        document.getElementById('statTotal').textContent = s.total ?? _accounts.length;
        document.getElementById('statActive').textContent = s.active ?? '-';
        document.getElementById('statCost').textContent = '$' + (s.cost ?? 0).toFixed(2);
        document.getElementById('statRequests').textContent = s.requests ?? '-';
        renderAccounts();
    }).catch(() => showToast('加载账号失败', 'error'));
}

let _pageSize = 20;
let _currentPage = 1;

function renderAccounts() {
    const box = document.getElementById('accountList');
    const filter = document.getElementById('accountFilter').value;
    const filtered = _accounts.map((a, i) => ({ ...a, _idx: i })).filter(a => {
        if (filter === 'active') return a.active === true;
        if (filter === 'expired') return a.active !== true;
        return true;
    });
    const totalPages = Math.max(1, Math.ceil(filtered.length / _pageSize));
    if (_currentPage > totalPages) _currentPage = totalPages;
    const start = (_currentPage - 1) * _pageSize;
    const paged = filtered.slice(start, start + _pageSize);
    if (!filtered.length) {
        box.innerHTML = `<tr><td colspan="6" class="text-center text-muted-foreground py-6 text-sm">${_accounts.length ? '无匹配账号' : '暂无账号，点击右上角添加'}</td></tr>`;
    } else {
        box.innerHTML = paged.map(a => {
            const active = a.active === true;
            const atTag = a.at_mask ? `<span class="text-green-600 font-mono text-xs">${a.at_mask}</span>` : '<span class="text-red-500">无</span>';
            const rtTag = a.rt_mask ? `<span class="text-green-600 font-mono text-xs">${a.rt_mask}</span>` : '<span class="text-red-500">无</span>';
            const statusHtml = active
                ? `<span class="inline-flex items-center gap-1.5 text-green-600"><span class="w-1.5 h-1.5 rounded-full bg-green-500"></span><span data-expires="${a.expires_at}"></span></span>`
                : `<span class="inline-flex items-center gap-1.5 text-muted-foreground"><span class="w-1.5 h-1.5 rounded-full bg-gray-400"></span>已过期</span>`;
            const checked = _selected.has(a._idx) ? 'checked' : '';
            return `<tr class="border-b border-border hover:bg-secondary/50 transition-colors">
                <td class="px-4 py-2.5 w-8"><input type="checkbox" data-idx="${a._idx}" ${checked} onchange="toggleSelect(${a._idx})" class="rounded"></td>
                <td class="px-4 py-2.5 font-medium">${a.email || '未知邮箱'}</td>
                <td class="px-4 py-2.5">${atTag}</td>
                <td class="px-4 py-2.5">${rtTag}</td>
                <td class="px-4 py-2.5">${statusHtml}</td>
                <td class="px-4 py-2.5 text-right">
                    <button onclick="refreshAccount(${a._idx})" class="text-xs px-2 py-1 rounded border border-border hover:bg-secondary transition-colors">刷新</button>
                    <button onclick="removeAccount(${a._idx})" class="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 transition-colors ml-1">删除</button>
                </td>
            </tr>`;
        }).join('');
    }
    const activeCount = _accounts.filter(a => a.active === true).length;
    const selCount = _selected.size;
    const selText = selCount ? `已选 ${selCount} | ` : '';
    // pagination
    let pageHtml = '';
    if (totalPages > 1) {
        pageHtml = `<button onclick="changePage(-1)" class="px-2 py-0.5 rounded border border-border hover:bg-secondary text-xs" ${_currentPage <= 1 ? 'disabled' : ''}>&lt;</button>
            <span class="mx-1">${_currentPage}/${totalPages}</span>
            <button onclick="changePage(1)" class="px-2 py-0.5 rounded border border-border hover:bg-secondary text-xs" ${_currentPage >= totalPages ? 'disabled' : ''}>&gt;</button>`;
    }
    document.getElementById('accountFooter').innerHTML = `<div class="flex items-center justify-between">
        <span>${selText}显示 ${filtered.length} / ${_accounts.length} 个账号（活跃 ${activeCount}）</span>
        <div class="flex items-center gap-2">
            ${pageHtml}
            <select onchange="changePageSize(this.value)" class="text-xs h-6 rounded border border-input bg-background px-1">
                ${[10,20,50,100,200,500,1000].map(n => `<option value="${n}" ${n===_pageSize?'selected':''}>${n}条/页</option>`).join('')}
            </select>
        </div>
    </div>`;
    document.getElementById('selectAll').checked = paged.length > 0 && paged.every(a => _selected.has(a._idx));
    updateCountdowns();
}

let _selected = new Set();
function toggleSelect(idx) {
    _selected.has(idx) ? _selected.delete(idx) : _selected.add(idx);
    renderAccounts();
}
function toggleSelectAll() {
    const all = document.getElementById('selectAll').checked;
    const filter = document.getElementById('accountFilter').value;
    const filtered = _accounts.map((a, i) => ({ ...a, _idx: i })).filter(a => {
        if (filter === 'active') return a.active === true;
        if (filter === 'expired') return a.active !== true;
        return true;
    });
    const start = (_currentPage - 1) * _pageSize;
    const paged = filtered.slice(start, start + _pageSize);
    paged.forEach(a => all ? _selected.add(a._idx) : _selected.delete(a._idx));
    renderAccounts();
}
function getSelectedIndices() { return [..._selected]; }
function changePageSize(v) { _pageSize = parseInt(v); _currentPage = 1; renderAccounts(); }
function changePage(delta) { _currentPage += delta; renderAccounts(); }

function updateCountdowns() {
    document.querySelectorAll('[data-expires]').forEach(el => {
        const exp = parseInt(el.dataset.expires);
        const diff = exp - Date.now();
        if (diff <= 0) { el.textContent = '已过期'; el.className = 'text-red-500'; return; }
        const d = Math.floor(diff / 86400000);
        const h = Math.floor((diff % 86400000) / 3600000);
        const m = Math.floor((diff % 3600000) / 60000);
        let text = '';
        if (d > 0) text += d + '天';
        text += h + 'h ' + m + 'm';
        el.textContent = text;
        if (d < 1) el.className = 'text-orange-500';
    });
}
if (!window._countdownTimer) window._countdownTimer = setInterval(updateCountdowns, 1000);

function refreshAccount(idx) {
    api(`/admin/accounts/${idx}/refresh`, { method: 'POST' }).then(d => {
        d.ok ? showToast('刷新成功', 'success') : showToast(d.error || '刷新失败', 'error');
        loadAccounts();
    });
}

function removeAccount(idx) {
    if (!confirm('确定删除该账号？')) return;
    api(`/admin/accounts/${idx}`, { method: 'DELETE' }).then(() => { showToast('已删除', 'success'); loadAccounts(); });
}

function refreshAllAccounts() {
    api('/admin/refresh', { method: 'POST' }).then(d => {
        d.ok ? showToast('全部刷新完成', 'success') : showToast('刷新失败', 'error');
        loadAccounts();
    });
}

function batchDeleteAccounts() {
    if (!confirm('确定删除所有账号？')) return;
    const indices = _accounts.map((_, i) => i);
    api('/admin/accounts/batch-delete', { method: 'POST', body: JSON.stringify({ indices }) }).then(d => {
        showToast(`已删除 ${d.removed} 个账号`, 'success'); loadAccounts();
    });
}

function exportAccounts() {
    api('/admin/accounts/export', { method: 'POST' }).then(d => {
        const blob = new Blob([JSON.stringify(d.accounts, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = 'ob1_accounts.json'; a.click();
        showToast('导出成功', 'success');
    });
}

function importAccounts() {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.json';
    input.onchange = e => {
        const file = e.target.files[0]; if (!file) return;
        const reader = new FileReader();
        reader.onload = ev => {
            try {
                const accounts = JSON.parse(ev.target.result);
                api('/admin/accounts/import', { method: 'POST', body: JSON.stringify({ accounts: Array.isArray(accounts) ? accounts : [accounts] }) })
                    .then(d => { showToast(`导入 ${d.imported} 个账号`, 'success'); loadAccounts(); });
            } catch { showToast('JSON 格式错误', 'error'); }
        };
        reader.readAsText(file);
    };
    input.click();
}

/* ===== Device Auth (Add Account) ===== */
let _pollTimer = null;

function openDeviceAuth() {
    document.getElementById('deviceAuthModal').classList.remove('hidden');
    document.getElementById('deviceAuthContent').classList.remove('hidden');
    document.getElementById('deviceAuthPending').classList.add('hidden');
}

function startDeviceAuth() {
    document.getElementById('deviceAuthContent').classList.add('hidden');
    document.getElementById('deviceAuthPending').classList.remove('hidden');
    api('/admin/device-auth', { method: 'POST' }).then(d => {
        if (d.error) {
            document.getElementById('deviceAuthContent').classList.remove('hidden');
            document.getElementById('deviceAuthPending').classList.add('hidden');
            showToast(d.error, 'error');
            return;
        }
        const link = document.getElementById('deviceAuthLink');
        link.href = d.verification_uri_complete || d.verification_uri;
        link.textContent = d.verification_uri_complete || d.verification_uri;
        document.getElementById('deviceAuthCode').textContent = d.user_code || '';
        pollDeviceAuth(d.device_code, d.interval || 5);
    }).catch(() => {
        document.getElementById('deviceAuthContent').classList.remove('hidden');
        document.getElementById('deviceAuthPending').classList.add('hidden');
        showToast('获取授权失败', 'error');
    });
}

function pollDeviceAuth(code, interval) {
    clearInterval(_pollTimer);
    _pollTimer = setInterval(() => {
        api('/admin/device-auth/poll', { method: 'POST', body: JSON.stringify({ device_code: code }) }).then(d => {
            if (d.status === 'complete') {
                clearInterval(_pollTimer);
                closeDeviceAuth();
                showToast(`已添加账号: ${d.email}`, 'success');
                loadAccounts();
            } else if (d.status === 'expired' || d.status === 'error') {
                clearInterval(_pollTimer);
                showToast(d.message || '授权失败', 'error');
            }
        });
    }, interval * 1000);
}

function closeDeviceAuth() {
    clearInterval(_pollTimer);
    document.getElementById('deviceAuthModal').classList.add('hidden');
}

/* ===== Settings ===== */
function loadSettings() {
    api('/admin/settings').then(d => {
        document.getElementById('cfgUsername').value = d.username || '';
        document.getElementById('cfgCurrentKey').value = d.api_key || '';
        document.getElementById('cfgProxy').value = d.proxy_url || '';
        selectRotation(d.rotation_mode || 'cache-first', false);
        document.getElementById('cfgDebugLog').checked = (d.log_level || 'INFO') === 'DEBUG';
        document.getElementById('cfgRefreshInterval').value = d.refresh_interval || 0;
    });
}

function updatePassword() {
    const old_password = document.getElementById('cfgOldPwd').value;
    const new_password = document.getElementById('cfgNewPwd').value;
    if (!old_password || !new_password) { showToast('请填写完整', 'error'); return; }
    api('/admin/settings/password', { method: 'POST', body: JSON.stringify({ old_password, new_password }) }).then(d => {
        d.ok ? (showToast('密码已更新', 'success'), document.getElementById('cfgOldPwd').value = '', document.getElementById('cfgNewPwd').value = '') : showToast(d.message || '更新失败', 'error');
    });
}

function updateUsername() {
    const username = document.getElementById('cfgUsername').value.trim();
    if (!username) return;
    api('/admin/settings/username', { method: 'POST', body: JSON.stringify({ username }) }).then(d => {
        d.ok ? showToast('用户名已更新', 'success') : showToast('更新失败', 'error');
    });
}

function updateAPIKey() {
    const api_key = document.getElementById('cfgNewKey').value.trim();
    if (!api_key) return;
    api('/admin/settings/api-key', { method: 'POST', body: JSON.stringify({ api_key }) }).then(d => {
        d.ok ? showToast('API Key 已更新', 'success') : showToast('更新失败', 'error');
    });
}

function updateProxy() {
    const url = document.getElementById('cfgProxy').value.trim();
    api('/admin/settings/proxy', { method: 'POST', body: JSON.stringify({ url }) }).then(d => {
        d.ok ? showToast('代理已更新', 'success') : showToast('更新失败', 'error');
    });
}

function testProxy() {
    const url = document.getElementById('cfgProxy').value.trim();
    if (!url) { showToast('请先填写代理地址', 'error'); return; }
    const btn = document.getElementById('btnTestProxy');
    btn.disabled = true; btn.textContent = '测试中...';
    api('/admin/settings/proxy-test', { method: 'POST', body: JSON.stringify({ url }) }).then(d => {
        if (d.ok) showToast('代理可用，IP: ' + d.ip, 'success');
        else showToast('代理不可用: ' + d.error, 'error');
    }).catch(() => showToast('测试请求失败', 'error'))
    .finally(() => { btn.disabled = false; btn.textContent = '测试'; });
}

function selectRotation(mode, save = true) {
    document.getElementById('cfgRotationMode').value = mode;
    if (save) {
        api('/admin/settings/rotation-mode', { method: 'POST', body: JSON.stringify({ mode }) }).then(d => {
            d.ok ? showToast('调度模式已更新', 'success') : showToast(d.message || '更新失败', 'error');
        });
    }
}

function toggleDebugLog() {
    const level = document.getElementById('cfgDebugLog').checked ? 'DEBUG' : 'INFO';
    api('/admin/settings/log-level', { method: 'POST', body: JSON.stringify({ level }) }).then(d => {
        d.ok ? showToast(level === 'DEBUG' ? '调试日志已开启' : '调试日志已关闭', 'success') : showToast(d.message || '更新失败', 'error');
    });
}

function updateRefreshInterval() {
    const interval = parseInt(document.getElementById('cfgRefreshInterval').value) || 0;
    api('/admin/settings/refresh-interval', { method: 'POST', body: JSON.stringify({ interval }) }).then(d => {
        d.ok ? showToast(interval > 0 ? `自动续期检查已设置为 ${interval} 分钟` : '自动续期已关闭', 'success') : showToast(d.message || '更新失败', 'error');
    });
}

/* ===== Chat ===== */
let _chatMessages = [];

const TOP_MODELS = [
    'anthropic/claude-opus-4.6',
    'anthropic/claude-sonnet-4.6',
    'openai/gpt-5.4-pro',
    'google/gemini-3.1-flash-image-preview',
    'openai/gpt-5.3-codex',
    'x-ai/grok-4.1-fast',
    'qwen/qwen-3.5-397b',
];

function _shortName(id) { return id.includes('/') ? id.split('/').pop() : id; }

function loadChatModels() {
    const sel = document.getElementById('chatModel');
    const prev = sel.value;
    fetch('/v1/models', { headers: { 'Authorization': 'Bearer ' + TOKEN } })
        .then(r => r.json())
        .then(d => {
            const apiIds = (d.data || []).map(m => m.id);
            _fillModelSelect(sel, apiIds, prev);
        })
        .catch(() => _fillModelSelect(sel, [], prev));
}

function _fillModelSelect(sel, apiIds, prev) {
    const all = new Set([...TOP_MODELS, ...apiIds]);
    const topSet = new Set(TOP_MODELS);
    const rest = [...all].filter(id => !topSet.has(id)).sort();
    let html = '<optgroup label="常用">';
    html += TOP_MODELS.map(id => `<option value="${id}">${_shortName(id)}</option>`).join('');
    html += '</optgroup>';
    if (rest.length) {
        html += '<optgroup label="全部">';
        html += rest.map(id => `<option value="${id}">${_shortName(id)}</option>`).join('');
        html += '</optgroup>';
    }
    sel.innerHTML = html;
    sel.value = prev && all.has(prev) ? prev : TOP_MODELS[0];
}

function _parseAssistantMsg(msg) {
    const content = msg.content;
    const result = { role: 'assistant', content: '', images: [] };
    if (typeof content === 'string') {
        result.content = content || '';
    } else if (Array.isArray(content)) {
        for (const part of content) {
            if (part.type === 'text') result.content += part.text || '';
            else if (part.type === 'image_url') result.images.push(part.image_url?.url || '');
        }
    }
    // OB1/OpenRouter puts images in message.images
    if (Array.isArray(msg.images)) {
        for (const img of msg.images) {
            if (img.image_url?.url) result.images.push(img.image_url.url);
            else if (typeof img === 'string') result.images.push(img);
        }
    }
    if (!result.content && !result.images.length) result.content = 'No response';
    return result;
}

function sendChat() {
    const input = document.getElementById('chatInput');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    _chatMessages.push({ role: 'user', content: msg });
    renderChat();

    const model = document.getElementById('chatModel').value;
    const stream = document.getElementById('chatStream').checked;

    if (stream) {
        streamChat(model, msg);
    } else {
        api('/v1/chat/completions', {
            method: 'POST',
            body: JSON.stringify({ model, messages: _chatMessages, stream: false })
        }).then(d => {
            const msg = d.choices?.[0]?.message || {};
            const parsed = _parseAssistantMsg(msg);
            _chatMessages.push(parsed);
            renderChat();
        }).catch(() => {
            _chatMessages.push({ role: 'assistant', content: '请求失败' });
            renderChat();
        });
    }
}

function streamChat(model, msg) {
    const assistantMsg = { role: 'assistant', content: '' };
    _chatMessages.push(assistantMsg);
    renderChat();

    fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, messages: _chatMessages.slice(0, -1), stream: true })
    }).then(resp => {
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        function read() {
            reader.read().then(({ done, value }) => {
                if (done) { renderChat(); return; }
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split('\n');
                buf = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith('data: ') || line === 'data: [DONE]') continue;
                    try {
                        const j = JSON.parse(line.slice(6));
                        const delta = j.choices?.[0]?.delta?.content;
                        if (delta) { assistantMsg.content += delta; renderChat(); }
                    } catch {}
                }
                read();
            });
        }
        read();
    }).catch(() => { assistantMsg.content = '流式请求失败'; renderChat(); });
}

function renderChat() {
    const box = document.getElementById('chatMessages');
    box.innerHTML = _chatMessages.map(m => {
        const isUser = m.role === 'user';
        let rendered = typeof marked !== 'undefined' ? marked.parse(m.content || '') : (m.content || '');
        if (m.images && m.images.length) {
            rendered += m.images.map(url => `<img src="${url}" class="mt-2 max-w-full rounded-lg cursor-pointer" style="max-height:400px" onclick="window.open(this.src,'_blank')" alt="生成图片">`).join('');
        }
        return `<div class="flex ${isUser ? 'justify-end' : 'justify-start'} mb-3">
            <div class="chat-msg max-w-[80%] rounded-lg px-4 py-2 text-sm ${isUser ? 'bg-primary text-primary-foreground' : 'bg-secondary'}">
                ${rendered}
            </div>
        </div>`;
    }).join('');
    box.scrollTop = box.scrollHeight;
    document.querySelectorAll('.chat-msg pre code').forEach(el => hljs.highlightElement(el));
}

function clearChat() {
    _chatMessages = [];
    document.getElementById('chatMessages').innerHTML = '';
}

/* ===== Init ===== */
window.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    loadAccounts();
    document.getElementById('chatInput').addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
});
