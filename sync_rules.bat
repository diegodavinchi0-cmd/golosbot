@echo off
xcopy /Y "C:\Users\hp\Desktop\Obsidian_Brain\Telegram_AI_Diego\Qoidalar\*.md" "C:\Users\hp\golosbot\rules\"
cd /d C:\Users\hp\golosbot
git add rules
git commit -m "rules: sync from Obsidian"
git push origin main
pause
