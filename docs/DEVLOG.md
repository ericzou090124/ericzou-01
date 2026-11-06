# 开发日志

> 项目：`resource-manager` · 仓库 `ericzou-01` · 记录日期 2026-11-06（GMT+8）
> 本文按时间顺序记录**做了什么、为什么这样做、遇到什么问题、怎么修的**，供验收与后续维护追溯。
> 版本化摘要见 [CHANGELOG.md](CHANGELOG.md)，逐项验证数据见 [VERIFICATION.md](VERIFICATION.md)。

---

## 22:29 — 任务起点与交付顺序

用户提出新目标：新建「资源管理」统一资源库并接为 Obsidian 新库，资料统一下载、自动分类、生成多级大纲、Obsidian 内 AI 辅助搜索；接入 QQ / 微信等账号，仅在授权范围内搜索和预览群文件、提取摘要，支持逐级下钻到单文件预览，支持点击 / 多选 / 整类下载；AI 可配外部 API 或本地模型，能基于**已授权可见但尚未下载**的内容回答，查不到如实说明。微信须先评估能否复用 QQ MCP 的登录接入思路，不可行则明确限制并只做 QQ 界面。交付顺序固定为「先设计 → 再实现与试跑 → 最后整理入库 GitHub」。

**决策**：把「设计」作为独立产物先落盘（`docs/DESIGN.md`），再动手写代码，避免边写边改需求；同时先做环境探查，用事实支撑微信可行性结论，而不是凭印象下判断。

## 22:30 — 环境探查（决定实现边界）

并行核查四类能力，结果：

- QQ：NapCat OneBot 初次探测返回 **502**；用 QQ MCP 的启动工具拉起后恢复，端口 3000/3001 正常。
- 微信：本机运行 `Weixin.exe`（微信 4.x），数据目录 `Documents/xwechat_files/wxid_.../`；`db_storage/*.db` 是加密 SQLite；`msg/file/` 有 378 个按月分目录的**已落地**明文文件（225 pdf / 78 docx / 23 xlsx / 12 zip / 11 pptx / 11 m4a …），只有文件名、大小、时间。没有 OneBot/Bot 协议端，也没有个人微信开放 API。
- 连接器：本机未绑定任何连接器；候选里有「企业微信」「微盛企微管家SCRM」，但都属企业微信生态，需要企业管理员 corpid/secret 与可见范围授权，不对等个人微信群文件。
- GitHub：`git` 2.55 可用、网络可达（`git ls-remote` 成功），但没有 `gh` CLI、没有 `~/.git-credentials` / `~/.ssh` 密钥，Windows 凭据管理器里也没有 GitHub 条目。
- Python：3.13.14，`yaml` / `pymupdf` 可用，`flask` / `fastapi` / `requests` / `watchdog` 缺失。

**决策**：全部用标准库实现（`http.server` + `sqlite3` FTS5 + `urllib`），配置改用 JSON 而非 YAML，前端零构建，保证克隆后无需 `pip install` 即可运行。微信结论定为**不可复现**，本期只做限制说明与预留适配器。

## 22:33 — 设计输出（交付顺序第 1 步）

输出整体流程、7 个模块划分、数据流、界面交互、权限与降级方案，并写入 `docs/DESIGN.md`。核心决策：

1. `catalog.json` 作为唯一事实源，未下载条目也存在，`downloaded=false`。
2. 三级分类 `领域 → 科目/主题 → 资源类型 → 单文件`，规则数据化在 `config.json`。
3. AI 分「元数据池」与「正文池」，上下文强制标注数据等级；命中判定与源文件索引由本地检索给出，模型只做中文概括。
4. 三种下载 UI 最终汇入同一个确认闸门，服务端重复校验；整类下载需输入节点名二次确认；单批上限 30。
5. 离线快照禁止下载；微信聊天库一律不读。

## 22:36 — 骨架与目录

创建 `resource-manager/`（程序仓库）与 `桌面/资源管理/`（独立 Obsidian 新库）。
明确「不碰原有 `ericzou的资料库`」：新库单独生成 `.obsidian/`，插件只部署到新库。

## 22:38–22:50 — 后端实现

按依赖顺序落地：

| 顺序 | 文件 | 要点 |
| --- | --- | --- |
| 1 | `config.json` / `lib/config.py` | 路径留空时自动取 `Path.home()/Desktop/资源管理`，不硬编码机器路径；`settings.json` 存运行时配置、`secrets.json` 存 API Key，均 gitignore |
| 2 | `lib/qq.py` | OneBot 令牌从本机 NapCat 配置动态读取，不下发前端；`walk()` 递归只读；`download_to()` 优先用 NapCat 缓存复制，失败直连 URL |
| 3 | `lib/wechat.py` | 6 条限制常量 + 默认关闭的本地授权目录只读适配器，明确不扫描 `.db` |
| 4 | `lib/classify.py` | 文件夹名权重 3 > 文件名 2 > 兜底；真实群目录几乎都是课程名，所以文件夹优先 |
| 5 | `lib/catalog.py` | `public()` 白名单过滤 `file_id`；`tree()` / `query()` 支持两种维度逐级下钻 |
| 6 | `lib/extract.py` / `lib/index.py` | 零依赖 OOXML/PDF 抽取 + 抽取式摘要；FTS5 trigram，短词退 LIKE 补充召回 |
| 7 | `lib/download.py` | 确认闸门 + 上限 + 离线锁定 + 入库流水线 |
| 8 | `lib/vault.py` | 总览、全量多级大纲、每节点 MOC、每文件预览笔记；生成内容带 `NOTE_MARK` |
| 9 | `lib/llm.py` / `lib/ai.py` | 本地 Bonsai2 关思考 / 外部 OpenAI 兼容；目录统计问答、命中闸门、防臆造提示词 |
| 10 | `server.py` / `web/` / `obsidian_plugin/` | 全部 API、三栏界面、右侧栏 AI 搜索插件 |

语法检查：`python -m py_compile server.py lib/*.py tools/*.py`、`node --check web/app.js`、`node --check obsidian_plugin/main.js` 全部通过。

## 22:51 — 离线引导与首次启动

`python tools/bootstrap.py` 从上一项目缓存的 `qqfiles.json` 导入 **1625 条元数据快照** → 索引 1625 篇 → 大纲 **208 页**，全程未下载任何文件。
`python server.py` 在线启动成功：三群实时遍历 423 / 422 / 796 条（共 1641，同路径同名去重后 1625），0 错误，`/api/health` 返回 `mode=live`。

## 22:52 — 逐级下钻与下载闸门实测

- 树：L1 学习 826 / 考试与复习 424 / 其他 229 …；L2 大学物理 114 / 综合 91 / 高等数学 86 …；L3 真题试卷 11 等 → 单文件预览。
- 闸门：无 `confirm` 拒绝、空 `ids` 拒绝、整类 `confirmText` 不匹配拒绝。
- 点击下载 1 个、多选 2 个、整类 3 个，共 **6 个文件全部入库成功**；`资源/` 与 `笔记/` 各 6 个，摘要与正文片段生成正常，zip 正确降级为「仅登记元数据」。

## 22:53–23:00 — 试跑中发现并修复的 5 个问题

1. **类型别名漏匹配**：「有哪些高数真题还没下载」把 202 份高数资料全算进去，且答案开头打印了 `subject=高等数学` 内部字段名。
   修：`_filters()` 增加类型别名/关键词匹配并排除「资料 / 其他」等泛词；新增 `_where()` 输出「科目「高等数学」、类型「真题试卷」」。修复后返回 86 份 / 171.6 MB。
2. **正文只截前 400 字导致漏答**：已下载资料答案落在后半段时模型答「依据不足」。
   修：新增 `_snippet()` 按命中词定位窗口，上下文预算 2600 → 4200 字符。修复后英语选课说明、C 语言未定义行为均完整回答。
3. **模型把选择题选项当答案**：核对 `微电子制造技术2026真题.md` 原文，只有题目与 A–D 选项、没有答案，模型却推断「投影式和浸没式」。
   修：系统提示词加硬约束——只有题目/选项/目录而无明确答案时必须回答「资料只给出题目与选项，未给答案」。复测正确返回该句。**这是本次最重要的一条防臆造修正**。
4. **离线快照仍可能放行下载**：`download.run()` 只检查 `qq.online()`，强制快照但 QQ 恰在线时会用旧 `file_id`。
   修：`server.py` 的 `/api/download` 增加 `mode == "snapshot"` 前置拒绝。
5. **同名文件覆盖**：资源与笔记文件名追加 6 位条目 id，保证跨群同名不互相覆盖。

## 23:01 — 综合验证

静态资源 `/`、`/app.js`、`/style.css` 均 200；`/api/settings/test` 本地模型可达；`/api/reindex` 重建 1625 篇索引与 208 页大纲；Obsidian 新库 `.obsidian` 配置与插件文件齐全；元数据问答 27 ms、未命中 8 ms、Bonsai2 grounded 问答 2.3–5.6 s。详细数据写入 `docs/VERIFICATION.md`。

## 23:02 — 文档整理与 GitHub 首次推送

写 `README.md`、`docs/ARCHITECTURE.md`、`docs/VERIFICATION.md`、`docs/PUSH.md`、`tools/push_to_github.bat`；`git init` + 提交 `52d728a`。
用户提供仓库 `https://github.com/ericzou090124/ericzou-01.git` 并要求「以后有改动直接在仓库里帮我改」「写进仓库的东西条理要清晰，我来验收」。
推送 `main` 成功（本机 git 凭据实际可用）；补 `docs/RELEASE.md`（存档 + 逐项验收清单）后提交 `ce184cf`，打注附标签 `v1.0.0` 并推送，远端 `main` 与标签均已核实。

## 23:05 — 两个收尾事项

**新增需求**：用户要求「还要加上开发日志和相关说明文字」→ 新增本文件、`docs/CHANGELOG.md`、`docs/GUIDE.md`、`docs/README.md`，并在 README / RELEASE 中补入口。

**运行中发现的真实状态问题**：QQ 接口在试跑后掉线，`/api/health` 显示 `qq_online=false`，但界面仍缓存着启动时的「在线」标记；重新拉起 NapCat 时返回 `login_required=true`（二维码已放到桌面 `qq_login_qrcode.png`），说明本次会话的 QQ 登录态已失效。

处理与决策：
- 在 `server.py` 增加 `_sync_source()`：每次请求实时探活，一旦掉线就把 `mode` 自动收紧为 `snapshot`、锁定下载，并在界面提示；**恢复在线不自动放开**，必须用户显式点「刷新来源」，避免拿失效 `file_id` 去下载。
- 离线快照回落时补一条明确提示文案到 `errors`，让界面能说明「为什么只能预览」。
- 复测：`/api/health` → `mode=snapshot, qq_online=false`；1625 条目录、6 个已下载文件完好，下载闸门锁定。
- **待用户操作**：用手机 QQ 扫桌面二维码重新登录，再在界面点「刷新来源」即可恢复在线下载。这属于 QQ 账号登录态，程序不保存也不索要账号密码。

## 23:10 — 收尾复核与 v1.0.1

上次会话在写完文档后被频率限制中断，服务停在已停止状态、改动未提交。本次从断点继续：

- 核对 `git status`：`server.py` 与 4 个文档已改、4 个新文档未跟踪，远端 `main` 仍停在 `ce184cf`，`v1.0.1` 标签尚未创建。
- 重启 `server.py` 加载最终代码，复核掉线降级：`/api/health` → `docs=1625, mode=snapshot, qq_online=false`，`errors` 明确写「下载已锁定，点「刷新来源」可恢复在线」；`/api/state` → 1625 条 / 已下载 6 / 仅元数据 1619 / 7 领域 17 科目。
- 复核降级下的闭环：`POST /api/download` 被拒（「当前为离线快照，只能预览元数据」）；静态资源 200；逐级下钻与单文件预览正常；AI 元数据问答 27 ms 命中、未命中 22 ms 如实回答。
- 顺手修掉复核中发现的计数缺陷：`/api/files` 的 `total` 原为 limit 截断后长度，大节点会把「共 826 份」显示成「共 200 份」。改为返回真实匹配总数 + `shown` / `truncated`，界面截断时给出下钻提示。
- 全量语法检查通过后分两次提交（`2ad755b` 代码修复、`02b1227` 文档），打注附标签 `v1.0.1` 并推送 `main` 与标签；`state/`、密钥、下载资料用 `git ls-files` 自检确认未入库。

---

## 维护备忘（给后续改动）

- 所有改动完成后直接 `git add -A && git commit -m "<类型>: <说明>" && git push origin main`（用户已授权）。
- `state/`、密钥、下载资料**永远不提交**；提交前用 `git ls-files | grep -E "state/|secrets"` 自检。
- 改分类规则只动 `config.json`，改完 `POST /api/reindex` 或重启服务即可，不需要改代码。
- 本地模型必须保持 `disable_thinking=true`；关掉后单问可达 51–325 秒。
- NapCat 重启后旧 `file_id` 会失效，出现 `real fileUUID not found!` 时让用户点「刷新来源」。
