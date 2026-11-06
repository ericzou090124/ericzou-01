# GitHub 仓库与提交约定

## 当前状态（2026-11-06 已验证）

| 项 | 值 |
| --- | --- |
| 仓库 | `https://github.com/ericzou090124/ericzou-01.git` |
| 本地 remote | `origin` 已设置，分支 `main` 跟踪 `origin/main` |
| 首次提交 | `52d728a feat: 资源管理器闭环 - QQ 群文件可视化导入、Obsidian 多级大纲与 grounded AI 检索` |
| 推送结果 | ✅ `git push -u origin main` 成功（本机 git 凭据可用） |
| 存档标签 | `v1.0.0`（注附标签，随仓库一起推送） |

## 后续改动约定

用户要求「以后有改动直接在仓库里帮我改就行」：

1. 后续所有代码 / 文档改动都在 `resource-manager/` 工作区完成。
2. 改动完成后直接 `git add -A && git commit -m "<类型>: <说明>" && git push origin main`。
3. 提交信息用 `feat / fix / docs / refactor / test / chore` 前缀，中文简述。
4. 重要里程碑打注附标签（`git tag -a vX.Y.Z -m "..."; git push origin vX.Y.Z`）。
5. **不要提交** `state/`（元数据、正文、密钥）、任何下载下来的群资料、任何令牌。

## 常用命令

```bash
git -C resource-manager status
git -C resource-manager log --oneline -5
git -C resource-manager remote -v
git -C resource-manager push origin main
```

若换机器后缺少认证，用 GitHub Desktop 登录，或配置 `gh auth login` / PAT；
**不要把令牌写进 `config.json`、`.bat`、文档或提交信息**。

## 仓库里有什么 / 没有什么

提交内容：`config.json`、`server.py`、`lib/`、`web/`、`obsidian_plugin/`、`tools/`、`docs/`、`start.bat`、`README.md`、`.gitignore`。

被 `.gitignore` 排除（**不上传**）：`state/catalog.json`（1625 条群文件元数据）、`state/index.db`、`state/bodies/`（已下载文件正文）、`state/secrets.json`（外部 API Key）、`state/qq_manifest.json`、`state/settings.json`、`__pycache__/`。

即：**群里下载的资料、正文、密钥都不进 GitHub**。克隆后需要本机 NapCat，或自备清单运行 `python tools/bootstrap.py` 才能重建目录与索引。

推送前自检：

```bash
git -C resource-manager ls-files | grep -E "state/|secrets|catalog.json|index.db"   # 应无输出
```
