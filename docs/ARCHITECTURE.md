# 技术实现路线

## 1. 分层

```
表现层   Web 单页（web/）        Obsidian 插件（obsidian_plugin/）
            │  fetch /api/*              │ requestUrl /api/ask
服务层   server.py  ThreadingHTTPServer（仅 127.0.0.1:8787）
            │
领域层   catalog.py ─ classify.py ─ download.py ─ ai.py
            │              │             │            │
基础层   qq.py / wechat.py   extract.py   vault.py   index.py   llm.py
            │
数据层   state/catalog.json  state/index.db  state/bodies/  桌面/资源管理/
```

## 2. 实现顺序与决策

| 步骤 | 决策 | 理由 |
| --- | --- | --- |
| 1 | 先用 JSON 配置而非 YAML，全项目只用标准库 | GitHub 克隆后 `python server.py` 即可跑，不需 pip install |
| 2 | 前端零构建（原生 HTML/CSS/JS） | 用户双击即用，不需要 Node 工具链 |
| 3 | `catalog.json` 作为唯一事实源 | 树、大纲、AI、下载状态全部同源，避免多处状态不一致 |
| 4 | 三级分类 `domain / subject / kind`，规则数据化在 `config.json` | 满足「学习 > 高数 > 单文件预览」下钻，改规则不用改代码 |
| 5 | 匹配顺序：文件夹名权重 3 > 文件名 2 > 兜底 | 真实群文件 143 个一级目录几乎都是课程名，文件夹名最可靠 |
| 6 | 未下载条目也进 FTS5（只有 title/meta） | AI 能回答「有哪些 / 多少份」，同时在上下文里强制标注「无正文」 |
| 7 | 命中判定与源索引完全由本地检索给出 | 模型只做中文概括，无权判断「有没有」，避免幻觉 |
| 8 | `LIST_INTENT` 走目录确定性统计 | 「未下载资料有哪些」不交给模型数数，答案可复核 |
| 9 | 上下文按命中词定位窗口 `_snippet()` | 实测只截前 400 字会漏掉答案，改为命中词附近 ±width/4 窗口 |
| 10 | 提示词禁止从题目/选项推断答案 | 实测《微电子制造技术2026真题》只有选项没有答案，模型曾把选项当结论 |
| 11 | 下载统一闸门 + 单批上限 30 | 单个/多选/整类三种 UI 最终同一路径，服务端重复校验 |
| 12 | 离线快照禁止下载 | 快照里的 `file_id` 可能已失效，且代表用户授权状态不明确 |
| 13 | 密钥写 `state/secrets.json` 并 gitignore | 外部 API 可配，但绝不进仓库 |
| 14 | 生成笔记带 `NOTE_MARK` | 重建只覆盖脚本生成内容，不碰手工笔记 |
| 15 | 独立 Obsidian 新库 | 不修改原有 `ericzou的资料库`，插件只部署到新库 |

## 3. 核心链路

### 3.1 只读盘点

```
POST /api/refresh
  → qq.online() 探活
  → 在线：对每个启用群 qq.walk(group_id)
        /get_group_root_files + /get_group_files_by_folder 递归
        → 每条记录 {path,name,folder,size_bytes,ext,file_id,busid,uploader,uploaded_at}
        → 成功后写 state/qq_manifest.json 快照
  → 失败/强制：读 state/qq_manifest.json 快照，mode=snapshot
  → catalog.upsert_manifest() 三级分类 + 保留已下载状态
  → index.rebuild() 全量重建 FTS5（未下载条目 body 为空）
  → vault.build_outlines() 生成总览 + 全量大纲 + 每节点 MOC
```

### 3.2 下载入库

```
POST /api/download {ids, scope, confirm, confirmText, nodeName}
  → server 校验 mode != snapshot
  → download.precheck()：confirm / ids / 整类二次确认 / 30 个上限
  → 逐个：qq.fetch_url() → qq.download_to()（NapCat 缓存复制，失败则直连）
        → extract.extract() 正文 → state/bodies/<id>.txt
        → extract.summarize() 抽取式摘要
        → vault.write_note() 预览笔记（frontmatter + 摘要 + 正文片段 + 原文件链接）
        → catalog 条目 downloaded=true / asset / note / summary
  → catalog.save() → index.rebuild() → vault.build_outlines()
```

### 3.3 AI 问答

```
GET /api/ask?q=...
  → LIST_INTENT（有哪些/多少/未下载/清单…）
        → _filters() 从问句抽 科目/领域/类型
        → catalog 确定性统计 → 答案 + 源文件索引（mode=catalog，不调模型）
  → 一般问题
        → index.search()（FTS5 trigram MATCH，失败退 LIKE 短词召回）
        → 有效词覆盖率闸门（≥2 个有效词）
        → 不足 → 直接 NOT_FOUND，不调模型
        → 命中 → 构造【已下载·含正文】/【仅元数据·未下载·无正文】上下文
        → llm.chat()（本地 Bonsai2 关思考 / 外部 OpenAI 兼容）
        → 模型误说「没有」→ 回落本地摘录；模型报错 → 降级摘录
        → 返回 answer / found / sources[] / mode / took_ms
```

## 4. 外部依赖与可移植性

- Python 3.10+（使用了 `str | None` 类型标注），标准库：`http.server` / `sqlite3`（FTS5 trigram，SQLite ≥3.34）/ `urllib` / `zipfile` / `xml.etree` / `hashlib` / `shutil`。
- 可选 `pymupdf`：缺失时 PDF 只登记元数据，不报错。
- 配置中的 `vault` 留空时自动取 `Path.home()/Desktop/资源管理`，不在仓库里硬编码机器路径。
- `state/` 全部被 gitignore，克隆后运行 `python tools/bootstrap.py`（需自备清单）或直接 `python server.py`（需本机 NapCat）。

## 5. 安全边界

- 服务只绑定 `127.0.0.1`，不监听外网；无账号密码入库，OneBot 令牌从本机 NapCat 配置动态读取。
- 前端不下发 `file_id` / 令牌 / 本地缓存绝对路径（`catalog.public()` 白名单）。
- 未下载内容只能问答元数据，不能问答正文；只有题目没有答案的资料必须如实说明。
- 下载必须显式确认，程序从不主动扩大范围到全量 12.73 GB。
- 微信聊天数据库不读取，企业微信需另行企业管理员授权。
