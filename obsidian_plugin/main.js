const { Plugin, ItemView, PluginSettingTab, Setting, Notice, requestUrl } = require('obsidian');

const VIEW_TYPE = 'resource-manager-ai-view';
const DEFAULTS = {
  serverUrl: 'http://127.0.0.1:8787',
  fastMode: false, autoOpen: true, topK: 5,
  vaultOnly: false, group: ''
};

class QQAIView extends ItemView {
  constructor(leaf, plugin) { super(leaf); this.plugin = plugin; this.history = []; }
  getViewType() { return VIEW_TYPE; }
  getDisplayText() { return '资源 AI 搜索'; }
  getIcon() { return 'search'; }

  async onOpen() {
    const c = this.containerEl.children[1];
    c.empty(); c.addClass('rm-ai-root');
    c.createEl('div', { cls: 'rm-ai-head', text: '资源 AI 搜索 · Obsidian 知识库' });
    this.status = c.createDiv({ cls: 'rm-ai-status' });
    // 范围控件：群聊 + 库内检索开关
    const filters = c.createDiv({ cls: 'rm-ai-filters' });
    this.dimSel = filters.createEl('select', { cls: 'rm-ai-select' });
    [['subject', '按学科'], ['kind', '按类型'], ['source', '按来源']].forEach(([v, t]) =>
      this.dimSel.createEl('option', { value: v, text: t }));
    this.groupSel = filters.createEl('select', { cls: 'rm-ai-select' });
    this.groupSel.createEl('option', { value: '', text: '全部群聊' });
    this.groupSel.onchange = () => { this.plugin.settings.group = this.groupSel.value; this.plugin.save(); };
    const lab = filters.createEl('label', { cls: 'rm-ai-toggle' });
    this.vaultChk = lab.createEl('input', { type: 'checkbox' });
    this.vaultChk.checked = !!this.plugin.settings.vaultOnly;
    this.vaultChk.onchange = () => { this.plugin.settings.vaultOnly = this.vaultChk.checked; this.plugin.save(); };
    lab.appendText(' 仅检索已入库笔记');
    this.log = c.createDiv({ cls: 'rm-ai-log' });
    this.addMsg('ai', '口语提问即可，如「给我找一套四六级真题」。回答下方列出可点击的源文件索引；查不到会如实说明，不编造。勾选「仅检索已入库笔记」可只搜本库已导入的资料。', []);
    const bar = c.createDiv({ cls: 'rm-ai-bar' });
    this.input = bar.createEl('textarea', { cls: 'rm-ai-input', attr: { placeholder: '例如：给我找一套四六级真题', rows: '2' } });
    this.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.ask(this.input.value); }
    });
    const send = bar.createEl('button', { cls: 'rm-ai-send', text: '提问' });
    send.onclick = () => this.ask(this.input.value);
    const chips = c.createDiv({ cls: 'rm-ai-chips' });
    ['给我找一套四六级真题', '有哪些高数真题？', '复变函数怎么复习？'].forEach(q => {
      const b = chips.createEl('button', { cls: 'rm-ai-chip', text: q });
      b.onclick = () => this.ask(q);
    });
    this.check();
  }

  async check() {
    const base = this.plugin.settings.serverUrl;
    try {
      const r = await requestUrl({ url: base + '/api/vault/status', method: 'GET' });
      const v = JSON.parse(r.text);
      this.status.textContent = `本库已导入 ${v.downloaded}/${v.total} 份 · 笔记 ${v.notes} 篇 · 大纲 ${v.outlines} 页`;
      const cur = this.plugin.settings.group;
      this.groupSel.empty();
      this.groupSel.createEl('option', { value: '', text: '全部群聊' });
      try {
        const g = await requestUrl({ url: base + '/api/groups', method: 'GET' });
        const gd = JSON.parse(g.text);
        (gd.configured || []).forEach(x => this.groupSel.createEl('option', { value: x.display, text: x.display }));
      } catch (e) { /* 群列表不可用时保持「全部群聊」 */ }
      this.groupSel.value = cur || '';
    } catch (e) {
      this.status.textContent = '服务未连接（请先运行 start.bat）';
    }
  }

  addMsg(role, text, sources) {
    const wrap = this.log.createDiv({ cls: 'rm-ai-msg ' + (role === 'me' ? 'me' : 'ai') });
    wrap.createDiv({ cls: 'rm-ai-text', text: text });
    if (sources && sources.length) {
      const box = wrap.createDiv({ cls: 'rm-ai-sources' });
      box.createDiv({ cls: 'rm-ai-srchead', text: '源文件索引' });
      sources.forEach((s) => {
        const row = box.createDiv({ cls: 'rm-ai-source' });
        const tag = s.downloaded ? '已下载' : '仅元数据';
        const title = row.createDiv({ cls: 'rm-ai-srcname', text: `${s.n}. ${s.name} · ${tag}` });
        title.onclick = () => { if (s.note) this.openNote(s.note); else new Notice('该条目尚未下载，无预览笔记'); };
        row.createEl('span', { cls: 'rm-ai-srcpath', text: `${s.domain} / ${s.subject} · ${s.path}` });
        const ops = row.createDiv({ cls: 'rm-ai-ops' });
        const b1 = ops.createEl('button', { text: '打开笔记' });
        b1.onclick = () => s.note ? this.openNote(s.note) : new Notice('尚未下载，无笔记');
        const b2 = ops.createEl('button', { text: '复制路径' });
        b2.onclick = () => { navigator.clipboard.writeText(s.path); new Notice('已复制群内路径'); };
      });
    }
    this.log.scrollTop = this.log.scrollHeight;
    return wrap;
  }

  openNote(rel) {
    const p = String(rel).replace(/\.md$/, '');
    this.app.workspace.openLinkText(p, '', false).catch(() => new Notice('无法打开笔记：' + rel));
  }

  async ask(q) {
    q = (q || '').trim();
    if (!q) return;
    this.input.value = '';
    if (this.groupSel && this.plugin.settings.group) this.groupSel.value = this.plugin.settings.group;
    this.addMsg('me', q, []);
    const pending = this.addMsg('ai', '检索中…', []);
    const base = this.plugin.settings.serverUrl;
    const group = this.plugin.settings.group || this.groupSel.value || '';
    try {
      if (this.vaultChk.checked) {
        // 库内检索：只搜已导入本库（含正文与笔记）的资料
        const url = base + '/api/vault/search?q=' + encodeURIComponent(q) +
          '&group=' + encodeURIComponent(group) + '&limit=20';
        const r = await requestUrl({ url, method: 'GET' });
        const d = JSON.parse(r.text);
        pending.remove();
        const srcs = (d.items || []).map((x, i) => ({
          n: i + 1, name: x.name, note: x.note, path: x.path || x.chain,
          domain: x.domain, subject: x.subject, downloaded: true, excerpt: x.excerpt
        }));
        this.addMsg('ai', d.answer + `\n\n[库内检索 · 命中 ${d.matched || 0} 份]`, srcs);
      } else {
        const url = base + '/api/ask?q=' + encodeURIComponent(q) +
          (this.plugin.settings.fastMode ? '&fast=1' : '') +
          '&group=' + encodeURIComponent(group) + '&dim=' + encodeURIComponent(this.dimSel ? this.dimSel.value : 'subject');
        const r = await requestUrl({ url, method: 'GET' });
        const d = JSON.parse(r.text);
        pending.remove();
        const extra = d.relaxed ? ` · ${d.relaxed}` : '';
        this.addMsg('ai', d.answer + `\n\n[${d.mode} · ${d.took_ms} ms${d.found ? '' : ' · 未命中'}${extra}]`, d.sources || []);
      }
    } catch (e) {
      pending.remove();
      this.addMsg('ai', '无法连接本地服务：' + (e && e.message ? e.message : e) + '\n请先双击项目里的 start.bat。', []);
    }
  }
}

module.exports = class ResourceManagerAI extends Plugin {
  async onload() {
    this.settings = Object.assign({}, DEFAULTS, await this.loadData());
    this.registerView(VIEW_TYPE, (leaf) => new QQAIView(leaf, this));
    this.addRibbonIcon('search', '资源 AI 搜索', () => this.activate());
    this.addCommand({ id: 'open-rm-ai', name: '打开资源 AI 搜索', callback: () => this.activate() });
    this.addCommand({ id: 'ask-rm-selection', name: '用选中的文字提问资源库', callback: () => {
      const sel = this.app.workspace.activeEditor?.editor?.getSelection?.() || '';
      this.activate().then(() => {
        const view = this.app.workspace.getLeavesOfType(VIEW_TYPE)[0]?.view;
        if (view) view.ask(sel);
      });
    }});
    this.addSettingTab(new RMSettingTab(this.app, this));
    if (this.settings.autoOpen) this.app.workspace.onLayoutReady(() => this.activate());
  }
  async activate() {
    let leaf = this.app.workspace.getLeavesOfType(VIEW_TYPE)[0];
    if (!leaf) leaf = this.app.workspace.getRightLeaf(false);
    await leaf.setViewState({ type: VIEW_TYPE, active: true });
    this.app.workspace.revealLeaf(leaf);
  }
  async save() { await this.saveData(this.settings); }
  onunload() { this.app.workspace.detachLeavesOfType(VIEW_TYPE); }
};

class RMSettingTab extends PluginSettingTab {
  constructor(app, plugin) { super(app, plugin); this.plugin = plugin; }
  display() {
    const { containerEl } = this; containerEl.empty();
    new Setting(containerEl).setName('本地服务地址').setDesc('仅本机回环地址，默认 http://127.0.0.1:8787')
      .addText(t => t.setValue(this.plugin.settings.serverUrl).onChange(async v => { this.plugin.settings.serverUrl = v; await this.plugin.save(); }));
    new Setting(containerEl).setName('快速模式').setDesc('跳过模型，只用本地检索/摘录，约 0.1 秒')
      .addToggle(t => t.setValue(this.plugin.settings.fastMode).onChange(async v => { this.plugin.settings.fastMode = v; await this.plugin.save(); }));
    new Setting(containerEl).setName('默认只检索已入库笔记').setDesc('开启后库内检索只返回已导入本库、含正文的资料')
      .addToggle(t => t.setValue(this.plugin.settings.vaultOnly).onChange(async v => { this.plugin.settings.vaultOnly = v; await this.plugin.save(); }));
    new Setting(containerEl).setName('默认群聊范围').setDesc('留空表示全部群聊')
      .addText(t => t.setValue(this.plugin.settings.group).onChange(async v => { this.plugin.settings.group = v.trim(); await this.plugin.save(); }));
    new Setting(containerEl).setName('Obsidian 库状态').setDesc('查看本库路径、已导入数量与大纲页数')
      .addButton(b => b.setButtonText('查看').onClick(async () => {
        try {
          const r = await requestUrl({ url: this.plugin.settings.serverUrl + '/api/vault/status', method: 'GET' });
          const v = JSON.parse(r.text);
          new Notice(`库：${v.path}\n已导入 ${v.downloaded}/${v.total} 份 · 笔记 ${v.notes} 篇 · 大纲 ${v.outlines} 页`, 10000);
        } catch (e) { new Notice('服务未连接，请先运行 start.bat'); }
      }));
    new Setting(containerEl).setName('启动时自动打开').addToggle(t => t.setValue(this.plugin.settings.autoOpen)
      .onChange(async v => { this.plugin.settings.autoOpen = v; await this.plugin.save(); }));
    new Setting(containerEl).setName('AI 模型设置').setDesc('外部 API / 本地模型在可视化界面的「设置」中配置')
      .addButton(b => b.setButtonText('打开界面').onClick(() => window.open(this.plugin.settings.serverUrl)));
  }
}
