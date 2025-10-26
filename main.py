#!/usr/bin/env python3
"""
Optimized News Scraper - Minimal & Fast
"""

import os
import requests
import subprocess
import time
import re
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime
from urllib.parse import urljoin, urlparse

load_dotenv()

class NewsProcessor:
    def __init__(self):
        # Session with minimal config for speed
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'})
        
        # No retries for maximum speed
        adapter = requests.adapters.HTTPAdapter(max_retries=0)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # Add proxy support if needed
        proxy = os.getenv('HTTP_PROXY')
        if proxy:
            self.session.proxies.update({'http': proxy, 'https': proxy})
        
        # Config
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        self.api_url = 'https://api.openrouter.ai/v1/chat/completions'
        self.model = os.getenv('AI_MODEL', 'google/gemini-2.0-flash-exp:free')
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        delay_str = os.getenv('RATE_SITE_DELAY', '1.0')
        self.delay = float(delay_str) if delay_str.strip() else 1.0
        
        # RSS paths
        self.rss_paths = ['/rss', '/feed', '/rss.xml', '/feed.xml', '/atom.xml', '/?feed=rss2']
    
    def log(self, msg, level="INFO"):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {level}: {msg}")
    
    def get_sites(self):
        sites = os.getenv('SITES', '').split(',')
        return [s.strip() for s in sites if s.strip()]
    
    def get_processed_titles(self):
        try:
            with open('last_link.txt', 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            return []
    
    def save_title(self, title):
        try:
            titles = self.get_processed_titles()
            if title not in titles:
                with open('last_link.txt', 'a', encoding='utf-8') as f:
                    f.write(('\n' if titles else '') + title)
                self.log("Title saved")
        except Exception as e:
            self.log(f"Save error: {e}", "ERROR")
    
    def get_rss_articles(self, url):
        """Fast RSS parsing"""
        try:
            parsed = urlparse(url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            
            for path in self.rss_paths:
                try:
                    rss_url = base + path
                    resp = self.session.get(rss_url, timeout=3)
                    
                    if resp.status_code == 200 and any(tag in resp.text.lower() for tag in ['<rss', '<feed', '<item>']):
                        return self.parse_rss(resp.content, base)
                except:
                    continue
            return []
        except:
            return []
    
    def parse_rss(self, xml, base_url):
        """Minimal RSS parser"""
        try:
            soup = BeautifulSoup(xml, 'xml')
            articles = []
            
            # RSS items
            for item in soup.find_all('item')[:5]:  # Limit to 5 for speed
                title_elem = item.find('title')
                link_elem = item.find('link')
                
                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    link = link_elem.get_text(strip=True)
                    
                    if title and link:
                        articles.append({
                            'title': title,
                            'link': urljoin(base_url, link)
                        })
            
            # Atom entries
            if not articles:
                for entry in soup.find_all('entry')[:5]:
                    title_elem = entry.find('title')
                    link_elem = entry.find('link')
                    
                    if title_elem and link_elem:
                        title = title_elem.get_text(strip=True)
                        link = link_elem.get('href') or link_elem.get_text(strip=True)
                        
                        if title and link:
                            articles.append({
                                'title': title,
                                'link': urljoin(base_url, link)
                            })
            
            return articles
        except:
            return []
    
    def select_article(self, all_articles, processed_titles):
        """Smart article selection with AI fallback"""
        if not all_articles:
            return None
        
        # Filter processed titles
        new_articles = [a for a in all_articles if a['title'].strip() not in processed_titles]
        if not new_articles:
            return None
        
        # Try AI selection
        if self.api_key:
            try:
                titles = "\n".join([f"- {a['title']}" for a in new_articles[:10]])  # Limit for speed
                processed = "\n".join([f"- {t}" for t in processed_titles[-10:]])  # Last 10 only
                
                prompt = f"""Select the BEST automotive news title focusing on car reviews, tests, culture, entertainment. Avoid sales/market news.

Processed (avoid similar):
{processed}

New titles:
{titles}

Return ONLY the exact title."""
                
                payload = {
                    'model': self.model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 100,
                    'temperature': 0.1
                }
                
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                }
                
                resp = self.session.post(self.api_url, headers=headers, json=payload, timeout=10)
                
                if resp.status_code == 200:
                    selected = resp.json()['choices'][0]['message']['content'].strip().lstrip('- ')
                    
                    # Find matching article
                    for article in new_articles:
                        if selected.lower() in article['title'].lower() or article['title'].lower() in selected.lower():
                            self.log(f"AI selected: {article['title'][:50]}...")
                            return article
                
            except Exception as e:
                self.log(f"AI selection error: {e}", "ERROR")
        
        # Fallback: first new article
        self.log("Using fallback selection")
        return new_articles[0]
    
    def get_content(self, url):
        """Fast content extraction"""
        try:
            resp = self.session.get(url, timeout=3)
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            # Remove unwanted elements
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
                tag.decompose()
            
            # Find content
            for selector in ['article', '.content', '.post-content', '.entry-content', 'main']:
                elements = soup.select(selector)
                if elements:
                    paragraphs = elements[0].find_all(['p', 'h1', 'h2', 'h3'])
                    content = '\n\n'.join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
                    if len(content) > 100:
                        return content[:3000]  # Limit for speed
            
            # Fallback: all paragraphs
            paragraphs = soup.find_all('p')
            content = '\n\n'.join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30])
            return content[:3000]
            
        except:
            return ""
    
    def process_content(self, article):
        """Fast content processing with AI fallback"""
        self.log(f"Processing: {article['title'][:50]}...")
        
        content = self.get_content(article['link'])
        if not content:
            return article['title'], article['link']
        
        # Try AI processing
        if self.api_key:
            try:
                prompt = f"""Create a 2-3 sentence Persian summary of this automotive news. If English, translate to Persian. Use natural Persian and accurate automotive terms.

Content:
{content}"""
                
                payload = {
                    'model': self.model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 300,
                    'temperature': 0.1
                }
                
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                }
                
                resp = self.session.post(self.api_url, headers=headers, json=payload, timeout=15)
                
                if resp.status_code == 200:
                    summary = resp.json()['choices'][0]['message']['content'].strip()
                    self.log("AI processed successfully")
                    return summary, article['link']
                    
            except Exception as e:
                self.log(f"AI processing error: {e}", "ERROR")
        
        # Fallback: first paragraph
        self.log("Using fallback processing")
        paragraphs = content.split('\n\n')
        summary = paragraphs[0][:250] + "..." if paragraphs and len(paragraphs[0]) > 250 else (paragraphs[0] if paragraphs else article['title'])
        return summary, article['link']
    
    def send_telegram(self, title, content, link):
        """Fast Telegram sending"""
        if not self.bot_token or not self.chat_id:
            self.log("Telegram credentials missing", "ERROR")
            return False
        
        try:
            footer = "♡ㅤㅤㅤ❍ㅤㅤㅤ⌲\nˡᶦᵏᵉㅤㅤᶜᵒᵐᵐᵉⁿᵗㅤㅤˢʰᵃʳᵉ\n\n<blockquote>🆔\n<code>@WheelWhispers</code></blockquote>"
            text = f"<b>{title}</b>\n\n<blockquote expandable>{content}</blockquote>\n\n<a href=\"{link}\">بیشتر بخوانید</a>\n\n{footer}"
            
            data = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            
            resp = self.session.post(f"https://api.telegram.org/bot{self.bot_token}/sendMessage", data=data, timeout=5)
            
            if resp.status_code == 200:
                self.log("Telegram sent successfully", "SUCCESS")
                return True
            else:
                self.log(f"Telegram error: {resp.status_code}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Telegram error: {e}", "ERROR")
            return False
    
    def commit_git(self):
        """Fast git operations"""
        try:
            if subprocess.run(['git', 'rev-parse', '--git-dir'], capture_output=True).returncode != 0:
                return
            
            subprocess.run(['git', 'add', 'last_link.txt'], check=True)
            subprocess.run(['git', 'commit', '-m', f'Update {datetime.now().strftime("%Y-%m-%d %H:%M")}'], check=True)
            
            # Check for remote
            if subprocess.run(['git', 'remote'], capture_output=True, text=True).stdout.strip():
                subprocess.run(['git', 'push'], check=True)
                self.log("Git pushed", "SUCCESS")
            else:
                self.log("Git committed (no remote)", "SUCCESS")
                
        except Exception as e:
            self.log(f"Git error: {e}", "ERROR")
    
    def run(self):
        """Main optimized execution"""
        self.log("Starting optimized news processing...")
        
        sites = self.get_sites()
        if not sites:
            self.log("No sites configured", "ERROR")
            return
        
        self.log(f"Processing {len(sites)} sites")
        
        # Collect articles fast
        all_articles = []
        processed_titles = self.get_processed_titles()
        
        for site in sites:
            self.log(f"Checking: {site}")
            articles = self.get_rss_articles(site)
            if articles:
                self.log(f"Found {len(articles)} articles")
                all_articles.extend(articles)
            else:
                self.log("No RSS found", "WARNING")
            time.sleep(self.delay)
        
        if not all_articles:
            self.log("No articles found", "ERROR")
            return
        
        # Try to process with retry
        for attempt in range(3):
            self.log(f"Attempt {attempt + 1}/3")
            
            article = self.select_article(all_articles, processed_titles)
            if not article:
                self.log("No new articles", "WARNING")
                return
            
            # Check if already processed
            if article['title'].strip() in processed_titles:
                processed_titles.append(article['title'].strip())  # Add to exclude list
                continue
            
            # Process and send
            try:
                content, link = self.process_content(article)
                
                if self.send_telegram(article['title'], content, link):
                    self.save_title(article['title'])
                    self.commit_git()
                    self.log("Processing completed successfully!", "SUCCESS")
                    return
                else:
                    processed_titles.append(article['title'].strip())  # Exclude failed
                    continue
                    
            except Exception as e:
                self.log(f"Processing error: {e}", "ERROR")
                processed_titles.append(article['title'].strip())  # Exclude failed
                continue
        
        self.log("Failed after 3 attempts", "ERROR")

if __name__ == "__main__":
    processor = NewsProcessor()
    processor.run()