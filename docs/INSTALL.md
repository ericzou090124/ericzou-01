# 从这里开始 · 零基础安装与使用指南

> **一句话**：下载 1 个文件 → 双击 → 浏览器自动打开 → 跟着向导点几下 → 你的 QQ / 微信群文件就变成了一个能搜、能问、能在 Obsidian 里读的本地知识库。
>
> 全程不用命令行、不用改配置、不用懂 Python。本文是**唯一权威入口**，其它文档都是补充。

---

## 🚀 先看这里：3 分钟速通

| 步骤 | 你要做的事 | 预计 |
| --- | --- | --- |
| 1 | 装好 Python（只做一次，见 [准备工作](#-准备工作一次性)） | 1 分钟 |
| 2 | [点这里下载一键安装器](#-我该下载哪个文件)，下载完**双击它** | 30 秒 |
| 3 | 等浏览器自动打开 `http://127.0.0.1:8787`，按页面上的「首次配置」向导点 3 下 | 1 分钟 |

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
2. **QQ 群文件功能**：需要本机跑一个叫 [NapCat](https://napneko.github.io/) 的本地登录工具（用手机 QQ 扫码，不保存账号密码）。**不用提前装**，首次配置向导会带你做；也可以点界面顶栏「QQ 登录」→「启动 NapCat」。
3. **以下都是可选的，不装程序照样能用**：
   - Obsidian（用来阅读生成的知识库）
   - 本地大模型 / OpenAI 兼容接口（AI 问答；不配就自动用「原文摘录」模式）
   - WeChatFerry（微信监听采集；默认关闭，见 [FEATURES.md](FEATURES.md)）

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

## 🧭 首次配置向导（界面里点 3 下）

第一次打开界面，顶部会出现一条**「首次配置」**横幅，点「开始配置」：

| 向导步骤 | 你要做的 |
| --- | --- |
| **① 装 NapCat** | 按提示下载 NapCat 一键包并启动，用**手机 QQ 扫码**登录。保持它开着；控制台 `http://127.0.0.1:6099/webui` |
| **② 填 QQ 群** | 点「① 自动列出我的群并勾选」，勾选要管理的群；或手动每行填 `群显示名,群号`（如 `考研资料群,123456789`）→ 保存并继续 |
| **③ 完成** | 点「打开登录页并进入主界面」，扫码后自动跳回，左侧分类树就会出现你的群文件 |

> 配置只写在本机 `config.json`，不上传任何地方。以后想加 / 减群，再跑一次向导即可。
> **没有 NapCat / 没登录 QQ 也能用**：程序会进入「离线快照」模式，用本地已有的清单浏览和检索，只是不能下载新文件。想体验效果可以先跳过第 ① 步。

---

## 🔄 完整使用闭环（做完这 6 步就复刻成功了）

```mermaid
flowchart LR
    A[下载安装器] --> B[双击启动]
    B --> C[首次配置向导]
    C --> D[刷新来源<br/>只读列群文件]
    D --> E[三级分类浏览<br/>领域 / 科目 / 类型]
    E --> F[勾选 + 显式确认下载]
    F --> G[全文检索 / 问 AI]
    G --> H[Obsidian 打开知识库]
    H --> D
```

| # | 在界面上怎么做 | 会发生什么 |
| --- | --- | --- |
| 1 | 顶栏点 **「刷新来源」** | 只读遍历群文件目录，自动生成分类；**不会下载任何文件** |
| 2 | 左栏点开分类树（领域 → 科目 → 类型） | 中栏列出该节点文件，可搜索、筛选、预览元数据 |
| 3 | 勾选文件 → 点 **「下载已选」** → 在确认框里确认 | 下载原文件到 Obsidian 库，抽取正文、生成笔记与摘要。**必须显式确认**，不会偷偷下载 |
| 4 | 顶栏搜索框输入关键词 → 回车，或点 **「问 AI」** | 命中处高亮；AI 只在**已下载正文**里找依据并标注来源，找不到就直说找不到，不瞎编 |
| 5 | 打开 Obsidian → 「打开文件夹作为库」→ 选界面上显示的库路径 | 看到自动生成的分类大纲与每篇文件的笔记，可直接点开原附件 |
| 6 | 顶栏点 **「系统诊断」** | 一眼看到配置是否正常、QQ 是否在线、索引多少篇、库在哪。有问题照提示修 |

> 库的默认位置：`~/Desktop/资源管理`（**新建独立库，绝不动你原有的笔记**）。在 `config.json` 的 `vault` 字段可改。

<details>
<summary><b>想用微信群文件？</b></summary>

微信侧是**监听式采集**，默认关闭，且只能收到「开启捕获之后」新发的文件（微信没有列出群文件全目录的开放接口）。启用方式：装 WeChatFerry → `config.json` 里 `sources.wechat.wcf.enabled = true` → 用 `/api/wechat/wcf/rooms` 保存要监听的群 → 点「开始监听」。详见 [FEATURES.md](FEATURES.md)。**不碰加密聊天数据库**。

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
| 回退到旧版本 | 见 [VERSION_AUDIT.md](VERSION_AUDIT.md) 与 [CHANGELOG.md](CHANGELOG.md)，`git checkout vX.Y.Z` |

---

## ❓ 常见问题

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

NapCat 没运行或登录过期。点顶栏「QQ 登录」扫码，或点「刷新来源」。登录态恢复必须由你显式操作，程序不会拿失效的 `file_id` 硬下载。

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
<summary><b>装不上 jieba / wcferry / pymupdf 会坏吗？</b></summary>

不会。三者都是可选增强：缺 jieba 自动回退 3-gram 分词，缺 wcferry 只是微信不可用，缺 pymupdf 时 PDF 只登记元数据。「系统诊断」里会标为提醒而不是错误。

</details>

<details>
<summary><b>我的资料会不会被上传 / 泄露？</b></summary>

不会。服务只监听 `127.0.0.1`，不对外暴露；所有资料、索引、密钥只在本机；`state/` 已被 gitignore。对 QQ / 微信只读或只监听，不修改群内任何内容。

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
| 看微信监听采集 / 群文件三级分类的实现细节 | [FEATURES.md](FEATURES.md) |
| 看全部历史版本是否可用、如何回退 | [VERSION_AUDIT.md](VERSION_AUDIT.md) |
| 看每次迭代改了什么 | [CHANGELOG.md](CHANGELOG.md) · [开发者日志 DEVLOG.md](DEVLOG.md) |
| 看验收清单与版本存档说明 | [RELEASE.md](RELEASE.md) |
| 看设计缘由（为什么这么做） | [GUIDE.md](GUIDE.md) · [ARCHITECTURE.md](ARCHITECTURE.md) |
| 更口语化的图文引导（另一份，内容更短） | [新手上手指南.md](新手上手指南.md) |

---

## 许可

本项目采用 [MIT 许可证](../LICENSE)：可自由使用、修改、二次分发，保留版权声明即可。

**还卡住了？** 到 [Issues](https://github.com/ericzou090124/ericzou-01/issues) 提一个问题，附上「系统诊断」面板截图与报错文字即可。
