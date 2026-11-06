# Resource Manager · QQ/微信 群文件 → Obsidian 知识库

把 QQ 群 / 微信群里的课程资料、试卷、笔记自动整理成**可检索、可问答**的本地知识库，
并同步进 Obsidian 笔记库。纯 Python 标准库实现，**零第三方硬依赖**，离线可用，数据全在本机。

> 版本：v1.6.0 · 单文件分发 · 双击即用

---

## 特性

- **QQ 群文件采集**：基于本机 NapCat（OneBot 11）只读遍历群文件目录，按科目 / 类型自动归类、批量下载、入库。
- **微信群文件采集（可选，GitHub 方案集成）**：基于 [WeChatFerry](https://github.com/lich0821/WeChatFerry)（`wcferry`）的**监听式**采集，仅捕获你指定群内的文件 / 附件消息，绝不读取加密聊天库。默认关闭，需自行安装并登录微信 3.9.x。
- **本地全文检索**：SQLite FTS5（trigram）+ 可选 jieba 中文分词，命中判定与 AI 生成解耦（模型只概括，不判定「有没有」）。
- **AI 问答**：把检索范围限定到当前浏览的科目 / 领域后再生成答案，缓解「问高数却答复变」的串味问题。
- **Obsidian 同步**：自动生成大纲笔记与附件链接，直接在你的 Obsidian 库中阅读。
- **Web 管理界面**：浏览分类树、全文搜索、按类型筛选、AI 助手对话。
- **自解压安装器**：`resource-manager-installer.bat` 双击即解压到 `RM_INSTALL_TARGET`（默认当前目录）并启动。

---

## 快速开始

### 方式一：安装器（推荐，给最终用户）

1. 双击 `resource-manager-installer.bat`。
2. 默认解压到同目录下的 `resource-manager/`，并自动启动服务。
3. 浏览器打开 `http://127.0.0.1:8787`，即可使用。

可选环境变量：

- `RM_INSTALL_TARGET=C:\path\to\dir`：指定解压目录。
- `RM_NO_LAUNCH=1`：只解压不启动。

### 方式二：源码运行（开发者）

```bash
# 1) 准备（可选）中文分词，提升检索精度
pip install -r requirements-optional.txt     # 含 jieba；不想装可跳过

# 2) 启动
python server.py
# 首次会刷新来源、建索引，然后监听 http://127.0.0.1:8787

# 3) 打开界面
#   http://127.0.0.1:8787
```

### 可选依赖

| 包 | 用途 | 不装会怎样 |
| --- | --- | --- |
| `jieba` | 中文分词，检索词更精准 | 自动回退到滑动 3-gram，功能不受影响 |
| `wcferry` | 微信监听式采集 | 微信源不可用，其余功能不受影响 |

关闭 jieba：`set RM_NO_JIEBA=1`（或环境变量）后再启动。

---

## 配置

见 `config.json`：

- `host` / `port`：服务监听地址，默认 `127.0.0.1:8787`（仅本机）。
- `sources.qq`：QQ 群列表（`pxb6` / `nzf4` / `xfq12` 三个示例群）。
- `sources.wechat.wcf`：微信采集开关，默认 `enabled: false`（见下方「启用微信采集」）。
- `classification`：领域 / 科目 / 类型 词库，可自由增删。
- `ai`：本地或远程 OpenAI 兼容接口（默认 `provider: local`，指向本机 8080 的推理服务）。

> 密钥类文件已写入 `.gitignore`（`secrets.json`、`state/secrets.json`），不会进仓库。

---

## 启用微信采集（GitHub 方案）

1. 安装并运行 [WeChatFerry](https://github.com/lich0821/WeChatFerry) 客户端，登录**微信 3.9.x**。
2. `pip install wcferry`。
3. 在 `config.json` 把 `sources.wechat.wcf.enabled` 设为 `true`，按需调整 `host` / `port`（默认 `127.0.0.1:10086`）。
4. 启动 `python server.py`，在 Web 界面「微信」面板启动捕获并指定要监听的群。
5. 捕获到的文件元数据以 5 秒防抖并入目录，自动增量重建索引与 Obsidian 大纲。

> ⚠️ 仅监听你指定群内的文件 / 附件消息；不读取任何加密聊天记录。使用前请遵守微信平台规则与当地法律。

---

## 架构

```
表现层   web/ (管理界面)  +  obsidian_plugin/ (Obsidian 对话插件)
   │
服务层   server.py  (ThreadingHTTPServer, 仅 127.0.0.1:8787)
   │
领域层   catalog(分类/清单) · classify · download · ai(问答)
   │
基础层   qq(OneBot) · wechat_wcf(微信监听) · extract · vault(Obsidian) · index(FTS5) · llm
   │
数据层   state/catalog.json · state/index.db · state/bodies/ · 桌面/资源管理 (Obsidian 库)
```

核心数据流：`来源刷新 → 归类 → 选择 → 下载 → 入库 → 建索引 → Obsidian 大纲 → AI 检索问答`。

---

## 持续迭代与回归

本仓库按版本持续迭代（见 `docs/CHANGELOG.md` 与 `docs/DEVLOG.md`）：

- `docs/REVIEW.md`：系统审查、性能瓶颈排序与优化路线图。
- `tools/smoke_test.py`：**回归自测**。每次修改核心链路后运行，退出码 0 即通过：

  ```bash
  python tools/smoke_test.py
  ```

- `tools/build_installer.py`：重建自解压安装器（把全程序 base64 内嵌进 `.bat`）。

### 版本一览

| 版本 | 内容 |
| --- | --- |
| v1.3.0 | 仓库基线 + 分类检索细化 |
| v1.4.0 | 检索精度与运行期开销优化（jieba / 缓存） |
| v1.5.0 | GitHub WeChatFerry 监听式微信适配器 |
| v1.6.0 | 索引增量同步 + 回归自测 |

---

## 安全与隐私

- 所有数据存于本机，服务仅监听回环地址 `127.0.0.1`，不外网暴露。
- QQ / 微信接入均为**只读 / 监听式**，不修改云端群任何内容，不读取加密聊天库。
- 未安装可选依赖时全部**优雅降级**，核心功能不受影响。
