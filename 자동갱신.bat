@echo off
chcp 65001 >nul
cd /d "%~dp0"
python run_all.py >> update.log 2>&1
git add docs >> update.log 2>&1
git diff --cached --quiet || git commit -m "local-auto-update %date%" >> update.log 2>&1
git pull --rebase -X ours origin main >> update.log 2>&1
git push >> update.log 2>&1
