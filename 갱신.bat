@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Viral Video Hub - 수동 갱신
echo ============================================
python run_all.py
if errorlevel 1 (
  echo [오류] 수집 실패
  pause
  exit /b 1
)
git add docs
git diff --cached --quiet || git commit -m "manual-update %date%"
git fetch origin main
git merge -s ours origin/main -m "merge remote"
git push
start "" "https://blinkaistudio.github.io/viral-video-hub/"
echo 완료! 브라우저에서 확인하세요.
pause
