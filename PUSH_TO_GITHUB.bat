@echo off
rem Push road6_cloud to GitHub. Double-click this file.
set "GIT=C:\Program Files\WorkBuddy\resources\vendor\PortableGit\mingw64\bin\git.exe"
cd /d %~dp0
echo ==== Pushing to GitHub, please wait... ====
echo ==== A browser window should open for login. ====
echo ==== If NO browser opens: look below for a one-time code (like ABCD-1234) ====
echo ==== and the URL https://github.com/login/device -- open that URL manually ====
echo ==== and type the code. ====
echo.
"%GIT%" -c credential.helper=manager push -u origin main
echo.
if errorlevel 1 (
  echo ==== PUSH FAILED ==== Please screenshot this whole window and send it to MG.
) else (
  echo ==== PUSH SUCCESS ==== You can close this window.
)
pause
