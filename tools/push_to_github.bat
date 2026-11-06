@echo off
chcp 65001 >nul
setlocal
if "%~1"=="" (
  echo 用法： tools\push_to_github.bat https://github.com/你的账号/你的仓库.git
  echo 说明： 推送认证由你本机 GitHub Desktop / git credential / PAT 提供，脚本不接收也不保存令牌。
  exit /b 1
)
cd /d "%~dp0.."
git rev-parse --is-inside-work-tree >nul 2>&1 || ( echo 尚未初始化 git 仓库 & exit /b 1 )
git branch -M main >nul 2>&1
git remote remove origin >nul 2>&1
git remote add origin "%~1"
echo 正在推送到 %~1 …
git push -u origin main
if errorlevel 1 (
  echo.
  echo 推送失败：通常是缺少 GitHub 认证。
  echo 请先在 GitHub Desktop 登录，或用 PAT / gh auth login 配置凭据后重试。
  echo 注意：不要把令牌写进本脚本或任何会被提交的文件。
)
endlocal
