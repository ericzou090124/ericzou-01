# Resource Manager

**把 QQ 群里散落的课程资料、合同单据与工作文件，整理成一个可检索、可问答的本地 Obsidian 知识库**

`QQ 群文件采集` · `单值自动分类` · `SQLite FTS5 全文检索` · `AI 防臆造问答` · `下载到 Obsidian` · `零第三方硬依赖`

[![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Deps](https://img.shields.io/badge/Deps-Zero_hard_dependency-00ADD8?style=flat-square)](requirements.txt)
[![Search](https://img.shields.io/badge/Search-SQLite_FTS5-003B57?style=flat-square&logo=sqlite&logoColor=white)](lib/index.py)
[![Vault](https://img.shields.io/badge/Vault-Obsidian-7C3AED?style=flat-square&logo=obsidian&logoColor=white)](lib/vault.py)
[![Privacy](https://img.shields.io/badge/Privacy-Local_only-2E8B57?style=flat-square)](#-安全与隐私)
[![Version](https://img.shields.io/badge/Version-v3.3.0-EA4AAA?style=flat-square)](docs/CHANGELOG.md)
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
> - 对 QQ 云端**只读**，不修改群内任何内容，**绝不读取加密聊天数据库**。
> - 下载必须经过界面**显式确认**；未下载条目只有文件名与元数据，AI 不会推测其内容。

---

## 项目简介

课程资料散落在十几个 QQ 群的层级目录里：找一份「复变函数期末真题」要翻遍群文件，下下来又散在桌面各处，更没法按科目检索或针对内容提问。

**Resource Manager** 用一条完整闭环解决这件事：

> **来源盘点 → 自动分类 → 逐级下钻 → 确认下载 → 正文入库 → 全文索引 → Obsidian 大纲 → AI 检索问答**

- **零第三方硬依赖**：核心链路全部 Python 标准库（`http.server` + `sqlite3` FTS5 + `urllib`），克隆后**不用 `pip install` 就能跑**。
- **未下载也能检索**：所有条目先进目录与索引，AI 可以基于「可见的元数据」回答「有哪些 / 多少 / 哪些还没下载」，但明确标注「仅元数据，无正文摘要」，绝不把文件名当内容。
- **本地模型或外部 API 都行**：默认指向本机推理服务（Bonsai2，自动 `disable_thinking`），也可切任意 OpenAI 兼容接口；模型挂了自动降级为纯本地检索，不编造答案。
- **Obsidian 独立新库**：自动生成独立 Obsidian 库（带多级大纲 MOC 与 AI 侧边栏插件），**不碰你原有的任何笔记库**。

实测数据：3 个 QQ 群、1641 条原始清单去重后 **1625 条 / 约 12.73 GB**，覆盖 29 个学科、13 种资源类型、59 个多归属主题标签。分类升级后**条目一条不少**（`catalog.verify_integrity()` 门禁）。

---

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 📥 **QQ 群文件只读盘点** | 通过本机 NapCat（OneBot 11）`get_group_root_files` + `get_group_files_by_folder` **递归遍历全部目录**，只取元数据；接口掉线自动收紧为「离线快照」并锁定下载，恢复在线需用户显式点「刷新来源」 |
| 🧠 **单值自动分类（v3.2.0 重写）** | 每个文件在「**学科 / 类型 / 来源**」三个维度上**各只有一个值**，因此任意层级节点计数之和**严格等于文件总数**——绝不出现「计数对不上、空分类、错分」。词库全部在 `config.json`（领域 / 29 学科 / 13 类型 + 相关主题别名）；详见 [群文件自动分类](#-群文件自动分类) |
| 🏷️ **多归属主题标签（仅用于搜索召回）** | 同一文件可带多个主题标签，用于搜索召回扩展；但**不进入分类树**，所以不会重复计数 |
| 🔎 **别名召回，不再漏项** | 搜索词按 `classification.aliases` 与相关主题语义展开：实测搜「高等代数」从旧版 **1 条 → 124 条**；`verify_integrity()` 保证条目数 / id / 标签 / 学科 / 类型不缺失 |
| 🔑 **QQ 登录本页闭环** | 二维码在资源管理器自己的页面直出、过期自动换新，「刷新二维码」会自动拉起未运行的 NapCat；**不需要打开任何 NapCat 控制台**，登录成功自动恢复在线来源 |
| 🛠️ **install 真的管 NapCat** | `install.bat` 内置 NapCat 安装自检：检测运行时 / 启动脚本 / WebUI / OneBot 配置，自动修复 `webui.json` 的 `host=::`（本机 127.0.0.1 拒绝连接的根因）并生成可回滚备份与 `state/napcat_setup.json` 报告；也可单独跑 `tools/setup_napcat.bat` |
| 💾 **下载到 Obsidian 分类知识库** | 勾选文件 → 显式二次确认 → 自动下载、分类入库、生成摘要与多级大纲，并写入 Obsidian 知识库 |
| 💬 **AI 问答（防臆造）** | 基于 FTS5 全文检索 + 本地/外部 LLM 作答，回答下方给出可点击的源文件索引；查不到如实说明，绝不编造 |
| 🔀 **随时切换 / 增减搜索群聊（v3.3.0）** | 顶部「群聊」按钮在登录态下随时增删要搜索的群（在线自动列出本 QQ 加入的群，离线可手动填群号）；左侧「群聊范围」下拉按群收窄分类树 / 文件列表 / AI 问答，无需手改 `config.json` |

---

## 群文件自动分类

分类逻辑是**内容驱动**的，代码里没有「学生用 A 目录 / 店主用 B 目录」的分支。每一条记录只有单值 `领域 / 学科 / 类型` 三级 + 多归属 `标签`：

- **学科（subject）**：29 个具体科目（高等代数、复变函数、大学物理、C 语言程序设 计…），文件名/路径命中科目全名会额外加权，避免泛词误判。
- **类型（kind）**：13 种资源类型（试卷与解析、习题作业、课件资源、上课笔记、实验代码、财务与票据、会议纪要、合同与协议、采购与供应、方案与报告、人事与制度、产品与资料、项目与工程…）。
- **来源（source）**：`来源 → 群 → 文件夹` 三级，点进去即可按群内真实目录逐级下钻。
- **多归属标签**：主学科 + 命中领域 + 类型 + 相关主题别名，仅用于搜索召回扩展。

> **v3.2.0 修复的核心 bug**：旧版用多值 `genre/topic/modality` 作树维度，同一文件会被重复计入多个树桶，导致「节点计数之和 ≠ 文件总数」「点了进去却是空」「严重错分」。新版改为纯单值维度，并新增 `catalog.verify_tree_consistency()` 门禁——实测三个维度子节点计数之和都严格等于 1625。

> **不错分**：裸扩展名 `.ppt` 已从词库剔除（这是「销售报表 .pptx 被错判成课件资源」的根因）；关键词按长度加权。实测「流体力学I期末试题」→ 大学物理 / 试卷与解析，销售报表 `.pptx` 不再判课件。

---

## 界面怎么用（简洁版）

打开 `http://127.0.0.1:8787` 后，界面只保留三件事：

1. **分类整理**（左栏「分类大纲」）：用顶部下拉在「按学科 / 按类型 / 按来源」之间切换；点节点逐级下钻。每个节点的数字就是该分类下的文件数，**加起来一定等于总数，不会出现空分类**。
2. **下载到 Obsidian**：主区勾选文件 → 点「下载已选」；或在某个分类下点「整类下载」（会要求你原样输入节点名二次确认）。下载前必须显式确认。
3. **AI 问答**（右栏）：直接口语提问（如「高数期末真题有哪些？」），回答下方列出可点击的源文件索引；查不到会如实说明。

其余只剩必要的 **QQ 登录 / 刷新来源 / 设置** 三个按钮（首次使用会顶部出现「首次配置」引导）。

---

## 安全与隐私

- **纯本地、只读**：服务只监听 `127.0.0.1`；对 QQ 云端只读取群文件元数据，不修改任何群内内容。
- **绝不读取加密聊天数据库**：不破解、不解密、不注入任何聊天记录或微信/QQ 客户端。
- **下载需显式确认**：未下载条目只有元数据，AI 不会把文件名当成正文内容。
- **密钥只存本机**：AI 的 API Key 写在 `state/secrets.json`（已 gitignore），不进仓库。

---

## 快速开始

### Windows（推荐，双击即用）
1. 下载并双击 [resource-manager-installer.bat](https://github.com/ericzou090124/ericzou-01/releases/latest/download/resource-manager-installer.bat)（自动解压到 `C:\Users\<你>\resource-manager`）。
2. 双击 `start.bat` 启动，浏览器自动打开 `http://127.0.0.1:8787`。
3. 第一次用：点顶部「QQ 登录」扫码（无需打开 NapCat 控制台），再点「群聊」按钮勾选要管理的 QQ 群，然后点「刷新来源」把群文件元数据拉进来（只读，不下载任何文件）。
4. **随时切换群聊**：登录状态下点顶部「群聊」即可增删要搜索的群，或在左侧「群聊范围」下拉里按群收窄检索与问答——无需手改 `config.json`。

### 从源码
```bash
git clone https://github.com/ericzou090124/ericzou-01.git
cd ericzou-01
pip install -r requirements.txt      # 仅需可选增强；核心功能零依赖
python server.py                      # 浏览器打开 http://127.0.0.1:8787
```

更完整的图文教程见 [docs/INSTALL.md](docs/INSTALL.md)。

---

## 架构

**分层**：`web/` → `server.py` → `catalog / classify / download / ai` → `qq / extract / vault / index / llm` → `state/`。

- `catalog`：全系统唯一事实源（单值 `领域/学科/类型` + 多归属标签），提供树与查询，并内置完整性门禁与树一致性门禁。
- `classify`：单值三级分类 + 多归属标签 + 别名召回扩展。
- `qq`：NapCat OneBot 11 只读遍历 + 定向下载（令牌从本机配置自动读取）。
- `index`：SQLite FTS5 全文索引（增量同步，绝不重建丢数据）。
- `vault`：Obsidian 独立新库生成（多级大纲 MOC、单文件预览笔记、插件部署）。
- `ai`：FTS5 检索优先、LLM 作答、防臆造降级。

---

## HTTP API（概览）

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/health` | GET | 健康检查 + 索引篇数 + 来源模式 |
| `/api/state` | GET | 完整状态：来源、统计、设置、下载上限、分类完整性 |
| `/api/tree?dim=subject\|kind\|source&node=[]` | GET | 单值分类树（节点计数之和 == 文件总数） |
| `/api/files?dim=...&node=[]&q=&limit=&kind=` | GET | 某分类/搜索下的文件列表（含总数） |
| `/api/file?id=` | GET | 单文件元数据 + 正文片段 |
| `/api/ask?q=&fast=&scope=` | GET/POST | AI 问答（防臆造） |
| `/api/download` | POST | 显式确认后下载到 Obsidian（必须 confirm=true） |
| `/api/refresh` | POST | 只读刷新来源元数据（不下载） |
| `/api/reclassify` | POST | 词库升级后原地重算分类（只改分类字段） |
| `/api/qqlogin/*` | GET/POST | QQ 登录二维码、快速登录、恢复在线 |
| `/api/napcat/*` | GET/POST | NapCat 安装自检 / 配置修复 / 启动 |
| `/api/settings` · `/api/settings/test` | GET/POST | AI 设置与连接测试 |
| `/api/diagnose` | GET | 配置自检 + 来源/索引/库路径 |
| `/api/setup` · `/api/setup/config` · `/api/setup/done` | GET/POST | 首次配置向导 |

---

## 配置（`config.json`）

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `port` | `8787` | 本地服务端口（只监听 127.0.0.1） |
| `sources.qq.groups` | 三个示例群 | 要管理的 QQ 群（`display` + `qq_group`） |
| `allowed_ext` | 文档/表格/图片/压缩包 | 允许进入目录的文件扩展名 |
| `max_download_per_batch` | `30` | 单批下载上限 |
| `classification.domains` | 8 领域 | 领域关键词 |
| `classification.subjects` | 29 科目 | 学科关键词（命中全名额外加权） |
| `classification.kinds` | 13 类型 | 资源类型关键词 |
| `classification.aliases` | 相关主题 | 同义/相关主题，用于搜索召回扩展 |
| `ai` | 本地模型 | LLM 来源、base_url、model、api_key（写 `state/secrets.json`） |

---

## 自测

```bash
python tools/smoke_test.py       # 回归自测：分类一致性 / 完整性 / 下载 / AI / 配置 / 集成
python tools/test_v3.py           # 真实 HTTP 服务端到端（单值分类一致性 / 刷新 / 召回 / 不错分）
python tools/reclassify.py        # 词库升级后原地重算（带四道门禁）
```

---

## 常见问题

**Q：界面打不开 / 显示连接被拒绝？**
A：确认 `start.bat` 或 `python server.py` 正在运行。`v3.2.0` 起服务**先启动再后台刷新来源**，即使 NapCat 未登录也不会卡在启动；若刷新长时间无响应，点顶部「刷新来源」即可。

**Q：分类数量对不上 / 出现空分类？**
A：`v3.2.0` 已彻底修复——分类改为单值维度，并新增树一致性门禁，每个节点的文件数加起来一定等于总数，不会出现空分类。

**Q：为什么只支持 QQ 群文件？**
A：微信没有列出群文件全目录的开放接口，且聊天库加密、本项目绝不读取。当前版本聚焦于 QQ 群文件的只读盘点与整理。

**Q：没装 jieba / wcferry / pymupdf 能跑吗？**
A：能。三者都是可选增强：jieba 缺失回退 3-gram，pymupdf 缺失 PDF 只登记元数据。启动自检会把它们列为提醒而非错误。

---

## 版本历史（摘要）

- **v3.2.0**：修复分类计数不一致/空分类/错分（多值 → 单值维度）；删除微信登录与分类体系；精简为「分类整理 / 下载到 Obsidian / AI 问答」三件事的简洁界面；服务启动不再阻塞。
- **v3.1.0**：内容驱动的泛化分类，工作群资料也能精细归类。
- **v3.0.0**：登录/安装/分类/微信四条链路实测修复。
- 更早版本：详见 [docs/CHANGELOG.md](docs/CHANGELOG.md)。

---

许可证：MIT（见 [LICENSE](LICENSE)）。
