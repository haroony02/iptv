@echo off
echo 🚀 إعداد المشروع على GitHub...
echo.

REM التحقق من وجود Git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ Git غير مثبت. يرجى تثبيته أولاً من https://git-scm.com/
    pause
    exit /b 1
)

REM إعداد Git
echo 📝 إعداد Git...
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

REM تهيئة المستودع
echo 📦 تهيئة المستودع...
git init

REM إضافة الملفات
echo ➕ إضافة الملفات...
git add .

REM أول commit
echo 💾 إنشاء أول commit...
git commit -m "Initial commit - قوائم IPTV العربية محدثة تلقائياً"

echo.
echo ✅ تم إعداد المستودع المحلي
echo.
echo 📋 الخطوات التالية:
echo 1. أنشئ مستودع جديد على GitHub (github.com/new)
echo 2. انسخ رابط المستودع (مثل: https://github.com/username/repo.git)
echo 3. شغّل الأوامر التالية في Git Bash أو CMD:
echo    git remote add origin YOUR_REPO_URL
echo    git branch -M main
echo    git push -u origin main
echo.
echo 🔄 بعد الرفع، سيبدأ GitHub Actions بتحديث القوائم تلقائياً كل 30 دقيقة
echo.
pause