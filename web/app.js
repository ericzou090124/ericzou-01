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
    `<option value="${esc(g)}" ${g === cur ? 'selected' : ''}>${esc(g)}</option>`).join('')
    + '<option value="__manage__">＋ 读取 / 添加群聊…</option>';
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
      await loadState(); await reload(); await loadVault();
      if (state.preview && ids.includes(state.preview.id)) showPreview(state.preview.id);
      if (r.imported) vaultResultModal(r);
    } catch (e) { btn.disabled = false; btn.textContent = '确认下载'; toast('下载失败：' + e.message, 7000); }
  };
  if (second) $('#cf').focus();
}

function addMsg(role, text, sources) {
  const el = document.createElement('div');
  el.className = 'msg' + (role === 'me' ? ' me' : '');
  el.innerHTML = esc(text) + (sources && sources.length ? `<div class="srcs"><b>源文件索引 · ${sources.length} 条</b>` +
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
    const matchedTxt = d.total_matched ? ` · 共命中 ${d.total_matched} 份` : '';
    el.remove(); addMsg('ai', d.answer + `\n\n[${d.mode} · ${d.took_ms} ms${d.found ? '' : ' · 未命中'}${matchedTxt}${scopeTxt} ]`, d.sources);
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

// v3.5.0 群聊框选：读取本 QQ 全部群（离线则读本机目录里的真实群号），多选保存
async function groupsModal() {
  let d;
  try { d = await api('/api/groups'); } catch (e) { return toast('获取群列表失败：' + e.message); }
  const all = d.available || [];
  const status = d.online
    ? `已读取本 QQ 加入的 <b>${d.total_groups || all.length}</b> 个群，勾选要纳入搜索的群聊。新人三步：① 点「读取我的 QQ 群」→ ② 勾群 / 搜索 / 全选 → ③「保存选择」后会自动拉取这些群的群文件。`
    : `QQ 未在线，当前只能列出本机缓存的 <b>${all.length}</b> 个群。<b>新人请先点右上角「去登录 / 换号」完成扫码</b>，回来再点「读取我的 QQ 群」即可拿到你加入的全部群；也可以先在下方手动填群号加入。`;
  const rows = all.length ? all.map(g =>
    `<label class="grow-row gm-row" data-k="${esc((g.name + ' ' + g.group_id).toLowerCase())}" style="cursor:pointer;align-items:center;gap:8px">
       <input type="checkbox" class="gm-chk" data-gid="${esc(g.group_id)}" data-name="${esc(g.name)}" ${g.checked ? 'checked' : ''}>
       <span style="flex:1">${esc(g.name)} <span class="muted">${esc(g.group_id)}${g.files ? ' · ' + g.files + ' 份文件' : ''}${g.member_count ? ' · ' + g.member_count + ' 人' : ''}</span></span>
       <span class="badge ${g.checked ? '' : 'warn'}" style="font-size:10px">${g.checked ? '已纳入' : (g.from === 'qq' ? '本 QQ 的群' : '缓存')}</span>
     </label>`).join('') : '<div class="muted" style="padding:8px">暂无可显示的群，请先扫码登录或手动添加群号。</div>';
  modal(`<div class="dialog-head"><h3>群聊 · 读取并框选</h3><span class="link dialog-close" id="gm-close">关闭 ✕</span></div>
    <div class="muted" id="gm-status">${status}${d.error ? '<br><span style="color:var(--warn)">' + esc(d.error) + '</span>' : ''}</div>
    <div class="row gap" style="margin:10px 0 6px">
      <input id="gm-search" placeholder="搜索群名 / 群号" style="flex:1">
      <button class="btn small" id="gm-reload">读取我的 QQ 群</button>
      <button class="btn small" id="gm-login">去登录 / 换号</button>
      <button class="btn small" id="gm-all">全选</button>
      <button class="btn small" id="gm-none">全不选</button>
    </div>
    <div class="grow-list" id="gm-list" style="max-height:320px;overflow:auto;border:1px solid var(--line);border-radius:8px">${rows}</div>
    <h4 style="margin:12px 0 6px">手动添加群号</h4>
    <div class="row gap">
      <input id="gm-gid" placeholder="群号（纯数字）" style="flex:1">
      <input id="gm-name" placeholder="显示名（可选）" style="flex:1">
      <button class="btn primary small" id="gm-add">加入列表</button>
    </div>
    <div class="actions"><button class="btn" id="gm-cancel">取消</button><button class="btn primary" id="gm-save">保存选择</button></div>
    <div class="muted" id="gm-msg" style="margin-top:8px"></div>`);
  const count = () => $('#dialog').querySelectorAll('.gm-chk:checked').length;
  const sync = () => { $('#gm-save').textContent = `保存选择（${count()} 个群）`; };
  sync();
  $('#gm-close').onclick = closeModal; $('#gm-cancel').onclick = closeModal;
  $('#dialog').querySelectorAll('.gm-chk').forEach(c => c.onchange = sync);
  $('#gm-all').onclick = () => { $('#dialog').querySelectorAll('.gm-chk').forEach(c => { c.checked = true; }); sync(); };
  $('#gm-none').onclick = () => { $('#dialog').querySelectorAll('.gm-chk').forEach(c => { c.checked = false; }); sync(); };
  $('#gm-search').oninput = (e) => {
    const k = (e.target.value || '').trim().toLowerCase();
    $('#dialog').querySelectorAll('.gm-row').forEach(r => { r.style.display = !k || r.dataset.k.includes(k) ? '' : 'none'; });
  };
  $('#gm-login').onclick = () => { location.href = '/login'; };
  $('#gm-reload').onclick = async () => {
    $('#gm-status').textContent = '正在读取本 QQ 的群列表…';
    try {
      const r = await api('/api/qq/groups');
      if (!r.groups || !r.groups.length) {
        $('#gm-status').innerHTML = '未读到在线群列表：' + esc(r.error || '请先在「QQ 登录」里扫码，或启动 NapCat');
        return;
      }
      // 把在线群合并进当前列表（保留已勾选项）
      const box = $('#gm-list');
      const seen = new Set([...box.querySelectorAll('.gm-chk')].map(c => c.dataset.gid));
      r.groups.forEach(g => {
        if (seen.has(g.group_id)) return;
        seen.add(g.group_id);
        const el = document.createElement('label');
        el.className = 'grow-row gm-row';
        el.dataset.k = (g.name + ' ' + g.group_id).toLowerCase();
        el.style.cssText = 'cursor:pointer;align-items:center;gap:8px';
        el.innerHTML = `<input type="checkbox" class="gm-chk" data-gid="${esc(g.group_id)}" data-name="${esc(g.name)}">
          <span style="flex:1">${esc(g.name)} <span class="muted">${esc(g.group_id)}</span></span>
          <span class="badge" style="font-size:10px">新读到</span>`;
        box.appendChild(el);
        el.querySelector('.gm-chk').onchange = sync;
      });
      $('#gm-status').innerHTML = `已读取本 QQ 加入的 <b>${r.groups.length}</b> 个群，可继续框选。`;
      sync();
    } catch (e) { $('#gm-status').textContent = '读取失败：' + e.message; }
  };
  $('#gm-add').onclick = () => {
    const gid = ($('#gm-gid').value || '').trim();
    const name = ($('#gm-name').value || '').trim() || ('群' + gid);
    if (!/^\d+$/.test(gid)) return toast('群号必须是纯数字');
    const box = $('#gm-list');
    const exists = [...box.querySelectorAll('.gm-chk')].find(c => c.dataset.gid === gid);
    if (exists) { exists.checked = true; toast('该群已在列表中，已为你勾选'); sync(); return; }
    const el = document.createElement('label');
    el.className = 'grow-row gm-row'; el.dataset.k = (name + ' ' + gid).toLowerCase();
    el.style.cssText = 'cursor:pointer;align-items:center;gap:8px';
    el.innerHTML = `<input type="checkbox" class="gm-chk" checked data-gid="${esc(gid)}" data-name="${esc(name)}">
      <span style="flex:1">${esc(name)} <span class="muted">${esc(gid)}</span></span>
      <span class="badge" style="font-size:10px">手动添加</span>`;
    box.appendChild(el); el.querySelector('.gm-chk').onchange = sync;
    $('#gm-gid').value = ''; $('#gm-name').value = ''; sync();
  };
  $('#gm-save').onclick = async () => {
    const picked = [...$('#dialog').querySelectorAll('.gm-chk:checked')]
      .map(c => ({ qq_group: c.dataset.gid, display: c.dataset.name }));
    const btn = $('#gm-save'); btn.disabled = true; btn.textContent = '保存中…';
    try {
      const r = await api('/api/groups/set', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({groups: picked, refresh: true})});
      closeModal();
      toast(`已保存 ${r.saved} 个群` + (r.refreshed ? `，已拉取这些群的群文件（${(r.refresh && r.refresh.items) || 0} 条）` : '，QQ 在线后点「刷新来源」即可读取群文件'), 7000);
      state.group = ''; state.path = []; state.selected.clear();
      await loadState(); await reload();
    } catch (e) { btn.disabled = false; btn.textContent = '保存选择'; $('#gm-msg').textContent = '保存失败：' + e.message; }
  };
}

// ---------- Obsidian 知识库：完整链路 ----------
async function loadVault() {
  try {
    const v = await api('/api/vault/status');
    $('#vault-path').textContent = `库：${v.path}` + (v.plugin ? ' · AI 插件已装' : '') + (v.obsidian_auto_open ? ' · 导入后自动打开' : '');
    $('#vault-path').title = '点击复制库路径：' + v.path;
    $('#vault-path').onclick = () => { navigator.clipboard.writeText(v.path); toast('库路径已复制，可在 Obsidian 里「打开文件夹作为库」'); };
    let localHint = '';
    try {
      const ls = await api('/api/local/scan');
      window.__local = ls;
      if (ls.pending > 0) localHint = ` · <b>本地已另存 ${ls.pending} 份</b>（QQ 离线时可直接导入）`;
    } catch (_) { /* 只读盘点失败不影响主链路 */ }
    const reportHint = v.report_exists ? ` · <b>导入报告已生成</b>（🆕 ${v.recent} 份）` : '';
    $('#vault-stat').innerHTML = `已入库 <b>${v.downloaded}</b> / ${v.total} 份 · 待导入 <b>${v.pending}</b> 份 · 笔记 <b>${v.notes}</b> 篇 · 大纲 <b>${v.outlines}</b> 页${reportHint}${localHint}`;
    $('#vault-note').textContent = `导入完成会自动打开 Obsidian 的「本次导入报告」：新文件在原有分类里带 🆕 标记，正文全文写入笔记，库内 AI 可读取全部已导入内容。导入需显式确认，单批最多 ${window.__cap || 30} 个；QQ 接口不可用时自动改从本机已另存的群文件导入。`;
  } catch (e) { $('#vault-stat').textContent = '库状态读取失败：' + e.message; }
}

async function vaultImportModal() {
  const cap = window.__cap || 30;
  const pending = state.files.filter(f => !f.downloaded);
  const preview = pending.slice(0, cap);
  let targets = null;
  try { targets = await api('/api/vault/targets'); } catch (_) { /* 目标库只读失败不阻断导入 */ }
  let localInfo = null;
  try { localInfo = await api('/api/local/scan'); } catch (_) { /* 离线清单读取失败不阻断导入 */ }
  window.__vaultTargets = targets;
  const opts = (targets?.vaults || []).map(v =>
    `<option value="${esc(v.path)}" ${v.current ? 'selected' : ''}>${esc(v.name)}${v.current ? '（当前库）' : ''} · ${esc(v.path)}</option>`).join('');
  modal(`<div class="dialog-head"><h3>一键批量导入到 Obsidian</h3><span class="link dialog-close" id="vi-close">关闭 ✕</span></div>
    <div class="muted">将按<b>当前筛选范围</b>（${state.path.length ? esc(state.path.join(' › ')) : '全部'}）导入尚未下载的文件，
    单批最多 <b>${cap}</b> 个。导入后自动抽取正文、按原有分类落盘，生成预览笔记、多级大纲与「本次导入报告」。</div>
    ${localInfo && localInfo.pending ? `<div class="muted" style="margin-top:8px">🔌 QQ 未在线：本机已另存 <b>${localInfo.pending}</b> 份可导入的真实群文件，
    当前筛选范围里没有对应文件时会自动从这批文件取满一批，不会再出现「报错且一份都没导入」。</div>` : ''}
    <div class="list" style="margin-top:10px">${preview.length ? preview.slice(0, 8).map(x => `<div>· ${esc(x.name)}</div>`).join('') : '<div>当前页没有待下载文件</div>'}${preview.length > 8 ? `<div>… 其余 ${preview.length - 8} 个</div>` : ''}</div>
    <label style="display:block;margin:12px 0 4px">导入到哪个 Obsidian 库</label>
    <select id="vi-target" class="mini" style="width:100%">${opts || '<option value="">当前库</option>'}</select>
    <input id="vi-newvault" placeholder="或新建一个库（填名称，自动建在桌面）" style="width:100%;margin-top:6px">
    <label style="display:block;margin:12px 0 0"><input type="checkbox" id="vi-open" checked> 导入后自动在 Obsidian 打开「本次导入报告」</label>
    <label style="display:block;margin:6px 0 0"><input type="checkbox" id="vi-confirm"> 我已确认：这会真实写入文件到本机 Obsidian 库（QQ 离线时用已另存的群文件）</label>
    <div class="actions"><button class="btn" id="vi-cancel">取消</button><button class="btn primary" id="vi-ok">确认批量导入</button></div>
    <div class="muted" id="vi-msg" style="margin-top:8px"></div>`);
  $('#vi-close').onclick = closeModal; $('#vi-cancel').onclick = closeModal;
  $('#vi-ok').onclick = async () => {
    if (!$('#vi-confirm').checked) return $('#vi-msg').textContent = '请先勾选确认。';
    const btn = $('#vi-ok'); btn.disabled = true; btn.textContent = '导入中…';
    const msg = (t) => { $('#vi-msg').textContent = t; };
    try {
      const newName = ($('#vi-newvault').value || '').trim();
      const sel = ($('#vi-target').value || '');
      const cur = targets?.current || '';
      let target = null;
      if (newName) target = { kind: 'new', name: newName };
      else if (sel && cur && sel !== cur) target = { kind: 'existing', path: sel };
      if (target) {
        msg('正在准备目标 Obsidian 库（部署 AI 插件、保留原有配置）…');
        const tr = await api('/api/vault/target', {method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({target, open:false})});
        if (!tr.ok) throw new Error(tr.error || '目标库切换失败');
      }
      msg('正在导入、抽取正文、自动分类入库（可能需要一点时间）…');
      const r = await api('/api/vault/import', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({confirm:true, ids:[], dim:state.dim,
          node:JSON.stringify(state.path), q:state.search||'', group:state.group||'', kind:state.kind||'',
          open_after: $('#vi-open').checked})});
      if (!r.ok) throw new Error(r.error || '未知原因');
      state.selected.clear(); await loadState(); await reload(); await loadVault();
      vaultResultModal(r);
    } catch (e) {
      msg('导入失败：' + e.message); btn.disabled = false; btn.textContent = '确认批量导入';
    }
  };
}

function vaultResultModal(r) {
  const v = r.vault || {};
  const bd = Object.entries(r.breakdown || {}).sort((a,b) => b[1]-a[1]);
  const open = r.open || {};
  const openTxt = open.method === 'obsidian_uri' ? '✅ 已自动在 Obsidian 打开「本次导入报告」'
    : open.method === 'folder' ? '⚠ 已打开库文件夹（Obsidian 未安装或协议未注册，请手动「打开文件夹作为库」）'
    : (open.method === 'skipped' ? '按你的选择，未自动打开 Obsidian' : '自动打开未成功，可用下方按钮手动打开');
  modal(`<div class="dialog-head"><h3>导入完成 · 现在就能看到成效</h3><span class="link dialog-close" id="vr-close">关闭 ✕</span></div>
    <div style="line-height:1.9">
      <div>本次成功导入 <b>${r.imported ?? r.succeeded ?? 0}</b> / ${r.attempted ?? 0} 份 · 通道：${esc(r.source || 'QQ 群文件')}</div>
      <div>导入到库：<b>${esc(v.name || v.path || '')}</b>${v.obsidian_registered === false ? '（⚠ 未登记到 Obsidian，点下方按钮会自动登记）' : '（已在 Obsidian 登记）'}</div>
      <div>本库已入库 <b>${v.downloaded ?? 0}</b> / ${v.total ?? 0} 份 · 笔记 <b>${v.notes ?? 0}</b> 篇 · 大纲 <b>${v.outlines ?? 0}</b> 页</div>
      ${r.offline_widened ? '<div>ℹ️ 当前筛选范围内没有本机另存的副本，已自动从本机可导入清单取满这一批。</div>' : ''}
      <div>${openTxt}</div>
    </div>
    <h4 style="margin:14px 0 6px">新文件已落在原有分类里</h4>
    <div class="grow-list">${bd.length ? bd.map(([k,n]) =>
      `<div class="grow-row"><span>${esc(k)}</span><span class="badge">+${n} 份 🆕</span></div>`).join('')
      : '<div class="muted" style="padding:6px">本次没有新增文件</div>'}</div>
    <div class="muted" style="margin-top:10px">报告：<b>${esc(r.report || '00-本次导入.md')}</b>（在 Obsidian 里打开即是第一页）。
      正文全文已写入每篇笔记，库内 AI 可读取全部已导入内容；未下载条目仍只有元数据。</div>
    <div class="actions">
      <button class="btn" id="vr-folder">打开库文件夹</button>
      <button class="btn primary" id="vr-open">在 Obsidian 打开报告</button>
      <button class="btn" id="vr-close2">关闭</button>
    </div>`);
  const close = () => { closeModal(); };
  $('#vr-close').onclick = close; $('#vr-close2').onclick = close;
  $('#vr-open').onclick = async () => {
    try { const d = await api('/api/vault/open-obsidian', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({file: r.report || ''})}); toast(d.opened ? '已在 Obsidian 打开' : ('请手动打开：' + d.path), 7000); }
    catch (e) { toast('打开失败：' + e.message); }
  };
  $('#vr-folder').onclick = () => $('#btn-vault-open').click();
}

async function vaultTargetModal() {
  let t;
  try { t = await api('/api/vault/targets'); } catch (e) { return toast('读取本机 Obsidian 库失败：' + e.message); }
  const vs = t.vaults || [];
  modal(`<div class="dialog-head"><h3>挑选 / 新建 Obsidian 库</h3><span class="link dialog-close" id="vt-close">关闭 ✕</span></div>
    <div class="muted">可选择本机已有库（会保留它原有的 Obsidian 设置，只追加 AI 插件与自动分类内容），或新建一个独立库。已导入的资料会自动迁移过去。</div>
    <h4 style="margin:14px 0 6px">本机已有库（${vs.length}）</h4>
    <div class="grow-list" style="max-height:220px;overflow:auto">
      ${vs.length ? vs.map(v => `<label class="grow-row" style="cursor:pointer;align-items:center;gap:8px">
        <input type="radio" name="vt" value="${esc(v.path)}" ${v.current ? 'checked' : ''}>
        <span style="flex:1">${esc(v.name)} ${v.current ? '<span class="badge">当前</span>' : ''}<br><span class="muted">${esc(v.path)}${v.plugin ? ' · 已装 AI 插件' : ''}</span></span></label>`).join('')
        : '<div class="muted" style="padding:8px">没有发现已有的 Obsidian 库，可以直接新建。</div>'}
    </div>
    <h4 style="margin:12px 0 6px">或新建一个库</h4>
    <input id="vt-new" placeholder="新库名称（如：我的课程资料库）" style="width:100%">
    <div class="actions"><button class="btn" id="vt-cancel">取消</button><button class="btn primary" id="vt-ok">使用这个库</button></div>
    <div class="muted" id="vt-msg" style="margin-top:8px"></div>`);
  $('#vt-close').onclick = closeModal; $('#vt-cancel').onclick = closeModal;
  $('#vt-ok').onclick = async () => {
    const name = ($('#vt-new').value || '').trim();
    const radio = $('#dialog').querySelector('input[name=vt]:checked');
    let target = name ? {kind:'new', name} : (radio ? {kind:'existing', path: radio.value} : {kind:'current'});
    const btn = $('#vt-ok'); btn.disabled = true; btn.textContent = '准备中…';
    try {
      const r = await api('/api/vault/target', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({target})});
      if (!r.ok) throw new Error(r.error || '切换失败');
      closeModal();
      toast(`已切换到「${r.name}」：AI 插件已部署、大纲已重建${r.migrated ? `、迁移 ${r.migrated} 份已导入资料` : ''}`, 8000);
      await loadVault(); await loadState(); await reload();
    } catch (e) { btn.disabled = false; btn.textContent = '使用这个库'; $('#vt-msg').textContent = '失败：' + e.message; }
  };
}

function vaultSearchModal() {
  modal(`<div class="dialog-head"><h3>库内 AI 检索 · 可读取全文</h3><span class="link dialog-close" id="vq-close">关闭 ✕</span></div>
    <div class="muted">默认检索<b>全部资料</b>：已导入的可读取完整正文，未下载的明确标注「仅元数据」；也可切换为只搜本库已导入笔记。</div>
    <div class="row gap" style="margin-top:10px">
      <select id="vq-scope" class="mini"><option value="all">全部资料（含元数据）</option><option value="vault">仅本库已导入</option></select>
      <input id="vq-q" class="ask" placeholder="如：四六级真题 / 罗尔中值定理 / 马原" style="flex:1">
      <button class="btn primary small" id="vq-go">检索</button>
    </div>
    <div class="muted" id="vq-sum" style="margin-top:6px"></div>
    <div class="list" id="vq-list" style="margin-top:6px;max-height:320px;overflow:auto">输入关键词开始检索…</div>
    <div id="vq-body" style="display:none;margin-top:10px;max-height:220px;overflow:auto;white-space:pre-wrap;font-size:12px;padding:10px;border:1px solid var(--line);border-radius:8px"></div>`);
  $('#vq-close').onclick = closeModal;
  const go = async () => {
    const q = ($('#vq-q').value || '').trim();
    if (!q) return toast('请输入检索词');
    const scope = $('#vq-scope').value;
    $('#vq-list').textContent = '检索中…';
    $('#vq-body').style.display = 'none';
    try {
      const r = await api(`/api/vault/search?q=${encodeURIComponent(q)}&scope=${scope}&limit=20`);
      $('#vq-sum').textContent = r.answer || '';
      $('#vq-list').innerHTML = r.found ? r.items.map(x =>
        `<div class="srcitem vq-item" data-id="${esc(x.id)}" style="display:block;padding:6px 0;border-bottom:1px solid var(--line)">
           <b>${esc(x.name)}</b> <span class="badge ${x.has_body ? '' : 'warn'}" style="font-size:10px">${x.has_body ? '含正文 ' + x.body_chars + ' 字' : '仅元数据'}</span>
           <div class="muted">${esc(x.chain)} · ${esc(x.subject)} / ${esc(x.kind)}</div>
           ${x.excerpt ? `<div class="muted">${esc(x.excerpt.slice(0,140))}…</div>` : ''}
           <div class="row gap" style="margin-top:4px">
             ${x.wikilink ? `<button class="btn small vq-note">打开预览笔记</button>` : ''}
             ${x.has_body ? `<button class="btn small primary vq-full">读取全文</button>` : ''}
           </div></div>`).join('')
        : `<div class="muted" style="padding:8px">${esc(r.answer || '没有命中')}</div>`;
      $('#vq-list').querySelectorAll('.vq-note').forEach(b => b.onclick = (e) => {
        e.stopPropagation(); showPreview(b.closest('.vq-item').dataset.id);
      });
      $('#vq-list').querySelectorAll('.vq-full').forEach(b => b.onclick = async (e) => {
        e.stopPropagation();
        const id = b.closest('.vq-item').dataset.id;
        $('#vq-body').style.display = 'block'; $('#vq-body').textContent = '正在读取全文…';
        try {
          const c = await api('/api/vault/content?id=' + encodeURIComponent(id));
          $('#vq-body').textContent = (c.name ? `【${c.name}】\n` : '') + (c.body || c.note_text || '（无正文）');
        } catch (err) { $('#vq-body').textContent = '读取失败：' + err.message; }
      });
      $('#vq-list').querySelectorAll('.vq-item').forEach(n => n.onclick = () => showPreview(n.dataset.id));
    } catch (e) { $('#vq-list').textContent = '检索失败：' + e.message; }
  };
  $('#vq-go').onclick = go;
  $('#vq-scope').onchange = go;
  $('#vq-q').onkeydown = (e) => { if (e.key === 'Enter') go(); };
}

$('#btn-vault-import').onclick = vaultImportModal;
$('#btn-vault-search').onclick = vaultSearchModal;
$('#btn-vault-target').onclick = vaultTargetModal;
const openInObsidian = async (file) => {
  try {
    const r = await api('/api/vault/open-obsidian', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({file: file || ''})});
    toast(r.opened ? (r.method === 'obsidian_uri' ? '已在 Obsidian 打开本库' : (r.note || '已打开库文件夹'))
                   : ('未能自动打开，库路径：' + r.path), 8000);
  } catch (e) { toast('打开失败：' + e.message); }
};
$('#btn-vault-obsidian').onclick = () => openInObsidian('');
$('#btn-vault-obsidian2').onclick = () => openInObsidian('');
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
$('#btn-reload').onclick = () => location.reload();

// v3.6.0：一键刷新网页 + 退出当前 QQ / 换号重新扫码
async function switchQQModal() {
  let uins = [];
  try { const s = await api('/api/qqlogin/status'); uins = s.local_uins || []; } catch (_) { /* 离线也可换号 */ }
  const opts = '<option value="">全新扫码（推荐 · 用任意 QQ 扫新码）</option>'
    + uins.map(u => `<option value="${esc(u)}">快速切换到本机已有账号 ${esc(u)}</option>`).join('');
  modal(`<div class="dialog-head"><h3>退出当前 QQ · 换号扫码</h3><span class="link dialog-close" id="sq-close">关闭 ✕</span></div>
    <div class="muted" style="line-height:1.9">这会关闭本机的「自动登录旧账号」，<b>干净重启 NapCat</b>（不继承旧的 -q 参数）并生成全新二维码。<br>
    如果当前 QQ 正在电脑 QQ 客户端里登录，直接扫码会一直提示「无法重复登录」，换号即可解决。<br>
    原来的账号凭证不会被删除，之后仍可切回；只操作本机 NapCat，不动 QQ 客户端、不删任何聊天或文件。</div>
    <label style="display:block;margin:12px 0 4px">切换方式</label>
    <select id="sq-uin" class="mini" style="width:100%">${opts}</select>
    <div class="actions"><button class="btn" id="sq-cancel">取消</button>
    <button class="btn warn" id="sq-ok">退出并重新扫码</button></div>
    <div class="muted" id="sq-msg" style="margin-top:8px"></div>`);
  $('#sq-close').onclick = closeModal; $('#sq-cancel').onclick = closeModal;
  $('#sq-ok').onclick = async () => {
    const b = $('#sq-ok'); b.disabled = true; b.textContent = '正在退出…';
    $('#sq-msg').textContent = '正在关闭自动登录、重启 NapCat、申请新二维码（约 10~20 秒）…';
    try {
      const r = await api('/api/qqlogin/switch', {method:'POST',
        headers:{'Content-Type':'application/json'}, body: JSON.stringify({uin: $('#sq-uin').value || ''})});
      if (!r.ok) throw new Error(r.error || '未知原因');
      $('#sq-msg').innerHTML = (r.steps || []).map(esc).join('<br>')
        + '<br><b>即将打开扫码页，请用新 QQ 扫码。</b>';
      setTimeout(() => { location.href = '/login'; }, 1500);
    } catch (e) {
      b.disabled = false; b.textContent = '退出并重新扫码';
      $('#sq-msg').textContent = '换号失败：' + e.message + '；可点「QQ 登录」页里的按钮重试。';
    }
  };
}
$('#btn-switch-qq').onclick = switchQQModal;
$('#group-focus').onchange = () => {
  const v = $('#group-focus').value;
  if (v === '__manage__') { $('#group-focus').value = state.group || ''; groupsModal(); return; }
  state.group = v; state.path = []; state.selected.clear(); state.kind = ''; state.kindOptions = []; reload();
};
$('#btn-ask-search').onclick = () => {
  const q = ($('#search').value || '').trim();
  if (!q) return toast('先在搜索框输入查询，再点「问 AI」');
  $('#ask').value = q; ask(q);
};
$('#chips').innerHTML = ['罗尔、拉格朗日、柯西中值定理', '线代期中真题有哪些？', '马原考试回忆版', '复变函数积分变换怎么复习？']
  .map(q => `<span class="chip">${esc(q)}</span>`).join('');
$('#chips').querySelectorAll('.chip').forEach(el => el.onclick = () => ask(el.textContent));

async function checkSetup() {
  try {
    const d = await api('/api/setup');
    if (!d.done) {
      const b = $('#setup-banner');
      b.classList.remove('hidden');
      b.innerHTML = '👋 <b>第一次用？</b> 点顶栏「群聊」读取并框选你要搜索的 QQ 群，再点「刷新来源」即可开始分类整理。'
        + ' <button class="btn small primary" id="sb-go">去框选群聊</button>'
        + ' <span class="muted">没登录也能先框选本机已缓存的群。</span>';
      $('#sb-go').onclick = groupsModal;
    }
  } catch (e) { /* 配置接口不可用时静默，不影响主界面 */ }
}

(async () => {
  try { await loadState(); await reload(); await loadVault(); await checkSetup(); addMsg('ai', '已连接本地资源库。可以直接用口语提问（如「给我找一套四六级真题」），回答下方会给出可点击的源文件索引；查不到会如实说明。');
  } catch (e) { toast('初始化失败：' + e.message, 9000); }
})();
