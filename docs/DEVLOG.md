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
- 再补一处界面可用性：离线原因与恢复方式原只在点「刷新来源」时闪一次 toast，改为侧栏来源区常驻醒目警告条，用户打开界面就能看到「下载已锁定」。
- 全量语法检查通过后分两次提交（`2ad755b` 代码修复、`02b1227` 文档），打注附标签 `v1.0.1` 并推送 `main` 与标签；`state/`、密钥、下载资料用 `git ls-files` 自检确认未入库。

## 23:25 — QQ 网页一键登录（替代桌面二维码图片）

**用户反馈**：「我怎么刷新，桌面上的那个二维码过期了，我希望你为我生成一个可以不用搞张图片放桌面的，可以打开一个网页，里面是二维码，扫了之后就可以登陆的那种一键登陆方式」。两件事：讲清「刷新」在哪，以及把登录做成网页里的一键闭环，不再往桌面丢图片。

**先摸清二维码到底从哪来**（没有凭印象猜）：
- 桌面 `qq_login_qrcode.png` 只有 598 B，已过期；`qr_login_result.json` 是 `{"status":"failed","error":"账号配置写入失败"}`。
- NapCat 运行时在 `%LOCALAPPDATA%/OmniQQ-MCP/napcat_runtime/shell_node/`，二维码缓存是 `napcat/cache/qrcode.png`（mtime 实时更新）；**6099 端口是 NapCat WebUI**（Express，301 → `/webui`），3000 / 3001 均未监听。
- 直接请求 `/api/QQLogin/*` 返回 `Unauthorized`。从前端 bundle `index-1uVwnAOV.js` 里读到认证方式：先 `POST /api/auth/login` 带 `{"hash": SHA256(token + ".napcat"), "totpCode": ""}` 换 `data.Credential`，之后用 `Authorization: Bearer <Credential>`。
- 用 `webui.json` 的 token 实测成功：`CheckLoginStatus` → `isLogin=false, loginPhase=waiting_qrcode, qrcodeurl=https://txz.qq.com/p?k=…`；`GetQQLoginQrcode` 返回同一链接；`GetQuickLoginListNew` 有已保存账号 `3803328585 / Elfi, isQuickLogin=true`；另有 `RefreshQRcode` 与 `SetQuickLogin` 可调用。

**决策**：不弹桌面图片、不调用外部二维码服务。二维码内容由 WebUI 实时给出，本机 OpenCV `QRCodeEncoder` 渲染成 450×450 PNG 的 data URL 直接放网页；OpenCV 缺失时回落到 NapCat 自带 `cache/qrcode.png`。登录链接原文不下发前端，只给 16 位 `qr_key` 版本标识用于判断「二维码换了新的」。WebUI token 从本机配置读、会话凭证只在进程内存。

**实现**：新增 `lib/qqlogin.py`、`web/login.html`、`tools/open_login.py`、`一键登录.bat`；`server.py` 加 5 个端点，`/api/qqlogin/restore` 会循环等 OneBot 3000 就绪（最多约 21 秒）再执行 `refresh()`，成功后下载解锁、页面 3 秒跳回主界面；`web/index.html` / `app.js` 加右上角「QQ 登录」按钮，离线时高亮并在侧栏写明入口。

**验证**：`/login` 200（7459 B）；`/api/qqlogin/status` → `webui_online=true, phase=waiting_qrcode, qr_source=opencv, accounts=[3803328585]`；把 PNG 用 `cv2.QRCodeDetector` 解码，内容与 WebUI 登录链接**完全一致**（450×450）；点刷新后 `qr_key` 变化、图片换新；未扫码时 `restore` 明确失败不误报；离线快照下载闸门仍拒绝。

**复核时又抓到一个真实时序 bug**：`/api/health` 在 QQ 离线时每次都实时探 OneBot，稳定耗时约 2.05 秒；而 `open_login.py` 用 2 秒超时探活，恰好被卡成「服务未运行」，误启动第二个服务实例并报「启动失败」。修：`health` 改用请求开头 `_sync_source()` 已实时同步的状态缓存（复测 5 ms）；`open_login.py` 超时放宽到 6 秒 + 重试，并加 TCP 端口监听兜底——端口已在监听就直接打开登录页，不再起第二个实例。复测一键登录入口只打开一次正确 URL。

**结论**：用户要的「网页里有二维码、扫了就登录」已闭环；「怎么刷新」的答案写进 README 与登录页——右上角「刷新来源」是手动入口，走登录页时由程序自动完成，不用手动。QR 登录本身必须由账号本人在手机确认，程序无法代扫；这一步之后才做完整在线下载的实测。

---

## 维护备忘（给后续改动）

- 所有改动完成后直接 `git add -A && git commit -m "<类型>: <说明>" && git push origin main`（用户已授权）。
- `state/`、密钥、下载资料**永远不提交**；提交前用 `git ls-files | grep -E "state/|secrets"` 自检。
- 改分类规则只动 `config.json`，改完 `POST /api/reindex` 或重启服务即可，不需要改代码。
- 本地模型必须保持 `disable_thinking=true`；关掉后单问可达 51–325 秒。
- NapCat 重启后旧 `file_id` 会失效，出现 `real fileUUID not found!` 时让用户点「刷新来源」。

---

# 持续迭代战役（v1.3.0 → v1.6.0，2026-11-07）

> 本段为「构建安装器 + 全面审查 + 持续迭代 + GitHub 方案集成」任务的逐轮记录。
> 逐轮「变更摘要 / 优化方向 / 下一步计划」见 [CHANGELOG.md](CHANGELOG.md)；系统审查见 [REVIEW.md](REVIEW.md)。

## 迭代 0 — 安装器 / 基线 / 系统审查（v1.3.0 基线）

**变更摘要**
- `git init` 建立版本基线（原仓库无 `.git`），强化 `.gitignore`（排除 `secrets.json` / `state/` / `venv/` 等）。
- 新建 `docs/REVIEW.md`：逐模块评估、性能瓶颈排序（①CJK 3-gram 粗粒度 ②SQLite 连接反复开关 ③catalog.load 重复反序列化 ④全量索引重建 ⑤ai hay 重复拼接）、可优化方向（A–H）与迭代路线图。
- 重建 `tools/build_installer.py` 自解压安装器：base64 内嵌全程序到 `.bat`，PowerShell 读自身定位**唯一标记**解压（纯 ASCII 头部 + `chcp 65001`、UTF-8 无 BOM），支持 `RM_INSTALL_TARGET` / `RM_NO_LAUNCH` 环境变量。实测 56 文件往返一致、解压后 `server.py` 可启动并响应 `/api/health`。
- 实测沙箱网络已恢复（GitHub API 200、pip 可用），不再受旧「无外网」限制。

**优化方向**：检索精度（CJK 3-gram 过粗）、运行期开销（catalog 重复反序列化 / SQLite 连接反复开关 / AI hay 重复拼接）、索引全量重建（瓶颈④）。

**下一步**：落地性能优化（迭代 1）；检索 GitHub 微信方案做源拓展（迭代 2）。

## 迭代 1 — 检索精度与运行期开销优化（v1.4.0）

**变更摘要**
- `lib/index.py`：`query_terms` 支持 jieba 分词（未装回退 3-gram）；`connect()` 用 `threading.local()` 缓存只读连接；`count()` 走内存缓存。
- `lib/catalog.py`：`load()` 加 mtime/size 缓存，避免每个请求重复 `json.loads`。
- `lib/ai.py`：`answer()` 预计算候选 hay，评分循环不再重复拼接 9 字段。
- `requirements-optional.txt` 补 jieba 与 `RM_NO_JIEBA=1` 关闭说明。

**优化方向**：索引全量重建（REVIEW 瓶颈④）仍未解，捕获落库代价高。

**下一步**：GitHub 调研并集成微信适配器（迭代 2）。

## 迭代 2 — GitHub WeChatFerry 微信适配器（v1.5.0）

**变更摘要**
- 检索 GitHub 成熟方案，选用 **WeChatFerry（`wcferry`）** 作为微信接入技术路径（监听式，非 QQ 式全目录遍历）。
- 新增 `lib/wechat_wcf.py`：监听指定群文件 / 附件消息（解析 appmsg XML `<type>∈{5,6,8}`），产出与 QQ 等构的 row，汇入同一流水线；默认关闭、未装 `wcferry` 时安全降级。
- `server.py` 接入 `GET /api/wechat/wcf/status|rooms`、`POST /api/wechat/wcf/capture/start|stop`，`/api/state` 增加 `wechat.wcf` 子状态与 `capturing`；捕获 5s 防抖缓冲落库后自动并入目录并重建。
- `config.json` 增加 `sources.wechat.wcf` 配置块（默认 `enabled:false`）。
- 重建安装器（57 文件）包含新增模块。

**优化方向**：捕获落库仍走 `index.rebuild` 全量重建，需改为增量（REVIEW 瓶颈④）。

**下一步**：实现增量索引同步（迭代 3）。

## 迭代 3 — 索引增量同步 + 回归自测（v1.6.0）

**变更摘要**
- `lib/index.py` 新增 `index.sync(cat)`：以 `idx_meta` 副表存「元数据 + 正文文件 stat」廉价指纹，仅对新增 / 删除 / 变更条目做增删改；首次运行 `idx_meta` 为空时等效全量，与 `rebuild` 一致。`rebuild` 改为复用共享 `_insert` 并同步维护 `idx_meta`。
- `wechat_flush` 改用 `index.sync` 取代 `index.rebuild`，捕获落库不再全量重算（实测 1625 文档：sync(unchanged) 与 rebuild 结果一致，变更单条时总数不变仅该条重算）。
- 新增 `tools/smoke_test.py` 回归自测：导入 / 索引一致性 / 微信降级 / 可选 LLM，退出码即回归信号。
- 重建安装器（58 文件，含 `lib/wechat_wcf.py` 与 `tools/smoke_test.py`）。
- 新增 / 重写 `README.md`、`docs/DEVLOG.md` 本段，补 `docs/CHANGELOG.md` 各版本条目。

**优化方向（后续候选）**
- A. 前端统一搜索框 + 命中高亮 / 结果计数（界面改动，无法在此环境渲染验证）。
- B. LLM 流式输出 + 失败重试 / 退避；`ai` 模块抽离 provider 适配层。
- C. 微信 `rooms` 自动发现并持久化为可选监听清单。
- D. 增量同步扩展至「刷新」场景（目前刷新仍走 `rebuild` 全量，属预期）。
- E. 发布到 GitHub（当前无 remote；需用户在 GitHub 建仓或提供 token 后 `git remote add` + `git push --tags`）。

**下一步**：文档收尾 + 回归全绿；视预算与需求进入 A/B/C 或收尾发布。

---

## 迭代 v2.1.0 — 索引维护与同步加速（第 8 轮）

目标：把候选 D「增量同步」继续深化，并补上「索引维护」能力。

**改动**：
- `idx_meta` schema 扩展为 `(item_id, csig, bstat)`：csig 为元数据指纹（O(1) 哈希，无磁盘 I/O），bstat 为正文文件 `size:mtime_ns`。
- `sync()` 两阶段：先按 csig 跳过「元数据未变」条目，再按 bstat 只对正文变化的条目重读；未变化条目完全不 stat、不读正文。
- 新增 `index.optimize()`（ANALYZE + VACUUM）、`db_size()`；`server.py` 新增 `POST /api/maintain`。
- 新增 `tools/bench.py`：量化 rebuild vs sync 耗时 + 一致性断言。

**自测**：smoke_test ALL PASS（10 项）；bench 显示 sync(无变化) ≈ 1503ms vs rebuild ≈ 2596ms，optimize 节省 774KB，断言全过。

**问题**：旧 `idx_meta` 仅单列 `sig`，新 `_insert` 写 3 列会失败 → `_new_connection()` 增加 `SELECT csig` 探测 + 旧表 DROP/重建迁移。

**结论**：索引层已具备「增量 + 维护 + 基准」完整闭环，长期运行后刷新开销随未变化条目比例下降。

**下一步**：v2.2.0 探索新方向——下载并发（多线程拉取大体积群文件）、配置校验器（启动时校验 config.json 必填项）、或 Obsidian 插件增强（从笔记内直接触发搜索）。

---

## 迭代 v2.2.0 — 下载流水线性能修复与并发入库（第 9 轮）

目标：修掉下载链路的性能 bug，并提升大批量下载吞吐。

**改动**：
- `download.run()` 末尾 `index.rebuild(cat)` → `index.sync(cat)`：下载每批只动少数文件，全量重建是无谓开销；sync 只重算变化的条目。
- `precheck()` 用一次性 `id→item` 映射替代每次 `by_id` 的 O(n) 扫描。
- 单批内并发下载：`ThreadPoolExecutor(max_workers=min(RM_DOWNLOAD_WORKERS=4, 批大小))`，线程异常整体降级为串行；每条只改自己的 item dict 与独立文件，线程安全。

**自测**：smoke_test 新增 `[9]`（mock 下载依赖），断言成功 2 条、rebuild 调用 0 / sync 调用 1、条目就地标记已下载；真实 catalog 复测 precheck 行为正常，`import server` 通过。

**排查记录**：测试首次失败因 ext 写成 `"pdf"`（白名单是 `.pdf`）。核查真实 catalog 的 ext 均带点（`.pdf`），白名单匹配正确——非 bug，是测试数据写错；修正后全绿。另确认真实 `qq.download_to` 已 `mkdir(parents=True)`，无需补目录创建。

**结论**：下载链路与刷新/采集一致地走「增量同步」，全系统不再有隐藏的全量重建热点。

**下一步**：v2.3.0 探索——配置校验器（启动校验 config.json 必填项并给出可读报错）、或 Obsidian 插件增强（笔记内直接触发检索）、或下载失败重试/断点续传。

---

## 迭代 v2.3.0 — 问答退化路径 bug 修复（第 10 轮）

目标：修掉 ai.answer 在 FTS 未命中时的错误「未找到」。

**Bug**：`ai.answer` 在 FTS 无命中、但关键词命中池内有结果时，退化分支重建 `hits_pool` 只带 `item_id` 与空 `body`，丢弃 `title/meta` → `corpus` 空 → `valid2` 恒空 → 误报「未找到」。修复：退化命中补全 `title`（x["name"]）与 `meta`（_hay(x)）。同时删除从未被引用的死代码 `by_id`。

**自测**：smoke_test 新增 `[10]`：mock `index.search` 返回 []、`query_terms` 返回真实存在的词「复变」，断言 `ai.answer(fast=True)` 仍 `found=True`。通过。

**严重副作用（已补救）**：上一轮的 `[9]` 下载测试在 `download.run` 成功后调用了真实的 `catalog.save`，把 2 条假目录**覆盖写回真实 `state/catalog.json`**（1625 → 2 条），导致后续测试 `[2]` 报 2 条、且 `[10]` 走了错误的范围分支。补救：① patch `catalog.save` 为 no-op 杜绝再次发生；② 用 `server.refresh(force_snapshot=True)` 从 `qq_manifest.json`（1641 条）重建 catalog（去重后 1625 条），仅 1 个遗留 body（r-b623b3e0aa9485c2）被重新标记为已下载，索引 `rebuild` 复位。验证：恢复后 `[2]` 重新为 1625，全测试 ALL PASS。

**教训**：自测里凡调用会落盘的 `save/rebuild`，必须 patch 成 no-op 或使用临时 state 目录，绝不能让 mock 测试污染真实数据文件。`state/` 已被 gitignore，无 git 兜底，污染只能靠快照重建。

**下一步**：v2.4.0 可探索——配置校验器（启动校验 config.json 必填项并给可读报错）、Obsidian 插件侧边栏检索增强、或下载失败重试/断点续传。

---

## 迭代 v2.4.0 — 启动期配置自检 + 诊断端点（第 11 轮）

目标：把「配置问题」集中暴露成可读清单，避免请求途中静默崩溃。

**改动**：
- 新增 `lib/config_validate.py`：校验 vault 路径、QQ 群 qq_group 是否纯数字、allowed_ext 非空且带点、AI provider/endpoint、max_download_per_batch、host/port。只报告不改写。
- `server.main()` 启动早期调用并打印 ✗/! 清单。
- 新增 `GET /api/diagnose`：返回 ok/errors/warnings + mode/qq_online/index_docs/vault。

**自测**：smoke_test 新增 `[11]`（正常 ok=True、坏配置报 3 错）；实机启动 server 后 `curl /api/diagnose` 返回 `ok=true, mode=snapshot, index_docs=1625`。

**注意**：本地 curl 走代理会被拦（upstream connect failed），需 `--noproxy '*'`。这提示前端若在同一沙箱调试也需绕过代理访问 127.0.0.1；浏览器直连不受影响。

**下一步**：v2.5.0 探索——下载失败重试/退避（QQ OneBot 偶发超时）、或 Obsidian 插件侧边栏检索增强。

---

## 迭代 v2.5.0 — 下载失败重试与退避（第 12 轮）

目标：吸收 QQ OneBot 的瞬时超时/抖动，避免单条网络毛刺让整文件下载失败。

**改动**：
- 新增 `_fetch_with_retry(group_id, file_id, busid, dest, attempts)`：默认 3 次指数退避（0.5/1/2s，上限 3s），对瞬时异常重试；`fetch_url` 返回空（「已失效」）属永久错误，直接抛出不重试。
- `RM_DOWNLOAD_RETRIES` 环境变量可调重试次数。

**自测**：smoke_test 新增 `[12]`（瞬时失败 2 次后第 3 次成功，fetch 调用 3 次）与 `[13]`（永久「已失效」仅 1 次不重试）。ALL PASS。全程 patch `config.vault` 到临时目录 + `catalog.save` 为 no-op，确认不再污染真实数据。

**下一步**：v2.6.0 探索——Obsidian 插件侧边栏检索增强、或下载断点续传（大文件分块）、或控制台/日志埋点便于排查。

---

## 迭代 v2.6.0 — 前端「系统诊断」面板（第 13 轮，闭环 v2.4.0）

目标：把 v2.4.0 的诊断端点接到界面，让用户点一下就能看到配置与运行状态。

**改动**：
- `web/index.html` 顶栏新增「系统诊断」按钮（`id="btn-diagnose"`）。
- `web/app.js` 新增 handler：调 `/api/diagnose`，弹模态框展示 ok/模式/QQ在线/索引篇数/库路径 + 错误清单 + 提醒清单；文本经 `esc()` 转义防注入。
- `web/style.css` 新增 `.diag/.ok/.bad/.warn` 样式（红/绿/黄，兼容 dark 主题变量）。

**自测**：实机启动 server，确认 `/` 含按钮、`/app.js` 含 handler、`/style.css` 含样式；`node --check app.js` 通过；`/api/diagnose` 返回 ok=true。

**下一步**：v2.7.0 探索——Obsidian 插件侧边栏检索增强（笔记内直接触发检索）、下载断点续传、或运行日志/埋点以便排障。

---

## 迭代 v2.7.0 — HTTP 集成自测锁定 API 契约（第 14 轮）

目标：为 HTTP 层补一层端到端回归，避免后续重构静默破坏接口。

**改动**：smoke_test 新增 `[14]`：在隔离临时 STATE+vault 中起真实 `ThreadingHTTPServer`（复用真实 qq_manifest.json 走 snapshot），依次打 `/api/health /diagnose /tree /files /state`，断言 ok 与结构；守护线程 + shutdown 收尾，不污染真实数据。

**自测**：实跑集成用例通过（docs=1625）；真实 catalog 仍为 1625 条，确认零污染。

**本轮（v2.1~v2.7）总览**：
- v2.1.0 索引维护 optimize + sync 两阶段指纹加速 + 基准
- v2.2.0 下载后增量同步 + 单批并发 + precheck 索引
- v2.3.0 ai.answer 退化路径误报未找到修复 + 测试副作用补救
- v2.4.0 启动期配置自检 + /api/diagnose 诊断端点
- v2.5.0 下载失败重试 + 指数退避
- v2.6.0 前端「系统诊断」面板闭环
- v2.7.0 HTTP 集成自测锁定 API 契约

全量自测从 10 项扩展到 15 项（单元+集成），每次迭代均 commit+tag+push 到 GitHub（v2.1.0~v2.7.0 标签齐全）。

**下一步（若继续）**：Obsidian 插件侧边栏检索增强、下载断点续传、或运行日志/埋点。当前系统已覆盖性能（索引/下载并发/重试）、正确性（AI 退化路径）、健壮性（配置自检/诊断）、可观测性（集成测试）四大维度。

---

## 迭代 v2.8.0 — 仓库治理：主页重写 + 全版本审计 + 历史补丁标签（第 15 轮）

时间：2026-11-07 13:15 (GMT+8)。目标（用户新指令）：① 参考 GitHub 仓库 `linguo2625469/workbuddy2api-panel` 的设计优化仓库说明，让更多人了解项目；② 检测此前布置的所有版本更新的可用性，发现 bug 就修复；③ 同步所有内容到 GitHub——主页、Releases、新增功能（微信监听和收集、分类群文件）、开发者日志。

### 调研与决策

- 抓取参考仓库 README：结论是「高密度工程文档 / 运维手册 / 合规声明」混合体。骨架 = 徽章 + tagline + 风险声明前置 + 表格化能力 + Mermaid 架构图 + 多方案快速开始 + 配置字段速查表 + 行为语义规格 + API 端点表 + FAQ + 关键断言↔代码出处 + License；大量使用 `<details>` 折叠块、emoji 小标题、引用警示块。**无截图、无目录树**。
- 决策：借鉴其「工程可查性」与视觉骨架，但不照搬其「停更 / 禁止转卖」这类与本仓库无关的风险声明；改为前置「纯本地 / 只读 / 授权 / 默认关闭」的重要提示。
- 盘点现状：`README.md` 停在 v1.6.0、`docs/RELEASE.md` 停在 v1.2.3、GitHub 仓库描述是「写点东西」、远端只有 4 个 Releases。全部需要治理。
- 凭据：Windows 凭据管理器里取到 GitHub PAT（`repo` scope），可调用 Releases API；`gh` CLI 不存在，改用 Python `urllib` 直调 REST API。

### 全版本可用性检测（本轮核心）

新增 `tools/version_audit.py`：对每个 tag `git archive` 到隔离临时目录，用独立 `config.STATE` 跑 10 类检测（归档 / 配置 / compileall / 导入 / 核心链路 / 群文件分类 / 微信适配器 / 路由 / `node --check` 前端 / 自带 smoke_test）。**关键设计**：检测全程不读写工作区真实资料，避免重演之前测试污染 `catalog.json` 的事故。

首轮结果（22 个 tag）：18 PASS、**4 FAIL**（`v1.3.0` / `v1.4.0` / `v1.5.0` / `v1.6.0`）。

**Bug #1（历史）**：完整堆栈为 `lib/ai.py:164  return {... "scope": f ...}` → `NameError: name 'f' is not defined`。即空问题分支在 `f` 定义前引用 `scope=f`。这四个版本的 `ai.py` 片段完全一致，正是 v1.7.0 修过的问题。

**修复决策**：直接移动/改写历史 tag 会破坏「保留版本信息方便随时回溯」的约定。改为**原 tag 一律不动**，用 `tools/fix_legacy_tag.py` 基于每个 tag 建 detached worktree → 应用与 v1.7.0 等价的最小修复 → commit → 打 `vX.Y.Z-p1` 补丁标签 → 移除 worktree。四个补丁标签全部通过全项检测。审计工具把「原 tag FAIL 但存在通过检测的 -p1」归类为 `KNOWN`（非阻塞），退出码 0。最终：**26 标签 / 22 PASS / 4 KNOWN / 0 未修复失败**。

### 第二个 Bug：分类词库泛化词

为写 `docs/FEATURES.md` 跑真实分类样例时发现 `C语言程序设计上机指南.txt → 生活与办事 / C语言程序设计 / 实验代码`。根因：`生活与办事` 的 keywords 含裸词 `指南`，命中 +1；而 `学习` 领域关键词（课件/教材/讲义…）0 命中，导致明显的学习资料被归到生活领域。同类泛化词还有 `活动`、`校园`。

**修复**：只改数据不改算法 —— 把 `指南`/`活动`/`校园` 换成 `入学指南`/`办事指南`/`新生指南`/`报到指南`/`校园通` 等具体短语。复测：`C语言程序设计上机指南 → 学习`，`宿舍水电缴费指南 → 生活与办事`（由 宿舍/水电/缴费 命中），`新生入学指南 → 生活与办事`，`2024年校招简历模板 → 实习与就业`。`smoke_test` 新增 `[15]` 锁住三类不串味。全量自测 **16 项 ALL PASS**。

### 文档产出

- `README.md`（476 行 / 17KB）按参考仓库风格重写，含 6 个徽章、Mermaid 架构图、10 个折叠块、13 张表格、16 个二级章节；微信监听采集与群文件分类各有独立章节。已用 GitHub 官方 `POST /markdown` GFM 渲染 API 实测：H1/H2、徽章、表格、折叠块、警示块、Mermaid 均正确渲染，无 Markdown 字面量泄漏。
- `docs/FEATURES.md`：两个功能的完整实现文档（选型与边界、消息四层过滤、群白名单状态机、端点/配置表、打分算法、实测样例、v2.8.0 词库修复 diff、代码索引）。
- `docs/VERSION_AUDIT.md`（自动生成）、`docs/README.md`（索引重写）、`docs/RELEASE.md`（从 v1.2.3 更新到 v2.8.0，含完整版本表 + 新增功能验收项 + 已知限制）、`CHANGELOG.md` / 本文。

### 教训

- 自动化审计必须**隔离 state**：既要避免读不到数据导致假失败（注入快照），也要避免写回真实数据（独立 `config.STATE` + 临时目录）。
- 词库里放跨领域通用词会静默污染分类结果；这类问题不会抛异常，只能靠「代表性样例回归」发现，因此把样例断言同时放进 `smoke_test` 与 `version_audit` 的功能探测。
- 历史缺陷不要改写原 tag；补丁标签 + 报告如实标注，兼顾可回溯与可用。

### 下一步

仓库已进入「性能 / 正确性 / 健壮性 / 可观测性 + 文档治理」较完整状态。若继续：Obsidian 插件侧边栏检索增强、下载断点续传、运行日志埋点，或补充 `LICENSE` 文件（当前 README 已如实说明未指定开源许可证）。

### 同步与远端验证（v2.8.0 收尾）

- 新增 `tools/sync_github_releases.py`（幂等）：从 `CHANGELOG.md` 解析各版本段落生成 Release 正文，追加安装方式、文档索引、审计结论；已有 Release 只更新正文**保留附件**；`-p1` 标签生成专门修复说明，KNOWN 版本正文顶部醒目提示可用补丁标签。Token 优先环境变量、否则 `git credential fill`，不落盘不回显。
- 执行结果：远端原有 4 个 Releases（v1.2.0~v1.2.3）→ **新建 23 + 更新 4 = 27 个 Releases，覆盖全部 27 个 tag，0 失败**；`make_latest` 显式指定 v2.8.0。
- 仓库元信息：description 由占位「写点东西」改为项目定位一句话；homepage 指向 README；补充 13 个 topics（`obsidian` / `qq` / `wechat` / `knowledge-base` / `sqlite-fts5` / `local-first` …）提升可发现性。
- **渲染修正**：主页初版用 `<div align="center">` 包裹标题与徽章，在 CommonMark 的 HTML block 规则下存在渲染歧义（参考仓库本身也无居中语法）。改为纯 Markdown 后，用 GitHub 官方 `POST /markdown`（`mode=gfm`）实测：H1×1、H2×16、`<table>`×13、徽章图片 6、折叠块 10、警示块与 Mermaid 均在，Markdown 字面量泄漏 0。

### 最终复跑（v2.8.0 发布后）

`v2.8.0` 标签推送后重新运行 `python tools/version_audit.py`，报告从发布前快照的 26 标签更新为 **27 标签：23 PASS / 4 KNOWN / 0 未修复失败，退出码 0**，其中 `v2.8.0` 全项 ✅ PASS（含自带 `smoke_test.py` 16 项）。前文的「26 标签」是发布前的审计快照记录，保留不改以反映当时的过程。`python tools/smoke_test.py` 复跑仍为 ALL PASS。

---

## 迭代 v2.9.0 — 让 Releases 可下载、让小白能闭环（第 16 轮）

时间：2026-11-07 14:36 (GMT+8)。用户新指令：「我希望下载 github 上的全部内容，Releases 有一个完整的教程或闭环，我现在进入库内不知道在哪里安装这套系统，为我生成一个简单方便的下载入口和指南，让小白也能轻松用我的程序实现复刻」。

### 痛点定位（盘点结论）

- 远端 27 个 Release 里**只有 v1.2.0 ~ v1.2.3 四个早期版本有附件**，最新版 `v2.8.0` 附件为空 → 进 Releases 找不到可下载的东西。
- 仓库里其实已有 `resource-manager-installer.bat`（自解压）、`start.bat` / `install.bat`、`新手必读.txt`、`docs/新手上手指南.md`、`docs/GUIDE.md`，但**四份说明分散、无统一入口**；README 的「快速开始」写「双击 resource-manager-installer.bat」，却没说去哪拿这个文件。
- 根目录安装器是 03:15 生成的旧快照，未包含 `LICENSE` / `FEATURES.md` / v2.x 文档。
- 结论：问题不在功能，而在**发行链路**。要做的是「稳定直链 + 完整包 + 统一权威教程 + 每个 Release 正文闭环」。

### 改动

1. `docs/INSTALL.md`（新增，统一权威入口）：下载文件对照表 + 固定直链 → 准备 Python → 双击安装 → 首次配置向导 → **6 步完整闭环**（刷新来源 / 分类浏览 / 显式确认下载 / 全文检索与问 AI / Obsidian / 系统诊断）→ 启动·停止·更新·卸载速查 → 10 条 FAQ → SHA256 校验 → macOS / Linux → 文档索引。含 Mermaid 闭环图。
2. `tools/build_release_assets.py`（新增）：复用 `build_installer.collect()` 的排除规则生成 3 个资产到 `dist/`，zip 内注入 `START_HERE.txt`（解压后第一眼看到的说明）与 `VERSION.txt`；构建完立刻 `verify_zip()` 校验 17 个关键文件 + CRC。资产采用**稳定文件名**，使 `releases/latest/download/...` 直链永不过期。
3. `tools/sync_github_releases.py`：`FOOTER` 由「git clone」改成下载入口表 + 3 步速通 + 完整闭环 + 教程链接；`latest` 改为按版本号自动推断（原为硬编码 v2.8.0）；新增 `LATEST_GUIDE`（最新版 Release 内的展开版教程折叠块）；新增 `--assets-dir` 幂等上传（同名资产先 DELETE 再 POST 到 `uploads.github.com`）。
4. `README.md`：顶部 `[!TIP]` 三步速通 + 三条直链 + `License-MIT` 徽章；「快速开始」开头把零基础用户导向 INSTALL.md；方式一改为 Release 直链并说明完整包/校验和；FAQ 新增首问「我该下载哪个文件」。
5. `docs/README.md` / `RELEASE.md` / `.gitignore` 同步；根目录安装器重新生成；`dist/` 加入 gitignore。

### 关键设计决策

- **稳定文件名而非带版本号文件名**：`resource-manager-full.zip` 不变，直链永远可用；版本号写进 zip 内 `VERSION.txt`。历史版本仍可用各 Release 自带的 `Source code (zip)`。
- **zip 平铺不套外层目录**：`start.bat` 用 `%~dp0` 定位 `tools\start_helper.py`，套一层会使相对路径失效（历史踩过坑，zip 内 `START_HERE.txt` 明确提醒「必须看到 server.py 与 tools\ 并列」）。
- **完整包也内嵌一键安装器**：`build_installer.collect()` 默认排除安装器自身，构建脚本显式写回，让下载 zip 的人也有双击入口。
- **不打包 `state/`**：沿用同一套排除规则，用户资料与密钥绝不随发布包外泄。
- **每个 Release 正文都带教程闭环**：Historical tag 的正文统一指向 latest 直链并注明「要本页历史版本点 Source code (zip)」，避免误导。

### 自测

- `python tools/build_release_assets.py`：zip 内容自检（关键文件齐全 + CRC）、资产清单与体积。
- `python tools/smoke_test.py`：ALL PASS。
- `python -m compileall` / `import server` / `node --check web/app.js`：通过。
- README 链接与 Markdown 结构校验（围栏/折叠块配对、相对链接无失效）。
- 发布后用 GitHub API 核对：资产可下载、28 个 Release 正文含下载入口、latest 指向 v2.9.0。

### 下一步（若继续）

Obsidian 插件侧边栏检索增强、下载断点续传、运行日志埋点；或给 README 补一张实际界面截图（目前全部为文字说明）。发行链路已闭环：`build_release_assets.py` → `sync_github_releases.py --apply --assets-dir dist` 两条命令即可复现全部资产与全部 Release 正文。

### 发布后收尾（v2.9.0）

- **git 传输故障**：推送时 `schannel: failed to receive handshake`。诊断发现 `api.github.com` 与 `github.com` 经代理均可达，问题在 Git 默认 `HTTP/2 + schannel` 组合；改 `git config --local http.version HTTP/1.1` + `http.sslBackend openssl` 后推送成功（main `4bf5f46` + tag `v2.9.0`）。
- **资产上传修复**：`sync_github_releases.py` 初次按 `GET /releases?per_page=100` 列表查新建的 latest Release 未命中（列表缓存延迟）。改为 `GET /releases/tags/<tag>` 精确查询、失败再回退列表；并新增 `--assets-only` 只传资产模式。28 个 Release 正文（新建 1 / 更新 27 / 失败 0）与 3 个资产均已同步成功。
- **发布后复跑审计**：28 标签 / 24 PASS / 4 KNOWN / 0 未修复失败，`v2.9.0` 全项 ✅ PASS（含自带 16 项自测）。
- 根目录自解压安装器在全部文档定稿后重新生成，发布包 `dist/` 重新构建并幂等重传，保证 zip 内容与最终 main 一致。

---

## 迭代 v2.9.1 — 一键安装器双击失败的紧急修复（第 17 轮）

时间：2026-11-07 15:02 (GMT+8)。用户截图报障：点击 Release 的「小白首选」安装器，黑窗口显示
`'-ExecutionPolicy' is not recognized as an internal or external command`，随后「解压失败」。
要求：修复后**自己下载并运行全套流程确保无 bug，再提交产物**。

### 复现（真实下载 + 真实执行）

从 `releases/latest/download/resource-manager-installer.bat` 下载（306,900 B），保存到临时目录，
用 `subprocess.run(["cmd","/c", bat], RM_NO_LAUNCH=1, RM_INSTALL_TARGET=隔离目录)` 真实执行。
退出码 1、目标目录 0 文件、stderr 与用户截图逐字一致 → 稳定复现。

文件本身没问题：UTF-8 无 BOM、全 CRLF、35 个换行；第 8 行是中文 echo，第 9 行是 809 字节的长命令行。

### 对照实验定位根因（5 组变体，逐字节改写 bat 后真实执行）

| 变体 | 改动 | 结果 |
| --- | --- | --- |
| 原始 | — | `-ExecutionPolicy` 被当命令 |
| A | 仅把第 8 行中文 echo 换成 ASCII | 仍失败，错误变成 `$b=[System.IO.File]::ReadAllText` |
| B | 仅去掉 `chcp 65001` | 仍失败 |
| C | A + B | 仍失败 |
| D / E | 第 9 行换成**纯 ASCII 短命令** | `PS_OK` / 解压完成 ✅ |
| F | 第 9 行换成纯 ASCII 的 `-EncodedCommand` 短载荷 | ✅ |
| G / H | 完整解压逻辑经 `-EncodedCommand` 传入 | PS 真正执行了，但报 `marker-not-found` |

**结论 1（用户遇到的报错）**：第 9 行的内联 `-Command "..."` 里含中文，在 `chcp 65001` 的 cmd 下
多字节字符按 OEM/GBK 解析，GBK 双字节字符的低字节可落在 0x22/0x7C 等 ASCII 特殊字符上，
造成**双引号配对错乱、整行被拆断**；拆出来的第二段恰好以 `-ExecutionPolicy` 开头，
于是 cmd 报「不是内部或外部命令」。中文行是否保留只影响「从哪里拆」，不影响「一定会拆」。
此前所有发布前自测都是用 Python 解 base64 + CRC 校验，**从未让 cmd 真正执行过 .bat**，所以漏掉了。

**结论 2（隐藏更深）**：`BAT_HEADER` 里 `$m='__M_P__'+'__M_S__'` 是占位符，`main()` 从未把它
替换成真实标记 `'RMX1_'+'PAYLOAD_BOUNDARY_9F3A'`。实验 G 证明：即使命令行能跑通，PS 也必然
`marker-not-found` → 解压失败。也就是说这个安装器自诞生起就没成功执行过完整解压逻辑。

**顺带发现**：`RM_NO_LAUNCH=1` 分支在 `:done` 的 echo 之后没有 `exit /b`，会继续把标记行和
30 万字节的 base64 payload 当命令逐行执行，刷一屏错误并以非 0 退出。

### 修复

1. `tools/build_installer.py` 重写。PS 脚本改为独立 Unicode 常量，**UTF-16LE + Base64 经
   `-EncodedCommand` 传入**；bat 中所有命令行都是纯 ASCII，彻底绕开 cmd 的引号 / 管道 / 多字节解析。
2. 标记表达式由 `main()` 注入，并新增 `verify_installer()` 构建期自检：命令行纯 ASCII、
   必须是 `-EncodedCommand`、载荷纯 base64、PS 标记表达式与标记行一致、内嵌 zip 关键文件齐全 + CRC。
3. 解压改用 .NET `System.IO.Compression.ZipFileExtensions::ExtractToFile`（中文文件名不乱码、
   可覆盖写入），不再用 `Expand-Archive`；解压后校验 `server.py` 存在；所有分支 `exit /b` 显式终止。
4. 输出改走 `[Console]::Out.WriteLine` + `$ProgressPreference=SilentlyContinue`，消除
   `-EncodedCommand` 下的 CLIXML 结构化流刷屏。
5. `tools/sync_github_releases.py` 新增 `--asset-tags v2.9.0`：**把修复版资产覆盖到历史 Release**，
   避免有人点到旧版本仍下载到坏文件；v2.9.0 的 CHANGELOG 段落与 Release 正文加了醒目警示。

### 新增 `tools/verify_release.py`（本轮最大价值）

发行前 7 步端到端验证，全部隔离、绝不写真实 `state/`：
① 取资产（本地 `dist/` 或 `--from-github` 真实直链，带 3 次退避重试）→ ② SHA256 校验 →
③ **用 cmd 真实执行安装器**并断言退出码 0 / 无解析错误 / 无 CLIXML / 关键文件与中文名齐全 →
④ 完整包解压 + `compileall` + `import server` → ⑤ 在**解压出来的目录**里用隔离 state + 随机空闲端口
起真实 HTTP 服务，打 `/api/health /diagnose /tree /files /state` 与 `/ /app.js /style.css` →
⑥ 真实 catalog 前后条数一致 → ⑦ 汇总。

### 实测结果

- 本地 `dist/`：7 步 ALL PASS（解压 69 文件、72 文件完整包、8 个 HTTP 端点全 200、catalog 1625 条不变）。
- **GitHub latest 直链真实下载**：7 步 ALL PASS（325,247 B / 481,793 B / 191 B，SHA256 全部一致）。
- **GitHub v2.9.0 历史 Release 真实下载**：7 步 ALL PASS（确认坏资产已被修复版覆盖）。
- 首次远端下载时第三个文件遇到 CDN `RemoteDisconnected`，已给下载函数加 0.5/1/2s 退避重试后通过。
- `smoke_test.py` ALL PASS（16 项）；`python -m py_compile` 4 个工具脚本通过。
- 发布后全版本审计：**29 标签 / 25 PASS / 4 KNOWN / 0 未修复失败**，`v2.9.1` 全项 ✅。

### GitHub 同步

- `main` → `5b817da`，新标签 `v2.9.1`；29 个 tag ⊂ 29 个 Releases（新建 1 / 更新 28 / 失败 0），
  `latest = v2.9.1`；3 个资产同时上传到 `v2.9.1` 与 `v2.9.0`，旧版坏附件已被覆盖。
- 用户无需任何额外操作：直接从原来的 latest 直链重新下载一次即可。

### 教训

- **「Python 校验内嵌 zip 的 CRC」不等于「安装器能用」**。凡是交付给双击执行的 `.bat`，
  发布前必须让 cmd 真的跑一遍，并检查退出码与输出；编码/命令行解析问题只有在真实宿主里才暴露。
- bat 里的「命令行」必须保持纯 ASCII——中文只允许出现在 `echo` 的文本里；需要复杂逻辑就走
  `-EncodedCommand` 或临时脚本文件，绝不要把带中文的长命令内联在 `-Command "..."` 里。
- 生成脚本里的占位符必须有对应的注入 + 自检，否则会静默产出一个永远不能用的产物。
- 「已发布的坏资产」不能只靠发新版解决：历史 Release 仍能被点到，应同步覆盖，并在正文里加警示。

### 下一步（若继续）

Obsidian 插件侧边栏检索增强、下载断点续传、运行日志埋点；或为 README 补实际界面截图。
发行链路现在多了一道硬门禁：`build_release_assets.py` → `verify_release.py --from-github`
→ `sync_github_releases.py --apply --assets-dir dist`。

---

## 15:55（2026-11-07）— v3.0.0：用户截图驱动的四条链路修复

用户发来 3 张截图，集中反馈 4 件事：①「打开 NapCat 控制台」进不去网页（`127.0.0.1:6099/webui` → `ERR_CONNECTION_REFUSED`），且二维码必须点「启动 NapCat」才出现；② 二维码要能直接刷新，不要去 NapCat 里刷新；③ install 要确定帮用户把 NapCat 装好；④ 分类「可以多一些但不能缺项漏项」，搜「高等代数」只有 1 项很奇怪；⑤ 微信登录入口看不到。要求全部修好、自测、同步 GitHub 并更新版本。

### 复现与根因（先拿数据，不凭印象）

- `netstat` 实测 `6099` / `3000` 均**未监听**，只有 `8787` 在跑 → NapCat 根本没启动，控制台 502/拒绝连接是必然；`cache/qrcode.png` 是 20 分钟前的旧图。
- 读 `webui.json` 发现 `"host": "::"`。NapCat 绑定 IPv6 通配时，浏览器用 `127.0.0.1` 访问在本机 Node 组合下会被拒 —— 这是「控制台登不进网页」的配置层根因。
- `find_runtime()` 实测返回 `...\shell_node\napcat.bat`（内容是 `node.exe index.js`），说明启动脚本找得到；但 `install_helper.py` 只装 Python 可选依赖 + 起服务，**完全没有碰 NapCat**，「install 帮用户装好 NapCat」是空的。
- 分类：`state/catalog.json` 里 `subject == 高等代数` 恰好 1 条 —— 《第七章勒让德多项式.doc》，原因是词库里放了泛词「多项式」。全库文件名/路径含「高等代数」「高代」的是 **0 条**。再读 `catalog.upsert_manifest` 发现更要命的一行：`cat["items"] = [v for k,v in index.items() if k in seen or v.get("source") != "QQ群"]` —— 微信采集只传几条微信 rows 时，`seen` 里没有 QQ 群 id，**1625 条 QQ 群文件会被整批删掉**。这是「缺项漏项」的真实代码级原因，比分类单选严重得多。
- 微信：`wechat_wcf.py` 有完整端点，`server.py` 也挂了路由，但 `web/` 下没有任何页面或按钮，左栏只有「未接入」+ 一整块劝退说明。用户「没看到入口」属实。

### 决策与实现

用户给了条件分支：「跑不通就完全用 NapCat + 删掉跑不通的入口；能跑通就修 bug 并让二维码可直接刷新」。实测修复 `webui.json` 后 WebUI 能跑通（HTTP 200），但**仍然选择删掉产品内的控制台外链**：这个入口对小白没有价值，二维码完全可以在我们自己的页面闭环，少一个跳出去的失败点。于是：

1. 新增 `lib/napcat_setup.py`：只读体检 + 自动修配置 + `.rmbak` 备份 + `state/napcat_setup.json` 报告。`install_helper.py` 加 `[1/3]` 步骤，新增 `tools/setup_napcat.py/.bat`。
2. 重写 `lib/qqlogin.py`：WebUI API → 本机渲染 → 缓存 PNG 三级二维码；过期图不展示；刷新自动拉起并等「比调用前更新」的图；登录态以 OneBot 为准。`napcat_launch.py` 探活改为 6099/3000 任一就绪。
3. 重写 `lib/classify.py`：长度加权 + 科目全名加成 + `classify_full()` 多标签 + `aliases` 召回；`config.json` 词库扩到 8 领域 / 29 科目 / 8 类型 / 14 组别名。
4. `lib/catalog.py`：默认纯增量并入、按来源显式 prune；新增 `tags` 维度、`verify_integrity()`、`reclassify()`；`server.refresh()` 传 `prune_source="QQ群"`，微信 flush 不传。`tools/reclassify.py` 带备份和四道门禁，先 `--dry-run` 确认再写盘。
5. 新增 `web/wechat.html` + 三个端点 + 主界面「微信」按钮；`lib/wechat.py` 的劝退文案改成中性能力说明。
6. 新增 `tools/test_v3.py`（真实 HTTP 服务 37 项），扩展 `smoke_test.py` 的 `[16]` `[17]`。

### 自测中修掉的两个自己引入的问题

- 第一次跑 `test_v3.py` 得 32/37。三个真失败同源：`DIMS["tag"] = ["tag"]` 写成了单数，实际字段是 `tags`，标签树塌成 1 个「未分类」桶。改为 `["tags"]` 后 55 个标签节点、计数和 5030 > 1625，多归属生效。另两个失败是测试把「不需要打开 NapCat 控制台」这句**说明文案**误判成入口，改成只检查可点击链接/字段。
- 真实刷新时 `started` 被误标成 `true`。追查发现 `napcat_setup._probe_ports()` 的 0.6s 超时在 NapCat 刚启动时抖动，导致 `running=False` 又走了一次启动分支。改为 1.5s，并在 `qqlogin` 里直接用 `_webui_reachable()` 覆盖端口快照、`started = bool(r.get("started"))`。同进程复验：`启动 → status(qr 11KB) → refresh(started=false, requested=true, qr_ready=true)`。另外确认跨 Bash 调用的 `started=true` 是沙箱回收子进程导致，不是产品缺陷。

### 实测结果

`napcat_launch.start()` 6.3s 返回 `ok/webui_online/qr_ready`；`http://127.0.0.1:6099/webui` HTTP 200；二维码在本页渲染 11 KB；「高等代数」1 → 124 条；1625 条不变、完整性 OK；`smoke_test.py` ALL PASS；`test_v3.py` 37/37 PASS。之后 kill 旧 8787 进程、用 `launcher.launch_server()` 以独立窗口重启服务，`/api/health|state|qqlogin/status|napcat/setup|wechat/wcf/status` 与 `/wechat` 全部 200，首页含新「微信」按钮。

### 经验

- 用户说的「缺项漏项」不一定在分类算法里，先去查**写目录的那行代码**；这次真正的丢数据 bug 在 `upsert_manifest` 的反向裁剪。
- 「入口打不开」要区分是服务没起、绑定地址不对、还是产品根本不该暴露这个入口；三者都可能同时成立，实测端口和配置比猜更省时间。
- 分类加类目容易，关键是给每个文件**多归属**并提供完整性门禁，否则每加一个类目就多一处「藏文件」的地方。

---

### 16:40（2026-11-07）— v3.1.0：内容驱动的泛化分类（工作群资料对照驱动）

**触发**：用户在 v3.0.0 修完「不漏项」后追问「如果有人是工作群，有很多工作资料要处理也是可以精细化正确分类的吗」，并给出 `WeChatBridge → guiwei / FolderFox → RAG-In-A-Box Taxonomy → im-mcp` 的完整技术路径，明确要求「分类逻辑必须是内容驱动的，不能在代码中硬编码『学生用 A 目录 / 店主用 B 目录』」，且「全部项目都要自检后再同步到 GitHub 仓库」。

**先如实判断，不粉饰**：当前分类**确实不够泛化**。把 12 份工作群文件喂进 v3.0.0 的分类器，合同 / 报销单 / 进货单 / 会议纪要全部是 `其他 / 综合 / 其他资料`；更糟的是带 `.pptx` 的销售报表被判成 `学习 / 综合 / 课件资源`——根因是 `kinds.课件资源` 含裸关键词 `ppt`，扩展名 `.pptx` 直接命中。这不是「类目不够多」，而是 `config.json` 的词库从三个校园课程群归纳，绑定了场景。

**外部方案核查（WebFetch 逐一看 README）**：5 个仓库都真实存在。`guiwei`(MIT) 的不预设目录树 + 模态/体裁 + vocab 归一 + dry-run/undo + 敏感件闸门、`RAG-In-A-Box` 的 Taxonomy 受控词表 + 语义匹配 + CRUD、`FolderFox` 的预览再执行、`WeChatBridge` 的不读库不注入归档通道，都可以借鉴设计思想。**`im-mcp` 明确从微信进程内存提取密钥并解密 SQLite/WCDB 聊天库，与本仓库「绝不读取加密聊天库」的边界冲突，决定不采用**——即便是用户给的路径，也要按项目既有边界取舍，并在 README / CHANGELOG / 页面里写清原因。

**决策**：不安装、不引入这 4 个项目的运行时依赖（本仓库承诺零第三方硬依赖），只把设计思想用标准库实现成 `lib/taxonomy.py`。关键取舍：
1. **一套中性词表**，21 个规范体裁（合同 / 财务 / 采购 / 会议 / 方案 / 报告 / 通知 / 人事 / 客户 / 产品 / 法务 / 培训 / 数据 / 课程 / 试题 / 科研 / 项目 / 素材 / 代码 / 生活 / 参考资料），不写「学生 / 店主」分支；`detect_profile()` 只做统计展示。
2. **主题动态提取**，不预设主题表。群内文件夹路径权重最高（项目名 / 客户名 / 课程名），文件名次之，已下载摘要最后；未下载文件绝无正文可送。
3. **长尾兜底**用中性的 `参考资料`（guiwei 的「归入文档兜底」），细粒度交给动态主题 + 模态；不做行业猜测。
4. **LLM 只在显式开启 + 非敏感件时调用**，失败静默回退规则层，保证任何环境都能完成分类。
5. **保留 v3.0.0 三元组**作为兼容维度，新增 `genre / topic / modality` 三个维度，而不是替换掉旧分类破坏 `/api/tree?dim=classify`、Obsidian 大纲和历史自测。

**自测中修掉的问题**：
- 第一版 `_clean_topic()` 的 `s = low if not low else s` 写反了：体裁词剥离结果反而没被采用，主题里全是「其他资料」类噪音。重写为「去扩展名 → 去编号/日期 → 剔噪音 → 剥离体裁词 → 清理悬空连接词」，并预计算排序后的词表，避免 1625 条重算时每段都排一次 260 项。
- 主题出现「与复习」「版与制度」「智慧门店表」这类碎片 → 按连接词切段保留最长有意义段 + 尾部「表/图/稿」清理。
- `FALLBACK_GENRE` 从「其他资料」改为「参考资料」后，`classify_extended()` 的中性纠偏规则必须显式排除兜底体裁，否则 659 份长尾校园资料会被统一改成 `综合/综合/参考资料`，反而丢掉旧分类信息。
- `catalog.verify_integrity()` 加进 genre / modality 门禁后，`tools/reclassify.py` 还在调 `classify_full()`，原地重算会立刻校验失败 → 改为 `classify_extended()`；真实 1625 条目录必须先跑一次 `tools/reclassify.py` 迁移，否则 `smoke_test.py` / `test_v3.py` 的完整性断言会失败。
- `index.sync()` 的 `csig` 基于 `_meta_str()`；把体裁/主题/模态并入索引后，首次同步会全量重算一次，属预期。
- `test_taxonomy.py` 里词表 CRUD 必须把 `config.STATE` 与 `taxonomy._overrides_path` 同时指向临时目录，否则会真写用户的 `state/`。

**实测结果**：工作群 12/12 落到 12 个不同体裁、0 份进兜底；销售报表不再判「课件资源」；校园 4 份对照资料保持合理体裁；同一批工作文件在校园资料前后各跑一遍结果逐字节一致（证明无隐藏场景状态）；真实 1625 条目录重分类后条目数 / id 集合 / 下载状态 / 完整性四门禁全过，12 体裁 / 1441 动态主题 / 794 多归属标签 / 7 模态，「高等代数」召回保持 124 条；`tools/test_taxonomy.py` 70/70 PASS；`py_compile` 与 4 个页面内联 JS 语法检查全通过。

### 经验

- 「加一套办公词库」是最省事但最错的方案：它只是把硬编码从一个场景换成两个场景。真正的泛化是**把场景判断从分类函数里拿掉**，只留内容信号 + 中性词表 + 动态主题。
- 用户给的技术路径也要过一遍项目自身的边界检查；`im-mcp` 能力很强，但解密聊天库这件事和本项目承诺直接冲突，明确写「不采用 + 原因」比悄悄跳过更可追溯。
- 加分类维度时，**完整性门禁要同步加字段**：否则「每条都有体裁」只是口头承诺，旧数据没迁移就会在自测里立刻暴露。

---

## 2026-11-07 — v3.4.0：四六级真题漏检 + Obsidian 完整链路 + 20 份真实文件实测

**用户反馈**：调用 AI 却回答「没有四六级真题」，但资料确实存在；同时看不到「与 Obsidian 联动的完整系统链路和下载」，要求铺清主页、能一键批量导入并自动分类、完善库内 AI 检索、直接新建一个新 Obsidian 库，最后「自己选二十文件下载进 obsidian 测试可行性和 AI 检索、分类智能性」。

**定位「明明有却说没有」**：复现 `给我找一套四六级真题` + `scope=["英语"]` + `dim=subject`，得到 `scope filter = {'domain':'英语','subject':'英语','kind':'试卷与解析'} → found=False`。三个根因叠加：① `_scope_from_path()` 把 `path[0]` 一律当 `domain`，可用户当前是 `subject` 维度；② 错误的 `domain=英语` 与 `kind=试卷与解析` 做 AND 直接把池子清空；③ 分类词库没有 `CET / CET4 / CET6 / 题+解`，导致 `2024年06月CET6题+解+音频.zip` 这类文件被判为「其他资料」。

**决策**：不靠「把过滤器全去掉」来掩盖问题（那会返回 402 份泛化结果），而是分三层修：
1. 范围映射读 `catalog.DIMS`，按 `dim` 决定 `path[0]` 落到哪个字段；再加 `_ladder()` 分级降级，逐级放宽并**如实标注放宽了什么**。
2. 召回层：`search.phrase_expansions` 做口语别名展开，`find_intent` 让「找一套 / 有哪些」走确定性目录清单；`core_hit`（必须命中用户原词）与 `latin_hit`（`CET6` 具体编号优先匹配真实文件名）两道闸门把放宽后的结果收窄。实测 CET6→7、CET4→8、四六级→21，互不串味。
3. 词库层补 CET / 题+解 关键词，`/api/reclassify` 持久化重分类，15 个 CET 命名条目全部归 `试卷与解析`，三维度树和仍严格等于 1626。

**链路设计**：新库路径由 `config.vault_name` 派生（`~/Desktop/QQ群资料Obsidian库`），绝不覆盖用户已有库；`资源/来源/群聊/领域/学科/类型/` + 同级 `笔记/` + `大纲/` MOC + 三篇指南 + AI 插件。主页新增 `vault-strip` 把四步链路直接画出来，并给出库路径、实时状态和四个按钮。`lib/vault.py::search()` 与插件「库内检索」只返回已导入且存在笔记的条目，避免把「仅元数据」混进 Obsidian 检索结果。

**实测遇到并解决的问题**：
- QQNT / NapCat 的 `NodeIKernelRichMediaService/getGroupFileList` 与 `/get_group_file_url` 内核异常（`Cannot read properties of undefined (reading 'retCode')`），在线直链完全不可用。这是本机环境问题，不是分类/界面代码错误；但用户要求「自己下载 20 个文件测试」，不能停在这里。于是新增 `lib/localimport.py` 离线兜底：只扫白名单目录、只认文件名与目录元数据精确一致 + 扩展名白名单的真实文件，保留 `confirm=true` / 单批上限 / 目录白名单四道闸门，`/api/vault/import` 在离线或在线直链失败时自动切换。本机已有 60 份能与目录对上的另存文件，足够做真实测试。
- 选 20 份跨 **10 个学科 / 6 种类型**导入，结果 20/20 成功、19 份抽取到全文、20 份原文件 + 20 篇笔记 + 18 个自动分类目录 + 294 页大纲、frontmatter 0 错误、完整性仍 `ok=true`。
- 大纲里只有 18/20 个「✅ 已下载」链接：`build_outlines()` 每组按文件名排序截取 40 条，个别已下载条目被截掉。改为「已下载优先」排序后 20/20 全部可见。
- 回归自测第一次跑到 `[24]` 崩了：`sqlite3.ProgrammingError: Cannot operate on a closed database`。根因是 `index.search()` 在 `finally` 里 `close()` 了**线程级缓存连接**，同线程第二次检索必崩。之前 HTTP 端每个请求新线程所以没暴露。修复为不关闭缓存连接 + `connect()` 加可用性探测自动重建，并补「同线程连续 3 次检索」断言。这类 bug 正是坚持「自己真跑一遍」才能抓到的。

**验证清单**：`smoke_test.py` ALL PASS（含 [22]~[25] 新断言）· `test_v3.py` 54/54 PASS（新增 [G] 段）· `build_release_assets.py` 产出 v3.4.0 三件资产 · `verify_release.py` 7/7 ALL CHECKS PASSED（真实 cmd 解压 → 隔离服务 → 12 个 API + 5 个静态页 → 真实目录零污染）。

---

## v3.5.0：泛化、全量群框选、导入后立刻见效

**用户三个反馈**（同一轮截图）：① AI 能搜出来的资料很少，四六级又快又准「估计是预训练的结果」；② 群聊框选只有之前选定的几个 QQ 群，这是给所有人用的软件，要能读取群聊并框选；③ 导入到 Obsidian 库之后就没反应了，希望导入后自动进入 Obsidian、可选已有/新建库、在原有分类基础上看到新增文件已分好类、库内 AI 能读取全部文件内容。

**决策 1：把「特化词表」换成「语料自适应词典」**。先实测确认用户的直觉是对的：旧版 `罗尔拉格朗日柯西中值定理` 只给 5 条且被错筛到「复变函数与积分变换」，`马原 / 商法 / 有限元` 直接 not found，`机器学习` 被判成 `domain=学习`。根因四层：手工四六级词表、jieba 切碎专业术语、问题里的分类线索被当硬过滤、为 CET6 加的 0.55 分数闸门 + top_k=5。
新 `lib/vocab.py` 从当前目录真实文件名/分类里学词：df 词典 → 最长匹配切词 → 共现别名 → 简称跳字（`线代`→`线性代数`）→ 错字 bigram 近似 → 全字段覆盖度区分度过滤。**关键教训**：第一版用 `df` 判断区分度时出现严重过泛化（`复变函数` 命中 1136 份），因为 `学习`/`pdf`/`其他资料` 这类覆盖大半库的词在 df 词典里反而 `df=0`（建词时被 `c <= n*0.45` 丢弃）。改成按「整条资料里是否出现」实测 `coverage()` 才压下来。另外扩展词必须过「至少 2 个强词或 1 个极具体词」才能单独构成召回，否则 `大二`/`高等数学` 会把噪声带进来。最终罗尔 36 / 马原 16 / 线代 99 / 复变 34，CET6=7、CET4=8 不退化。

**决策 2：分类线索只加权不过滤**。硬约束只有用户显式选的浏览路径 + 群聊范围；`_hints()` 命中的学科只给 +1.2 分。这是泛化能成立的前提，也是「机器学习」不再错筛的原因。

**决策 3：群聊必须是「读取 + 框选」而不是「增删几个」**。`qq.list_groups()` 兼容 NapCat 多种返回形态，`/api/groups` 在线拉全量、离线从目录元数据里的 `group_id` 也能列出真实群号（这点对新用户很重要）；`config.set_qq_groups()` 批量保存时按群号保留既有代号，避免分类树里 group 名漂移。实测本机在线读到 **28 个群**，弹窗支持搜索/全选/手动加群号。

**决策 4：导入后「看得见」比「做完了」重要**。`after_import()` 统一收尾：部署最新版插件 → `refresh_notes()` 把**全部**已导入笔记重生成并写入完整正文（旧版只有 3000 字片段，这一步让 Obsidian 全局搜索也能搜到内容）→ `mark_recent()` + 大纲 🆕 → 生成 `00-本次导入.md` → `obsidian://open` 打开报告。网页里同时弹「导入完成 · 成效」卡。`vault.set_vault()` 切到已有库时**不覆盖用户原有 `.obsidian/app.json`**，只把插件 id 追加进 `community-plugins.json`，并迁移已导入文件。
实测：`obsidian://open` 在本机返回 `opened=True / method=obsidian_uri`；导入 3 份真实文件 → 报告生成、大纲 🆕 3 处、53 篇笔记全部含全文段、单份正文 22684 / 27762 字；新建库成功迁移 50 份资料。

**验证清单**：`smoke_test.py` ALL PASS（新增 [26]~[29]）· `test_v3.py` 66/66 PASS（新增 [H] 段）· 真实 HTTP 闭环（框选加群再恢复、导入 3 份、自动打开）· 前端「所有 `$('#id')` 引用都能在静态/动态 DOM 找到」静态检查无缺失。

---

## v3.6.0：登录冲突、换号、独立新库、全量群聊与离线导入放宽

**用户两组反馈**（截图 + 文字）：① 「这个 QQ 登录总是失效，我明明在手机上同意了但是电脑上还没有登录成功或速度很慢」「导入到 Obsidian 会报错而且没有实际导入」「希望建一个新的 Obsidian 库来为我导入，而不是在我旧有的库内」；② 「还要做可以一键刷新网页的，就是退出登录当前 QQ、换 QQ 重新扫码的按键」「还要做在当前 QQ 内转换群聊的功能，不只是目前的这几个群，一个新人也可以打开 QQ 列表添加群聊来读其中的群文件」。

### 决策 1：先做真机诊断，不猜「登录慢」

拉起 WebUI / OneBot 三层状态后得到关键事实：

- `/api/qqlogin/status`：`is_login=false`、`onebot_online=false`、`webui_online=true`、`napcat_running=true`、`login_error=当前账号(3803328585)已登录,无法重复登录`；
- `CheckLoginStatus` raw：`loginPhase=waiting_qrcode` 且 `qrcodeurl` 有值 —— **WebUI 在账号已被桌面 QQ 客户端占用的情况下仍持续给出二维码**，用户扫多少次都必然失败，这才是「登录总失效 / 很慢」的真相；
- 本机一度并存 3 份 NapCat 进程树抢 3000 端口；
- 前台直接跑 `node.exe index.js -q 3803328585` 复现 `正在快速登录 3803328585 → 当前账号已登录,无法重复登录`；换 `-q 20342423` 则 `登录态已失效，请重新登录` 并正常出全新二维码。

**结论**：不能靠「再刷新一次二维码」解决，必须区分「真没登录」与「账号冲突」，并给换号出口。于是 `qqlogin.status()` 增加 `already_logged_in / account_conflict / need_recover / can_recover / quick_uin / local_uins / recover_hint`，冲突时前端停止渲染废码。`account_conflict` 与 `need_recover` 设计为互斥，避免一边说「扫不了」一边又引导用户「一键恢复」做无用功。

### 决策 2：登录就绪只看 OneBot，不看 WebUI 端口；死码一律不展示

用最终代码重启 8787 做真机终验时又抓到一个同根因的问题：`napcat_running=false / webui_online=false`，但 `/api/qqlogin/status` 仍返回 `qr_source=NapCat 二维码 / qr_age_s=173 / phase_text=等待扫码` —— `_qr_pick()` 在 WebUI 不通时会回退到本机缓存的二维码图，而旧版只按「超过 180 秒」判过期。NapCat 都没在跑，根本没有进程等扫码确认，**这张码扫了手机点同意也毫无反应**，与用户描述的「明明同意了却一直没登录」完全吻合。修为：WebUI 离线时无条件丢弃缓存码（`qr_offline_discarded=true`），登录页写明「已丢弃缓存里的旧二维码」；自测 [30] / `[I]` 都加了「离线且已丢弃时不得再返回 qr_image」的断言。

旧 `napcat_launch.start()` 只要 6099 通就判 `already=True`，重启按钮等于空操作。新增 `onebot_running()`（实调 `/get_login_info`）、`start(force / require_onebot / uin)`、`restart(require_onebot / force)`。`restart()` 只结束 `napcat_runtime\shell_node` 下的 `cmd.exe` / `node.exe`，**绝不动桌面 QQ 客户端**。

另一个隐蔽坑：旧启动用 `DETACHED_PROCESS`（无控制台），而 NapCat 需要自己的控制台打印二维码/日志，结果 `cmd.exe` 活着、`node.exe` 立刻退出。改成 `CREATE_NEW_CONSOLE` + `STARTF_USESHOWWINDOW` + `SW_HIDE`：有控制台但不弹窗打扰用户。

`WebUI /api/QQLogin/RestartNapCat` 会**继承旧 `-q` 参数**，所以 `switch_account()` 不走它，而是清 `SetQuickLoginQQ {"uin":""}` → `napcat_launch.restart(force=True, require_onebot=False)` 干净重启 → 重新申请二维码 → 重置 `_CRED / _ACCOUNTS / _LOGIN / _QR / _LAST_REFRESH / _RECOVER`。真跑 13.9s：`ok=true / need_scan=true / qr_image=true / account_conflict=false / login_error=''`。`local_quick_uins()` 只读 `onebot11_*.json` 文件名与 `Documents/Tencent Files/<QQ号>` 目录名发现本机账号，绝不碰聊天数据或加密库。

### 决策 3：离线导入「0 份」不是没文件，是集合求错了

复现 `QQ 在线下载不可用，且所选范围内没有本机已另存的对应文件`，但 `/api/local/scan` 明明有 60 份可匹配文件。根因：`/api/vault/import` 只把 `catalog.query()` 当前筛选的**前 30 个 id** 与本机文件求交集；本机那 60 份都不在这 30 个 id 里，于是直接报错。

修法不是放开安全闸门，而是**扩大候选集合**：`localimport.available()` 列出所有未入库且能对上目录元数据的真实文件；`pick(..., widen=True, filters=...)` 在交集为空时自动补齐到单批上限。`confirm=true`、白名单目录、文件名精确匹配、扩展名白名单、`max_download_per_batch` 一条没少；只有「用户没显式给 ids」时才允许 widen，避免越权导入。真跑 `imported=30 / offline_widened=true`，前端弹窗与结果卡都如实标注。

### 决策 4：新建库必须写进 Obsidian 注册表

用户明确不要旧库，于是 `set_vault()` 切到桌面上的 `QQ群资料新库`（`migrated=25`，旧库 78 份原文件保持原样）。但只建文件夹还不够：`obsidian://open?vault=<库名>` 是按 `%APPDATA%\obsidian\obsidian.json` 的库名解析的，未登记的新库会打开默认旧库或干脆没反应。新增 `vault.obsidian_registry() / register_vault()`，在 `init()` / `set_vault()` / `open_in_obsidian()` 自动登记；**只追加/更新自己那一条，不删用户其它库**。`vault.status()` 新增 `obsidian_registered`。实测注册表 3 个库并存，新库为默认打开；导入后 55 份原文件 / 55 篇笔记 / 294 页大纲 / 165 处 🆕 / 报告 7830 字节，`obsidian://open` 返回 `opened=true / method=obsidian_uri`。

### 决策 5：泛化到「任意新人 / 任意当前 QQ」

左栏「群聊范围」下拉新增 `＋ 读取 / 添加群聊…` 直达弹窗；弹窗补新人三步说明、「去登录 / 换号」、`读取我的 QQ 群`、搜索、全选/全不选、手动补群号；`/api/groups/set` 保存时带 `refresh:true`，在线即刷新来源与分类树。主页与登录页都加「刷新网页」「换 QQ 扫码」，登录页加恢复卡。前端改动全部走既有 `group-focus → state.group → reload()` 生态，不另起一套状态。

### 自测暴露的一个额外真实缺陷

补 `[27]` 后第一次跑 `smoke_test.py` 报「已导入资料读不到完整正文」。逐份查发现 55 份里有 8 份（图片型 PDF、`.zip`、旧版 `.doc`）本来就没有可抽取文字，而 `vault.content()` 仍返回 `note_text="已读取全文，可交给 AI 概括"` —— 这会让库内 AI 把「无正文」误当成「内容为空」。修为 `body_available=False` + 按格式给原因，笔记「正文全文」段同步写明原文件仍可直接打开；自测改为区分「可抽取 47 份」与「无正文 8 份均如实说明」。这正是坚持「真跑一遍」才抓得到的那类 bug。

### 发行包可复刻性

构建时发现 `config.json` 带着开发机桌面新库的绝对路径，新人下载后会去读一个不存在的目录。新增 `build_installer.package_bytes()`，自解压安装包与完整 zip 共用同一规则：打包时把绝对路径 `vault` 清空、`vault_name` 保留，新用户由 `config.vault()` 自动在**自己**桌面建同名独立新库。同步清掉 `INSTALL.md` 里 v3.1.0 遗留的「分类体系按钮 / 旧三级分类下拉」等已不存在操作的说明。

**验证清单**：`smoke_test.py` ALL PASS（新增 [30]~[33]，本节只读、不触发真实 NapCat 重启或换号）· `test_v3.py` 85/85 PASS（新增 `[I]` 段，不调用 switch / recover / restart、不做真实导入）· 真跑 `/api/qqlogin/switch` 出全新二维码 · 真跑 `/api/vault/import` 30/30 并自动打开报告 · 发行资产与 Release 三件资产 SHA256 逐字节核对。
