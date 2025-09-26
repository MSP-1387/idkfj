"""
Configuration file for News Scraper Bot
تنظیمات پیشرفته ربات خبرخوان
"""

# Default RSS paths to try
DEFAULT_RSS_PATHS = [
    '/rss',
    '/feed', 
    '/rss.xml',
    '/feed.xml',
    '/atom.xml',
    '/?feed=rss2',
    '/feeds/all.atom.xml',
    '/rss/news',
    '/feed/news'
]

# CSS selectors for finding news titles
TITLE_SELECTORS = [
    'h1 a',
    'h2 a', 
    'h3 a',
    '.title a',
    '.headline a',
    'article h1',
    'article h2',
    '.post-title a',
    '.entry-title a',
    '.news-title a'
]

# Content selectors for extracting article content
CONTENT_SELECTORS = [
    'article',
    '.content',
    '.post-content',
    '.article-content', 
    '.entry-content',
    '.news-content',
    'main',
    '.main-content',
    '[role="main"]',
    '.post-body',
    '.article-body'
]

# Image selectors for finding featured images
IMAGE_SELECTORS = [
    'article img',
    '.featured-image img',
    '.post-image img',
    '.article-image img',
    '.hero-image img',
    'meta[property="og:image"]',
    'meta[name="twitter:image"]'
]

# Tags to remove when cleaning content
TAGS_TO_REMOVE = [
    'script',
    'style', 
    'nav',
    'header',
    'footer',
    'aside',
    'advertisement',
    '.ad',
    '.ads',
    '.advertisement',
    '.social-share',
    '.comments'
]

# Default prompts (can be overridden by environment variables)
DEFAULT_PROMPTS = {
    'selection': """Choose the best 3 news titles from the following list. Focus on car reviews, automotive entertainment, car culture, driving experiences, road tests, and fun automotive content. Prioritize articles about actual driving experiences, car comparisons, automotive technology reviews, and entertainment content related to cars. Avoid news about car prices, sales figures, market analysis, or purely commercial content. Return only the exact titles, one per line, nothing else.""",
    
    'summarization': """Create an engaging summary from this car news article. The summary should be 150-250 words, exciting and captivating to make readers want to read more car content. Focus on the most interesting highlights, and make it sound dynamic and engaging for car enthusiasts. Do not use emojis. Write in a style that encourages readers to follow for more automotive content.""",
    
    'translation': """Translate the following car news summary from English to Persian (Farsi). Keep automotive terms accurate and use natural Persian language. Maintain the engaging tone. Keep the same length. Do not use emojis. If the text is already in Persian, return it unchanged. Only return the translated text, nothing else."""
}

# Rate limiting settings
RATE_LIMITS = {
    'api_call_delay': 2,  # seconds between API calls
    'site_scrape_delay': 2,  # seconds between scraping different sites
    'news_process_delay': 3,  # seconds between processing different news items
    'max_retries': 3,  # maximum retries for failed requests
    'timeout': 30  # request timeout in seconds
}

# Scraping limits
SCRAPING_LIMITS = {
    'max_news_per_site': 15,  # maximum news items to collect per site
    'max_content_length': 20000,  # maximum content length to process
    'max_description_length': 200,  # maximum description length
    'min_title_length': 10,  # minimum title length to consider
    'max_sites': 20  # maximum number of sites to process
}

# Database settings
DATABASE_CONFIG = {
    'name': 'news.db',
    'backup_enabled': True,
    'cleanup_days': 30  # days to keep old records
}

# Logging configuration
LOG_ICONS = {
    "info": "ℹ️",
    "success": "✅", 
    "warning": "⚠️",
    "error": "❌",
    "process": "🔄",
    "debug": "🐛"
}

# Persian text detection threshold
PERSIAN_TEXT_THRESHOLD = 0.3  # 30% Persian characters to consider text as Persian