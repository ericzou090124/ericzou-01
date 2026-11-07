# 存档说明与版本记录

> 仓库：`https://github.com/ericzou090124/ericzou-01.git` · 分支 `main`
> 标签：`v1.0.0` ~ `v3.0.0`，另有 4 个历史补丁标签 `v1.3.0-p1` ~ `v1.6.0-p1`
> 最近更新：2026-11-07 · 状态：代码、文档、全部标签与 GitHub Releases 已同步

---

## 1. 这次交付了什么

一个完整闭环的本地「资源管理」程序：**QQ / 微信群文件只读盘点 → 三级自动分类 → 可视化逐级下钻 / 预览 → 显式确认下载 → 自动入库、摘要、多级大纲 → Obsidian 新库 + AI 检索问答**。

- **统一资源库**：`桌面/资源管理/`（新建独立 Obsidian 库，原有库不动）
- **界面**：`http://127.0.0.1:8787`，双击 `start.bat` 或安装器启动
- **QQ 接入**：本机 NapCat OneBot 11，三群实时遍历 1641 条，去重后 **1625 条 / 12.73 GB**
- **微信接入**：v1.5.0 起集成 GitHub 成熟方案 **WeChatFerry** 的监听式采集（默认关闭、指定群白名单、绝不读加密库）；v1.9.0 加固为「清单为空拒绝启动」
- **质量保障**：18 项回归自测 + `tools/test_v3.py` 真实 HTTP 服务 37 项端到端自测 + 全版本可用性审计（`docs/VERSION_AUDIT.md`）+ **`tools/verify_release.py` 发行前端到端验证**（真实 cmd 执行安装器、起真实 HTTP 服务打 API/静态资源、校验 SHA256 与数据零污染）
- **v3.0.0 实测修复**：QQ 二维码改为本页直出并可直接刷新（删掉跑不通的 NapCat 控制台入口、修复 `webui.json` 的 `host=::`）、`install.bat` 真正完成 NapCat 安装自检与配置修复、分类不再漏项（「高等代数」1→124 条，1625 条不丢）、补齐微信登录与群文件采集可视化入口。详见 [CHANGELOG.md](CHANGELOG.md) 与 [FEATURES.md](FEATURES.md) 的 v3.0.0 章节。
- **v2.9.1 紧急修复**：v2.9.0 的一键安装器因 cmd 解析带中文的长 PowerShell 命令而解压失败（报 `'-ExecutionPolicy' is not recognized`），已改用 `-EncodedCommand` 纯 ASCII 命令行，并补上「标记占位符未替换」的隐藏缺陷。**已下载过 v2.9.0 安装器的用户请重新从 latest 直链下载一次**。
- **📥 从哪里下载**：打开 [最新版 Release](https://github.com/ericzou090124/ericzou-01/releases/latest) 底部 **Assets** 区 → `resource-manager-installer.bat`（**双击即用**，小白首选）或 `resource-manager-full.zip`（**仓库全部内容**：源码 + 全部文档 + 安装器 + 教程），另有 `SHA256SUMS.txt` 可校验。两个直链文件名固定，永远指向最新版。**全部 Releases 正文均附同一套下载入口与安装闭环**；零基础图文教程见 [INSTALL.md](INSTALL.md)。

> 早期版本（v1.2.x 及以前）的存档说明里写「微信不可复现、只做限制说明」。该结论**已在 v1.5.0 被推翻**——通过 WeChatFerry 监听式方案实现了授权范围内的微信群文件采集。限制仍在（不能列全目录、不能读加密库、不能补历史文件），但能力已从「无」变为「可选可用」。详见 [FEATURES.md](FEATURES.md)。

---

## 2. 仓库导读

| 想看什么 | 读哪个文件 |
| --- | --- |
| 项目主页（能力表、架构图、快速开始、API、FAQ） | 根目录 `README.md` |
| **微信群文件监听采集 / 群文件三级分类详解** | `docs/FEATURES.md` |
| **全版本可用性审计结果与补丁标签** | `docs/VERSION_AUDIT.md` |
| 文档总索引与建议阅读顺序 | `docs/README.md` |
| 整体流程 / 模块划分 / 数据流 / 界面交互 / 权限方案 | `docs/DESIGN.md` |
| 分层架构、技术决策、核心链路伪代码 | `docs/ARCHITECTURE.md` |
| 项目通读式说明文字（背景、防臆造、隐私） | `docs/GUIDE.md` |
| **按时间顺序的开发者日志**（15 轮迭代、决策、故障与修复） | `docs/DEVLOG.md` |
| **逐版本更新日志** | `docs/CHANGELOG.md` |
| 系统审查、性能瓶颈排序与优化路线图 | `docs/REVIEW.md` |
| 本地试跑逐项结果、耗时、已知限制 | `docs/VERIFICATION.md` |
| 本页：存档清单、验收清单、全版本记录 | `docs/RELEASE.md` |
| GitHub 仓库地址、提交约定、敏感文件排除规则 | `docs/PUSH.md` |

代码导读：

```
server.py                 所有 API 入口（先读这个）
lib/catalog.py            唯一事实源 catalog.json / 分类树 / 查询
lib/classify.py           三级分类规则（领域→科目→类型）
lib/download.py           下载闸门 + 并发/重试 + 增量入库
lib/vault.py              Obsidian 大纲 / 笔记生成
lib/index.py              FTS5 索引 + 增量同步 + 维护
lib/ai.py                 grounded 问答与防臆造闸门
lib/qq.py                 QQ OneBot 只读 / 下载
lib/wechat_wcf.py         微信群文件监听采集（WeChatFerry）
lib/wechat.py             微信限制声明
lib/config_validate.py    启动期配置自检
lib/llm.py                本地模型 / 外部 API 抽象
lib/extract.py            正文抽取与摘要
web/                      零构建可视化界面
obsidian_plugin/          Obsidian 右侧栏 AI 搜索插件
tools/                    自测 / 审计 / 基准 / 安装器 / 登录工具
```

---

## 3. 验收清单

### 3.1 基础闭环

- [ ] `python server.py` 或双击 `start.bat` 能启动，`/api/health` 返回 `ok=true`
- [ ] 浏览器打开 `http://127.0.0.1:8787` 出现三栏界面
- [ ] 点击 `学习 → 高等数学 → 试卷与解析` 能逐级下钻，面包屑可回退
- [ ] 点「预览」能看到元数据；未下载条目明确写「仅元数据，未下载，无正文摘要」
- [ ] 勾选文件 → 下载已选 → 确认弹窗 → 原文件与笔记出现在 `资源管理/资源/`、`资源管理/笔记/`
- [ ] 整类下载需原样输入节点名，输错会被拒绝
- [ ] 未确认 / 空 ids / 离线快照三种情况下载被服务端拒绝
- [ ] 提问「有哪些高数真题还没下载？」→ 返回份数、体积、代表文件名，并标注仅元数据
- [ ] 提问「量子纠缠超导材料制备工艺」→ 如实返回未命中，无来源
- [ ] 「设置」里能切本地模型 / 外部 API，能测试连接；密钥不回显
- [ ] Obsidian 打开 `桌面/资源管理/` 作为新库，右侧栏出现「资源 AI 搜索」
- [ ] 二维码登录、过期自动换新、免扫码快速登录、扫码后自动恢复在线

### 3.2 新增功能（v1.5.0 起）

- [ ] 未安装 `wcferry` 时 `/api/wechat/wcf/status` 给出明确指引，其余功能不受影响
- [ ] `sources.wechat.wcf.enabled=false`（默认）时无法启动捕获
- [ ] 开启并登录后 `GET /api/wechat/wcf/rooms` 能列出 `@chatroom` 群
- [ ] `POST /api/wechat/wcf/rooms/save` 保存清单到 `state/wechat_rooms.json`，重启后仍在
- [ ] **清单为空时 `capture/start` 被拒绝**（不会监听全部群）
- [ ] 指定群内发送文件 → 5 秒内并入目录，索引与 Obsidian 大纲增量更新
- [ ] 非白名单群 / 非文件类消息不产生条目
- [ ] 三级分类结果符合 `docs/FEATURES.md` 的实测样例表
- [ ] `C语言程序设计上机指南.txt` 归到「学习」而非「生活与办事」（v2.8.0 修复）

### 3.3 运维与回溯

- [ ] `python tools/smoke_test.py` → `ALL PASS`（16 项）
- [ ] `python tools/version_audit.py` → 退出码 0，无「未修复失败」
- [ ] 点界面「系统诊断」能看到配置状态、错误/提醒、索引篇数
- [ ] `git tag --list` 含全部版本与 4 个 `-p1` 补丁标签
- [ ] GitHub Releases 覆盖全部主要版本
- [ ] 仓库 `main` 不含 `state/`、密钥、下载的群资料

---

## 4. 全版本记录

| 版本 | 内容 |
| --- | --- |
| `v1.0.0` | 首次交付：QQ 只读盘点、三级分类、可视化下载、自动入库与大纲、FTS5、grounded AI、Obsidian 插件、微信限制评估、设计与验证文档 |
| `v1.0.1` | 补充 DEVLOG / GUIDE / CHANGELOG / 文档索引；修复 QQ 运行中途掉线时状态显示与下载锁定 |
| `v1.1.0` | QQ 网页一键登录：实时二维码、过期自动换新、免扫码快速登录、扫码后自动恢复在线 |
| `v1.2.0` | 零配置新手：首次配置向导、一键安装脚本、纯图文《新手上手指南》、根目录 `新手必读.txt` |
| `v1.2.1` | 修复压缩包 `install.bat` 中文乱码：三个 .bat 改纯 ASCII 启动器，中文提示移入 Python 助手 |
| `v1.2.2` | 修复登录页「无法连接 NapCat WebUI」：按错误性质给可操作指引 + 新增「启动 NapCat」按钮与后端拉起工具 |
| `v1.2.3` | 修复 `install.bat` 双击闪退与扫码后主界面加载失败；`find_root` 改有界爬祖先 |
| `v1.3.0` | 仓库基线 + 系统审查 `REVIEW.md`（瓶颈排序与优化路线图）+ 自解压安装器 |
| `v1.4.0` | 检索精度与运行期开销优化（可选 jieba 中文分词、线程级只读连接缓存） |
| `v1.5.0` | **GitHub WeChatFerry 监听式微信适配器**：指定群文件消息采集、状态/启停端点、5 秒防抖入库 |
| `v1.6.0` | 索引增量同步 `index.sync()` + 回归自测 `smoke_test.py` + README/DEVLOG 文档补全 |
| `v1.7.0` | 修复空问题 `NameError`（`scope=f` 在定义前引用）；LLM 代理策略修正（本地直连 / 外部走代理）+ 超时重试 + 答案长度回归 |
| `v1.8.0` | 刷新来源改用 `index.sync()` 增量同步 |
| `v1.9.0` | 微信监听群清单持久化 + 群发现/保存端点；**清单为空拒绝启动**，不再监听全部群 |
| `v2.0.0` | 前端统一搜索框 + 命中高亮（先转义防 XSS）+「问 AI」按钮 |
| `v2.1.0` | 索引维护 `optimize()` / `db_size()` + `sync` 两阶段指纹加速 + `bench.py` 基准 + `POST /api/maintain` |
| `v2.2.0` | 下载后 `rebuild`→`sync`（修掉每批全量重建）+ 单批并发下载 + `precheck` 一次性 id 映射 |
| `v2.3.0` | 修复问答退化路径（FTS miss 时 corpus 为空）误报「未找到」；修复测试污染真实 catalog 的副作用 |
| `v2.4.0` | 启动期配置自检 `config_validate.py` + `GET /api/diagnose` 诊断端点 |
| `v2.5.0` | 下载失败重试 + 指数退避（`RM_DOWNLOAD_RETRIES`），永久「已失效」不重试 |
| `v2.6.0` | 前端「系统诊断」面板，闭环诊断端点 |
| `v2.7.0` | HTTP 集成自测：隔离起真实服务打 5 个核心端点，锁定 API 契约 |
| `v2.8.0` | 主页重写（工程化 README）、全版本可用性审计工具与报告、历史补丁标签、分类词库泛化词修复、功能详解文档、仓库描述与 Releases 治理 |
| `v1.3.0-p1` ~ `v1.6.0-p1` | 历史补丁标签：仅含空问题 NameError 最小修复，原 tag 保持不动 |

> 全部版本的可用性检测结果见 [VERSION_AUDIT.md](VERSION_AUDIT.md)。审计发现 `v1.3.0` ~ `v1.6.0` 存在空问题 `NameError`（v1.7.0 已修），为保留历史原貌不改写原 tag，改由 `tools/fix_legacy_tag.py` 生成 `-p1` 补丁标签。

---

## 5. 给第一次使用的人

1. **双击 `resource-manager-installer.bat`**（或克隆源码后 `python server.py`）。安装器自解压并自动启动服务，浏览器打开 `http://127.0.0.1:8787`。
2. 第一次打开会弹出「首次配置」横幅：按向导装好 NapCat（QQ 机器人，必需）并扫码登录 → 勾选或填写 QQ 群 → 保存。
3. 向导完成后自动跳回主界面，即可浏览、搜索、预览、下载群文件。
4. 若主界面显示「离线快照」，点「刷新来源」或登录页的「启动 NapCat」按钮。

压缩包里的 `新手必读.txt` 与 `docs/新手上手指南.md` 是同一份引导。详细图文步骤见 `docs/新手上手指南.md`。

---

## 6. 已知限制

1. **微信群文件**只能监听开启捕获之后的新消息，不能列出云端群文件全目录、不能补采历史文件、不能读加密聊天库；微信 4.x 不在 WeChatFerry 支持范围内。详见 `FEATURES.md`。
2. 未下载文件只有元数据，没有正文摘要；要内容必须先显式确认下载。
3. 整类下载单批上限 30 个文件；超出需再次确认。
4. 扫描版 PDF / 老格式 Office / zip 只登记元数据，无正文（可选 `pymupdf` 提升 PDF 抽取率）。
5. 三级分类基于文件名与文件夹名的关键词打分，无法理解语义；跨领域通用词需人工从词库剔除（v2.8.0 已修 `指南` 等泛化词）。
6. 浏览器 GUI 未做自动化点击验证，以 HTTP / API / 集成自测为主，建议人工目视确认一次。
7. 本地 Bonsai2 常驻显存约 7.3 GB；模型未启动时 AI 自动降级为纯本地检索。
8. `v1.3.0` ~ `v1.6.0` 原 tag 保留已知空问题缺陷（历史回溯用），需要可用版本请检出对应 `-p1` 标签。
