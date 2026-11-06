# 资源管理 · QQ 群文件 → Obsidian 可视化知识库闭环

把「授权只读盘点 → 统一分类目录 → 显式确认下载 → 自动入库 / 摘要 / 多级大纲 → 可视化界面 + Obsidian AI 检索」串成一个本地闭环程序。

- **统一资源库**：`桌面/资源管理/`，同时是一个**新建的独立 Obsidian 库**（不修改原有任何库）。
- **QQ 接入**：本机 NapCat OneBot 11 HTTP 接口，递归只读遍历群文件目录；未获确认前**不下载任何文件**。
- **微信**：评估后确认**不能复现 QQ MCP 的登录/接入流程**，本期只做限制说明与预留适配器，详见下方「微信接入评估」。
- **零第三方运行时依赖**：Python 3.13 标准库 + SQLite FTS5 + 原生 HTML/CSS/JS；PyMuPDF 可选。
- **AI**：可配本机 Bonsai2 27B 或任意 OpenAI 兼容外部 API；可基于**已授权可见但尚未下载**的元数据回答，查不到如实说明、不臆造。

---

## 快速开始

```bash
cd resource-manager
python tools/bootstrap.py      # 可选：先用已有清单离线初始化（元数据库 + 大纲）
python server.py              # 或双击 start.bat
```

浏览器打开 `http://127.0.0.1:8787`。服务只监听 `127.0.0.1`。
Obsidian 里用「打开文件夹作为库」选择 `桌面/资源管理/`，右侧栏「资源 AI 搜索」即可提问。

> 本机 Bonsai2 模型（可选）：`http://127.0.0.1:8080/v1`，model `ternary-bonsai-2-27b`。
> 必须保持「关闭思考模式」开启，否则单问可达 51–325 秒；关闭后约 2–4 秒。
> 模型没起时 AI 会自动降级到纯本地检索/摘录，仍返回源文件索引。

## 界面怎么用

1. **逐级下钻**：左栏「分类大纲」或中间卡片，按 `领域 → 科目/主题 → 资源类型` 逐层点击；面包屑可回退。可切换「按来源」维度浏览（来源 → 群 → 群内目录）。
2. **单文件预览**：点「预览」，右栏显示元数据、摘要、正文片段、原文件路径；未下载条目明确写「仅元数据，未下载，无正文摘要」。
3. **点击下载**：预览面板「下载此文件」→ 确认弹窗。
4. **多选下载**：勾选多行 → 「下载已选」→ 弹窗列出数量与体积 → 确认。
5. **整类一键下载**：当前节点「整类下载」→ 需**原样输入节点名称**做二次确认。
   三种方式最终都走同一个 `POST /api/download` 闸门，服务端会重复校验；单批上限默认 30 个文件。
6. **AI 助手**：直接口语化提问，回答下方是**可点击的源文件索引**（点开即预览）。「设置」里切换本地模型 / 外部 API，可测试连接。

## 权限与降级（写死在代码里）

| 场景 | 行为 |
| --- | --- |
| 刷新来源 | 只读元数据，`file_id` 只留在服务端状态里，**不下发前端** |
| 未确认下载 | `confirm != true` / `ids` 为空 / 整类 `confirmText` 不匹配 → 一律拒绝 |
| 离线快照 | 界面标注「离线快照」，**下载接口直接拒绝**；只能预览元数据与大纲 |
| NapCat 502 / `file_id` 失效 | 提示重新「刷新来源」，不自动重试放大范围 |
| 未下载内容问答 | 只能基于文件名、路径、分类、体积回答「有哪些 / 在哪 / 多大 / 多少份」，答案明确标注「仅元数据，未下载，无正文摘要」 |
| 只有题目没有答案的资料 | 提示词强制模型回答「资料只给出题目与选项，未给答案」，禁止用常识推断 |
| 不相关问题 | 检索闸门判定命中不足 → 直接返回「授权可见的资料中没有检索到相关信息」，**不调用模型** |
| 本地模型不可用 / 外部 API 超时 | 自动降级为本地摘录式回答，源索引不变；密钥错误只提示认证失败，不回显密钥 |
| 密钥存放 | 外部 API Key 只写 `state/secrets.json`，`.gitignore` 排除，不进仓库 |
| 文件安全 | 不移动、不删除、不重命名任何源文件；重建笔记只覆盖带生成标记的 `.md` |

## 微信接入评估（2026-11-06 实测）

**结论：不可复现 QQ MCP 的登录与接入流程，本期只完成 QQ 导入的完整可视化界面。**

| 检查项 | 实测 |
| --- | --- |
| 客户端 | 微信 4.x `Weixin.exe` 在运行；本地数据目录 `Documents/xwechat_files/wxid_.../` |
| 协议端 | 无 OneBot / Bot 协议端；个人微信没有官方开放 API |
| 聊天库 | `db_storage/*.db` 为加密 SQLite，聊天内容与群归属不可读，程序也不读取 |
| 本地文件 | `msg/file/2026-07 … 2026-11` 共 378 个**已落地本地**的明文文件（225 pdf / 78 docx / 23 xlsx …），只有文件名、大小、月份 |
| 云端未下载 | **看不到**。无法列出云端群文件、无法预览未落地内容、无法获知群归属与发送者 |
| 企业微信 | 连接器市场有 `wecom` / `微盛企微管家SCRM`，但需企业管理员 corpid/secret 与可见范围授权，且是企业微信生态，不对等个人微信群文件 |

因此界面上微信显示「未接入」并可展开 6 条限制说明；`lib/wechat.py` 只保留 `WeChatLocalSource` 式适配器接口（默认关闭）：**只有在用户显式填写 `authorized_local_dir` 并开启后**，才只读扫描本地已落地文件的文件名/大小/时间，且明确不扫描聊天数据库、不猜测群归属。

## 目录结构

```
resource-manager/                      本仓库（程序）
├── config.json                       路径 / 来源 / 分类规则 / AI 默认参数
├── server.py                         stdlib HTTP 服务 + 全部 API
├── lib/
│   ├── config.py     配置、路径、settings/secrets
│   ├── qq.py         OneBot 只读遍历 + 定向下载
│   ├── wechat.py     限制声明 + 预留本地授权目录适配器
│   ├── classify.py   领域 / 科目 / 资源类型 三级分类
│   ├── catalog.py   catalog.json 单一事实源 + 树形查询
│   ├── extract.py    零依赖正文抽取 + 抽取式摘要
│   ├── download.py  下载确认闸门与入库
│   ├── vault.py      多级大纲 MOC / 预览笔记 / 插件部署
│   ├── index.py      FTS5（元数据 + 正文）
│   ├── llm.py        本地模型 / 外部 API 抽象
│   └── ai.py         grounded QA、目录统计问答、命中闸门
├── web/               index.html / app.js / style.css（零构建）
├── obsidian_plugin/   manifest.json / main.js / styles.css
├── tools/
│   ├── bootstrap.py          离线引导（导入已有元数据快照）
│   └── push_to_github.bat    推送到你的 GitHub 仓库
├── docs/
│   ├── DESIGN.md        实现流程 / 模块 / 数据流 / 交互 / 权限降级
│   ├── ARCHITECTURE.md  技术实现路线
│   └── VERIFICATION.md 本地试运行结果与已知问题
├── start.bat
└── state/            catalog.json / index.db / bodies/ / secrets.json（gitignore）
```

```
桌面/资源管理/                        统一资源库 = 独立 Obsidian 新库
├── .obsidian/plugins/resource-manager-ai/
├── 00-资源总览.md / 00-多级大纲.md / 00-使用说明.md
├── 大纲/       每个领域、每个科目、每个类型各一页 MOC
├── 资源/       原文件，按 来源/群/领域/科目/类型 分类存放
├── 笔记/       每个文件一篇预览笔记（frontmatter + 摘要 + 正文片段）
└── _system/
```

## 主要 API（仅 loopback）

| 端点 | 说明 |
| --- | --- |
| `GET /api/health` | 服务状态、文档数、QQ 在线状态 |
| `GET /api/state` | 来源状态、统计、微信限制、AI 设置 |
| `GET /api/tree?dim=classify&node=["学习"]` | 下一级节点与计数 |
| `GET /api/files?dim=&node=&q=` | 当前节点文件列表 |
| `GET /api/file?id=` | 单文件预览（元数据 / 摘要 / 正文片段 / 路径） |
| `POST /api/refresh` | 只读刷新元数据（`{"snapshot":true}` 强制离线快照） |
| `POST /api/download` | 下载闸门，需 `ids` + `confirm:true`；整类需 `confirmText` |
| `GET /api/ask?q=&fast=1` | AI 问答，返回 answer / found / sources / mode / took_ms |
| `GET|POST /api/settings` | 读取 / 保存 AI 配置（密钥不回显） |
| `POST /api/settings/test` | 测试模型接口连通性 |
| `POST /api/reindex` | 重建索引与全部大纲 |

## 文档

完整索引见 [docs/README.md](docs/README.md)。

- **验收入口 / 存档说明**：[docs/RELEASE.md](docs/RELEASE.md)（含逐项验收清单）
- **开发日志**：[docs/DEVLOG.md](docs/DEVLOG.md)（按时间顺序记录决策、故障与修复）
- **相关说明文字**：[docs/GUIDE.md](docs/GUIDE.md)（项目通读，解释为什么这样设计）
- **更新日志**：[docs/CHANGELOG.md](docs/CHANGELOG.md)
- 设计（交付顺序第 1 步）：[docs/DESIGN.md](docs/DESIGN.md)
- 技术实现路线：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 本地试运行结果与问题：[docs/VERIFICATION.md](docs/VERIFICATION.md)
- GitHub 仓库与提交约定：[docs/PUSH.md](docs/PUSH.md)

## 仓库

`https://github.com/ericzou090124/ericzou-01.git` · 分支 `main` · 存档标签 `v1.0.0`（首次交付）、`v1.0.1`（开发日志与说明文字）。
后续改动直接提交并推送到该仓库；`state/`（元数据、正文、密钥）与下载资料一律不入库。
