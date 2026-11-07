# 文档索引

所有说明文档集中在这里，按阅读目的选择入口。根目录 [README.md](../README.md) 是项目主页（含徽章、能力表、架构图、快速开始、API、FAQ）。

| 我想… | 读这个 |
| --- | --- |
| **第一次用 / 不知道该下载哪个文件 / 从安装到用起来的完整闭环** | **[INSTALL.md](INSTALL.md)** ⭐ 零基础唯一入口（下载 → 双击 → 向导 → 下载资料 → 问答 → Obsidian） |
| **了解微信群文件监听采集 / 群文件三级自动分类**（新增功能详解） | [FEATURES.md](FEATURES.md) |
| **查看全部历史版本的可用性检测结果** | [VERSION_AUDIT.md](VERSION_AUDIT.md)（由 `tools/version_audit.py` 生成） |
| 验收、看这次到底交付了什么 | [RELEASE.md](RELEASE.md) — 存档说明 + 逐项验收清单 + 全版本记录 |
| 快速上手、查接口、看权限表、FAQ | 根目录 [README.md](../README.md) |
| 查版本变化摘要 | [CHANGELOG.md](CHANGELOG.md) |
| 追溯开发过程、每次决策与故障处理（开发者日志） | [DEVLOG.md](DEVLOG.md) — 按时间顺序，v1.0.0 ~ v3.0.0 共 17 轮迭代 |
| 了解整体流程 / 模块 / 数据流 / 界面交互 / 权限降级（设计阶段产物） | [DESIGN.md](DESIGN.md) |
| 通读一遍，明白「为什么这样设计」 | [GUIDE.md](GUIDE.md) — 说明性文字，不重复表格 |
| 看技术实现路线与代码结构 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 查系统审查、性能瓶颈排序与优化路线图 | [REVIEW.md](REVIEW.md) |
| 查本地试跑结果、耗时、修过的问题、已知限制 | [VERIFICATION.md](VERIFICATION.md) |
| 查 GitHub 仓库与后续提交约定 | [PUSH.md](PUSH.md) |
| 纯图文新手引导 | [新手上手指南.md](新手上手指南.md) |

## 建议阅读顺序

- **第一次来 / 想快速判断项目是否适合自己**：根目录 `README.md` → `FEATURES.md`（若关心微信或分类）→「快速开始」。
- **验收者**：`RELEASE.md` → 根目录 `README.md` → `VERSION_AUDIT.md` → `VERIFICATION.md`。
- **接手维护的开发者**：`GUIDE.md` → `ARCHITECTURE.md` → `DEVLOG.md` → `CHANGELOG.md` → `server.py` → `lib/`。
- **只想用起来（零基础）**：**`INSTALL.md`** 从头照做即可；不用读 `README.md` 的技术章节。
- **只想用起来（熟悉命令行）**：根目录 `README.md` 的「快速开始」和「Web 管理界面」两节即可。
- **要回退版本**：先看 `VERSION_AUDIT.md` 的结论与补丁标签表，再 `git checkout <tag>`。

## 文档分工原则

- 设计说明写「打算怎么做」，实现后不回改结论，差异记在 `VERIFICATION.md` 与 `DEVLOG.md`。
- 验证数据只在 `VERIFICATION.md`，过程叙述只在 `DEVLOG.md`，版本摘要只在 `CHANGELOG.md`。
- 接口与操作清单只在根目录 `README.md`；`FEATURES.md` 只写两个重点功能的实现细节；`GUIDE.md` 只写解释性文字，避免多处重复维护。
- `VERSION_AUDIT.md` 由工具生成，**不要手工编辑**；要更新请运行 `python tools/version_audit.py`。

## 维护工具

| 工具 | 用途 |
| --- | --- |
| `tools/smoke_test.py` | 18 项单元 + HTTP 集成回归（含 v3.0.0 分类完整性 / NapCat 自检 / 入口断言），退出码 0 即通过 |
| `tools/test_v3.py` | v3.0.0 真实 HTTP 服务端到端自测 37 项（登录 / 安装自检 / 分类召回 / 微信 / 老端点回归） |
| `tools/setup_napcat.py` · `tools/setup_napcat.bat` | NapCat 网关安装自检、自动修配置、拉起并等二维码（`--check` 只读体检） |
| `tools/reclassify.py` | 词库升级后原地重算分类，带备份与四道完整性门禁（`--dry-run` 可预览） |
| `tools/version_audit.py` | 全 tag 可用性审计 → `docs/VERSION_AUDIT.md` |
| `tools/fix_legacy_tag.py` | 为历史缺陷版本生成 `-p1` 补丁标签（不改原 tag） |
| `tools/bench.py` | 索引 rebuild / sync / optimize 微基准 |
| `tools/sync_github_releases.py` | 同步仓库描述/topics 与全部 GitHub Releases（幂等，正文取自 CHANGELOG，`--assets-dir dist` 可幂等上传发布资产） |
| `tools/build_release_assets.py` | **构建 Release 资产** → `dist/`：一键安装器 + 完整内容 zip + SHA256SUMS，并自校验 zip |
| `tools/build_installer.py` | 重建自解压安装器（被上一项复用；含命令行 ASCII / EncodedCommand / 标记一致性静态自检） |
| `tools/verify_release.py` | **发行前端到端验证**：下载 → SHA256 → cmd 真实执行安装器 → 解压包编译 → 起真实 HTTP 服务打 5 个 API + 3 个静态资源 → 真实数据零污染。支持 `--from-github` |
