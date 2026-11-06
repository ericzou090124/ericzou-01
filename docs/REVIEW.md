# 系统审查报告 · resource-manager

> 审查时间：2026-11-07 · 审查范围：整套程序体系（表现层 / 服务层 / 领域层 / 基础层 / 数据层）
> 结论：架构清晰、分层合理、安全边界到位；主要可优化点在**检索精度、运行期开销、数据源扩展性**三处。

---

## 1. 系统概览（架构复盘）

```
表现层   web/ 单页应用（原生 HTML/CSS/JS，零构建）   obsidian_plugin/（资源 AI 搜索）
   │  fetch /api/*                                          │ requestUrl /api/ask
服务层   server.py · ThreadingHTTPServer（仅 127.0.0.1:8787）
   │
领域层   catalog.py ─ classify.py ─ download.py ─ ai.py
   │              │             │            │
基础层   qq.py / wechat.py   extract.py   vault.py   index.py   llm.py
   │
数据层   state/catalog.json  state/index.db  state/bodies/  桌面/资源管理/
```

设计亮点（保留，不作为优化目标）：
- **单一事实源**：`catalog.json` 同时驱动树、大纲、AI、下载状态，避免多处状态不一致。
- **命中判定与内容生成解耦**：检索/统计由本地确定性逻辑给出，模型只做中文概括，无权判断「有没有」，从根上杜绝幻觉式「没有/有」。
- **不可变安全边界**：服务只绑 127.0.0.1；前端 `catalog.public()` 白名单绝不下发 `file_id`/令牌/本地缓存绝对路径；下载必须显式确认，绝不隐式扩到全量 12.7 GB。
- **离线快照兜底**：QQ 接口不可用时回落 `qq_manifest.json`，只预览元数据、锁下载。

---

## 2. 逐模块评估

| 模块 | 职责 | 评价 | 主要问题 |
|---|---|---|---|
| `config.py` | 配置/路径/密钥 | 稳 | 无缓存，`settings()` 每次读盘 |
| `catalog.py` | 统一目录（事实源） | 稳 | `load()` 每次重新 `json.loads`；`query/tree` 全量线性扫描 |
| `classify.py` | 三级分类 | 可用 | 关键词子串匹配，对「高代/数分/复变」等易混淆科目靠配置顺序补，缺分词 |
| `index.py` | FTS5 全文索引 | 关键瓶颈 | ① 每次 `search/count` 重新 `connect()` 开 SQLite 连接；② `query_terms` 用**滑动 3-gram** 切中文，精度低（「考试」命中「考场」）；③ `rebuild` 每次重读全部 body 文件 |
| `ai.py` | 范围受限问答 | 已修（v1.3.0） | 已做科目/类型识别+范围限定；但底层检索词仍是 3-gram，精度受 `index` 制约 |
| `extract.py` | 正文抽取+摘要 | 稳 | 零依赖；PDF 需可选 PyMuPDF；图片不 OCR（合理） |
| `download.py` | 确认闸门+入库 | 稳 | 每批后 `index.rebuild(cat)` 全量重建（O(n)，可增量） |
| `qq.py` | NapCat OneBot 读取 | 稳 | 探活/兜底完善 |
| `wechat.py` | 微信数据源 | **占位** | 安全原因不做登录；仅「本地授权目录」只读——**未覆盖「群文件」获取**，是扩展点 |
| `vault.py` | Obsidian 库/大纲 | 稳 | — |
| `llm.py` | 模型适配 | 稳 | OpenAI 兼容 + 本地 Bonsai2；无流式、无重试退避 |
| `server.py` | HTTP 服务 | 稳 | 全局 `CAT` 缓存，但 `ai.answer` 默认分支仍可能 `catalog.load()` |

---

## 3. 性能瓶颈（按影响排序）

1. **CJK 检索词粒度粗（最高优先级）**
   `index.query_terms` 把中文按窗口 3 切分（`高等代数考试内容`→`高等代/等代数/代数考/…`），FTS5 trigram 再按 3 字子串匹配。后果：
   - 召回噪声大：「考试」匹配「考场」「试卷」匹配「答卷」；
   - 无法区分「高等代数」与「高等数学」的语义边界；
   - `ai` 的 `valid2` 覆盖率闸门因此被放宽，间接放大跨科目风险。
   → **引入中文分词（jieba，可选依赖、优雅降级）** 可显著提升精度。

2. **SQLite 连接反复开关**
   `index.search` / `index.count` 每次 `connect()` 新建连接并 `CREATE VIRTUAL TABLE IF NOT EXISTS`（触发一次元数据检查）。高并发（多线程）下连接创建开销叠加。
   → 用 `threading.local` 缓存只读连接；`count()` 结果内存缓存。

3. **`catalog.load()` 重复反序列化**
   每次 `/api/ask|files|tree|state` 都重新读 `catalog.json` 并 `json.loads`（1600+ 条目）。`ensure()` 已缓存全局 `CAT`，但 `ai.answer` 默认分支与直接调用仍走 `load()`。
   → 加「mtime + 大小」校验的进程内缓存，文件不变直接命中。

4. **全量索引重建**
   `download.run` 每批后 `index.rebuild(cat)` 重读全部 body。单批 30 个文件却重建 1600 篇。
   → 改为「增量 upsert」：仅对本次变更 id 重写 FTS 行（body 已在内存）。

5. **`_hay` 重复拼接**
   `ai.py` 打分循环对每个候选重拼 9 字段字符串。可预计算一次缓存到 item。

---

## 4. 可优化方向与可行性

| # | 方向 | 收益 | 风险/成本 | 优先级 |
|---|---|---|---|---|
| A | **jieba 可选分词**接入 `query_terms` + `classify` | 检索精度↑、「其他资料」↓ | 新增可选依赖，需保证无 jieba 时回退 | 高 |
| B | catalog mtime 缓存 + index 连接/计数缓存 | 运行期开销↓ | 低，纯内部 | 高 |
| C | index 增量 upsert | 下载批次响应↑ | 中，需保证一致性 | 中 |
| D | **微信(群文件)可选适配器**（GitHub: WeChatFerry/wcferry、wechaty） | 覆盖用户点名的「微信获取群文件」扩展 | 需本机配套服务+显式开启；安全边界须守住 | 高（用户点名） |
| E | 检索结果预计算 hay + 轻量排序特征 | 问答打分更稳 | 低 | 中 |
| F | llm 流式/重试退避 + 超时保护 | 大模型问答更稳 | 低 | 中 |
| G | 前端：当前范围内跨类型「统一搜索框」+ 结果高亮 | 检索体验↑ | 低 | 中 |
| H | 安装器 + 一键发布脚本（自解压 .bat） | 交付/迭代闭环 | 已完成重建 | 已做 |

> 安全红线（不可动）：127.0.0.1 绑定、前端白名单、下载显式确认、微信/聊天库不读加密数据。

---

## 5. 安全 posture

- ✅ 服务仅 `127.0.0.1`，无外网监听。
- ✅ 前端白名单 `catalog.public()` 不含 `file_id`/令牌/绝对路径。
- ✅ 密钥仅 `state/secrets.json`，已 gitignore。
- ✅ 离线快照锁下载；下载单批上限 30，绝不隐式全量。
- ⚠️ OneBot 令牌从本机 NapCat 配置动态读取（不落盘到项目），但**运行期内存**中存在，属可接受范围。
- ⚠️ 微信扩展必须保持「默认关闭 + 需用户显式授权目录或运行本机 RPC」，**绝不读取加密聊天数据库**。

---

## 6. 后续迭代路线图（本次实施）

- **迭代 0（本篇）**：git 基线 + 本审查 + 重建自解压安装器。
- **迭代 1**：性能与检索精度（A + B + E）→ jieba 可选分词、catalog/index 缓存、预计算 hay。
- **迭代 2**：GitHub 集成微信可选适配器（D）→ `lib/wechat_wcf.py`，gated、安全。
- **迭代 3**：重建安装器 + 打标签 v1.4.0 + 文档收尾。

> 目标：在「零第三方硬依赖、双击即用、安全边界不变」的前提下，把检索精度、运行开销、数据源覆盖面三处短板补齐。
