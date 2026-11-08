# 从这里开始 · 零基础安装与使用指南

> **一句话**：下载 1 个文件 → 双击 → 浏览器自动打开 → 顶栏「群聊」读取并框选全部群、主页「Obsidian 知识库」一键导入 → **Obsidian 自动打开导入报告** → 你的 QQ 群文件就变成了一个能搜、能问、能在 Obsidian 里读的本地知识库。
>
> 全程不用命令行、不用改配置、不用懂 Python。本文是**唯一权威入口**，其它文档都是补充。

---

## 🚀 先看这里：3 分钟速通

| 步骤 | 你要做的事 | 预计 |
| --- | --- | --- |
| 1 | 装好 Python（只做一次，见 [准备工作](#-准备工作一次性)） | 1 分钟 |
| 2 | [点这里下载一键安装器](#-我该下载哪个文件)，下载完**双击它** | 30 秒 |
| 3 | 等浏览器自动打开 `http://127.0.0.1:8787`，顶栏「群聊」框选 QQ 群 → 主页「Obsidian 知识库」点「一键批量导入」→ Obsidian 自动打开报告 | 1 分钟 |

就这三步。下面所有内容，都是给你「卡住了」或者想深挖时看的。

---

## 📥 我该下载哪个文件

打开 [**最新版 Releases 页面**](https://github.com/ericzou090124/ericzou-01/releases/latest)，在页面最下方的 **Assets（附件）** 区域能看到下面这些文件：

| 文件 | 给谁 | 怎么用 |
| --- | --- | --- |
| ⭐ **`resource-manager-installer.bat`** | **绝大多数人 / 小白首选** | 下载后**直接双击**，自动解压 + 自动启动 + 自动开浏览器。不需要先解压任何东西 |
| `resource-manager-full.zip` | 想「把仓库全部内容都下载下来」、离线保存、或要改代码的人 | **先解压整个压缩包**到任意文件夹（右键 → 全部提取），再双击里面的 `start.bat` |
| `SHA256SUMS.txt` | 想核对文件是否被篡改的人 | 可选，见 [校验文件完整性](#-校验文件完整性可选) |

**固定直链（永远指向最新版，可以收藏）**

- 一键安装器： https://github.com/ericzou090124/ericzou-01/releases/latest/download/resource-manager-installer.bat
- 完整压缩包： https://github.com/ericzou090124/ericzou-01/releases/latest/download/resource-manager-full.zip
- 全部历史版本： https://github.com/ericzou090124/ericzou-01/releases
- GitHub 自动生成的源码归档（也可拿全部内容）： https://github.com/ericzou090124/ericzou-01/archive/refs/heads/main.zip

> ⚠️ **别踩这个坑**：如果你下载的是 `.zip`，**一定要先解压**，不要在压缩包预览窗口里直接双击里面的 `.bat`。Windows 会把单个文件临时抽出来运行，程序找不到同目录的其它文件就会报错。`installer.bat` 是唯一的例外——它是自解压的，直接双击没问题。

---

## 🧰 准备工作（一次性）

1. **安装 Python 3.10 或更高版本**（Windows / macOS 通用）
   - 官网下载：https://www.python.org/downloads/
   - Windows 安装时**务必勾选最下面的 `Add python.exe to PATH`**，然后点 Install Now。漏勾会导致双击没反应。
   - 验证（可选）：按 `Win + R` 输入 `cmd` 回车，敲 `python --version`，能显示版本号就成功。
2. **QQ 群文件功能**：需要本机跑一个叫 [NapCat](https://napneko.github.io/) 的本地登录工具（用手机 QQ 扫码，不保存账号密码）。**`install.bat` 会自动检测并修好它的配置**（v3.0.0 起）；没装的话安装器会给你两种明确安装方式。扫码在资源管理器的「QQ 登录」页完成，**不用打开 NapCat 控制台**。
3. **以下都是可选的，不装程序照样能用**：
   - Obsidian（用来阅读生成的知识库；装了才能体验「导入后自动打开」）
   - 本地大模型 / OpenAI 兼容接口（AI 问答；不配就自动用「原文摘录」模式）
   - 可选 Python 包（PyMuPDF 抽 PDF 正文、jieba 分词等）；**v3.2.0 起已移除微信登录与采集链路，不再需要 WeChatFerry**

---

## 🪟 安装（Windows，推荐路径）

**第 1 步**：下载 `resource-manager-installer.bat`（链接见上）。
浏览器若提示「此文件可能有害」，选择**保留**——它是纯文本批处理脚本，内容可直接用记事本打开检查。

**第 2 步**：**双击**它。会弹出一个黑色窗口，自动依次完成：

```text
[资源管理] 正在解压安装包，请稍候…
[资源管理] 已解压 NN 个文件到 C:\Users\你的用户名\resource-manager
[资源管理] 正在启动本地服务（仅本机 127.0.0.1:8787）…
[资源管理] 浏览器已打开 http://127.0.0.1:8787
```

**第 3 步**：浏览器打开 `http://127.0.0.1:8787` 就成功了。如果没自动打开，手动在地址栏输入这个地址。

<details>
<summary><b>如果黑窗口提示「未检测到 Python」怎么办？</b></summary>

回到上面的「准备工作」重装 Python 并勾选 `Add python.exe to PATH`，**重启一次电脑**，然后再双击安装器。已经解压好的程序在 `C:\Users\你的用户名\resource-manager`，之后直接双击里面的 `start.bat` 即可，不用重新下载。

</details>

**程序装在哪**：`C:\Users\你的用户名\resource-manager`。
下次要启动，进这个文件夹双击 `start.bat`；要停止，双击 `tools\stop.bat` 或直接关掉那个名为 `python` 的服务窗口。

<details>
<summary><b>我下载的是 resource-manager-full.zip（完整包）怎么装？</b></summary>

1. 右键 zip → 「全部提取 / Extract All」→ 选一个空文件夹（例如 `D:\resource-manager`）→ 提取。
2. 进入解压后的文件夹，确认里面能同时看到 `server.py`、`start.bat`、`install.bat`、`START_HERE.txt` 和 `tools\` 子目录。
3. 双击 `start.bat` 启动（或双击 `install.bat` 顺带装可选增强）。浏览器会自动打开界面。
4. 完整包里包含**全部源码、全部文档、一键安装器、教程、开发者日志**，离线也能看。

</details>

---

## 🧭 第一次使用：登录与选群（不用手改配置）

| 步骤 | 你要做的 |
| --- | --- |
| **① 装 NapCat 并登录** | `install.bat` 已自动完成安装自检与配置修复（也可单独双击 `tools/setup_napcat.bat`）。然后点顶栏「QQ 登录」：NapCat 没运行会**自动拉起**，二维码直接显示在这个页面上，用**手机 QQ 扫码**确认即可。**不需要打开任何 NapCat 控制台**；二维码会过期自动换新，也可以随时点「刷新二维码」 |
| **② 框选 QQ 群** | 点顶栏「**群聊**」按钮 →「读取我的 QQ 群」：会列出本 QQ 加入的**全部群**（实测 28 个），可按群名/群号搜索、全选/全不选、逐个勾选，点「保存选择」一次写入。离线时也能列出本机目录里缓存的真实群号，仍可框选；还可手动填群号加入列表。保存后自动点「刷新来源」 |
| **③ 收窄范围** | 左栏「群聊范围」下拉选「全部群聊」或某个群，分类树、文件列表与 AI 问答会一起按该群收窄 |

> 配置只写在本机 `config.json`，不上传任何地方。以后想加 / 减群，随时点「群聊」即可，**不需要重跑向导**。
> **没有 NapCat / 没登录 QQ 也能用**：程序会进入「离线快照」模式，用本地已有的清单浏览和检索；`v3.4.0` 起还可以从本机已另存的群文件继续导入（见下方「QQ 直链异常」）。

---

## 🔄 完整使用闭环（做完这 6 步就复刻成功了）

```mermaid
flowchart LR
    A[下载安装器] --> B[双击启动]
    B --> C[群聊按钮选群]
    C --> D[刷新来源<br/>只读列群文件]
    D --> E[分类整理<br/>学科 / 类型 / 来源]
    E --> F[一键批量导入<br/>可选已有库 / 新建库]
    F --> G[自动分类入库<br/>笔记(含全文) + 大纲 🆕]
    G --> H[自动打开 Obsidian<br/>本次导入报告 + AI 读全文]
    H --> D
```

| # | 在界面上怎么做 | 会发生什么 |
| --- | --- | --- |
| 1 | 顶栏点 **「群聊」** → **「刷新来源」** | 确认要搜索的 QQ 群，只读遍历群文件目录、自动生成分类；**不会下载任何文件** |
| 2 | 左栏「分类方式」选 学科 / 类型 / 来源，点节点下钻 | 中栏列出该节点文件，可搜索、筛选、预览元数据；每个节点的数字加起来一定等于总数 |
| 3 | 主页「Obsidian 知识库」卡片点 **「一键批量导入到 Obsidian」**，选目标库、勾选确认 | 弹窗里可「挑选已有库」或「新建库」；自动下载 / 导入原文件，抽取正文并按「来源 / 群聊 / 领域 / 学科 / 类型」分类落盘，生成含完整正文的预览笔记与多级大纲，新文件带 🆕。**必须显式确认**，单批最多 30 个 |
| 4 | 导入完成，**Obsidian 会自动打开** | 自动用 `obsidian://open` 定位到 `00-本次导入.md` 报告：新增文件落在哪些原有分类、每份多少字正文、可点开的笔记链接。网页同时弹出「导入完成 · 现在就能看到成效」结果卡 |
| 5 | 右栏「AI 问答」口语提问，或卡片上点 **「库内 AI 检索」** | 任意学科都能大量召回（「罗尔中值定理」「马原」「线代」等），回答给出共命中份数与可点击索引；库内检索可选「全部资料（含元数据）」或「仅本库已导入」，命中项可一键「读取全文」 |
| 6 | 卡片上的实时库状态 / **「在 Obsidian 打开」** | 一眼看到已入库 / 待导入 / 笔记 / 大纲 / AI 插件状态、导入报告与库路径（点一下即可复制）；右侧栏「资源 AI 搜索」插件 v1.2.0 可选三种检索范围 |

> 库的默认位置：`~/Desktop/QQ群资料Obsidian库`（**新建独立库，绝不动你原有的笔记**）。也可点「挑选 / 新建库」选本机已有库：会**保留它原有的 Obsidian 设置**，只追加 AI 插件，并把已导入的资料与笔记迁移过去。

<details>
<summary><b>QQ 直链异常 / 没登录 QQ 时还能导入吗？</b></summary>

能。`v3.4.0` 起，若 NapCat / QQNT 的群文件内核异常（`get_group_file_url` 拿不到直链），一键批量导入会**自动改走本机已另存的群文件**：把 QQ 群文件另存到 `config.json` 的 `local_import_dirs` 目录（默认含桌面「QQ资料自动入库」与工作区 inbox），程序只认文件名与目录元数据精确一致、扩展名在白名单内的真实文件，同样要求显式确认与单批上限，导入后的抽取 / 笔记 / 大纲 / 检索流程完全一致。可用 `GET /api/local/scan` 先盘点有多少能匹配。

</details>

---

## 🛠️ 日常操作速查

| 我想… | 怎么做 |
| --- | --- |
| 启动 | 进 `C:\Users\你的用户名\resource-manager` 双击 `start.bat`，或双击安装器重新跑一遍（不会覆盖你的 `state/` 资料） |
| 停止 | 双击 `tools\stop.bat`，或关掉 python 服务窗口 |
| 更新到新版 | 重新下载最新的 `resource-manager-installer.bat` 双击即可；你的 `config.json`、`state/`、Obsidian 库都会保留。**建议先备份 `state/` 与库目录** |
| 卸载 | 停止服务 → 删除程序文件夹 → （可选）删除 `~/Desktop/资源管理` 里的生成内容。程序不写注册表、不设开机自启 |
| 验证程序是否正常 | 命令行运行 `python tools/smoke_test.py`，看到 `ALL PASS` 即正常 |
| 看看分类有没有把我的资料归错 | 顶部「**分类体系**」按钮 → 载入「工作群样例」或自己贴几行 `文件夹 \| 文件名` → 点「预览推断结果」。**这只是试跑，不会改动任何文件**；确认后可在同页新增同义词并勾选「同时重新归类现有目录」 |
| 换一种角度看资料 | 左栏「分类大纲」的下拉框可切到「按体裁（内容驱动）」「按动态主题」「按文件模态」「按主题标签」「按旧三级分类」「按来源」 |
| 回退到旧版本 | 见 [VERSION_AUDIT.md](VERSION_AUDIT.md) 与 [CHANGELOG.md](CHANGELOG.md)，`git checkout vX.Y.Z` |

> **分类不挑群**：不管是课程群、工作群还是项目群，用的都是同一套内容驱动的受控词表，不会硬编码「学生一套目录 / 上班一套目录」。工作群里的合同、进货单、报销单、会议纪要会自动落到各自的体裁；找不到明确体裁的文件归到中性的「参考资料」，再靠从文件夹名提取的动态主题细分。想看依据，点任一文件的「预览」，里面有命中词、引擎和置信度。

---

## ❓ 常见问题

<details>
<summary><b>双击一键安装器提示「'-ExecutionPolicy' is not recognized… / 解压失败」？</b></summary>

这是 **v2.9.0 及更早的 `resource-manager-installer.bat` 的已知缺陷**，已在 **v2.9.1** 修复：旧安装器把带中文的长命令直接交给 cmd，中文在 `chcp 65001` 下会破坏命令行的引号配对，导致整条命令被拆断。

处理只需一步：**重新下载**。请从 [最新版 Release](https://github.com/ericzou090124/ericzou-01/releases/latest) 重新下载 `resource-manager-installer.bat`（或直接用固定直链 [点这里下载](https://github.com/ericzou090124/ericzou-01/releases/latest/download/resource-manager-installer.bat)），覆盖旧文件后双击即可。直链文件名固定，永远指向最新版。

如果仍然失败：① 换用 `resource-manager-full.zip`，先「全部提取」到空文件夹再双击 `start.bat`；② 确认下载完整（可在 PowerShell 里用 `Get-FileHash` 对照 `SHA256SUMS.txt`）；③ 把黑窗口里的报错截图发出来。

</details>

<details>
<summary><b>双击 bat 没反应 / 一闪而过？</b></summary>

99% 是 Python 没装或没勾 `Add python.exe to PATH`。重装并勾选后重启电脑。也可在程序文件夹按住 `Shift` + 右键 →「在此处打开终端」→ 输入 `python server.py`，把报错截图留下来排查。

</details>

<details>
<summary><b>浏览器打不开 / 显示无法访问？</b></summary>

① 确认黑色服务窗口还开着；② 手动访问 `http://127.0.0.1:8787`（**不是** `localhost` 带端口以外的地址）；③ 若提示端口被占用，在 `config.json` 改 `port` 后重启；④ 公司代理环境请让浏览器直连 `127.0.0.1`。

</details>

<details>
<summary><b>提示「离线快照」，下载按钮点不动？</b></summary>

NapCat 没运行或登录过期。点顶栏「QQ 登录」：页面会自动拉起 NapCat 并显示二维码，手机 QQ 扫码确认后自动恢复在线来源；或点「刷新来源」。若提示「未检测到 NapCat」，双击 `install.bat` / `tools/setup_napcat.bat` 做安装自检与配置修复。登录态恢复必须由你显式操作，程序不会拿失效的 `file_id` 硬下载。

</details>

<details>
<summary><b>为什么搜不到某个文件内容？</b></summary>

未下载的文件**只有文件名和元数据**，没有正文，所以全文检索与 AI 问答不会命中内容。先把文件下载入库（第 3 步）再搜。

</details>

<details>
<summary><b>AI 说「未找到」，但我觉得库里有？</b></summary>

确认：① 顶栏面包屑当前浏览范围是否正确（AI 严格限定范围内检索）；② 该文件是否已下载；③ 在「设置」里适当调低 `min_relevance`（默认 0.22）。命中判定由本地检索给出，模型不参与判断。

</details>

<details>
<summary><b>装不上 jieba / PyMuPDF 等可选包会坏吗？</b></summary>

不会。核心功能只用 Python 标准库。缺 jieba 自动回退 3-gram 分词（v3.5.0 另有语料自适应词典与短专业词兜底，检索照常可用），缺 PyMuPDF 时 PDF 只登记元数据。「系统诊断」里会标为提醒而不是错误。微信相关依赖自 v3.2.0 起已不再需要。

</details>

<details>
<summary><b>我的资料会不会被上传 / 泄露？</b></summary>

不会。服务只监听 `127.0.0.1`，不对外暴露；所有资料、索引、密钥只在本机；`state/` 已被 gitignore。对 QQ 云端**只读**，不修改群内任何内容，也绝不读取加密聊天数据库。

</details>

<details>
<summary><b>macOS / Linux 能用吗？</b></summary>

可以跑核心服务：`bash install.sh` 或 `python3 server.py`，然后打开 `http://127.0.0.1:8787`。但 `.bat` 一键安装器是 Windows 专用；QQ 群文件依赖的 NapCat 在其它平台需自行部署。

</details>

---

## 🔐 校验文件完整性（可选）

Release 附件里附有 `SHA256SUMS.txt`。在下载目录打开终端：

```bash
# Windows PowerShell
Get-FileHash resource-manager-installer.bat -Algorithm SHA256

# macOS / Linux
sha256sum resource-manager-installer.bat
```

把输出的哈希与 `SHA256SUMS.txt` 中对应行比对，一致即文件完整。

---

## 📚 想再深入一点

| 我想… | 文档 |
| --- | --- |
| 看项目全貌、能力表、架构图、API、FAQ | [项目主页 README](../README.md) |
| 看分类与检索实现细节（含历史微信方案的取舍，v3.2.0 起微信能力已移除） | [FEATURES.md](FEATURES.md) · [ARCHITECTURE.md](ARCHITECTURE.md) |
| 看全部历史版本是否可用、如何回退 | [VERSION_AUDIT.md](VERSION_AUDIT.md) |
| 看每次迭代改了什么 | [CHANGELOG.md](CHANGELOG.md) · [开发者日志 DEVLOG.md](DEVLOG.md) |
| 看验收清单与版本存档说明 | [RELEASE.md](RELEASE.md) |
| 看设计缘由（为什么这么做） | [GUIDE.md](GUIDE.md) · [ARCHITECTURE.md](ARCHITECTURE.md) |
| 更口语化的图文引导（另一份，内容更短） | [新手上手指南.md](新手上手指南.md) |

---

## 许可

本项目采用 [MIT 许可证](../LICENSE)：可自由使用、修改、二次分发，保留版权声明即可。

**还卡住了？** 到 [Issues](https://github.com/ericzou090124/ericzou-01/issues) 提一个问题，附上「系统诊断」面板截图与报错文字即可。
