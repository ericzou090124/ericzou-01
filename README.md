# Resource Manager

**把 QQ / 微信群里散落的课程资料、合同单据与工作文件，整理成一个可检索、可问答的本地 Obsidian 知识库**

`群文件采集` · `内容驱动泛化分类` · `微信监听式收集` · `SQLite FTS5 全文检索` · `AI 防臆造问答` · `Obsidian 多级大纲` · `零第三方硬依赖`

[![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Deps](https://img.shields.io/badge/Deps-Zero_hard_dependency-00ADD8?style=flat-square)](requirements.txt)
[![Search](https://img.shields.io/badge/Search-SQLite_FTS5-003B57?style=flat-square&logo=sqlite&logoColor=white)](lib/index.py)
[![Vault](https://img.shields.io/badge/Vault-Obsidian-7C3AED?style=flat-square&logo=obsidian&logoColor=white)](lib/vault.py)
[![Privacy](https://img.shields.io/badge/Privacy-Local_only-2E8B57?style=flat-square)](#-安全与隐私)
[![Version](https://img.shields.io/badge/Version-v3.1.0-EA4AAA?style=flat-square)](docs/CHANGELOG.md)
[![License](https://img.shields.io/badge/License-MIT-2E8B57?style=flat-square)](LICENSE)

---

> [!TIP]
> **🚀 第一次来？3 分钟跑起来，完全不用命令行**
>
> ① [⬇️ 下载一键安装器（Windows，双击即用）](https://github.com/ericzou090124/ericzou-01/releases/latest/download/resource-manager-installer.bat) → ② **下载完直接双击它** → ③ 浏览器自动打开 `http://127.0.0.1:8787`，按页面「首次配置」向导点 3 下 → 完成。
>
> 想把仓库全部内容拿下来：[📦 完整内容包 ZIP](https://github.com/ericzou090124/ericzou-01/releases/latest/download/resource-manager-full.zip) · [全部 Releases](https://github.com/ericzou090124/ericzou-01/releases) · **[📖 零基础图文教程（下载 → 安装 → 配置 → 下载资料 → AI 问答 → Obsidian 完整闭环）](docs/INSTALL.md)**

> [!IMPORTANT]
> **这是一个纯本地、只读、授权范围受限的个人资料整理工具。**
> - 服务**只监听 `127.0.0.1`**，不对外暴露；所有资料、索引、密钥都留在本机。
> - 对 QQ / 微信云端**只读 / 只监听**，不修改群内任何内容，**绝不读取加密聊天数据库**。
> - 下载必须经过界面**显式确认**；未下载条目只有文件名与元数据，AI 不会推测其内容。
> - 微信能力依赖第三方 [WeChatFerry](https://github.com/lich0821/WeChatFerry)，**默认关闭**；使用前请自行确认符合平台规则与当地法律。

---

## 项目简介

课程资料散落在十几个 QQ 群、微信群的层级目录里：找一份「复变函数期末真题」要翻遍群文件，下下来又散在桌面各处，更没法按科目检索或针对内容提问。

**Resource Manager** 用一条完整闭环解决这件事：

> **来源盘点 → 自动分类 → 逐级下钻 → 确认下载 → 正文入库 → 全文索引 → Obsidian 大纲 → AI 检索问答**

- **零第三方硬依赖**：核心链路全部 Python 标准库（`http.server` + `sqlite3` FTS5 + `urllib`），克隆后**不用 `pip install` 就能跑**。
- **未下载也能检索**：所有条目先进目录与索引，AI 可以基于「可见的元数据」回答「有哪些 / 多少 / 哪些还没下载」，但明确标注「仅元数据，无正文摘要」，绝不把文件名当内容。
- **本地模型或外部 API 都行**：默认指向本机推理服务（Bonsai2，自动 `disable_thinking`），也可切任意 OpenAI 兼容接口；模型挂了自动降级为纯本地检索，不编造答案。
- **Obsidian 独立新库**：自动在桌面生成 `资源管理/` 独立 Obsidian 库（带多级大纲 MOC 与 AI 侧边栏插件），**不碰你原有的任何笔记库**。

实测数据：3 个 QQ 群、1641 条原始清单去重后 **1625 条 / 约 12.73 GB**，覆盖 9 个领域、29 个具体科目、12 个规范体裁、1441 个动态主题、794 个多归属主题标签。分类升级后**条目一条不少**（`catalog.verify_integrity()` 门禁）。

> **v3.1.0 起分类不再挑场景**：不是「学生群用校园目录、工作群用办公目录」两套硬编码，而是一套中性受控词表 + 动态主题提取。把工作群的合同、进货单、报销单、会议纪要、法务文件放进来，会分别落到对应体裁，不会全挤进「综合 / 其他资料」。详见 [内容驱动的泛化分类](#-内容驱动的泛化分类)。

---

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 📥 **QQ 群文件只读盘点** | 通过本机 NapCat（OneBot 11）`get_group_root_files` + `get_group_files_by_folder` **递归遍历全部目录**，只取元数据；接口掉线自动收紧为「离线快照」并锁定下载，恢复在线需用户显式点「刷新来源」 |
| 🧠 **群文件三级自动分类 + 多归属标签** | `领域 → 科目/主题 → 资源类型` 三层归类，词库全部在 `config.json`（8 领域 / 29 科目 / 8 类型 + 14 组相关主题别名）；关键词按长度加权避免泛词误判，另生成**多归属主题标签**，「按主题标签」视图里同一文件会在多个节点出现，**绝不藏文件**；详见 [群文件自动分类](#-群文件自动分类) |
| 🧬 **内容驱动的泛化分类（v3.1.0）** | **同一套中性受控词表服务所有场景**：21 个规范体裁 / 267 个同义词（合同、财务、采购、会议、方案、人事、客户、法务、课程、试题…），主题词从群内文件夹与文件名**动态提取**，模态按扩展名识别；不硬编码「学生用 A 目录 / 店主用 B 目录」；工作群资料实测 **12/12 落到具体体裁**，不会全进「其他资料」；顶部「分类体系」页可对照试跑（dry-run，只预览不写盘）+ 词表 CRUD；详见 [内容驱动的泛化分类](#-内容驱动的泛化分类) |
| 🔎 **别名召回，不再漏项** | 搜索词同时按 `classification.aliases` 与受控词表语义匹配展开：实测搜「高等代数」从旧版 **1 条 → 124 条**；`verify_integrity()` 保证条目数 / id / 标签 / 体裁 / 模态不缺失 |
| 💬 **微信群文件监听采集** | 基于 GitHub 成熟方案 **WeChatFerry** 的监听式适配器，只接收你**指定群**内的文件/附件消息，5 秒防抖并入目录；**界面顶部「微信」按钮直达登录/群清单/监听页面**，一键启用、安装、检测，不用手改配置；默认关闭、绝不读加密库；详见 [微信监听与收集](#-微信监听与收集) |
| 🔑 **QQ 登录本页闭环** | 二维码在资源管理器自己的页面直出、过期自动换新，「刷新二维码」会自动拉起未运行的 NapCat；**不需要打开任何 NapCat 控制台**，登录成功自动恢复在线来源 |
| 🛠️ **install 真的管 NapCat** | `install.bat` 内置 NapCat 安装自检：检测运行时 / 启动脚本 / WebUI / OneBot 配置，自动修复 `webui.json` 的 `host=::`（本机 127.0.0.1 拒绝连接的根因）并生成可回滚备份与 `state/napcat_setup.json` 报告；也可单独跑 `tools/setup_napcat.bat` |
| 🔍 **SQLite FTS5 全文检索** | trigram 分词 + 可选 `jieba` 中文分词；命中判定与答案生成**解耦**——模型只负责概括，不负责判断「有没有」；支持按当前浏览范围限定检索，避免「问高数却答复变」 |
| 🤖 **AI 防臆造问答** | 未命中直接如实回答、不调模型；「有哪些/多少/未下载」走目录确定性统计；已下载条目可概括正文，未下载条目强制标注「仅元数据」；来源索引可点击回跳 |
| 📚 **Obsidian 同步** | 自动生成 `00-资源总览`、全量多级大纲、每个层级一页 MOC、单文件预览笔记；所有生成笔记带 `NOTE_MARK`，重建时只删带标记的，**不碰手工笔记** |
| 🖥️ **零构建 Web 界面** | 三栏布局、分类树逐级下钻、全文搜索 + 命中高亮、类型筛选、单文件预览、AI 对话、系统诊断面板；原生 HTML/CSS/JS，无打包步骤 |
| 🔐 **下载确认闸门** | `confirm=true` + 显式 `ids` 才放行；整类下载需原样输入节点名；单批上限默认 30；离线快照拒绝下载；扩展名白名单校验；服务端二次校验，前端不可绕过 |
| ⚡ **增量索引与并发下载** | `index.sync()` 用「元数据指纹 + 正文 stat」两阶段比对，未变化条目完全跳过；下载单批内并发拉取、失败指数退避重试、`file_id` 失效不重试 |
| 🩺 **启动自检与诊断** | 启动时校验 `config.json`（群号/白名单/端口/AI 配置）并打印可读清单；`GET /api/diagnose` 与界面「系统诊断」按钮随时查看状态 |
| 📦 **双击即用的安装器** | `resource-manager-installer.bat` 自解压全程序（base64 内嵌），无需 Python 环境配置即可解压启动；新手向导 2 步完成 NapCat + 群号配置 |

---

## 🎯 群文件自动分类

群文件往往只有文件名和所在文件夹可用。分类器（`lib/classify.py`）按**可解释的加权打分**做三级归类，规则全部外置在 `config.json`，改词库不用改代码：

| 层级 | 取值来源 | 打分规则 |
| --- | --- | --- |
| **领域** `domain` | 8 个领域词库（学习 / 考试与复习 / 科研与论文 / 证书与竞赛 / 实习与就业 / 生活与办事 / 党团与校园 / 选课与培养） | `2 × 文件夹命中 + 1 × 文件名命中`，命中词按长度加权；均未命中时若已识别出科目或属于课件/习题/笔记，则兜底「学习」 |
| **科目** `subject` | 29 个科目词库（高等数学、线性代数、复变函数与积分变换、高等代数、数据结构、C语言程序设计、Fortran与工程计算…） | `3 × 文件夹命中 + 2 × 文件名命中`，科目全名出现额外加权，取最高分；无命中兜底「综合」 |
| **类型** `kind` | 8 类资源（试卷与解析 / 习题作业 / 课件资源 / 上课笔记 / 实验代码 / 指南说明 / 模板与表单 / 书单与推荐） | `2 × 文件夹命中 + 1 × 文件名命中`，取最高分；无命中兜底「其他资料」 |
| **主题标签** `tags` | **多值**：所有命中的科目 / 领域 / 类型 + 14 组相关主题别名 | 一份文件可落在多个标签节点下；`dim=tag` 可逐级下钻，计数之和 > 文件总数即代表多归属生效 |

**为什么文件夹权重更高？** 群里通常已按「考试与复习 / 课件 / 作业」分好目录，文件夹名比文件名更可信；文件名只用来在同目录内区分科目与具体类型。

**为什么不制造空类目？** v3.0.0 之前「高等代数」词库含泛词「多项式」，把一份无关的《第七章勒让德多项式》误判成高等代数，导致该科目全库只剩 1 条、搜索看起来像严重漏项。现在长关键词权重更高、科目全名额外加权，并去掉容易误伤的泛词；相关主题改用 `aliases` 做**召回扩展**而不是硬归类。实测「高等代数」搜索由 1 条提升到 124 条，1625 条目录一条不少。

<details>
<summary><b>分类结果如何被使用</b>（点击展开）</summary>

- **左侧分类树**：`GET /api/tree?dim=classify` 按 `领域 → 科目 → 类型` 逐级聚合，显示每层份数 / 已下载数 / 体积；`dim=source` 可切到 `来源 → 群 → 文件夹` 视角。
- **检索范围**：AI 问答会先识别问题里的科目 / 领域 / 类型，并与当前浏览路径合并成过滤器，**严格只在范围内检索**。
- **Obsidian 大纲**：`vault.build_outlines()` 按三级分类生成总览、全量大纲与每个节点一页 MOC。
- **结果幂等**：`catalog.upsert_manifest()` 每次刷新重新计算分类，但保留已有的 `downloaded / note / asset / summary` 状态。

</details>

> 词库可按自己的课程表调整：`config.json → classification` 的 `domains / subjects / kinds / aliases`。改完执行 `python tools/reclassify.py`（自动备份 + 四道完整性门禁）原地重算，或 `POST /api/reclassify`；`--dry-run` 可先预览。`tools/version_audit.py` 会拿代表性文件名回归验证分类词库是否失效。

---

## 🧬 内容驱动的泛化分类（v3.1.0）

上面那套三级词库是从**校园课程群**归纳出来的。如果用户换成一个工作群（合同、进货单、报销单、会议纪要、法务文件、客户报表），它会把所有东西判成「其他 / 综合 / 其他资料」——这是真实缺陷，不是理论风险。v3.1.0 增加了一层**与场景无关**的分类：

| 维度 | 字段 | 怎么来的 |
| --- | --- | --- |
| **规范体裁** `genre` | 21 个中性体裁：`合同与协议`、`财务与票据`、`采购与供应`、`会议与纪要`、`方案与规划`、`报告与总结`、`通知与公告`、`人事与行政`、`客户与销售`、`产品与需求`、`法务与合规`、`培训与资料`、`数据与报表`、`课程与教学`、`试题与考核`、`科研与文献`、`项目与任务`、`素材与媒体`、`代码与工程`、`生活与事务`、`参考资料`（长尾兜底） | 受控词表按别名长度加权打分；**只有一套词表，学生群 / 工作群 / 任何群共用** |
| **动态主题** `topics` | 1441 个（真实目录） | 从群内文件夹路径、文件名括号、已下载正文摘要**实时提取**；不预设主题表，所以「华南区客户」「智慧门店」「高等代数」都能成为主题 |
| **文件模态** `modality` | 文档 / 表格 / 演示 / 图片 / 音视频 / 压缩包 / 代码 | 只看扩展名，不读未下载文件的云端内容 |
| **依据与置信度** | `reason.matched` / `genre_scores` / `confidence` / `engine` | 规则层可解释；`llm_assist` 显式开启且非敏感件才调模型，失败静默回退规则层 |

**关键约束：分类逻辑是内容驱动的，代码里没有「学生用 A 目录 / 店主用 B 目录」的分支。** `detect_profile()` 只统计「校园 / 职场 / 通用」的分布用于界面展示，**从不参与分类**；`tools/test_taxonomy.py` 会把同一批工作群文件在校园资料前后各跑一遍，断言结果逐字节一致（无隐藏场景状态）。

**结果（真实对照自测，12 份工作群文件）**：销售合同 → 合同与协议、差旅费报销单 → 财务与票据、供应商进货单 → 采购与供应、周会纪要 → 会议与纪要、NDA → 法务与合规、员工手册 → 人事与行政、PRD → 产品与需求、里程碑排期 → 项目与任务、销售报表 → 客户与销售、放假通知 → 通知与公告、指标看板 → 数据与报表、接口文档 → 代码与工程，**0 份落进长尾兜底**。同时旧三级词库把 `.pptx` 销售报表误判成「学习 / 课件资源」的问题也一并纠偏：无科目证据时以内容驱动体裁为准。

**可撤销 / 先看再执行**：`GET /taxonomy` 页面提供
- 双场景对照 dry-run（`POST /api/taxonomy/preview`，只推断、不写目录、不移动或改名文件）；
- 受控词表同义词 CRUD（`POST /api/taxonomy/synonym`，写 `state/taxonomy_overrides.json`，不进仓库，可随时移除）；
- 语义匹配自检（`GET /api/taxonomy?q=进货单`）；
- 主界面新增「按体裁 / 按动态主题 / 按文件模态」三个下钻维度，默认视图改为「按体裁（内容驱动）」。

**技术来源**：借鉴 [guiwei](https://github.com/xntj-ai/guiwei)（MIT，不预设目录树 + 模态/体裁 + vocab 归一 + dry-run/可撤销 + 敏感件闸门）、[RAG-In-A-Box](https://github.com/DevNexsler/RAG-In-A-Box)（Taxonomy 受控词表 + 语义匹配 + CRUD）、[FolderFox](https://github.com/ChenAI-TGF/FolderFox)（预览再执行）、[WeChatBridge](https://github.com/freestylefly/WeChatBridge)（不读库不注入的本地归档通道）的**设计思想**，零运行时依赖。**不采用** [im-mcp](https://github.com/stkoecn/im-mcp)：它需从微信进程内存提取密钥并解密 SQLite 聊天库，与本项目「绝不读取加密聊天数据库」的边界冲突。

---

## 💬 微信监听与收集

> [!WARNING]
> 个人微信**没有**「列出群文件全目录」的开放接口，也无法像 QQ 那样通过 OneBot 拉取云端群文件；聊天数据库是加密的。本项目**不破解、不读取**任何聊天记录。

因此微信侧采用**监听式采集**：借助 GitHub 上成熟的 [WeChatFerry](https://github.com/lich0821/WeChatFerry)（`wcferry`）方案，它在本机对「微信 3.9.x」进程暴露本地 RPC。本项目只订阅**你指定群**里出现的「文件 / 附件」消息，拿到文件名、体积、发送者、时间等元数据后并入统一目录。

| 环节 | 行为 |
| --- | --- |
| **启用前提** | ① 界面顶部「微信」按钮 →「启用微信采集」+「安装 wcferry」（不用手改 `config.json`）；② 电脑版**微信 3.9.x 已扫码登录**并运行 WeChatFerry 客户端（RPC `:10086`）；③ 页面「检查微信登录状态」显示已登录 |
| **群白名单** | 必须显式指定监听群（wxid 列表）。`GET /api/wechat/wcf/rooms` 发现群、`POST /api/wechat/wcf/rooms/save` 保存到 `state/wechat_rooms.json`；**清单为空时明确报错，绝不监听全部群** |
| **采集流程** | `POST /api/wechat/wcf/capture/start` → 解析 appmsg XML 中的 `<type>` 过滤出文件/附件 → 5 秒防抖缓冲 → `catalog.upsert_manifest()` → `index.sync()` 增量索引 → `vault.build_outlines()` |
| **停止** | `POST /api/wechat/wcf/capture/stop`；`GET /api/wechat/wcf/status` 随时查看 enabled / available / login / capturing |
| **降级** | 未装 `wcferry` 或客户端未登录时，`status` 给出明确指引，微信源不可用但**其余功能完全不受影响** |

**启用步骤（界面版，推荐）**：点顶部「微信」打开 `http://127.0.0.1:8787/wechat` → ①「启用微信采集」→「安装 wcferry」 → ② 在电脑版微信 3.9.x 里扫码登录并启动 WeChatFerry 客户端，回页面点「检查微信登录状态」 → ③「拉取我的群清单」勾选群 →「保存监听群」→「开始监听」。页面实时显示监听状态与已采集条数。

> 微信登录**必须在微信客户端里完成**，本程序只检测登录态、不代扫码；微信 4.x 暂不被 WeChatFerry 支持，请继续使用 QQ 群文件通道。

等价的 API（自动化时使用）：

```bash
curl -s -X POST http://127.0.0.1:8787/api/wechat/wcf/enable \
     -H "Content-Type: application/json" -d '{"enabled":true}'
curl -s -X POST http://127.0.0.1:8787/api/wechat/wcf/install
curl -s -X POST http://127.0.0.1:8787/api/wechat/wcf/login
curl -s http://127.0.0.1:8787/api/wechat/wcf/rooms
curl -s -X POST http://127.0.0.1:8787/api/wechat/wcf/rooms/save \
     -H "Content-Type: application/json" -d '{"rooms":["wxid_xxx"]}'
curl -s -X POST http://127.0.0.1:8787/api/wechat/wcf/capture/start \
     -H "Content-Type: application/json" -d '{"rooms":["wxid_xxx"]}'
```

> 采集到的同样是**元数据**；要拿到正文仍需像 QQ 文件一样在界面里显式确认下载（微信附件由 WeChatFerry 侧落地）。未监听到的历史群文件不会被凭空补出来——这是方案边界，不是 bug。

---

## 架构总览

```mermaid
flowchart LR
    subgraph SRC["来源层 · 只读 / 授权"]
        QQ["QQ 群文件<br/>NapCat OneBot 11 :3000"]
        WX["微信群文件<br/>WeChatFerry RPC :10086"]
        SNAP["离线快照<br/>state/qq_manifest.json"]
    end
    subgraph APP["resource-manager · 127.0.0.1:8787"]
        SRV["server.py<br/>ThreadingHTTPServer"]
        CAT["catalog<br/>唯一事实源"]
        CLS["classify<br/>三级分类"]
        DL["download<br/>确认闸门/并发/重试"]
        EXT["extract<br/>正文抽取/摘要"]
        IDX["index<br/>FTS5 增量同步"]
        AIM["ai + llm<br/>grounded 问答"]
        VLT["vault<br/>Obsidian 生成"]
    end
    subgraph OUT["输出层"]
        WEB["Web 管理界面<br/>零构建三栏"]
        OBS["Obsidian 独立库<br/>桌面/资源管理"]
        API["HTTP API<br/>/api/*"]
    end
    QQ --> SRV
    WX -.可选.-> SRV
    SNAP -.降级.-> SRV
    SRV --> CAT --> CLS --> IDX
    SRV --> DL --> EXT --> IDX
    IDX --> AIM
    CAT --> VLT --> OBS
    SRV --> WEB
    SRV --> API
```

**分层**：`web/ + obsidian_plugin/` → `server.py` → `catalog / classify / download / ai` → `qq / wechat_wcf / extract / vault / index / llm` → `state/`。

**核心数据流**：`来源刷新 → 归类 → 选择 → 下载 → 抽取 → 增量索引 → Obsidian 大纲 → AI 检索问答`。

---

## 快速开始

> **完全零基础？别看这一节**，直接打开 [📖 零基础安装与使用指南](docs/INSTALL.md)：从「我该下哪个文件」到「Obsidian 里看到知识库」，每一步都写清楚了，含常见问题与启动 / 停止 / 更新 / 卸载。下面是给熟悉命令行的人的浓缩版。

### 环境要求

- Python **3.13+**（核心链路零第三方依赖）
- QQ 群文件功能：本机已部署并登录 [NapCat](https://github.com/NapCatQQ/NapCatQQ)（OneBot 11 HTTP，默认 `:3000`）
- 微信功能（可选）：WeChatFerry + 微信 3.9.x
- Obsidian（可选，用于阅读生成的知识库）

### 方式一：一键安装器（推荐给所有人）

```text
1. 打开最新版 Releases → Assets，下载 resource-manager-installer.bat
   固定直链（永远指向最新版）：
   https://github.com/ericzou090124/ericzou-01/releases/latest/download/resource-manager-installer.bat
2. 直接双击它（不需要先解压、不需要命令行）
3. 自动解压到 %USERPROFILE%\resource-manager，启动服务并打开 http://127.0.0.1:8787
4. 点界面顶部「首次配置」向导：一键检测并修复 NapCat 配置 → 勾选 QQ 群 → 完成
```

同页还有 `resource-manager-full.zip`（**仓库全部内容**：源码 + 全部文档 + 安装器 + 教程），下载后**先解压整个 zip**，再双击里面的 `start.bat`；以及 `SHA256SUMS.txt` 可校验文件完整性。

可选环境变量：`RM_INSTALL_TARGET`（指定解压目录）、`RM_NO_LAUNCH=1`（只解压不启动）。
发布包由 `python tools/build_release_assets.py` 生成，资产由 `python tools/sync_github_releases.py --apply --assets-dir dist` 幂等上传，保证每个版本页面都有可下载入口。

### 方式二：源码运行（开发者）

```bash
# 1. 克隆
git clone https://github.com/ericzou090124/ericzou-01.git
cd ericzou-01

# 2.（可选）装中文分词，提升检索精度；不装自动回退 3-gram
pip install -r requirements-optional.txt

# 3. 启动（首次会刷新来源、建索引）
python server.py

# 4. 打开界面
#    http://127.0.0.1:8787
```

### 方式三：只跑验证（不启动服务）

```bash
python tools/smoke_test.py        # 18 项单元 + HTTP 集成回归，退出码 0 即通过
python tools/test_v3.py           # v3.0.0 端到端自测（真实 HTTP）+ v3.1.0 泛化回归
python tools/test_taxonomy.py     # 泛化分类双场景对照自测 70 项（学生群 / 工作群）
python tools/verify_release.py    # 发行资产端到端验证（可加 --from-github）
python tools/bench.py             # 索引 rebuild / sync / optimize 微基准
python tools/version_audit.py     # 全版本可用性审计，生成 docs/VERSION_AUDIT.md
```

### 可选依赖

| 包 | 用途 | 不装会怎样 |
| --- | --- | --- |
| `jieba` | 中文分词，检索词更精准 | 自动回退滑动 3-gram，功能不受影响；`RM_NO_JIEBA=1` 可强制关闭 |
| `wcferry` | 微信群文件监听采集 | 微信源不可用，其余功能不受影响 |
| `pymupdf` | PDF 正文抽取 | PDF 只登记元数据，标记「扫描件需 OCR」 |

---

## 配置说明

`config.json` 是唯一配置文件；运行时设置（模型、密钥）覆盖写在 `state/settings.json` / `state/secrets.json`，**均已 gitignore**。

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `vault` | `""` | Obsidian 库路径；空则回退 `~/Desktop/资源管理`（独立新库，不动原有笔记） |
| `host` / `port` | `127.0.0.1` / `8787` | 仅监听回环；改成非回环地址启动自检会给出告警 |
| `sources.qq.enabled` / `.groups` | `true` / 3 个示例群 | 群代号 → `{display, qq_group}`；群号必须是纯数字 |
| `sources.wechat.wcf.enabled` | `false` | 微信监听总开关，**默认关闭** |
| `sources.wechat.wcf.host/port` | `127.0.0.1:10086` | WeChatFerry RPC 地址 |
| `classification` | 8 领域 / 29 科目 / 8 类型 / 14 组别名 | 三级分类词库，可自由增删 |
| `classification.taxonomy` | `enabled=true` / `llm_assist=false` / `max_topics=4` | 泛化分类开关：中性受控词表在 `lib/taxonomy.py`；用户新增同义词写 `state/taxonomy_overrides.json`（不进仓库）；敏感件关键词永不送模型 |
| `allowed_ext` | 17 种 | 下载白名单（带点，如 `.pdf`）；为空时所有下载被拒绝 |
| `max_download_per_batch` | `30` | 单批下载上限，超出部分需再次确认 |
| `max_chars_per_file` | `60000` | 单文件入索引的正文截断长度 |
| `ai.provider` | `local` | `local` 或 `openai`（任意 OpenAI 兼容接口） |
| `ai.local.*` | `127.0.0.1:8080/v1` | 本地推理服务地址、模型名、`disable_thinking`（Bonsai2 需 `true`） |
| `ai.min_relevance` / `top_k` | `0.22` / `5` | 命中阈值与送入模型的最大片段数 |
| `RM_DOWNLOAD_WORKERS` | `4`（环境变量） | 单批并发下载线程数，设 `1` 强制串行 |
| `RM_DOWNLOAD_RETRIES` | `3`（环境变量） | 瞬时失败退避重试次数（0.5s / 1s / 2s） |
| `RM_NO_JIEBA` | 未设（环境变量） | 设为 `1` 禁用 jieba 分词 |

启动时 `lib/config_validate.py` 会校验全部关键项，把问题打印成可读清单；运行中可随时点界面「系统诊断」或请求 `GET /api/diagnose` 查看。

---

## 核心行为语义

### 下载闸门（不可绕过）

| 条件 | 服务端行为 |
| --- | --- |
| `confirm != true` 或 `ids` 为空 | 拒绝，返回明确原因 |
| 整类下载 `confirmText` ≠ 节点名 | 拒绝，要求原样输入 |
| 当前为离线快照 | 拒绝，提示先「刷新来源」切回在线 |
| 超出 `max_download_per_batch` | 只处理上限内条目，返回 `skipped_over_cap`，需再次确认剩余 |
| 扩展名不在 `allowed_ext` | 单条失败，不影响同批其它条目 |
| `file_id` 失效 / 直链为空 | 判定为**永久错误**，不重试，提示刷新来源 |
| 网络抖动 / OneBot 超时 / 空文件 | 判定为**瞬时错误**，指数退避重试至 `RM_DOWNLOAD_RETRIES` |

下载成功后 `catalog.save()` → `index.sync()` → `vault.build_outlines()`，均为增量/最小写入，不做全量重建。

### AI 防臆造

- **命中判定与生成解耦**：先本地检索，未命中直接返回「授权可见的资料中没有检索到相关信息」，**不调用模型**。
- **范围优先**：问题中的科目 / 领域 / 类型识别结果，与当前浏览路径合并成过滤器，检索严格限定在范围内。
- **未下载标注**：未下载条目在上下文与回答中必须写「仅元数据，未下载，无正文摘要」，不得描述文件内容。
- **模型降级**：`llm.chat()` 对超时 / 连接中断 / 5xx 指数退避重试；本地地址直连、外部地址走环境代理；模型返回「未找到」或不可用时自动改用本地原文摘录，不虚构。

### 索引增量同步

`index.sync()` 为每个条目维护 `(csig, bstat)` 两个指纹：`csig` 是元数据哈希（O(1)，无磁盘 I/O），`bstat` 是正文文件 `size:mtime_ns`。两者都命中即整条跳过；只有正文变化才重读。实测 `sync(无变化) ≈ 1503ms` vs `rebuild ≈ 2596ms`；`POST /api/maintain` 的 `ANALYZE + VACUUM` 可回收约 774KB 空闲页。

---

## 🖥️ Web 管理界面

`http://127.0.0.1:8787` · 三栏布局 · 明暗主题自适应 · 无构建步骤

| 区域 | 内容 |
| --- | --- |
| **顶栏** | 面包屑、统一搜索框（命中高亮 +「问 AI」）、AI 助手、设置、QQ 登录、首次配置、刷新来源、**系统诊断** |
| **左栏** | 授权来源状态（QQ 在线 / 离线快照、微信实时状态与「微信登录 / 群文件采集」按钮）、分类大纲树（按分类 / **按主题标签（多归属）** / 按来源切换）、统计卡（含分类完整性校验） |
| **中栏** | 当前节点、全选本页 / 下载已选 / 整类下载、子级下钻、类型筛选条、文件列表（预览 / 下载 / 状态标签） |
| **右栏** | 单文件预览（元数据 / 摘要 / 正文片段 / 资产与笔记路径）、AI 助手（快速模式、范围显示、可点击来源索引、快捷提问） |

**系统诊断面板**：一键展示配置状态、错误清单、提醒清单、来源模式、QQ 在线状态、索引篇数与 Obsidian 库路径。

---

## 🔌 API 端点

服务仅监听 `127.0.0.1:8787`，无需鉴权（本地回环）。全部返回 JSON。

<details>
<summary><b>状态与目录</b></summary>

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/health` | GET | `ok` / 索引篇数 / 来源模式 / QQ 在线状态 |
| `/api/diagnose` | GET | 配置自检 + 错误/提醒 + 运行态 |
| `/api/state` | GET | 完整状态：来源、统计、微信、设置、下载上限 |
| `/api/tree` | GET | `dim=classify / source / tag / genre / topic / modality` 六种视角的树子节点（份数、已下载数、体积） |
| `/api/files` | GET | 节点内文件列表，支持 `q` 搜索、`kind` 筛选、`limit`，返回 `total` |
| `/api/file` | GET | 单文件详情 + 正文摘录 + 资产/笔记绝对路径 |
| `/api/outline` | GET | Obsidian 大纲信息 |
| `/api/ask` | GET / POST | AI 问答（支持 `fast`、`scope`） |

</details>

<details>
<summary><b>下载与维护</b></summary>

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/download` | POST | 下载闸门；需 `confirm` + `ids`（+整类 `confirmText` / `nodeName`） |
| `/api/refresh` | POST | 只读刷新来源元数据，增量同步索引，不下载任何文件 |
| `/api/reindex` | POST | 强制全量重建索引 |
| `/api/maintain` | POST | `ANALYZE + VACUUM`，返回维护前后体积 |
| `/api/settings` | GET / POST | 读取 / 保存 AI 设置（密钥不回显） |
| `/api/settings/test` | POST | 测试模型连通性 |
| `/api/init` | POST | 初始化 Obsidian 库骨架 |

</details>

<details>
<summary><b>QQ 登录 / NapCat / 微信 / 新手向导</b></summary>

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/qqlogin/status` · `/refresh` · `/quick` · `/restore` | GET / POST | 本页二维码状态 / 刷新（自动拉起 NapCat）/ 免扫码快登 / 扫码后恢复在线 |
| `/api/napcat/status` · `/start` · `/setup` | GET / POST | NapCat 完整自检 / 拉起服务 / **安装自检并自动修复配置** |
| `/api/qq/groups` | GET | 列出本机 QQ 已加入的群 |
| `/api/reclassify` | POST | 词库升级后原地重算分类（不增删条目，带完整性门禁）；返回体裁分布与场景统计 |
| `/api/taxonomy` | GET | 受控词表快照：`genres` / 同义词 / 体裁与模态分布 / 场景统计 / 技术来源；`?q=` 附带语义匹配 |
| `/api/taxonomy/preview` | POST | FolderFox 式 dry-run：给若干 `{folder, name}` 预览推断结果，**不写目录** |
| `/api/taxonomy/synonym` | POST | 词表 CRUD：新增/移除同义词（写 `state/`，可撤销），可选 `reclassify` 原地重算 |
| `/taxonomy` | GET | 分类体系页面：对照试跑、词表管理、语义匹配、边界说明 |
| `/api/wechat/wcf/status` | GET | 微信适配器状态（enabled / available / login / capturing / captured / saved_rooms / login_hint） |
| `/api/wechat/wcf/enable` · `/install` · `/login` | POST | 一键启用 / 安装 wcferry / 检测微信登录态 |
| `/api/wechat/wcf/rooms` · `/rooms/save` | GET / POST | 发现群 / 保存监听群清单 |
| `/api/wechat/wcf/capture/start` · `/stop` | POST | 开始 / 停止微信监听采集 |
| `/wechat` | GET | 微信登录与群文件采集可视化页面 |
| `/api/setup` · `/setup/config` · `/setup/done` | GET / POST | 首次配置向导状态、保存群配置、标记完成 |

</details>

---

## 版本、回归与开发者日志

本仓库按版本持续迭代，**每个版本都有独立 git tag 与 GitHub Release**，可随时 `git checkout vX.Y.Z` 回溯。

| 里程碑 | 内容 |
| --- | --- |
| `v1.0.0` ~ `v1.2.3` | 首次交付闭环、QQ 网页一键登录、零配置新手向导与安装器 |
| `v1.3.0` | 仓库基线审查（`REVIEW.md`）与自解压安装器 |
| `v1.4.0` | 检索精度与运行期开销优化（jieba 分词 / 缓存） |
| `v1.5.0` | **GitHub WeChatFerry 微信监听式适配器**（本项目首个外部成熟方案集成） |
| `v1.6.0` ~ `v1.8.0` | 索引增量同步、回归自测、刷新链路改走 `sync` |
| `v1.9.0` | 微信监听群清单持久化 + 群发现/保存端点 |
| `v2.0.0` ~ `v2.3.0` | 前端统一搜索框与高亮、索引维护/基准、下载并发与增量、AI 退化路径修复 |
| `v2.4.0` ~ `v2.7.0` | 配置自检与诊断端点、下载重试退避、系统诊断面板、HTTP 集成自测 |
| `v2.8.0` | 主页重写、全版本可用性审计、历史补丁标签、文档与 Release 治理 |
| `v2.9.0` ~ `v2.9.1` | 小白下载入口与完整教程闭环、可下载 Release 资产、一键安装器 cmd 解析故障修复 |
| `v3.0.0` | **登录/安装/分类/微信四条链路实测修复**：NapCat 控制台入口移除与二维码本页直出、install 真正安装配置 NapCat、分类不漏项（高等代数 1→124 条）、微信登录与群文件采集可视化入口 |
| `v3.1.0` | **内容驱动的泛化分类**：中性受控词表（21 体裁 / 267 同义词）+ 动态主题 + 模态、工作群双场景对照自测 70/70、dry-run 预览与词表 CRUD 页面、三个新下钻维度；借鉴 guiwei / RAG-In-A-Box / FolderFox / WeChatBridge，明确不采用 im-mcp |

### 全版本可用性审计

`tools/version_audit.py` 会把**每个 tag** 检出到隔离临时目录，执行：归档完整性 / 配置解析 / 全量编译 / 模块导入 / 核心链路 / 群文件分类 / 微信适配器 / 路由完整性 / 前端语法 / 自带自测 —— 全程使用独立 `state/`，不碰真实资料。

```bash
python tools/version_audit.py                    # 全部 tag → docs/VERSION_AUDIT.md
python tools/version_audit.py --tags v2.7.0      # 指定版本
```

审计发现 `v1.3.0` ~ `v1.6.0` 的空问题 `NameError`（已在 v1.7.0 修复）。为保留历史原貌，**不改写原 tag**，而是用 `tools/fix_legacy_tag.py` 生成只含最小修复的补丁标签 `v1.3.0-p1` … `v1.6.0-p1`，全部通过检测。详见 [全版本审计报告](docs/VERSION_AUDIT.md)。

### 开发者日志

| 想看什么 | 读哪个文件 |
| --- | --- |
| 逐版本变更摘要 | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| **按时间顺序的开发日志**（每次决策、故障、修复、实测数据） | [docs/DEVLOG.md](docs/DEVLOG.md) |
| 系统审查、瓶颈排序与优化路线图 | [docs/REVIEW.md](docs/REVIEW.md) |
| 整体设计 / 模块划分 / 数据流 | [docs/DESIGN.md](docs/DESIGN.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 通读式说明文字（背景、使用旅程、隐私） | [docs/GUIDE.md](docs/GUIDE.md) |
| 本地试跑逐项结果、耗时、已知限制 | [docs/VERIFICATION.md](docs/VERIFICATION.md) |
| 存档说明与逐项验收清单 | [docs/RELEASE.md](docs/RELEASE.md) |
| 文档总索引 | [docs/README.md](docs/README.md) |

---

## 常见问题

<details>
<summary><b>我第一次进这个仓库，到底该下载哪个文件？完全不懂命令行怎么办？</b></summary>

点 [最新版 Releases](https://github.com/ericzou090124/ericzou-01/releases/latest)，拉到页面底部 **Assets**，下载 **`resource-manager-installer.bat`**，**直接双击**即可（不用解压、不用命令行）。程序会自动装好、启动并打开浏览器。唯一的准备是本机装了 Python 3.10+（安装时勾选 `Add python.exe to PATH`）。

想拿到仓库全部内容（源码 + 文档 + 教程）就下 `resource-manager-full.zip`，**先解压**再双击 `start.bat`。完整图文步骤见 **[docs/INSTALL.md](docs/INSTALL.md)**。

</details>

<details>
<summary><b>主界面显示「离线快照」，下载按钮用不了？</b></summary>

NapCat / OneBot 没在运行或运行中途掉线。点顶栏「QQ 登录」打开登录页：如果 NapCat 没跑，页面会**自动拉起**并在本页显示二维码（也可随时点「刷新二维码」），**不需要打开任何 NapCat 控制台**。扫码确认后页面会自动等待群文件接口就绪、刷新来源并跳回主界面。首次使用若提示「未检测到 NapCat」，双击 `install.bat` 或 `tools/setup_napcat.bat` 完成安装自检与配置修复。**恢复在线必须用户显式操作**，避免拿失效 `file_id` 下载。

</details>

<details>
<summary><b>为什么微信群里以前发的文件看不到？</b></summary>

微信没有「列出群文件全目录」的开放接口，监听式方案只能收到**开启捕获之后**新增的文件消息。历史文件不会凭空补出来。请把重要资料重新在群里发一次，或改用 QQ 群文件能力。

</details>

<details>
<summary><b>AI 回答「未找到」，但我觉得库里明明有？</b></summary>

先确认：① 当前浏览范围是否正确（AI 严格限定范围内检索，顶栏面包屑可回退到「全部资源」）；② 该条目是否只是元数据（未下载就没有正文，检索不到内容）；③ 在「设置」里适当调低 `min_relevance`（默认 0.22）。命中判定完全由本地检索给出，模型不会替你判断「有没有」。

</details>

<details>
<summary><b>装不上 jieba / wcferry / pymupdf 会坏吗？</b></summary>

不会。三者都是可选增强：jieba 缺失回退 3-gram，wcferry 缺失仅微信源不可用，pymupdf 缺失 PDF 只登记元数据。启动自检会把这些列为提醒而非错误。`RM_NO_JIEBA=1` 可主动关闭分词。

</details>

<details>
<summary><b>索引越来越大 / 刷新变慢？</b></summary>

点「系统诊断」或调用 `POST /api/maintain` 执行 `ANALYZE + VACUUM` 回收空闲页；刷新来源已走 `index.sync()` 增量同步。只有 `POST /api/reindex` 才会全量重建。`python tools/bench.py` 可量化当前耗时。

</details>

<details>
<summary><b>如何回退到某个历史版本，且保证它可用？</b></summary>

```bash
git tag --list                 # 查看全部版本
git checkout v2.5.0            # 回退
python tools/smoke_test.py     # 验证
```

若需要 `v1.3.0` ~ `v1.6.0` 系列，请改用补丁标签 `v1.3.0-p1` 等（原 tag 如实保留了一个空问题 NameError）。完整检测结果见 [docs/VERSION_AUDIT.md](docs/VERSION_AUDIT.md)。

</details>

---

## 关键断言 ↔ 代码出处

| 断言 | 出处 |
| --- | --- |
| 下载必须显式确认 / 整类二次确认 / 单批上限 | `lib/download.py::precheck` |
| 下载失败退避重试、永久错误不重试 | `lib/download.py::_fetch_with_retry` |
| 下载后只做增量同步而非全量重建 | `lib/download.py::run` → `index.sync()` |
| 三级分类加权打分（文件夹权重更高） | `lib/classify.py::classify_full` |
| 内容驱动泛化分类（不硬编码场景目录） | `lib/taxonomy.py::infer` / `lib/classify.py::classify_extended` |
| 动态主题提取（不预设主题表） | `lib/taxonomy.py::extract_topics` |
| 敏感件不送 LLM / 规则层兜底 | `lib/taxonomy.py::is_sensitive` / `llm_enrich` |
| 词表 CRUD 可撤销（写 state，不进仓库） | `lib/taxonomy.py::save_synonym` |
| 分类完整性门禁（含体裁 / 模态） | `lib/catalog.py::verify_integrity` |
| 微信监听群清单为空则拒绝启动 | `lib/wechat_wcf.py::start_capture` |
| 微信采集 5 秒防抖 + 增量索引 | `server.py::wechat_on_row` / `wechat_flush` |
| 命中判定与生成解耦、未下载标注 | `lib/ai.py::answer` / `SYSTEM` |
| 本地直连 / 外部走代理 + 5xx 退避 | `lib/llm.py::_opener_for` / `_call` |
| `csig + bstat` 两阶段增量指纹 | `lib/index.py::sync` |
| 生成笔记带 `NOTE_MARK`，不删手工笔记 | `lib/vault.py::NOTE_MARK` / `_write` |
| 启动期配置自检 | `lib/config_validate.py::validate` |
| 全版本可用性审计 | `tools/version_audit.py` |

---

## 安全与隐私

1. **本地闭环**：服务仅监听 `127.0.0.1`，无内置 TLS、无外网暴露；所有资料、`state/`、密钥都在本机。
2. **只读 / 监听**：QQ 侧只读遍历群文件元数据；微信侧只监听指定群的文件消息，**不读取加密聊天库**，不向群内发送任何内容。
3. **显式授权**：下载必须界面确认；微信群白名单必须显式指定，绝不「默认监听全部群」。
4. **密钥隔离**：`state/secrets.json`、`state/settings.json` 与整个 `state/` 已 gitignore，不进仓库、不下发前端（`catalog.public()` 过滤 `file_id` 等敏感字段）。
5. **优雅降级**：可选依赖缺失、模型不可用、QQ 掉线时均降级而非崩溃，并在界面明确标注。

---

## 免责声明

本项目为**非官方**的个人资料整理工具，与腾讯 QQ / 微信 / Obsidian 官方无关。使用者需自行遵守相关平台服务条款与当地法律，自行承担账号与合规风险。项目仅供学习与个人自用，作者不对任何因使用本项目产生的直接或间接损失负责。

**许可**：本项目采用 MIT 许可证，详情请参阅 LICENSE 文件。

## 致谢与参考

- [NapCatQQ](https://github.com/NapCatQQ/NapCatQQ) — QQ OneBot 11 接入
- [WeChatFerry](https://github.com/lich0821/WeChatFerry) — 微信群文件监听方案（`lib/wechat_wcf.py`）
- [guiwei](https://github.com/xntj-ai/guiwei)（MIT）— 内容驱动分类、模态/体裁、vocab 归一、dry-run 与敏感件闸门
- [RAG-In-A-Box](https://github.com/DevNexsler/RAG-In-A-Box) — Taxonomy 受控词表、语义匹配与 CRUD
- [FolderFox](https://github.com/ChenAI-TGF/FolderFox) — 预览方案后再执行、可撤销
- [WeChatBridge](https://github.com/freestylefly/WeChatBridge) — 不读库、不注入的本地归档通道
- [Obsidian](https://obsidian.md) — 知识库载体与插件接口
- README 的文档结构与工程化排版参考了 [workbuddy2api-panel](https://github.com/linguo2625469/workbuddy2api-panel)
