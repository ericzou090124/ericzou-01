# 文档索引

所有说明文档集中在这里，按阅读目的选择入口。

| 我想… | 读这个 |
| --- | --- |
| 验收、看这次到底交付了什么 | [RELEASE.md](RELEASE.md) — 存档说明 + 逐项验收清单（含 QQ 网页一键登录） |
| 快速上手、查接口、看权限表 | 根目录 [README.md](../README.md) |
| 了解整体流程 / 模块 / 数据流 / 界面交互 / 权限降级（设计阶段产物） | [DESIGN.md](DESIGN.md) |
| 通读一遍，明白「为什么这样设计」 | [GUIDE.md](GUIDE.md) — 说明性文字，不重复表格 |
| 看技术实现路线与代码结构 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 查本地试跑结果、耗时、修过的问题、已知限制 | [VERIFICATION.md](VERIFICATION.md) |
| 追溯开发过程、每次决策与故障处理 | [DEVLOG.md](DEVLOG.md) — 按时间顺序 |
| 查版本变化 | [CHANGELOG.md](CHANGELOG.md) |
| 查 GitHub 仓库与后续提交约定 | [PUSH.md](PUSH.md) |

## 建议阅读顺序

- **验收者**：`RELEASE.md` → 根目录 `README.md` → `VERIFICATION.md`。
- **接手维护的开发者**：`GUIDE.md` → `ARCHITECTURE.md` → `DEVLOG.md` → `server.py` → `lib/`。
- **只想用起来**：根目录 `README.md` 的「快速开始」和「界面怎么用」两节即可。

## 文档分工原则

- 设计说明写「打算怎么做」，实现后不回改结论，差异记在 `VERIFICATION.md` 与 `DEVLOG.md`。
- 验证数据只在 `VERIFICATION.md`，过程叙述只在 `DEVLOG.md`，版本摘要只在 `CHANGELOG.md`。
- 接口与操作清单只在根目录 `README.md`；`GUIDE.md` 只写解释性文字，避免两处重复维护。
