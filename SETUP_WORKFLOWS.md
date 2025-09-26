# 🔧 راهنمای فعال‌سازی GitHub Actions

پس از clone کردن این پروژه، برای فعال‌سازی GitHub Actions این مراحل را دنبال کنید:

## 1️⃣ ایجاد فایل‌های Workflow

در پوشه `.github/workflows/` دو فایل زیر را ایجاد کنید:

### فایل `news-scraper.yml`:
```yaml
name: News Scraper Bot

on:
  schedule:
    # Run at Iran time: 1:00 PM, 3:00 PM, 6:00 PM (UTC+3:30)
    - cron: '30 9 * * *'   # 1:00 PM Iran time (9:30 UTC)
    - cron: '30 11 * * *'  # 3:00 PM Iran time (11:30 UTC)
    - cron: '30 14 * * *'  # 6:00 PM Iran time (14:30 UTC)
  workflow_dispatch: # Allow manual trigger

jobs:
  scrape-news:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
      
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
        
    - name: Cache pip dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
        restore-keys: |
          ${{ runner.os }}-pip-
        
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        
    - name: Download previous database
      uses: actions/download-artifact@v3
      continue-on-error: true
      with:
        name: news-database-${{ github.repository_owner }}
        path: .
        
    - name: Run news scraper
      env:
        NEWS_SITE_1: ${{ vars.NEWS_SITE_1 || secrets.NEWS_SITE_1 || 'https://pedal.ir' }}
        NEWS_SITE_2: ${{ vars.NEWS_SITE_2 || secrets.NEWS_SITE_2 || 'https://www.motor1.com' }}
        NEWS_SITE_3: ${{ vars.NEWS_SITE_3 || secrets.NEWS_SITE_3 || 'https://www.autocar.co.uk' }}
        OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
        TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
        TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
      run: |
        echo "🚀 Starting news scraper..."
        python main.py
        echo "✅ News scraper completed"
        
    - name: Upload database artifact
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: news-database-${{ github.repository_owner }}
        path: news.db
        retention-days: 90
```

### فایل `test.yml`:
```yaml
name: Test News Scraper

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
      
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
        
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        
    - name: Test imports and basic functionality
      run: |
        python -c "
        import sys
        sys.path.append('.')
        from main import NewsScraper
        
        scraper = NewsScraper()
        print('✅ NewsScraper initialized successfully')
        
        scraper.init_db()
        print('✅ Database initialized successfully')
        
        sites = scraper._get_sites()
        print(f'✅ Found {len(sites)} configured sites')
        
        scraper.db.close()
        print('✅ All tests passed!')
        "
```

## 2️⃣ تنظیم Secrets

در GitHub repository خود:
1. برو به **Settings > Secrets and variables > Actions**
2. این secrets را اضافه کن:

| Secret Name | مقدار |
|-------------|-------|
| `OPENROUTER_API_KEY` | کلید API OpenRouter شما |
| `TELEGRAM_BOT_TOKEN` | توکن ربات تلگرام |
| `TELEGRAM_CHAT_ID` | شناسه کانال/گروه تلگرام |

## 3️⃣ فعال‌سازی Actions

1. برو به تب **Actions** در repository
2. اگر Actions غیرفعال است، فعالش کن
3. برای تست، روی **Run workflow** کلیک کن

## 4️⃣ زمان‌بندی

ربات روزانه 3 بار اجرا می‌شود:
- **13:00** (1:00 PM) ایران
- **15:00** (3:00 PM) ایران  
- **18:00** (6:00 PM) ایران

---

**نکته**: فایل‌های workflow باید دقیقاً در مسیر `.github/workflows/` قرار گیرند.