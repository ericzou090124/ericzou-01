# 推送到 GitHub

## 当前状态

- 本机 `git` 可用（2.55.0），`user.name=ericzou090124`、`user.email=ericzou375@gmail.com`。
- 网络可达：`git ls-remote https://github.com/octocat/Hello-World.git HEAD` 成功。
- **缺少认证**：没有 `gh` CLI、`~/.git-credentials`、`~/.ssh` 密钥，Windows 凭据管理器里也没有 GitHub 条目；`credential.helper` 未配置。
- 因此**助手不能代替你完成推送**，否则就是伪造凭证或把令牌写进仓库。项目已在本地完成 `git init` + 首次提交，推送只差「仓库地址 + 认证」这两个由你提供的信息。

## 三种可行方式

### A. 用 GitHub Desktop（最省事，推荐）

1. 打开 GitHub Desktop 并登录你的账号。
2. `File → Add Local Repository`，选择 `resource-manager/` 目录（已有 `.git`）。
3. `Publish repository`（新建仓库）或在 `Repository → Repository Settings → Remote` 填入已有仓库地址，然后 `Push origin`。

### B. 提供仓库地址，用本机的 git 凭据推送

```bat
tools\push_to_github.bat https://github.com/<你的账号>/<仓库名>.git
```

脚本只设置 remote 并 `git push -u origin main`，**不接收、不保存令牌**。认证由你本机的 GitHub Desktop / Windows 凭据管理器 / `gh auth login` 提供。

### C. 一次性 PAT（不要写进任何会被提交的文件）

```bash
git -C resource-manager remote add origin https://github.com/<账号>/<仓库>.git
git -C resource-manager push -u origin main
```

在弹出的凭据窗口里填用户名 + Personal Access Token；或让凭据管理器记住。
**不要把 PAT 粘贴给助手、不要写进 `config.json` / `.bat` / 文档。**

## 仓库里有什么 / 没有什么

提交内容：`config.json`、`server.py`、`lib/`、`web/`、`obsidian_plugin/`、`tools/`、`docs/`、`start.bat`、`README.md`、`.gitignore`。

被 `.gitignore` 排除（**不会上传**）：

- `state/catalog.json`（1625 条群文件元数据）、`state/index.db`、`state/bodies/`（已下载文件正文）
- `state/secrets.json`（外部 API Key）
- `state/qq_manifest.json`、`state/settings.json`、`__pycache__/`

也就是说：**群里下载的资料、正文、密钥都不进 GitHub**。克隆后需要本机 NapCat 或自备清单重新 `bootstrap.py` 才能生成目录与索引。

## 推送前自检

```bash
git -C resource-manager status
git -C resource-manager log --oneline -3
git -C resource-manager ls-files | grep -E "state/|secrets"   # 应无输出
```
