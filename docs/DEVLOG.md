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
