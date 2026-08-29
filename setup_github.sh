#!/bin/bash
# سكربت لإعداد GitHub ورفع المشروع

echo "🚀 إعداد المشروع على GitHub..."

# التحقق من وجود Git
if ! command -v git &> /dev/null; then
    echo "❌ Git غير مثبت. يرجى تثبيته أولاً."
    exit 1
fi

# إعداد Git
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# تهيئة المستودع
git init

# إضافة الملفات
git add .

# أول commit
git commit -m "Initial commit - قوائم IPTV العربية محدثة تلقائياً"

echo "✅ تم إعداد المستودع المحلي"
echo ""
echo "📋 الخطوات التالية:"
echo "1. أنشئ مستودع جديد على GitHub (github.com/new)"
echo "2. انسخ رابط المستودع (مثل: https://github.com/username/repo.git)"
echo "3. شغّل الأمر التالي:"
echo "   git remote add origin YOUR_REPO_URL"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "🔄 بعد الرفع، سيبدأ GitHub Actions بتحديث القوائم تلقائياً كل 30 دقيقة"