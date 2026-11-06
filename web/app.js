const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = { dim: 'classify', path: [], files: [], selected: new Set(), counts: {}, source: {}, preview: null, kind: '', kindOptions: [] };

async function api(path, opts) {
  const r = await fetch(path, opts);
  const d = await r.json();
  if (!d.ok && d.error) throw new Error(d.error);
  return d;
}
function toast(msg, ms = 4200) {
  const t = $('#toast'); t.textContent = msg; t.classList.remove('hidden');
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add('hidden'), ms);
}
function nodeParam(path) { return encodeURIComponent(JSON.stringify(path)); }

async function loadState() {
  const d = await api('/api/state');
  state.counts = d.counts; state.source = d.source;
  const on = d.source.mode === 'live';
  const offlineNote = (!on && (d.source.errors || []).length)
    ? `<div class="mini" style="margin-top:6px;padding:6px 8px;border-radius:6px;background:var(--warn-bg);color:var(--warn)">${esc(d.source.errors[0])}<br>通常是本机 NapCat 没运行。点「启动 NapCat」可自动拉起，或右上角「QQ 登录」网页里扫码：<button class="btn small primary" id="sb-napcat">启动 NapCat</button></div>`
    : '';
  const loginBtn = $('#btn-login');
  loginBtn.className = on ? 'btn' : 'btn warn';
  loginBtn.title = on ? 'QQ 已在线，可打开登录页查看状态' : 'QQ 登录态失效，打开网页扫码登录';
  $('#sources').innerHTML = `
    <div class="src"><span>QQ 群文件</span><span class="badge ${on ? '' : 'warn'}">${on ? '在线' : (d.source.mode === 'snapshot' ? '离线快照' : '未连接')}</span></div>
    <div class="src"><span>微信</span><span class="badge off">未接入</span></div>
    ${offlineNote}
    <div class="muted" style="font-size:11px">${esc(Object.entries(d.source.groups || {}).map(([k,v]) => `${k} ${v.files}`).join(' · '))}</div>`;
  const bn = $('#sb-napcat');
  if (bn) bn.onclick = async () => {
    toast('正在拉起 NapCat…', 4000);
    let r;
    try {
      r = await (await fetch('/api/napcat/start', {method:'POST',
              headers:{'Content-Type':'application/json'}, body:'{}'})).json();
    } catch (e) { toast('启动请求失败：' + e.message, 7000); return; }
    toast(r.ok ? (r.msg || '已启动 NapCat，稍后点「刷新来源」') : ('启动失败：' + (r.error || '')), 7000);
    if (r.ok) setTimeout(() => $('#btn-refresh').click(), 9000);
  };
  const w = d.wechat || {};
  $('#wechat-limits').innerHTML = `<details><summary>微信接入限制（点击展开）</summary>
    ${esc(w.reason || '')}<br>${Object.values(w.limits || {}).map(x => '· ' + esc(x)).join('<br>')}</details>`;
  const c = d.counts;
  $('#stats').innerHTML = `<div>授权可见 <b>${c.total}</b> 份</div>
    <div>已下载 <b>${c.downloaded}</b> · 仅元数据 <b>${c.metadata_only}</b></div>
    <div>${c.domains} 个领域 / ${c.subjects} 个科目</div>
    <div class="muted">合计约 ${(c.size_bytes/1024/1024/1024).toFixed(2)} GB</div>
    <div class="muted">单批下载上限 ${d.download_cap} 个文件</div>`;
}

function renderCrumb() {
  const parts = ['<span>全部</span>'];
  let acc = [];
  state.path.forEach((n, i) => { acc.push(n); parts.push(`<span>›</span><b data-i="${i}">${esc(n)}</b>`); });
  $('#crumb').innerHTML = parts.join(' ');
  $('#crumb').querySelectorAll('b').forEach(el => el.onclick = () => {
    state.path = state.path.slice(0, +el.dataset.i + 1); reload();
  });
  $('#crumb').querySelector('span').onclick = () => { state.path = []; reload(); };
  $('#node-title').textContent = state.path.length ? state.path.join(' › ') : '全部资源';
}

async function reload() {
  renderCrumb();
  $('#search').value = state.search || '';
  const node = nodeParam(state.path);
  const [t, f] = await Promise.all([
    api(`/api/tree?dim=${state.dim}&node=${node}`),
    api(`/api/files?dim=${state.dim}&node=${node}&q=${encodeURIComponent(state.search || '')}&limit=500&kind=${encodeURIComponent(state.kind || '')}`)
  ]);
  // 左栏：当前节点的同级（点选可切换分支）
  const parent = nodeParam(state.path.slice(0, -1));
  const sib = state.path.length ? await api(`/api/tree?dim=${state.dim}&node=${parent}`) : { children: [] };
  $('#tree').innerHTML = (sib.children.length ? sib.children : t.children).map(c =>
    `<div class="${c.name === state.path[state.path.length-1] ? 'active' : ''}" data-name="${esc(c.name)}"><span>${esc(c.name)}</span><span class="n">${c.count}</span></div>`
  ).join('') || '<div class="muted">暂无分类</div>';
  $('#tree').querySelectorAll('[data-name]').forEach(el => el.onclick = () => {
    const name = el.dataset.name;
    state.path = state.path.length ? [...state.path.slice(0, -1), name] : [name];
    state.selected.clear(); state.kind = ''; state.kindOptions = []; reload();
  });
  $('#children').innerHTML = t.children.map(c =>
    `<div class="child" data-name="${esc(c.name)}"><div class="t">${esc(c.name)}</div>
     <div class="d">${c.count} 份 · 已下载 ${c.downloaded} · ${esc(c.size)}</div></div>`
  ).join('');
  $('#children').querySelectorAll('[data-name]').forEach(el => el.onclick = () => {
    state.path.push(el.dataset.name); state.selected.clear(); state.kind = ''; state.kindOptions = []; reload();
  });
  state.files = f.items;
  const cap = f.truncated ? `（当前显示前 ${f.shown} 份，可继续下钻缩小范围）` : '';
  $('#node-sub').textContent = `${f.total} 份文件${cap}${t.children.length ? ' · 可继续下钻到下一级' : ' · 当前层级为末级'}`;
  renderKindBar();
  renderFiles();
  $('#ai-scope').textContent = '当前范围：' + (state.path.length ? state.path.join(' › ') : '全部') + (state.kind ? ' › ' + state.kind : '');
}

function renderKindBar() {
  // 仅在「未指定类型」时根据当前文件集重新计算可选类型，避免被单类型过滤结果反向覆盖
  if (!state.kind) {
    const seen = {};
    state.files.forEach(x => { if (x.kind) seen[x.kind] = (seen[x.kind] || 0) + 1; });
    state.kindOptions = Object.keys(seen).sort((a, b) => seen[b] - seen[a]);
  }
  const opts = [{ name: '', n: state.files.length }, ...state.kindOptions.map(k => ({ name: k, n: state.files.filter(x => x.kind === k).length }))];
  if (opts.length <= 1) { $('#kindbar').innerHTML = ''; return; }
  $('#kindbar').innerHTML = opts.map(o =>
    `<span class="k ${state.kind === o.name ? 'active' : ''}" data-kind="${esc(o.name)}">${o.name || '全部'}<i>${o.n}</i></span>`).join('');
  $('#kindbar').querySelectorAll('[data-kind]').forEach(el => el.onclick = () => {
    state.kind = el.dataset.kind; reload();
  });
}

function renderFiles() {
  if (!state.files.length) { $('#files').innerHTML = '<div class="empty">没有匹配的文件</div>'; return; }
  $('#files').innerHTML = state.files.map((x, i) => `
    <div class="file">
      <input type="checkbox" data-id="${esc(x.id)}" ${state.selected.has(x.id) ? 'checked' : ''} ${x.downloaded ? 'disabled' : ''}>
      <div class="name">${esc(x.name)}
        <div class="meta">${esc(x.domain)} / ${esc(x.subject)} / ${esc(x.kind)} · ${esc(x.size)} · ${x.downloaded ? '<span style="color:var(--ok)">已下载</span>' : '<span style="color:var(--warn)">仅元数据 · 未下载</span>'}${x.summary ? ' · ' + esc(x.summary.slice(0, 42)) : ''}</div>
      </div>
      <span class="link" data-id="${esc(x.id)}">预览</span>
    </div>`).join('');
  $('#files').querySelectorAll('input[data-id]').forEach(el => el.onchange = () => {
    el.checked ? state.selected.add(el.dataset.id) : state.selected.delete(el.dataset.id);
    $('#btn-download-selected').textContent = `下载已选（${state.selected.size}）`;
  });
  $('#files').querySelectorAll('.link').forEach(el => el.onclick = () => showPreview(el.dataset.id));
  $('#btn-download-selected').textContent = `下载已选（${state.selected.size}）`;
}

async function showPreview(id) {
  const d = await api('/api/file?id=' + encodeURIComponent(id));
  const x = d.item; state.preview = x;
  $('#preview').innerHTML = `
    <div style="font-weight:600;margin-bottom:6px">${esc(x.name)}</div>
    <div class="muted" style="line-height:1.8">
      来源：${esc(x.source)} / ${esc(x.group)}<br>
      分类：${esc(x.domain)} › ${esc(x.subject)} › ${esc(x.kind)}<br>
      群内路径：${esc(x.path)}<br>
      体积：${esc(x.size)} · 上传：${esc(x.uploaded_at || '未知')}<br>
      状态：${x.downloaded ? '<span style="color:var(--ok)">已下载</span>' : '<span style="color:var(--warn)">仅元数据，未下载，无正文摘要</span>'}
    </div>
    <div style="margin-top:10px"><b>内容摘要</b><div class="muted" style="margin-top:4px">${esc(x.summary || '尚未下载，无正文摘要；只有文件名、路径与分类等元数据')}</div></div>
    ${x.body_excerpt ? `<div style="margin-top:10px"><b>正文片段</b><div class="muted" style="max-height:150px;overflow:auto;white-space:pre-wrap;margin-top:4px">${esc(x.body_excerpt.slice(0, 900))}</div></div>` : ''}
    ${x.note_abs ? `<div class="muted" style="margin-top:8px;word-break:break-all">笔记：${esc(x.note_abs)}</div>` : ''}
    <div class="row gap" style="margin-top:12px">
      <button class="btn small primary" id="pv-download" ${x.downloaded ? 'disabled' : ''}>${x.downloaded ? '已下载' : '下载此文件'}</button>
      <button class="btn small" id="pv-copy">复制路径</button>
    </div>`;
  const b = $('#pv-download');
  if (b) b.onclick = () => confirmDownload([x.id], 'selection', '', x.name);
  $('#pv-copy').onclick = () => { navigator.clipboard.writeText(x.asset_abs || x.path); toast('已复制路径'); };
}

function modal(html) { $('#dialog').innerHTML = html; $('#modal').classList.remove('hidden'); }
function closeModal() { $('#modal').classList.add('hidden'); }
$('#modal').onclick = (e) => { if (e.target.id === 'modal') closeModal(); };

async function confirmDownload(ids, scope, nodeName, singleName) {
  if (!ids.length) return toast('请先勾选文件');
  const chosen = ids.map(id => state.files.find(f => f.id === id)).filter(Boolean);
  const bytes = chosen.reduce((a, b) => a + (b.size_bytes || 0), 0);
  const second = scope === 'category';
  modal(`<h3>${second ? '整类下载 · 二次确认' : '确认下载'}</h3>
    <div class="muted">即将下载 <b>${ids.length}</b> 个文件，合计约 <b>${(bytes/1024/1024).toFixed(2)} MB</b>。
    下载后会自动分类入库、生成摘要与多级大纲。${second ? '<br><span style="color:var(--warn)">整类下载影响范围较大，请原样输入节点名称确认。</span>' : ''}</div>
    <div class="list" style="margin-top:10px">${chosen.slice(0, 12).map(x => `<div>· ${esc(x.name)}</div>`).join('')}${chosen.length > 12 ? `<div>… 其余 ${chosen.length-12} 个</div>` : ''}</div>
    ${second ? `<label>请输入节点名称「${esc(nodeName)}」</label><input id="cf" placeholder="${esc(nodeName)}">` : ''}
    <div class="actions"><button class="btn" id="mc">取消</button><button class="btn primary" id="mok">确认下载</button></div>`);
  $('#mc').onclick = closeModal;
  $('#mok').onclick = async () => {
    const ct = second ? ($('#cf').value || '') : '';
    const btn = $('#mok'); btn.disabled = true; btn.textContent = '下载中…';
    try {
      const r = await api('/api/download', { method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ ids, scope, confirm: true, confirmText: ct, nodeName }) });
      closeModal();
      toast(`完成 ${r.succeeded}/${r.attempted} 个${r.skipped_over_cap ? `，另有 ${r.skipped_over_cap} 个超出单批上限` : ''}${r.error ? ' · ' + r.error : ''}`, 7000);
      state.selected.clear();
      await loadState(); await reload();
      if (state.preview && ids.includes(state.preview.id)) showPreview(state.preview.id);
    } catch (e) { btn.disabled = false; btn.textContent = '确认下载'; toast('下载失败：' + e.message, 7000); }
  };
  if (second) $('#cf').focus();
}

function addMsg(role, text, sources) {
  const el = document.createElement('div');
  el.className = 'msg' + (role === 'me' ? ' me' : '');
  el.innerHTML = esc(text) + (sources && sources.length ? `<div class="srcs"><b>源文件索引</b>` +
    sources.map(s => `<div class="srcitem" data-id="${esc(s.id)}">↳ ${esc(s.name)} · ${s.downloaded ? '已下载' : '仅元数据'}</div>`).join('') + '</div>' : '');
  $('#chat').appendChild(el);
  $('#chat').scrollTop = $('#chat').scrollHeight;
  el.querySelectorAll('.srcitem').forEach(n => n.onclick = () => showPreview(n.dataset.id));
}

async function ask(q) {
  if (!q.trim()) return;
  addMsg('me', q); $('#ask').value = '';
  const el = document.createElement('div'); el.className = 'msg'; el.textContent = '检索中…';
  $('#chat').appendChild(el);
  try {
    const scope = JSON.stringify(state.path);
    const d = await api(`/api/ask?q=${encodeURIComponent(q)}&fast=${$('#fast').checked ? 1 : 0}&scope=${encodeURIComponent(scope)}`);
    const scopeTxt = d.scope && Object.keys(d.scope).length ? ' · 范围 ' + Object.values(d.scope).join('›') : '';
    el.remove(); addMsg('ai', d.answer + `\n\n[${d.mode} · ${d.took_ms} ms${d.found ? '' : ' · 未命中'}${scopeTxt} ]`, d.sources);
  } catch (e) { el.remove(); addMsg('ai', '请求失败：' + e.message); }
}

function settingsModal() {
  api('/api/settings').then(d => {
    const s = d.settings;
    modal(`<h3>AI 助手设置</h3>
      <label>模型来源</label><select id="st-provider">
        <option value="local" ${s.provider === 'local' ? 'selected' : ''}>本地模型（Bonsai2 / llama.cpp）</option>
        <option value="openai_compatible" ${s.provider !== 'local' ? 'selected' : ''}>外部 API（OpenAI 兼容）</option>
      </select>
      <label>本地模型接口 base_url</label><input id="st-local-url" value="${esc(s.base_url)}">
      <label>本地模型名称</label><input id="st-local-model" value="${esc(s.model)}">
      <label>外部 API base_url（provider 选外部时生效）</label><input id="st-url" placeholder="https://api.example.com/v1">
      <label>外部 API 模型名</label><input id="st-model" placeholder="gpt-4o-mini">
      <label>外部 API Key（只存本机 state/secrets.json，不进仓库）</label><input id="st-key" type="password" placeholder="${s.has_api_key ? '已保存，留空表示不修改' : 'sk-...'}">
      <label><input type="checkbox" id="st-think" ${s.disable_thinking ? 'checked' : ''}> 关闭本地模型思考模式（强烈建议，否则单问可达数百秒）</label>
      <div class="actions"><button class="btn" id="st-test">测试连接</button><button class="btn" id="mc">取消</button><button class="btn primary" id="st-save">保存</button></div>
      <div class="muted" id="st-msg" style="margin-top:8px"></div>`);
    $('#mc').onclick = closeModal;
    $('#st-test').onclick = async () => {
      $('#st-msg').textContent = '测试中…';
      const r = await api('/api/settings/test', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
      $('#st-msg').textContent = (r.ok ? '接口可达 · ' : '') + r.message;
    };
    $('#st-save').onclick = async () => {
      const body = { provider: $('#st-provider').value,
        local_base_url: $('#st-local-url').value, local_model: $('#st-local-model').value,
        base_url: $('#st-url').value, model: $('#st-model').value,
        disable_thinking: $('#st-think').checked };
      if ($('#st-key').value) body.api_key = $('#st-key').value;
      await api('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
      closeModal(); toast('设置已保存（密钥仅存本机）');
    };
  });
}

$('#btn-login').onclick = () => window.open('/login', '_blank');
$('#btn-setup').onclick = () => { window.location.href = '/setup'; };
$('#btn-refresh').onclick = async () => {
  $('#btn-refresh').disabled = true; $('#btn-refresh').textContent = '刷新中…';
  try { const r = await api('/api/refresh', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    toast(`刷新完成：${r.mode} · ${r.items} 条元数据（仅只读，未下载任何文件）${r.errors?.length ? ' · ' + r.errors[0] : ''}`, 7000);
    await loadState(); await reload();
  } catch (e) { toast('刷新失败：' + e.message); }
  $('#btn-refresh').disabled = false; $('#btn-refresh').textContent = '刷新来源';
};
$('#dim').onchange = () => { state.dim = $('#dim').value; state.path = []; state.selected.clear(); state.kind = ''; state.kindOptions = []; reload(); };
$('#search').oninput = (e) => { state.search = e.target.value; clearTimeout(state._t); state._t = setTimeout(reload, 240); };
$('#btn-select-all').onclick = () => {
  state.files.filter(f => !f.downloaded).forEach(f => state.selected.add(f.id)); renderFiles();
};
$('#btn-download-selected').onclick = () => confirmDownload([...state.selected], 'selection', '');
$('#btn-download-category').onclick = () => {
  if (!state.path.length) return toast('请先下钻到一个具体分类，再执行整类下载');
  const ids = state.files.filter(f => !f.downloaded).map(f => f.id);
  if (!ids.length) return toast('当前分类没有待下载文件');
  confirmDownload(ids, 'category', state.path[state.path.length - 1]);
};
$('#btn-ask').onclick = () => ask($('#ask').value);
$('#ask').onkeydown = (e) => { if (e.key === 'Enter') ask($('#ask').value); };
$('#btn-settings').onclick = settingsModal;
$('#btn-ai').onclick = () => { $('#ai-card').scrollIntoView({behavior:'smooth'}); $('#ask').focus(); };
$('#chips').innerHTML = ['高等数学有哪些期末真题？', '复变函数积分变换怎么复习？', '线性代数课件资源在哪？', '宿舍水电费在哪交？']
  .map(q => `<span class="chip">${esc(q)}</span>`).join('');
$('#chips').querySelectorAll('.chip').forEach(el => el.onclick = () => ask(el.textContent));

async function checkSetup() {
  try {
    const d = await api('/api/setup');
    $('#btn-setup').onclick = () => { window.location.href = '/setup'; };
    if (!d.done) {
      const b = $('#setup-banner');
      b.classList.remove('hidden');
      b.innerHTML = '👋 <b>第一次用？</b> 花 2 分钟完成 2 步配置（安装 NapCat + 填你的 QQ 群）就能开始，不用懂原理。'
        + ' <button class="btn small primary" id="sb-go">开始配置</button>'
        + ' <span class="muted">配置向导会一步步带你做。</span>';
      $('#sb-go').onclick = () => { window.location.href = '/setup'; };
    }
  } catch (e) { /* 配置接口不可用时静默，不影响主界面 */ }
}

(async () => {
  try { await loadState(); await reload(); await checkSetup(); addMsg('ai', '已连接本地资源库。可以直接用口语提问，回答下方会给出可点击的源文件索引；查不到会如实说明。');
  } catch (e) { toast('初始化失败：' + e.message, 9000); }
})();
