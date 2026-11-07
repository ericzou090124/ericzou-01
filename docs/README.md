# 文档索引

所有说明文档集中在这里，按阅读目的选择入口。根目录 [README.md](../README.md) 是项目主页（含徽章、能力表、架构图、快速开始、API、FAQ）。

| 我想… | 读这个 |
| --- | --- |
| **了解微信群文件监听采集 / 群文件三级自动分类**（新增功能详解） | [FEATURES.md](FEATURES.md) |
| **查看全部历史版本的可用性检测结果** | [VERSION_AUDIT.md](VERSION_AUDIT.md)（由 `tools/version_audit.py` 生成） |
| 验收、看这次到底交付了什么 | [RELEASE.md](RELEASE.md) — 存档说明 + 逐项验收清单 + 全版本记录 |
| 快速上手、查接口、看权限表、FAQ | 根目录 [README.md](../README.md) |
| 查版本变化摘要 | [CHANGELOG.md](CHANGELOG.md) |
| 追溯开发过程、每次决策与故障处理（开发者日志） | [DEVLOG.md](DEVLOG.md) — 按时间顺序，v1.0.0 ~ v2.8.0 共 15 轮迭代 |
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
- **只想用起来**：根目录 `README.md` 的「快速开始」和「Web 管理界面」两节即可。
- **要回退版本**：先看 `VERSION_AUDIT.md` 的结论与补丁标签表，再 `git checkout <tag>`。

## 文档分工原则

- 设计说明写「打算怎么做」，实现后不回改结论，差异记在 `VERIFICATION.md` 与 `DEVLOG.md`。
- 验证数据只在 `VERIFICATION.md`，过程叙述只在 `DEVLOG.md`，版本摘要只在 `CHANGELOG.md`。
- 接口与操作清单只在根目录 `README.md`；`FEATURES.md` 只写两个重点功能的实现细节；`GUIDE.md` 只写解释性文字，避免多处重复维护。
- `VERSION_AUDIT.md` 由工具生成，**不要手工编辑**；要更新请运行 `python tools/version_audit.py`。

## 维护工具

| 工具 | 用途 |
| --- | --- |
| `tools/smoke_test.py` | 16 项单元 + HTTP 集成回归，退出码 0 即通过 |
| `tools/version_audit.py` | 全 tag 可用性审计 → `docs/VERSION_AUDIT.md` |
| `tools/fix_legacy_tag.py` | 为历史缺陷版本生成 `-p1` 补丁标签（不改原 tag） |
| `tools/bench.py` | 索引 rebuild / sync / optimize 微基准 |
| `tools/build_installer.py` | 重建自解压安装器 |
