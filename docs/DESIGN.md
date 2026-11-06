# 资源管理程序 · 设计说明

> 交付顺序第 1 步产物：整体实现流程、模块划分、数据流、界面交互、权限与降级方案。
> 版本 1.0 · 2026-11-06

## 0. 目标

在本地新建 `桌面/资源管理/` 作为统一资源库（同时是一个**新建的、独立的 Obsidian 库**），把 QQ 群文件等授权来源的资料统一下载到该目录并自动分类；生成可逐级下钻的多级大纲（如 `学习 > 高等数学 > 单文件预览`）；提供可视化界面支持点击下载、多选下载、整类一键下载；提供可配置「外部 API / 本地模型」的 AI 助手，能基于**已授权可见但尚未下载**的元数据回答，查不到时如实说明且不臆造。

## 1. 环境评估结论（决定实现边界）

| 项目 | 实测结果 | 结论 |
| --- | --- | --- |
| QQ | 本机 NapCat OneBot 11 HTTP `127.0.0.1:3000`，令牌从 `%LOCALAPPDATA%\OmniQQ-MCP\...\onebot11_*.json` 读取；`/get_group_root_files` + `/get_group_files_by_folder` 可递归只读遍历；三个群共 1625 个文件 / 12.73 GB，快照 `qqfiles.json` 可用 | ✅ 可完整接入 |
| 微信 | 本机运行微信 4.x `Weixin.exe`；无 OneBot/Bot 协议端、无个人微信开放 API；`db_storage/*.db` 为加密库，聊天/群归属不可读也不应读；`msg/file/` 下 378 个文件是**已落地本地**的明文文件，只有文件名/大小/月份，看不到云端未下载文件、群归属、发送者 | ❌ **不可复现 QQ MCP 登录与接入流程** |
| 企业微信 | 连接器市场有 `wecom` / `微盛企微管家SCRM`，但需企业管理员 corpid/secret 与可见范围授权，且是企业微信生态，不提供个人微信群文件 | ⚠️ 属「等账号」预留适配器，本期不实现 |
| GitHub | 网络可达（`git ls-remote` 成功）；无 `gh` CLI、无 git 凭证 / SSH key；`git config` 仅有 `ericzou090124 <ericzou375@gmail.com>` | ⚠️ 推送需用户补充仓库地址与授权 |

**微信明确限制**：无法列出云端未下载群文件、无法获取群/发送者归属、无法读取聊天记录；只能（在用户显式授权指定目录后）只读扫描本地已落地文件。按需求「不可行则明确限制，并仅先完成 QQ 导入的完整可视化界面」，本期微信在界面上显示为「未接入 · 限制说明」，只保留 `WeChatLocalSource` 适配器接口（默认关闭），不实现微信界面、不读取任何聊天数据库。

## 2. 目录与仓库结构

```
resource-manager/                       ← 程序 / Git 仓库根
├── config.json                        全局配置（路径、来源、分类规则、AI 默认参数）
├── server.py                          stdlib HTTP 服务（仅 127.0.0.1:8787）
├── lib/
│   ├── config.py       配置与路径解析
│   ├── qq.py           QQ OneBot 只读遍历 + 定向下载
│   ├── wechat.py       微信限制声明 + 预留本地授权目录适配器
│   ├── classify.py     三级分类：领域 / 科目主题 / 资源类型
│   ├── catalog.py      catalog.json 单一事实源 + 树形查询
│   ├── extract.py      零依赖正文抽取 + 摘要
│   ├── download.py     下载确认闸门与队列
│   ├── vault.py         Obsidian 库：多级大纲 / 笔记 / 插件部署
│   ├── index.py        SQLite FTS5（元数据 + 正文）
│   ├── llm.py          本地模型 / 外部 API 抽象
│   └── ai.py           grounded QA 与命中闸门
├── web/                index.html / app.js / style.css（零构建）
├── obsidian_plugin/    manifest.json / main.js / styles.css
├── tools/bootstrap.py  从 QQ 快照初始化目录
├── docs/               DESIGN.md / ARCHITECTURE.md / VERIFICATION.md
├── state/              catalog.json / index.db / secrets.json（gitignore）
├── start.bat           一键启动
└── README.md
```

```
桌面/资源管理/                         ← 统一资源库 = 独立 Obsidian 新库
├── .obsidian/          plugins/resource-manager-ai + community-plugins.json
├── 00-资源总览.md       一级大纲（来源 / 领域 / 统计）
├── 00-多级大纲.md       全量逐级大纲（wikilink 下钻）
├── 00-使用说明.md
├── 大纲/                每个领域、每个科目、每个类型各一页 MOC
├── 资源/<来源>/<领域>/<科目>/<类型>/   下载后的原文件（保持分类）
├── 笔记/<来源>/<领域>/<科目>/<类型>/   每个文件一篇预览笔记
└── _system/            状态与索引（Obsidian 不索引）
```

## 3. 模块划分与职责

| 模块 | 职责 | 关键约束 |
| --- | --- | --- |
| M1 配置与权限 | `config.json`、来源白名单、路径、secrets 本地化 | API Key 只写 `state/secrets.json`，不进仓库 |
| M2 数据源适配 | `QQSource.refresh()` 只读元数据；`WeChatSource` 限制声明；`LocalSource` 预留 | 任何 source 都不得在 refresh 阶段写文件内容 |
| M3 统一目录与分级 | `catalog.json` 唯一事实源，每条含 `id/source/group/path/name/size/domain/subject/kind/downloaded/note/asset/summary` | 未下载也建条目，`downloaded=false` |
| M4 下载闸门 | 单个 / 多选 / 整类统一走 `POST /api/download` | 必须显式 ids + `confirm:true`；整类额外要求 `scope=category` 与 `confirmText` 等于节点名；离线快照时拒绝 |
| M5 入库与索引 | 抽正文 → 摘要 → 写预览笔记 → 重建多级大纲 → 刷新 FTS5 | 不移动/不删除源文件；只删带生成标记的笔记 |
| M6 Web UI / API | 三栏单页 + stdlib HTTP，仅绑定 loopback | 所有写操作共用同一闸门 |
| M7 AI 助手 | provider = `local`(Bonsai2) / `openai_compatible`；Obsidian 插件 | 命中判定与源索引由检索给出，未命中直接如实回答且不调模型 |

## 4. 数据流

```
[只读] QQ OneBot ─┐
[限制] 微信 ──────┼→ refresh() → qq_manifest.json（元数据快照）
[预留] 本地目录 ─┘                    │
                                      ▼
                         classify() → catalog.json（全量条目，含未下载）
                                      │
        ┌─────────────────────────────┼──────────────────────────────┐
        ▼                             ▼                              ▼
   Web 树形大纲                AI 元数据检索                 显式确认下载
   （逐级下钻）              （仅元数据，明确标注）                  │
                                                                      ▼
                                        取直链 → 资源/<分类>/ → 抽取正文
                                                                      ▼
                          摘要 + 预览笔记 + 多级大纲重建 + FTS5 索引
                                                                      ▼
                              Web 单文件预览 / Obsidian 笔记 / AI 正文检索
```

**AI 双池检索**：`pool=metadata`（所有授权可见条目，无论是否下载）与 `pool=body`（已下载文件正文）。上下文里逐条注明 `【已下载·含正文】` 或 `【仅元数据·未下载·无正文】`。模型提示词禁止把元数据推断成文件内容；回答里对未下载条目必须写明「仅元数据，未下载，无正文摘要」。

## 5. 界面交互

- 顶栏：全局搜索（同时查元数据与正文）、AI 助手开关、设置、来源状态。
- 左栏：**授权来源**（QQ 在线 / 离线快照、微信未接入）、**分类大纲树**（领域 → 科目 → 类型），点击节点逐级下钻；另有「按来源浏览」切换视图。
- 中栏：面包屑 + 当前层级的下一级节点卡片 + 文件列表。每行含勾选框、名称、状态徽标（已下载 / 仅元数据）、体积、摘要片段、预览按钮。
- 右栏：单文件预览抽屉（元数据、摘要、正文片段、原文路径、下载按钮、在 Obsidian 打开）+ AI 对话区。
- 下载交互：
  1. **点击下载**：单文件预览里「下载此文件」→ 确认弹窗。
  2. **多选下载**：勾选多行 → 「下载已选 N 项」→ 弹窗列出数量与总体积 → 确认。
  3. **整类一键下载**：当前节点「下载本类 N 项」→ 弹窗要求输入节点名做二次确认 → 确认。
  所有路径最终调用同一个 `POST /api/download`，服务端重复校验闸门；下载进度以任务形式返回。
- 设置页：AI provider（本地 Bonsai2 / OpenAI 兼容 API）、base_url、model、api_key、关闭思考模式、测试连接。

## 6. 权限与降级方案

| 场景 | 行为 |
| --- | --- |
| QQ 接口在线 | 只读遍历元数据；`file_id` 只在服务端内存/状态里，不下发前端 |
| QQ 接口 502 / 重启 | 自动回落到 `state/qq_manifest.json` 离线快照，界面标注「离线快照」；**下载按钮禁用**并提示先刷新 |
| NapCat `file_id` 失效 | 下载失败时提示重新 `refresh`，不自动重试放大范围 |
| 微信 | 界面明确「未接入」+ 限制说明卡；预留 `WeChatLocalSource`，仅在用户显式填写授权本地目录并开启后，只读扫描文件名/大小/时间，**不读聊天库、不猜群归属** |
| 未下载内容问答 | 只能基于元数据回答「有哪些 / 在哪 / 多大 / 属于哪类」，答案标注数据等级；不得生成内容摘要或推测正文 |
| 本地模型不可用 | 自动降级为抽取式回答（原文摘录 / 元数据清单），仍返回源文件索引 |
| 外部 API 未配置 / 超时 | 同上降级；密钥错误只提示「认证失败」，不回显密钥 |
| 不相关的问题 | 检索闸门判定命中不足 → 直接返回「授权可见的资料中没有检索到相关信息」，不调用模型 |
| 下载范围 | 未带显式 ids 与 `confirm:true` 一律拒绝；整类下载另需节点名二次确认；程序从不主动扩大到全量 |
| AI 服务 | 仅监听 `127.0.0.1`；无 CORS 通配开放；不上传任何资料到外部（除非用户主动配置外部 API，此时仅发送命中片段） |
| GitHub | 无凭证不臆造推送；交付本地 git 仓库 + 一键推送脚本，凭证由用户提供 |

## 7. 技术选型

- **零第三方运行时依赖**：Python 3.13 标准库（`http.server` / `sqlite3` FTS5 / `urllib` / `zipfile` / `xml.etree`）；配置用 JSON 而非 YAML。PyMuPDF 可选（缺失时 PDF 降级为仅文件名可检索）。
- **零前端构建**：原生 HTML/CSS/JS，直接由本地服务托管。
- **Obsidian 插件**：CommonJS 单文件，读取本地服务 `/api/ask`，渲染简短回答与可点击源文件索引。
- **模型**：默认本机 Bonsai2 `http://127.0.0.1:8080/v1`，通过 `chat_template_kwargs: {"enable_thinking": False}` 关思考（否则单问 51–325 秒，关闭后 2–4 秒）；外部 API 走同一 OpenAI 兼容协议。
