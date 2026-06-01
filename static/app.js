/** 智能监控平台 — 管理端 SPA */

const API = '/api';

// ==================== 路由 ====================
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        tab.classList.add('active');
        const viewId = 'view-' + tab.dataset.view;
        document.getElementById(viewId).classList.add('active');
        if (tab.dataset.view === 'dashboard') loadDashboard();
        if (tab.dataset.view === 'systems') loadSystems();
        if (tab.dataset.view === 'incidents') loadIncidents();
        if (tab.dataset.view === 'register') loadDetectorOptions();
    });
});

// ==================== 仪表盘 ====================
async function loadDashboard() {
    try {
        const resp = await fetch(API + '/monitoring/status');
        const data = await resp.json();
        const d = data.data.result;

        document.getElementById('stats').innerHTML = `
            <div class="stat-card"><div class="label">监控系统</div><div class="value">${d.systems_total}</div></div>
            <div class="stat-card healthy"><div class="label">健康系统</div><div class="value">${d.systems_healthy}</div></div>
            <div class="stat-card warning"><div class="label">活跃告警</div><div class="value">${d.active_alerts}</div></div>
            <div class="stat-card critical"><div class="label">严重告警</div><div class="value">${d.critical_alerts}</div></div>
        `;

        let html = '<table><tr><th>名称</th><th>健康分</th><th>状态</th><th>调度</th><th>最后检测</th><th>操作</th></tr>';
        for (const s of d.systems) {
            const score = s.health_score || 100;
            const barColor = score >= 80 ? 'health-good' : score >= 50 ? 'health-warn' : 'health-bad';
            html += `<tr>
                <td><strong>${esc(s.name)}</strong></td>
                <td><div class="health-bar"><div class="fill ${barColor}" style="width:${score}%"></div></div>${score}</td>
                <td><span class="badge badge-${s.status === 'active' ? 'normal' : 'warning'}">${s.status}</span></td>
                <td>${s.scheduled ? '⏰ 已调度' : '⏸ 未调度'}</td>
                <td>${s.last_checked_at ? timeAgo(s.last_checked_at) : '从未'}</td>
                <td>
                    <button class="btn-sm" onclick="manualCheck('${s.id}')">🔍 检测</button>
                    <button class="btn-sm ${s.status === 'active' ? 'danger' : 'success'}" onclick="togglePause('${s.id}', '${s.status}')">${s.status === 'active' ? '⏸ 暂停' : '▶ 恢复'}</button>
                    <button class="btn-sm danger" onclick="deleteSystem('${s.id}')">🗑</button>
                </td>
            </tr>`;
        }
        html += '</table>';
        document.getElementById('dashboard-systems').innerHTML = html;
    } catch (e) { console.error(e); }
}

// ==================== 系统管理 ====================
async function loadSystems() {
    try {
        const resp = await fetch(API + '/systems');
        const data = await resp.json();
        const systems = data.data.result.systems;
        let html = '<table><tr><th>名称</th><th>类型</th><th>地址</th><th>检测器</th><th>间隔</th><th>状态</th><th>操作</th></tr>';
        for (const s of systems) {
            html += `<tr>
                <td><strong>${esc(s.name)}</strong></td>
                <td>${esc(s.system_type)}</td>
                <td><code>${esc(s.endpoint || '-')}</code></td>
                <td>${(s.detectors || []).map(d => d.name).join(', ') || '-'}</td>
                <td>${s.check_interval_seconds}s</td>
                <td><span class="badge badge-${s.status === 'active' ? 'normal' : 'warning'}">${s.status}</span></td>
                <td>
                    <button class="btn-sm" onclick="manualCheck('${s.id}')">🔍</button>
                    <button class="btn-sm danger" onclick="deleteSystem('${s.id}')">🗑</button>
                </td>
            </tr>`;
        }
        html += '</table>';
        if (systems.length === 0) html = '<p style="color:#94a3b8;margin-top:20px">还没有注册系统，点击 "➕ 注册系统" 开始监控</p>';
        document.getElementById('systems-list').innerHTML = html;
    } catch (e) { console.error(e); }
}

// ==================== 故障历史 ====================
async function loadIncidents() {
    const severity = document.getElementById('filter-severity')?.value || '';
    const status = document.getElementById('filter-status')?.value || '';
    let url = API + '/incidents?limit=50';
    if (severity) url += '&severity=' + severity;
    if (status) url += '&status=' + status;
    try {
        const resp = await fetch(url);
        const data = await resp.json();
        const incidents = data.data.result.incidents;
        if (incidents.length === 0) {
            document.getElementById('incidents-list').innerHTML = '<p style="color:#94a3b8;margin-top:20px">暂无故障记录 🎉</p>';
            return;
        }
        let html = '';
        for (const i of incidents) {
            html += `<div style="background:#1e293b;padding:16px;border-radius:8px;margin-bottom:8px;border-left:3px solid ${i.severity==='critical'?'#ef4444':'#f59e0b'}">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <strong>${esc(i.title)}</strong>
                    <span class="badge badge-${i.severity}">${i.severity}</span>
                </div>
                <div style="margin:8px 0;font-size:13px;color:#94a3b8">
                    ${esc(i.system_name)} | ${timeAgo(i.detected_at)}
                    <span class="badge badge-${i.status}">${i.status}</span>
                </div>
                <div>
                    <button class="btn-sm" onclick="viewReport('${i.id}')">📋 查看报告</button>
                    ${i.status === 'pending' ? `<button class="btn-sm" style="background:#0ea5e9;color:#fff;border-color:#0ea5e9" onclick="pushIncident('${i.id}')">📤 推送飞书</button>` : ''}
                    ${i.status === 'open' ? `<button class="btn-sm success" onclick="ackIncident('${i.id}')">✅ 确认</button>` : ''}
                    ${i.status !== 'resolved' ? `<button class="btn-sm success" onclick="resolveIncident('${i.id}')">✔ 解决</button>` : ''}
                </div>
            </div>`;
        }
        document.getElementById('incidents-list').innerHTML = html;
    } catch (e) { console.error(e); }
}

// ==================== 注册系统 ====================
async function loadDetectorOptions() {
    try {
        const resp = await fetch(API + '/detectors');
        const data = await resp.json();
        const detectors = data.data.result.detectors;
        let html = '';
        for (const d of detectors) {
            html += `<div class="detector-option">
                <label><input type="checkbox" name="detector" value="${d.name}" data-metric="${d.metric_name}"> ${d.name} <code style="font-size:11px;color:#64748b">(${d.metric_name})</code></label>
                <div class="desc">${esc(d.description)}</div>
                <div class="thresholds">
                    <span>警告≥</span><input type="number" value="${d.name.includes('http') ? 200 : 60}" data-th="warning" disabled>
                    <span>严重≥</span><input type="number" value="${d.name.includes('http') ? 200 : 80}" data-th="critical" disabled>
                </div>
            </div>`;
        }
        document.getElementById('detector-options').innerHTML = html;

        // 勾选检测器时启用阈值输入
        document.querySelectorAll('input[name="detector"]').forEach(cb => {
            cb.addEventListener('change', () => {
                const inputs = cb.closest('.detector-option').querySelectorAll('input[data-th]');
                inputs.forEach(i => i.disabled = !cb.checked);
            });
        });
    } catch (e) { console.error(e); }
}

document.getElementById('register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const detectors = [];
    document.querySelectorAll('input[name="detector"]:checked').forEach(cb => {
        const container = cb.closest('.detector-option');
        const warning = container.querySelector('input[data-th="warning"]');
        const critical = container.querySelector('input[data-th="critical"]');
        detectors.push({
            name: cb.value,
            thresholds: {
                warning: parseFloat(warning.value) || 60,
                critical: parseFloat(critical.value) || 80,
            }
        });
    });
    if (detectors.length === 0) {
        document.getElementById('register-result').innerHTML = '请至少选择一个检测器';
        document.getElementById('register-result').className = 'error';
        return;
    }
    const payload = {
        name: document.getElementById('reg-name').value,
        system_type: document.getElementById('reg-type').value,
        endpoint: document.getElementById('reg-endpoint').value,
        detectors: detectors,
        check_interval_seconds: parseInt(document.getElementById('reg-interval').value) || 60,
        alert_enabled: document.getElementById('reg-alert').checked,
    };
    try {
        const resp = await fetch(API + '/systems', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        const resultDiv = document.getElementById('register-result');
        if (data.data.success) {
            resultDiv.innerHTML = `✅ 系统 "${payload.name}" 注册成功！每 ${payload.check_interval_seconds}s 检测一次。`;
            resultDiv.className = 'success';
            document.getElementById('register-form').reset();
        } else {
            resultDiv.innerHTML = `❌ ${data.data.errorMessage}`;
            resultDiv.className = 'error';
        }
    } catch (err) {
        document.getElementById('register-result').innerHTML = `❌ 请求失败: ${err.message}`;
        document.getElementById('register-result').className = 'error';
    }
});

// ==================== 操作函数 ====================
async function manualCheck(systemId) {
    try {
        await fetch(API + '/systems/' + systemId + '/check', { method: 'POST' });
        setTimeout(loadDashboard, 2000);
    } catch (e) { console.error(e); }
}

async function togglePause(systemId, status) {
    const action = status === 'active' ? 'pause' : 'resume';
    await fetch(API + '/systems/' + systemId + '/' + action, { method: 'POST' });
    loadDashboard();
}

async function deleteSystem(systemId) {
    if (!confirm('确定要删除这个系统吗？')) return;
    await fetch(API + '/systems/' + systemId, { method: 'DELETE' });
    loadDashboard();
}

async function viewReport(incidentId) {
    try {
        const resp = await fetch(API + '/incidents/' + incidentId);
        const data = await resp.json();
        const incident = data.data.result;
        const isPending = incident.status === 'pending';
        document.getElementById('modal-body').innerHTML = `
            <h2>${esc(incident.title)}</h2>
            <p><span class="badge badge-${incident.severity}">${incident.severity}</span> <span class="badge badge-${incident.status}">${incident.status}</span> | ${timeAgo(incident.detected_at)}</p>
            <div class="markdown">${renderMarkdown(incident.report_markdown || incident.description || '无详细报告')}</div>
            <div style="margin-top:16px;display:flex;gap:8px">
                ${isPending ? `<button class="btn-primary" style="width:auto;padding:8px 20px" onclick="pushIncident('${incidentId}')">📤 保存并推送飞书</button>` : ''}
                <button class="btn-sm" onclick="closeModal()">关闭</button>
            </div>
        `;
        document.getElementById('modal').style.display = 'flex';
    } catch (e) { console.error(e); }
}

async function pushIncident(id) {
    await fetch(API + '/incidents/' + id + '/push', { method: 'POST' });
    closeModal();
    loadIncidents();
}

function closeModal() {
    document.getElementById('modal').style.display = 'none';
}

async function ackIncident(id) {
    await fetch(API + '/incidents/' + id + '/acknowledge', { method: 'PUT' });
    loadIncidents();
}

async function resolveIncident(id) {
    await fetch(API + '/incidents/' + id + '/resolve', { method: 'PUT' });
    loadIncidents();
}

// ==================== 工具函数 ====================
function esc(str) {
    return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function timeAgo(isoStr) {
    if (!isoStr) return '未知';
    const diff = Date.now() - new Date(isoStr).getTime();
    const sec = Math.floor(diff / 1000);
    if (sec < 60) return sec + '秒前';
    if (sec < 3600) return Math.floor(sec / 60) + '分钟前';
    if (sec < 86400) return Math.floor(sec / 3600) + '小时前';
    return Math.floor(sec / 86400) + '天前';
}

function renderMarkdown(md) {
    return (md || '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/### (.+)/g, '<h3>$1</h3>')
        .replace(/## (.+)/g, '<h2>$1</h2>')
        .replace(/# (.+)/g, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\|(.+)\|/g, (m) => {
            const cells = m.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
            return `<tr>${cells}</tr>`;
        })
        .replace(/\n/g, '<br>');
}

// 初始化
loadDashboard();
loadDetectorOptions();
