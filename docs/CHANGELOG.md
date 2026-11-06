# 更新日志

本文件按版本记录对外可见的变化；开发过程详见 [DEVLOG.md](DEVLOG.md)。
格式：`## [版本] - 日期`，条目用 `新增 / 修复 / 变更 / 文档` 分类。

## [v2.0.0] - 2026-11-07

前端：统一搜索框 + 命中高亮（持续迭代第 7 轮，候选 A）。

### 新增
- **搜索命中高亮**：`web/app.js` 新增 `hl()`——先转义防 XSS，再按查询词（CJK 整串 / 拉丁按空白切词）不区分大小写包裹 `<mark>`；文件列表的「文件名」与「摘要」命中处高亮。`web/style.css` 增加 `mark` 样式。
- **搜索框「问 AI」按钮**：搜索框右侧增加「问 AI」，一键把当前查询连同**当前浏览范围**交给 AI 助手回答，无需复制粘贴；搜索与 AI 检索共用同一范围上下文。

### 安全
- 高亮严格先 `esc()` 转义再包裹 `<mark>`，不对用户输入与文件名做裸 HTML 注入；查询词中的正则特殊字符先转义，避免 ReDoS / 注入。

### 验证
- `node --check web/app.js` 通过；服务实测 `/`、`/app.js`、`/style.css` 均返回含新标记的内容。

## [v1.9.0] - 2026-11-07

微信监听群清单持久化 + 发现端点（持续迭代第 6 轮，GitHub WeChatFerry 拓展补全）。

### 新增
- **监听群清单持久化**：`lib/wechat_wcf.py` 新增 `load_rooms` / `save_rooms`（存于 `state/wechat_rooms.json`，已 gitignore），记住用户上次选择的群，重启后无需重选。
- **群发现端点** `GET /api/wechat/wcf/rooms` 改走 `get_rooms(cfg)`，仅 available+login 时返回群列表。
- **保存端点** `POST /api/wechat/wcf/rooms/save`：前端发现群后保存监听清单。

### 变更（安全）
- `start_capture` 不再「空 rooms = 监听全部群」。改为：请求传 rooms 优先，否则回退到已保存清单；**两者皆空则明确报错要求先选择群**，避免误采集无关群文件。

### 文档
- `tools/smoke_test.py` 增加群清单持久化往返 + `get_rooms` 结构断言。

## [v1.8.0] - 2026-11-07

刷新来源改用增量同步（持续迭代第 5 轮）。

### 变更
- `server.refresh()`（启动刷新 + `POST /api/refresh`）由 `index.rebuild` 改为 `index.sync`：刷新来源后只重算变化的条目；首次运行 `idx_meta` 为空时等效全量重建，行为与旧 `rebuild` 一致。
- `POST /api/reindex` 保留为**显式全量重建**（用户主动「重建索引」按钮，例如改了分词/规则后整体重算），不动。

### 影响
- 日常「刷新来源」不再每次全量重建 1625 文档索引，启动与刷新更快；其余全量重建语义保持。

## [v1.7.0] - 2026-11-07

Bug 修复 + LLM 健壮性（持续迭代第 4 轮，自测驱动）。

### 修复
- **`ai.answer("")` 崩溃（NameError）**：空问题分支在 `f` 定义前就引用 `scope=f`，导致每次空 `?q=` 抛异常。已将 `cfg` 提前，空问题改为返回 `scope=_scope_from_path(scope)`，不再崩。
- **LLM 代理失效（外部模型在代理网内无法出网）**：原 `lib/llm.py` 用 `build_opener(ProxyHandler({}))` 强制清空代理，导致任何外部 OpenAI 兼容接口在必须经由代理出网的环境里直接失败。改为按地址区分：本地地址（`127.0.0.1`/`localhost`）直连，外部地址沿用环境变量代理。

### 优化
- **LLM 调用加退避重试**：`chat`/`test` 对超时、连接中断、5xx 等瞬时错误重试 2 次（0.5s/1s 指数退避），4xx 确定性错误不重试，避免偶发抖动直接答非所问。
- 答案长度上限回归 `max_answer_chars`（原 `×3` 会突破配置上限）。

### 文档
- `tools/smoke_test.py` 增加空问题不崩溃、LLM 代理策略两项断言。

## [v1.6.0] - 2026-11-07

索引增量同步 + 回归自测（持续迭代第 3 轮）。消除 REVIEW.md 性能瓶颈 #4（每次捕获落库都全量重建索引）。

### 优化
- **索引增量同步 `index.sync(cat)`**：以「元数据 + 正文文件 stat」的廉价指纹（`idx_meta` 副表）判定变化，仅对新增 / 删除 / 变更的条目做增删改，不再每次整表 `DELETE` 后全量重插。首次运行 `idx_meta` 为空时等效全量构建，与 `rebuild` 行为一致。
- **微信捕获落库改用 `sync`**：`wechat_flush` 原先每次防抖落库都调 `index.rebuild`（1625+ 文档全量重算），现改为增量同步——只有真正变化的条目参与重算，`rebuild` 保留给「刷新」等需整体重算的场景。

### 新增
- **回归自测 `tools/smoke_test.py`**：覆盖 lib 全模块导入、rebuild/sync 增量一致性、微信适配器默认安全降级、可选 LLM 最小调用；退出码即回归信号，供后续持续迭代防回归。

### 文档
- 重建自解压安装器（58 文件，含 `lib/wechat_wcf.py` 与 `tools/smoke_test.py`）。

## [v1.5.0] - 2026-11-07

微信源拓展（持续迭代第 2 轮，GitHub 方案集成）。检索 GitHub 成熟方案后选用 **WeChatFerry（PyPI: `wcferry`）** 作为微信接入技术路径，并落地为可选、默认关闭、安全降级的适配器。

### 新增
- **微信监听式适配器** `lib/wechat_wcf.py`：基于 WeChatFerry 注入本机微信 3.9.x 暴露的本地 RPC，以**监听式**捕获指定群的文件/附件消息（解析 appmsg XML `<type>∈{5,6,8}`），产出与 QQ 适配器等构的 row 字典，汇入同一 catalog/index/vault 流水线。
- **服务端端点**：`GET /api/wechat/wcf/status`、`GET /api/wechat/wcf/rooms`、`POST /api/wechat/wcf/capture/start`、`POST /api/wechat/wcf/capture/stop`；`/api/state` 增加 `wechat.wcf` 子状态与 `capturing` 标记。捕获采用 5s 防抖缓冲（`wechat_on_row` → `wechat_flush`），落库后自动 `upsert_manifest → save → rebuild → build_outlines`。
- **配置项** `sources.wechat.wcf`：`{enabled,host,port,note}`，默认 `enabled=false`。

### 安全与降级
- **绝不读取加密聊天库**：仅监听用户显式指定群、且为文件类消息；与 QQ 的全目录遍历式不同，微信为事件驱动监听。
- **未安装 `wcferry` / 未登录微信 / 未开启**：端点与状态一律 `ok:false` + 明确可读原因，不抛错、不阻断主程序；主程序零新增硬依赖。
- `available()` 仅尝试 `import wcferry`，失败即视为不可用，不影响 QQ / Web / AI 任何既有功能。

### 文档
- `config.json` 增加 `wcf` 块与启用说明；`docs/REVIEW.md` 路线图同步。

## [v1.4.0] - 2026-11-07

性能与检索精度优化（持续迭代第 1 轮）。核心功能零新增硬依赖，所有增强均为可选/优雅降级。

### 新增
- **可选中文分词（jieba）**：`index.query_terms` 默认用 jieba 切词（如「常微分方程数值解讲义」→ 微分方程/数值/讲义，而非 8 个噪声 trigram），显著提升检索词精度与召回纯净度；未安装 jieba 时自动回退到滑动 3-gram，功能不受影响。可用环境变量 `RM_NO_JIEBA=1` 强制关闭。已写入 `requirements-optional.txt`。
- **系统审查文档** `docs/REVIEW.md`：逐模块评估、性能瓶颈、可优化方向与后续路线图（本迭代的依据）。

### 优化
- **`catalog.load` 加 mtime 缓存**：文件未变化时直接命中内存，避免每个请求重复 `json.loads`（1600+ 条目）。`save()` 自动失效缓存，一致性不受影响。
- **`index` 连接/计数缓存**：FTS5 只读连接按线程（`threading.local`）复用，不再每次检索新建/关闭 SQLite 连接；`count()` 结果内存缓存，`rebuild` 时失效。写路径（`rebuild`）仍用独立连接并关闭，互不污染。
- **`ai.answer` 预计算 hay**：每个候选的 9 字段检索串只拼接一次，避免打分循环重复计算。

### 文档
- `requirements-optional.txt` 补 jieba 说明。

## [v1.3.0] - 2026-11-07

让 AI 检索按科目/范围收敛、分类检索更细，解决「问高等代数却答复变函数」「分类太粗别人用不起来」两类反馈。

### 修复

- **AI 答非所问（跨科目串味）**：原 `ai.answer()` 只在「有哪些 / 未下载」这类列举性问题上做科目/类型识别，内容型问题走全局关键词检索，会把别的科目的资料塞进来（例如问「高等代数考试内容」却返回「复变函数」资料）。现改为**所有问题都先识别科目/领域/类型**，并把检索候选集严格限定在该范围内再排序；范围为空时如实说明「该科目仅元数据，无法作答」，不再臆造或串科目。
- **分类错挂**：`复变函数` 系列资料此前因文件名含「积分」被误挂到「高等数学」。现已新增「复变函数与积分变换」「高等代数」「数学分析」「离散数学」「数值分析」「运筹学」等科目，并把专精度高的科目排在「高等数学」之前按分值匹配——复变函数不再混入高数。

### 新增

- **浏览范围自动成为 AI 检索范围**：前端把当前所在的「领域 › 科目 › 类型」路径随提问一起发给后端，AI 只在该范围内作答，并在回答末尾标注「范围 X」。
- **类型筛选 chips**：文件区上方新增筛选条（全部 / 试卷与解析 / 习题作业 / 课件资源 / 上课笔记 / 实验代码 / 指南说明），点击即得「某科目下的试卷/课件/笔记」等细分视图；切换分类或搜索时自动重置。
- **类型标签中文化、更细**：`真题试卷→试卷与解析`、`课件教材→课件资源`、`笔记总结→上课笔记`，并扩充关键词，使「其他资料」占比从高 35% 降到约 30%，检索颗粒度更可用。
- **接口扩展**：`GET /api/ask` 支持 `scope` 参数（当前浏览路径）；`GET /api/files` 支持 `kind` 参数按类型过滤。

## [v1.2.3] - 2026-11-07

修复「install.bat 双击后命令行闪退」与「扫码登录后页面加载失败（ERR_CONNECTION_REFUSED）」两个新手高频卡点，并补齐若干易崩环节。

### 修复

- **点击 install.bat / start.bat 弹出命令行后直接闪退**：根因是纯 Python 助手在非交互环境下 `input()` 抛出 `EOFError` 没有任何兜底，加上 `.bat` 没有 `pause`，异常一冒出来窗口就关了。给所有 `input()` 调用包上 `safe_input()`（捕获 `EOFError`/`KeyboardInterrupt` 返回默认值），并在 `.bat` 末尾加 `pause` 与退出码提示，再也不会“闪一下就没”。
- **扫码成功跳转主界面时页面加载失败**：根因是本地服务只是启动器（install/start.bat）的子进程，用户关掉启动窗口、或启动窗口因异常退出，服务跟着一起死，页面 `/` 请求 8787 端口时已是 `ERR_CONNECTION_REFUSED`。改为**服务以独立控制台窗口（Windows `CREATE_NEW_CONSOLE`）运行**——关闭启动器窗口不影响服务；新增共用模块 `tools/launcher.py` 统一负责「探活 / 端口检测 / 独立窗口拉起」。
- **登录页跳转前先确认服务可达**：`web/login.html` 的 `goHome()` 在跳转 `/` 前先 `fetch('/api/health')`，最多重试 25 次（约 20 秒）；仍不可达时显示「点此打开资源管理器」的可点链接与明确提示，而不是硬跳到一个死页。
- **`find_root()` 全盘遍历卡死**：原实现用 `os.walk` 从分区根递归，在部分机器上会长时间无响应。改为**只向上爬祖先目录、最多 5 层**定位 `server.py`，找不到时给友好中文提示（「请先解压整个文件夹再运行」），不再遍历整盘。
- **`.bat` 健壮性收尾**：`install.bat`/`start.bat`/`一键登录.bat`/`tools/start_napcat.bat` 全部为纯 ASCII 启动器，`python` 缺失自动回退 `py`，找不到 `server.py` 时由 Python 助手优雅提示而非抛 traceback；新增 `tools/stop.bat` 一键停止 8787 服务。
- **所有命令行工具（`open_login.py`/`napcat_ctl.py`）加 `if __name__=='__main__': try/except` 兜底**，任何异常都打印可截图信息并 `input` 暂停，不再闪退。
- **自测发现并修复：`/api/qqlogin/restore` 在 NapCat 未运行时卡住 20+ 秒**：原实现无条件轮询 `qq.online()` 并 `sleep(1.5)×14`，即使 OneBot 端口根本没监听也会空等 21 秒，页面看起来像卡死。新增 `lib/qq.reachable()` 端口探活，NapCat 没运行时立即返回「请先启动 NapCat」的可操作提示；已运行但未就绪时最多等约 8 秒。
- **二次热修（同版本 v1.2.3 重新发布）—「在压缩包里直接双击 .bat 报找不到 tools/ 文件」**：根因是用户在资源管理器里**直接打开 zip 并双击里面的 `install.bat`**，Windows 只会把那一个 `.bat` 抽到临时目录运行，不会带上 `tools/` 等文件，于是 Python 找不到 `install_helper.py` 报 `can't open file`。修复方式：`install.bat`/`start.bat`/`一键登录.bat` 改为**先稳健探测 helper 位置**（`tools\` 与同名文件），找不到时打印一眼就懂的英文指引（提示「先完整解压再运行」）并安全退出 `exit /b 2`，不再甩 Python 报错；同时移除会导致 cmd 解析错误（`此时不应有 .`）的 `..\` 路径候选与未转义括号。另新增 `新手必读.txt`（UTF-8 中文零配置上手指南），`.bat` 报错时指引用户阅读。各 helper 的 `find_root()` 也增加「向下一层兜底」以兼容解压时多套一层文件夹的情况。

### 新增

- `tools/launcher.py`：统一的本地服务启动/探活模块（被 install/start 共用），服务以独立窗口运行。
- `tools/stop.bat`：双击即停止 8787 本地服务。
- **自解压安装器 `resource-manager-installer.bat`（根治“解压后才能用”的手动操作痛点）**：`tools/build_installer.py` 把整个程序（git archive，自动排除发布脚本）以 base64 内嵌进一个纯 ASCII 的 `.bat`。用户**直接双击它即可**——无论在压缩包预览里双击、还是先解压再双击，它都会自动解压到 `C:\Users\<你>\resource-manager`、检查 Python、装好可选增强、启动服务、打开浏览器，**全程无需手动解压**。中文提示通过 base64(UTF-16LE) 内嵌、PowerShell 解码弹窗，彻底摆脱 GBK/UTF-8 代码页乱码。GitHub Release 主附件改为该安装器。

## [v1.2.2] - 2026-11-07

修复登录页「无法连接 NapCat WebUI」相关的一连串问题，并补齐自测发现的其它易错环节。

### 修复

- **登录页直接报原始 Python 异常**：`lib/qqlogin.status()` 在 WebUI 连不上时把 `URLError: <urlopen error [WinError 10061] ...>` 这类原始异常塞进页面提示，用户看到的是一堆技术报错。改为按错误性质给出可操作指引，并新增 `need_start` 标记；连接类错误（端口无响应 / 超时 / 拒绝）统一提示「NapCat 未运行，点启动按钮或打开控制台」。
- **NapCat 没运行时没有任何恢复手段**：登录页 / 主界面离线提示都只能干瞪眼。新增「启动 NapCat」按钮（登录页 `web/login.html`、主界面 `web/app.js` 离线提示），点击后由后端 `lib/napcat_launch.start()` 自动定位 NapCat 运行时（`napcat.bat`，兼容 OmniQQ-MCP 部署路径）并以独立进程拉起，最多等待 40 秒让 WebUI 端口就绪，页面自动刷新出二维码。
- **新增接口** `GET /api/napcat/status`、`POST /api/napcat/start`，以及命令行工具 `tools/napcat_ctl.py` + `tools/start_napcat.bat` / `tools/start_napcat.sh`（双击即可手动拉起 NapCat）。
- **自测补强（其它易错环节）**：
  - `lib/napcat_launch` 只在用户显式触发时启动，不读不写任何令牌；启动用 `DETACHED_PROCESS` 脱离父控制台，关掉资源管理器也不会带走 NapCat。
  - 登录页轮询在 `need_start` 变 false（WebUI 恢复）后自动隐藏「启动 NapCat」按钮，二维码正常显示。

### 新增

- `lib/napcat_launch.py`：定位 / 探活 / 拉起 NapCat 的独立模块。
- `web/login.html`：新增「启动 NapCat」按钮与更清晰的离线指引文案。
- `web/app.js`：主界面离线提示新增「启动 NapCat」按钮，点击后自动拉起并延时刷新来源。

## [v1.2.1] - 2026-11-07

修复 v1.2.0 Release 压缩包「双击 install.bat 装不上」的问题。

### 修复

- **install.bat 从压缩包内直接运行找不到 server.py / requirements-optional.txt**：
  助手脚本会递归定位 `server.py`（兼容解压后多一层文件夹），找不到时给出友好中文提示——「请先把整个压缩包解压到一个文件夹，再双击里面的 install.bat，不要在压缩包里直接双击运行」。
- **install.bat 启动后中文行乱码（`♦地址:` 未识别）**：根因是 `.bat` 里直接写中文会被 `cmd.exe` 多字节边界截断/误读；改为 `.bat` 只做纯 ASCII 启动器，中文提示全部移到 Python 助手（`tools/install_helper.py`、`tools/start_helper.py`），由 Python 以 UTF-8 正确输出。
- **可选增强装失败会中断启动**：可选依赖改为「能装就装，装不上只提示、不中断」，核心功能照常运行（PDF 只登记元数据等降级行为）。
- **增强健壮性**：`python` 缺失时自动回退 `py`；`start.bat` / `一键登录.bat` 同样改为 ASCII 启动器 + Python 助手；启动后自动打开浏览器界面。

### 变更

- 发布用压缩包**不再带 `resource-manager-vX.Y.Z/` 顶层前缀**，解压后文件就在所选文件夹根目录，`install.bat` 与 `server.py` 同级，从根源上避免「解压多一层 / 压缩包内运行」导致的找不到文件。
- 根目录 `新手必读.txt` 顶部新增醒目提示：必须先解压整个文件夹、再运行 install.bat。

## [v1.2.0] - 2026-11-06

面向**零配置新手**：让第一次用、从没配置过的人也能在不懂原理的情况下轻松跑起来。

### 新增

- **首次配置向导** `web/setup.html` + `GET /api/setup` / `POST /api/setup/config` / `POST /api/setup/done` / `GET /api/qq/groups`：首次打开主界面会弹出横幅，进入向导后只需 2 步——① 安装并登录 NapCat（含官网下载链接与控制台地址）；② 在向导里「自动列出我的群」勾选或手动填群号，保存即写入 `config.json`。
- **一键安装脚本** `install.bat`（Windows）/ `install.sh`（Mac·Linux）：检查 Python、按需安装可选增强（PyMuPDF / OpenCV）、自动启动服务并打开界面。
- **依赖说明** `requirements.txt`（核心零依赖）+ `requirements-optional.txt`（可选增强）。
- **新手文档** `docs/新手上手指南.md`：纯图文、不用懂原理的 3 步上手；仓库根目录新增 `新手必读.txt` 给压缩包用户。
- `lib/qq.py` 新增 `list_groups()`：通过 OneBot `get_group_list` 自动列出当前 QQ 加入的群，供向导勾选。
- `lib/config.py` 新增 `save_qq_groups()` / `setup_done()` / `mark_setup_done()`：原子写盘并同步内存。

### 文档

- `README.md` 顶部新增「🚀 第一次用？3 步上手」速览框，并链接新手上手指南。
- `RELEASE.md` 增加 v1.2.0 版本记录与「给第一次使用的人」说明。

## [v1.1.0] - 2026-11-06

QQ 网页一键登录：**不再往桌面生成二维码图片**，扫码后自动恢复在线下载。

### 新增

- `lib/qqlogin.py`：适配本机 NapCat WebUI（默认 `127.0.0.1:6099`）。用 `SHA256(token + ".napcat")` 换会话凭证，读取实时二维码内容、扫码阶段、已保存账号与 OneBot 状态；二维码由本机 OpenCV 渲染，缺失时回落到 NapCat 自带缓存图。
- `web/login.html`：网页扫码登录页。实时二维码、过期自动换新、手动「刷新二维码」、已保存凭证可「一键快速登录」免扫码、扫码后自动等待接口就绪并刷新来源、成功 3 秒跳回主界面。
- `tools/open_login.py` + `一键登录.bat`：双击即确保服务在跑并打开登录页；主界面右上角新增「QQ 登录」按钮，离线时高亮并在侧栏提示。
- 服务端 5 个端点：`GET /login`、`GET /api/qqlogin/status`、`POST /api/qqlogin/refresh` / `quick` / `restore`。`restore` 会等 OneBot 3000 就绪后自动执行刷新来源并解锁下载。

### 变更

- 恢复在线不再依赖助手生成桌面图片，也不需要用户手动点「刷新来源」（手动入口仍保留在右上角）。
- 隐私收紧：WebUI token 只在本机读取、会话凭证只在进程内存；接口只向页面返回二维码版本标识（`qr_key`），**不下发登录链接原文**；二维码不经任何第三方服务。
- 未扫码时 `restore` 明确提示「请先扫码并确认」，不再误报「QQ 已登录」。

### 修复

- `/api/health` 在 QQ 离线时每次实时探测 OneBot，稳定耗时约 2 秒 → 改用请求开头 `_sync_source()` 已实时同步的状态缓存，健康检查降到约 5 ms。
- `tools/open_login.py` 原用 2 秒超时探活，恰好被上面这个 2 秒卡住，误判「服务未运行」并尝试再起一个实例 → 超时放宽到 6 秒并重试，同时增加 TCP 端口监听兜底：端口已在监听时直接打开登录页，绝不重复启动服务。

### 文档

- 根目录 `README.md` 新增「QQ 一键登录」章节、API 与目录结构；`GUIDE.md` 更新离线恢复叙述；`VERIFICATION.md` 追加登录链路验证并修正过时的 GitHub / 二维码结论；`RELEASE.md` 补版本与验收项。

## [v1.0.1] - 2026-11-06

文档补全与运行中稳定性收尾。

### 新增

- `docs/DEVLOG.md`：按时间顺序的开发日志（决策、故障、修复全过程）。
- `docs/GUIDE.md`：项目通读式说明文字（背景、使用旅程、防臆造机制、微信限制、隐私安全）。
- `docs/CHANGELOG.md`、`docs/README.md`：版本日志与文档索引。

### 修复

- QQ 在运行中途掉线时界面仍显示「在线」 → 每次请求实时探活，掉线自动收紧为离线快照并锁定下载；恢复需显式点「刷新来源」。
- 离线快照回落没有提示文案 → `errors` 补充「下载已锁定，点『刷新来源』恢复在线」。
- `/api/files` 的 `total` 返回的是 `limit` 截断后的条数，节点超过 200 份时界面把「共 826 份」错显示成「共 200 份」 → `catalog.query(..., with_total=True)` 返回匹配总数，`/api/files` 增加 `total / shown / truncated`，截断时界面明确提示「当前显示前 N 份，可继续下钻缩小范围」。
- 离线原因与「下载已锁定、点刷新来源恢复」只在点刷新时闪一次 toast，用户平时看不到 → 侧栏来源区常驻醒目警告条，实时展示 `source.errors[0]`。

### 文档

- 根目录 `README.md`、`docs/RELEASE.md`、`docs/VERIFICATION.md` 补齐新文档入口、验收导读与掉线状态说明。

## [v1.0.0] - 2026-11-06

首次交付，标签 `v1.0.0`，提交 `52d728a`（实现）+ `ce184cf`（存档文档）。

### 新增

- 新建统一资源库 `桌面/资源管理/`，同时是一个独立 Obsidian 新库，不影响原有资料库。
- QQ 群文件只读接入：NapCat OneBot 11 递归遍历三群目录，实时 1641 条 / 去重 1625 条 / 12.73 GB，刷新阶段不下载任何文件内容。
- 三级分类体系 `领域 → 科目/主题 → 资源类型 → 单文件`，7 个领域、17 个科目，规则数据化在 `config.json`。
- `catalog.json` 单一事实源；未下载条目也建索引，使 AI 能基于「已授权可见但尚未下载」的元数据回答。
- 可视化界面：三栏布局、逐级下钻面包屑、单文件预览、状态徽标、全局搜索、AI 对话面板、设置页。
- 三种下载方式（点击 / 多选 / 整类）统一走确认闸门；整类需输入节点名二次确认；单批上限 30 个文件。
- 自动入库流水线：正文抽取 → 抽取式摘要 → 预览笔记 → 原文件分类存放 → 重建 FTS5 与全部大纲。
- 多级大纲：总览、全量大纲、每层级 MOC 共 208 页，每篇已下载文件一篇预览笔记，均可在 Obsidian 内点击下钻。
- AI 助手：可配置本机 Bonsai2 27B 或任意 OpenAI 兼容外部 API；配置页含连接测试；密钥只存 `state/secrets.json`。
- grounded 防臆造：检索闸门、元数据/正文数据等级标注、目录确定性统计问答、未命中不调用模型、源索引由检索给出。
- Obsidian 插件 `resource-manager-ai`：右侧栏「资源 AI 搜索」，简短回答 + 可点击源文件索引。
- 离线降级：QQ 不可用时自动使用元数据快照并锁定下载；模型不可用时降级为本地摘录式回答。
- 微信能力评估与限制声明：`lib/wechat.py` 保留默认关闭的本地授权目录只读适配器，不读聊天数据库。

### 修复

- 口语「真题」未匹配类型标签、统计答案暴露内部字段名 → 类型别名匹配 + 中文标签输出。
- 已下载正文只截前 400 字导致答案落在后半段时被漏答 → 改为按命中词定位的上下文窗口，预算提到 4200 字符。
- 无答案的选择题资料被模型按常识推断出结论 → 提示词硬约束「只有题目与选项时必须说明未给答案」。
- 强制离线快照但 QQ 恰在线时可能用旧 `file_id` 下载 → 服务端前置拒绝 `mode == "snapshot"` 的下载请求。
- 跨群同名文件覆盖 → 资源与笔记文件名追加 6 位条目 id。
- 离线快照回落时补充提示文案（后续 v1.0.1 又补了运行中实时探活）。

### 变更

- 运行时改用纯标准库（无 flask / requests / yaml 依赖），配置用 JSON，前端零构建。
- 配置中的库路径留空时自动取 `Path.home()/Desktop/资源管理`，避免仓库硬编码机器路径。
- `state/`、密钥、下载资料全部由 `.gitignore` 排除，不进入 GitHub 仓库。

### 文档

- `docs/DESIGN.md`：交付顺序第 1 步的设计说明（流程、模块、数据流、界面交互、权限与降级）。
- `docs/ARCHITECTURE.md`：分层架构、15 条技术决策、核心链路、可移植性与安全边界。
- `docs/VERIFICATION.md`：端到端逐项验证结果、耗时、发现并修复的问题、已知限制。
- `docs/RELEASE.md`：v1.0.0 存档说明与逐项验收清单。
- `docs/PUSH.md`：GitHub 仓库、推送约定与敏感文件排除规则。

### 已知限制

- 个人微信无法接入；企业微信需另行企业管理员授权。
- 未下载文件只有元数据，无正文摘要；要内容必须先显式确认下载。
- 扫描版 PDF / 老格式 Office / zip 只登记元数据。
- 浏览器 GUI 未做自动化点击验证，建议人工目视确认。
- 本地 Bonsai2 常驻显存约 7.3 GB；未启动时 AI 自动降级。
- QQ 登录态过期时需用户扫码，再点「刷新来源」恢复在线下载。
