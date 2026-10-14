@echo off
rem Push road6_cloud to GitHub. Double-click this file (GUI login needs your desktop).
cd /d %~dp0
if not exist .git (
  git init
  git branch -M main
  git add -A
  git commit -m "road6 cloud monitor init"
)
git remote remove origin 2>nul
git remote add origin https://github.com/zhaohui86-png/road6-cloud.git
git push -u origin main
echo.
echo ==== If a browser window opened, click Authorize to finish login. ====
pause
