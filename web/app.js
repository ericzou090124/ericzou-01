// 资源管理 v3.2.0 前端：分类整理（单值 subject/kind/source）、下载到 Obsidian、AI 问答。
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// 命中高亮：先转义防 XSS，再按查询词（CJK 整串 / 拉丁按空白切词）不区分大小写包裹 <mark>
function hl(text) {
  const q = (state.search || '').trim();
  const safe = esc(text);
  if (!q) return safe;
  const terms = q.split(/[\s,，。、；;]+/).map(t => t.trim()).filter(t => t.length >= 1);
  if (!terms.length) return safe;
  const pat = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).sort((a, b) => b.length - a.length).join('|');
  try { return safe.replace(new RegExp('(' + pat + ')', 'gi'), '<mark>$1</mark>'); }
  catch (e) { return safe; }
}
const state = { dim: 'subject', path: [], files: [], selected: new Set(), counts: {}, source: {}, preview: null, kind: '', kindOptions: [], search: '', group: '' };

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
  window.__cap = d.download_cap || 30;
  const on = d.source.mode === 'live';
  const loginBtn = $('#btn-login');
  loginBtn.className = on ? 'btn' : 'btn warn';
  loginBtn.title = on ? 'QQ 已在线，可打开登录页查看状态' : 'QQ 登录态失效，打开网页扫码登录';
  const offlineNote = (!on && (d.source.errors || []).length)
    ? `<div class="mini" style="margin-top:6px;padding:6px 8px;border-radius:6px;background:var(--warn-bg);color:var(--warn)">${esc(d.source.errors[0])}<br>通常是本机 NapCat 没运行。点「启动 NapCat」可自动拉起，或右上角「QQ 登录」网页里扫码：<button class="btn small primary" id="sb-napcat">启动 NapCat</button></div>`
    : '';
  $('#stats').innerHTML = `
    <div class="row between"><span>QQ 群文件</span><span class="badge ${on ? '' : 'warn'}">${on ? '在线' : (d.source.mode === 'snapshot' ? '离线快照' : '未连接')}</span></div>
    ${offlineNote}
    <div class="muted" style="font-size:11px;margin:6px 0">${esc(Object.entries(d.source.groups || {}).map(([k,v]) => `${k} ${v.files}`).join(' · '))}</div>
    <hr>
    <div>授权可见 <b>${d.counts.total}</b> 份</div>
    <div>已下载 <b>${d.counts.downloaded}</b> · 仅元数据 <b>${d.counts.metadata_only}</b></div>
    <div>${d.counts.subjects} 个学科 · ${d.counts.kinds} 种类型 · ${d.counts.sources} 个来源</div>
    <div>${d.counts.tags} 个主题标签 · 覆盖 ${d.counts.tagged} 份</div>
    <div class="${d.integrity.ok === false ? 'bad' : 'muted'}">${d.integrity.ok === false ? '⚠ 分类完整性校验异常' : '分类完整 · 无缺项漏项 ✓'}</div>
    <div class="muted">合计约 ${(d.counts.size_bytes/1024/1024/1024).toFixed(2)} GB</div>
    <div class="muted">单批下载上限 ${d.download_cap} 个文件</div>`;
  // 群聊范围下拉：用已纳入搜索池的群（SOURCE_STATUS.groups 的键即群显示名）
  const gf = $('#group-focus');
  const groups = Object.keys(d.source.groups || {});
  const cur = state.group;
  gf.innerHTML = '<option value="">全部群聊</option>' + groups.map(g =>
    `<option value="${esc(g)}" ${g === cur ? 'selected' : ''}>${esc(g)}</option>`).join('');
  if (cur && !groups.includes(cur)) { state.group = ''; }
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
    api(`/api/tree?dim=${state.dim}&node=${node}&group=${encodeURIComponent(state.group || '')}`),
    api(`/api/files?dim=${state.dim}&node=${node}&q=${encodeURIComponent(state.search || '')}&limit=500&kind=${encodeURIComponent(state.kind || '')}&group=${encodeURIComponent(state.group || '')}`)
  ]);
  // 左栏：当前节点的同级（点选可切换分支），顶层则展示当前层级
  const parent = nodeParam(state.path.slice(0, -1));
  const sib = state.path.length ? await api(`/api/tree?dim=${state.dim}&node=${parent}`) : { children: [] };
  const treeKids = (sib.children && sib.children.length ? sib.children : t.children);
  $('#tree').innerHTML = treeKids.map(c =>
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
  $('#ai-scope').textContent = '范围：' + (state.path.length ? state.path.join(' › ') : '全部') + (state.kind ? ' › ' + state.kind : '') + (state.group ? ' › ' + state.group : '');
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
      <div class="name">${hl(x.name)}
        <div class="meta">学科 ${hl(x.subject || '综合')} · 类型 ${hl(x.kind || '其他资料')} · ${esc(x.size)}${x.downloaded ? ' · <span style="color:var(--ok)">已下载</span>' : ' · <span style="color:var(--warn)">仅元数据 · 未下载</span>'}${x.summary ? ' · ' + hl(x.summary.slice(0, 42)) : ''}</div>
        <div class="meta">来源 ${esc(x.source)} / ${esc(x.group)}${(x.tags || []).length ? ' · 标签：' + hl((x.tags || []).slice(0, 4).join(' / ')) : ''}</div>
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
  $('#dialog').innerHTML = `
    <div class="dialog-head"><h3>${esc(x.name)}</h3><span class="link dialog-close" id="pv-close">关闭 ✕</span></div>
    <div class="muted" style="line-height:1.9">
      来源：${esc(x.source)} / ${esc(x.group)}<br>
      学科 / 类型：${esc(x.subject || '综合')} · ${esc(x.kind || '其他资料')}<br>
      <span class="mini">置信度 ${esc(x.confidence ?? '—')} · 引擎 ${esc(x.engine || 'rules')}</span><br>
      主题标签：${(x.tags || []).map(esc).join(' / ') || '（无）'}<br>
      群内路径：${esc(x.path)}<br>
      体积：${esc(x.size)} · 上传：${esc(x.uploaded_at || '未知')}<br>
      状态：${x.downloaded ? '<span style="color:var(--ok)">已下载</span>' : '<span style="color:var(--warn)">仅元数据，未下载，无正文摘要</span>'}
    </div>
    <div style="margin-top:10px"><b>内容摘要</b><div class="muted" style="margin-top:4px">${esc(x.summary || '尚未下载，无正文摘要；只有文件名、路径与分类等元数据')}</div></div>
    ${x.body_excerpt ? `<div style="margin-top:10px"><b>正文片段</b><div class="muted" style="max-height:160px;overflow:auto;white-space:pre-wrap;margin-top:4px">${esc(x.body_excerpt.slice(0, 1000))}</div></div>` : ''}
    ${x.note_abs ? `<div class="muted" style="margin-top:8px;word-break:break-all">笔记：${esc(x.note_abs)}</div>` : ''}
    <div class="row gap" style="margin-top:14px">
      <button class="btn small primary" id="pv-download" ${x.downloaded ? 'disabled' : ''}>${x.downloaded ? '已下载' : '下载此文件'}</button>
      <button class="btn small" id="pv-copy">复制路径</button>
    </div>`;
  $('#modal').classList.remove('hidden');
  $('#pv-close').onclick = closeModal;
  const b = $('#pv-download');
  if (b) b.onclick = () => confirmDownload([x.id], 'selection', '', x.name);
  $('#pv-copy').onclick = () => { navigator.clipboard.writeText(x.asset_abs || x.path); toast('已复制路径'); };
}

function modal(html) { $('#dialog').innerHTML = html; $('#modal').classList.remove('hidden'); }
function closeModal() { $('#modal').classList.add('hidden'); }
$('#modal').onclick = (e) => { if (e.target.id === 'modal') closeModal(); };

async function confirmDownload(ids, scope, nodeName, singleName) {
  if (!ids.length) return toast('请先勾选文件');
  if (state.source.mode === 'snapshot') {
    return toast('当前为离线快照，只能预览元数据，不能下载。请先「刷新来源」切回在线状态。', 7000);
  }
  const chosen = ids.map(id => state.files.find(f => f.id === id)).filter(Boolean);
  const bytes = chosen.reduce((a, b) => a + (b.size_bytes || 0), 0);
  const second = scope === 'category';
  modal(`<h3>${second ? '整类下载 · 二次确认' : '确认下载'}</h3>
    <div class="muted">即将下载 <b>${ids.length}</b> 个文件，合计约 <b>${(bytes/1024/1024).toFixed(2)} MB</b>。
    下载后会自动分类入库、生成摘要与多级大纲，并写入 Obsidian 知识库。
    ${second ? '<br><span style="color:var(--warn)">整类下载影响范围较大，请原样输入节点名称确认。</span>' : ''}</div>
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
    const d = await api(`/api/ask?q=${encodeURIComponent(q)}&fast=${$('#fast').checked ? 1 : 0}&scope=${encodeURIComponent(scope)}&group=${encodeURIComponent(state.group || '')}&dim=${encodeURIComponent(state.dim || 'subject')}`);
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

async function groupsModal() {
  let d;
  try { d = await api('/api/groups'); } catch (e) { return toast('获取群列表失败：' + e.message); }
  const cfg = d.configured || [];
  const avail = (d.available || []).filter(g => !g.configured);
  const cfgHtml = cfg.length ? cfg.map(g =>
    `<div class="grow-row"><span>${esc(g.display)} <span class="muted">${esc(g.qq_group)}${g.files != null ? ' · ' + g.files + ' 份' : ''}</span></span>
     <button class="btn small warn" data-remove="${esc(g.code)}">移除</button></div>`).join('')
    : '<div class="muted">尚未配置任何群</div>';
  const availHtml = avail.length ? avail.map(g =>
    `<div class="grow-row"><span>${esc(g.name)} <span class="muted">${esc(g.group_id)}</span></span>
     <button class="btn small primary" data-add-gid="${esc(g.group_id)}" data-add-name="${esc(g.name)}">添加</button></div>`).join('')
    : (d.online ? '<div class="muted">本 QQ 加入的其它群为空</div>'
                : '<div class="muted">QQ 未在线，无法列出可添加群；请先扫码登录，或手动填入群号添加。</div>');
  modal(`<div class="dialog-head"><h3>群聊管理</h3><span class="link dialog-close" id="gm-close">关闭 ✕</span></div>
    <div class="muted">这里管理「搜索群文件」的群聊范围。新增的群会在下次「刷新来源」（需 QQ 在线）时拉取文件；移除的群会在在线刷新时从索引清理。</div>
    <h4 style="margin:14px 0 6px">已纳入搜索池（${cfg.length}）</h4>
    <div class="grow-list">${cfgHtml}</div>
    <h4 style="margin:14px 0 6px">可添加（本 QQ 加入的群）</h4>
    <div class="grow-list">${availHtml}</div>
    <h4 style="margin:14px 0 6px">手动添加群号</h4>
    <div class="row gap">
      <input id="gm-gid" placeholder="群号（纯数字）" style="flex:1">
      <input id="gm-name" placeholder="显示名（可选）" style="flex:1">
      <button class="btn primary small" id="gm-add">添加</button>
    </div>
    <div class="muted" id="gm-msg" style="margin-top:8px"></div>`);
  $('#gm-close').onclick = closeModal;
  $('#dialog').querySelectorAll('[data-remove]').forEach(b => b.onclick = async () => {
    b.disabled = true;
    try {
      const r = await api('/api/groups/remove', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({code: b.dataset.remove})});
      if (!r.ok) return toast('移除失败：' + (r.error || ''), 6000);
      toast('已移除，点「刷新来源」清理该群索引', 6000);
      await groupsModal();
    } catch (e) { toast('移除失败：' + e.message); }
  });
  $('#dialog').querySelectorAll('[data-add-gid]').forEach(b => b.onclick = async () => {
    b.disabled = true;
    try {
      const r = await api('/api/groups/add', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({code:'', display: b.dataset.addName, qq_group: b.dataset.addGid})});
      if (!r.ok) return toast('添加失败：' + (r.error || ''), 6000);
      toast('已添加，点「刷新来源」拉取该群文件', 6000);
      await groupsModal();
    } catch (e) { toast('添加失败：' + e.message); }
  });
  $('#gm-add').onclick = async () => {
    const gid = ($('#gm-gid').value || '').trim();
    if (!gid) return toast('请填写群号');
    try {
      const r = await api('/api/groups/add', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({code:'', display: ($('#gm-name').value || '').trim(), qq_group: gid})});
      if (!r.ok) return toast('添加失败：' + (r.error || ''), 6000);
      toast('已添加，点「刷新来源」拉取该群文件', 6000);
      await groupsModal();
    } catch (e) { toast('添加失败：' + e.message); }
  };
}

// ---------- Obsidian 知识库：完整链路 ----------
async function loadVault() {
  try {
    const v = await api('/api/vault/status');
    $('#vault-path').textContent = `库：${v.path}` + (v.plugin ? ' · AI 插件已装' : '');
    $('#vault-path').title = '点击复制库路径：' + v.path;
    $('#vault-path').onclick = () => { navigator.clipboard.writeText(v.path); toast('库路径已复制，可在 Obsidian 里「打开文件夹作为库」'); };
    let localHint = '';
    try {
      const ls = await api('/api/local/scan');
      window.__local = ls;
      if (ls.pending > 0) localHint = ` · <b>本地已另存 ${ls.pending} 份</b>（QQ 离线时可直接导入）`;
    } catch (_) { /* 只读盘点失败不影响主链路 */ }
    $('#vault-stat').innerHTML = `已入库 <b>${v.downloaded}</b> / ${v.total} 份 · 待导入 <b>${v.pending}</b> 份 · 笔记 <b>${v.notes}</b> 篇 · 大纲 <b>${v.outlines}</b> 页${localHint}`;
    $('#vault-note').textContent = `自动分类目录：${v.structure}。导入需显式确认，单批最多 ${window.__cap || 30} 个；QQ 接口不可用时会自动改从本机已另存的群文件导入，链路不中断。`;
  } catch (e) { $('#vault-stat').textContent = '库状态读取失败：' + e.message; }
}

function vaultImportModal() {
  const cap = window.__cap || 30;
  const pending = state.files.filter(f => !f.downloaded);
  const preview = pending.slice(0, cap);
  modal(`<div class="dialog-head"><h3>一键批量导入到 Obsidian</h3><span class="link dialog-close" id="vi-close">关闭 ✕</span></div>
    <div class="muted">将按<b>当前筛选范围</b>（${state.path.length ? esc(state.path.join(' › ')) : '全部'}）导入尚未下载的文件，
    单批最多 <b>${cap}</b> 个。导入后自动抽取正文、生成摘要，按「来源 / 群聊 / 领域 / 学科 / 类型」落盘，
    并生成一一对应的预览笔记与多级大纲。</div>
    <div class="list" style="margin-top:10px">${preview.length ? preview.slice(0, 12).map(x => `<div>· ${esc(x.name)}</div>`).join('') : '<div>当前页没有待下载文件</div>'}${preview.length > 12 ? `<div>… 其余 ${preview.length - 12} 个</div>` : ''}</div>
    <label style="display:block;margin:12px 0 0"><input type="checkbox" id="vi-confirm"> 我已确认：这会真实写入文件到本机 Obsidian 库（QQ 离线时用已另存的群文件）</label>
    <div class="actions"><button class="btn" id="vi-cancel">取消</button><button class="btn primary" id="vi-ok">确认批量导入</button></div>
    <div class="muted" id="vi-msg" style="margin-top:8px"></div>`);
  $('#vi-close').onclick = closeModal; $('#vi-cancel').onclick = closeModal;
  $('#vi-ok').onclick = async () => {
    if (!$('#vi-confirm').checked) return $('#vi-msg').textContent = '请先勾选确认。';
    const btn = $('#vi-ok'); btn.disabled = true; btn.textContent = '导入中…';
    $('#vi-msg').textContent = '正在下载、抽取正文、自动分类入库（可能需要一点时间）…';
    try {
      const r = await api('/api/vault/import', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({confirm:true, ids:[], dim:state.dim,
          node:JSON.stringify(state.path), q:state.search||'', group:state.group||'', kind:state.kind||''})});
      if (!r.ok) { $('#vi-msg').textContent = '导入未完成：' + (r.error || '未知原因'); btn.disabled=false; btn.textContent='确认批量导入'; return; }
      closeModal();
      toast(`批量导入完成：成功 ${r.succeeded}/${r.attempted} 个，已自动分类入库并生成笔记与大纲${r.note ? ' · '+r.note : ''}`, 8000);
      state.selected.clear(); await loadState(); await reload(); await loadVault();
    } catch (e) { $('#vi-msg').textContent = '导入失败：' + e.message; btn.disabled=false; btn.textContent='确认批量导入'; }
  };
}

function vaultSearchModal() {
  modal(`<div class="dialog-head"><h3>库内 AI 检索</h3><span class="link dialog-close" id="vq-close">关闭 ✕</span></div>
    <div class="muted">只检索<b>已导入 Obsidian 库</b>（含正文与笔记）的资料，结果可直接点开预览笔记。</div>
    <div class="row gap" style="margin-top:10px"><input id="vq-q" class="ask" placeholder="如：四六级真题 / 高等数学 / 复变函数" style="flex:1"><button class="btn primary small" id="vq-go">检索</button></div>
    <div class="list" id="vq-list" style="margin-top:10px;max-height:300px">输入关键词开始检索…</div>`);
  $('#vq-close').onclick = closeModal;
  const go = async () => {
    const q = ($('#vq-q').value || '').trim();
    if (!q) return toast('请输入检索词');
    $('#vq-list').textContent = '检索中…';
    try {
      const r = await api(`/api/vault/search?q=${encodeURIComponent(q)}&limit=20`);
      $('#vq-list').innerHTML = r.found ? r.items.map(x =>
        `<div class="srcitem" data-id="${esc(x.id)}" style="display:block;padding:5px 0;border-bottom:1px solid var(--line)">
           <b>${esc(x.name)}</b><div class="muted">${esc(x.chain)} · ${esc(x.subject)} / ${esc(x.kind)}</div>
           ${x.excerpt ? `<div class="muted">${esc(x.excerpt.slice(0,120))}…</div>` : ''}</div>`).join('')
        : `<div class="muted" style="padding:8px">${esc(r.answer || '库内没有命中')}</div>`;
      $('#vq-list').querySelectorAll('.srcitem').forEach(n => n.onclick = () => showPreview(n.dataset.id));
    } catch (e) { $('#vq-list').textContent = '检索失败：' + e.message; }
  };
  $('#vq-go').onclick = go;
  $('#vq-q').onkeydown = (e) => { if (e.key === 'Enter') go(); };
}

$('#btn-vault-import').onclick = vaultImportModal;
$('#btn-vault-search').onclick = vaultSearchModal;
$('#btn-vault-open').onclick = async () => {
  try { const r = await api('/api/vault/open', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    toast(r.opened ? '已打开库文件夹：' + r.path : '库路径：' + r.path + '（可复制后在 Obsidian 里打开）', 7000);
  } catch (e) { toast('打开失败：' + e.message); }
};
$('#btn-vault-init').onclick = async () => {
  toast('正在初始化新库并重建多级大纲…', 4000);
  try { await api('/api/vault/init', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    toast('完成：独立 Obsidian 库 + 预览笔记 + 多级大纲已就绪'); await loadVault();
  } catch (e) { toast('初始化失败：' + e.message); }
};

$('#btn-login').onclick = () => window.open('/login', '_blank');
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
$('#btn-groups').onclick = groupsModal;
$('#group-focus').onchange = () => { state.group = $('#group-focus').value; state.path = []; state.selected.clear(); state.kind = ''; state.kindOptions = []; reload(); };
$('#btn-ask-search').onclick = () => {
  const q = ($('#search').value || '').trim();
  if (!q) return toast('先在搜索框输入查询，再点「问 AI」');
  $('#ask').value = q; ask(q);
};
$('#chips').innerHTML = ['高等数学有哪些期末真题？', '复变函数积分变换怎么复习？', '线性代数课件资源在哪？', '宿舍水电费在哪交？']
  .map(q => `<span class="chip">${esc(q)}</span>`).join('');
$('#chips').querySelectorAll('.chip').forEach(el => el.onclick = () => ask(el.textContent));

async function checkSetup() {
  try {
    const d = await api('/api/setup');
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
  try { await loadState(); await reload(); await loadVault(); await checkSetup(); addMsg('ai', '已连接本地资源库。可以直接用口语提问（如「给我找一套四六级真题」），回答下方会给出可点击的源文件索引；查不到会如实说明。');
  } catch (e) { toast('初始化失败：' + e.message, 9000); }
})();
