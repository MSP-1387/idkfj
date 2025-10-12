#!/usr/bin/env python3
"""
Minimal News Scraper for GitHub Actions
Fetches one new article, processes it, and sends to Telegram
"""

import os
import requests
import subprocess
import time
import json
import re
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime
from urllib.parse import urljoin, urlparse

load_dotenv()

class NewsProcessor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Load configuration
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
        self.openrouter_api_url = os.getenv('OPENROUTER_API_URL', 'https://api.openrouter.ai/v1/chat/completions')
        self.ai_model = os.getenv('AI_MODEL', 'gpt-4o-mini')
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # Prompts and settings
        self.title_similarity_prompt = os.getenv('TITLE_SIMILARITY_PROMPT', 
            'Compare {{title_a}} and {{title_b}} and return a similarity score between 0 and 1 as JSON: {"score": number}.')
        self.rate_site_delay = float(os.getenv('RATE_SITE_DELAY', '1.5'))
        self.similarity_threshold = float(os.getenv('SIMILARITY_THRESHOLD', '0.8'))
        
        # RSS paths to try
        self.rss_paths = ['/rss', '/feed', '/rss.xml', '/feed.xml', '/atom.xml', '/?feed=rss2']
    
    def log(self, message, level="INFO"):
        """Simple logging with timestamp"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] {level}: {message}")
    
    def get_sites(self):
        """Get sites from environment variables or SITES_FILE"""
        sites_env = os.getenv('SITES')
        if sites_env:
            return [site.strip() for site in sites_env.split(',') if site.strip()]
        
        sites_file = os.getenv('SITES_FILE')
        if sites_file and os.path.exists(sites_file):
            with open(sites_file, 'r') as f:
                return [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        return []
    
    def get_last_title(self):
        """Read the last processed title from file"""
        try:
            with open('last_link.txt', 'r') as f:
                return f.read().strip()
        except FileNotFoundError:
            return ""
    
    def save_last_title(self, title):
        """Save the last processed title to file"""
        with open('last_link.txt', 'w') as f:
            f.write(title)
    
    def check_title_similarity(self, title_a, title_b):
        """Check similarity between two titles using Gemini API"""
        if not self.gemini_api_key:
            self.log("No Gemini API key, skipping similarity check", "WARNING")
            return 0.0
        
        try:
            prompt = self.title_similarity_prompt.replace('{{title_a}}', title_a).replace('{{title_b}}', title_b)
            
            headers = {
                'Content-Type': 'application/json',
            }
            
            # Using Gemini API directly
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={self.gemini_api_key}"
            
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
            
            response = self.session.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                text = result['candidates'][0]['content']['parts'][0]['text']
                
                # Extract JSON from response
                json_match = re.search(r'\{[^}]*"score"[^}]*\}', text)
                if json_match:
                    score_data = json.loads(json_match.group())
                    return float(score_data.get('score', 0))
            
            self.log(f"Gemini API error: {response.status_code}", "ERROR")
            return 0.0
            
        except Exception as e:
            self.log(f"Similarity check error: {str(e)}", "ERROR")
            return 0.0
    
    def try_rss_feed(self, base_url):
        """Try to find and parse RSS feed"""
        parsed_url = urlparse(base_url)
        base = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Try common RSS paths
        for path in self.rss_paths:
            try:
                rss_url = base + path
                response = self.session.get(rss_url, timeout=10)
                
                if response.status_code == 200 and any(tag in response.text.lower() for tag in ['<rss', '<feed', '<item>']):
                    return self.parse_rss(response.content, base)
                    
            except Exception:
                continue
        
        return []
    
    def parse_rss(self, xml_content, base_url):
        """Parse RSS/Atom feed content"""
        try:
            soup = BeautifulSoup(xml_content, 'xml')
            articles = []
            
            # Parse RSS items
            for item in soup.find_all('item')[:10]:
                title_elem = item.find('title')
                link_elem = item.find('link')
                
                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    link = link_elem.get_text(strip=True)
                    
                    if title and link:
                        articles.append({
                            'title': title,
                            'link': urljoin(base_url, link),
                            'source': urlparse(base_url).netloc
                        })
            
            # Parse Atom entries if no RSS items found
            if not articles:
                for entry in soup.find_all('entry')[:10]:
                    title_elem = entry.find('title')
                    link_elem = entry.find('link')
                    
                    if title_elem and link_elem:
                        title = title_elem.get_text(strip=True)
                        link = link_elem.get('href') if link_elem.get('href') else link_elem.get_text(strip=True)
                        
                        if title and link:
                            articles.append({
                                'title': title,
                                'link': urljoin(base_url, link),
                                'source': urlparse(base_url).netloc
                            })
            
            return articles
            
        except Exception as e:
            self.log(f"RSS parsing error: {str(e)}", "ERROR")
            return []
    
    def select_best_new_article_with_ai(self, sites):
        """Use AI to select one best new article that hasn't been processed"""
        last_title = self.get_last_title()
        self.log(f"Last processed title: {last_title[:50]}..." if last_title else "No previous title found")
        
        # Collect all articles from all sites
        all_articles = []
        for site in sites:
            self.log(f"Checking site: {site}")
            
            try:
                articles = self.try_rss_feed(site)
                
                if not articles:
                    self.log(f"No RSS feed found for {site}", "WARNING")
                    continue
                
                self.log(f"Found {len(articles)} articles from {site}")
                all_articles.extend(articles)
                
                time.sleep(self.rate_site_delay)
                
            except Exception as e:
                self.log(f"Error processing site {site}: {str(e)}", "ERROR")
                continue
        
        if not all_articles:
            self.log("No articles found from any site", "ERROR")
            return None
        
        # Filter out exact duplicate titles if we have a last title
        filtered_articles = []
        for article in all_articles:
            if last_title:
                # Simple string comparison instead of AI similarity
                if article['title'].strip().lower() != last_title.strip().lower():
                    filtered_articles.append(article)
                else:
                    self.log(f"Skipping exact duplicate: {article['title'][:50]}...")
            else:
                filtered_articles.append(article)
        
        if not filtered_articles:
            self.log("No new articles found after duplicate filtering", "WARNING")
            return None
        
        # Use AI to select the best article
        return self.ai_select_best_article(filtered_articles)
    
    def ai_select_best_article(self, articles):
        """Use AI to select the best article from the list"""
        if not self.openrouter_api_key:
            self.log("No OpenRouter API key, selecting first article", "WARNING")
            return articles[0] if articles else None
        
        try:
            # Create prompt with article titles
            titles_text = "\n".join([f"- {article['title']}" for article in articles])
            
            selection_prompt = os.getenv('AI_SELECTION_PROMPT', 
                'Choose the best news title from the following list. Focus on interesting, engaging content. Return only the exact title, nothing else.')
            
            prompt = f"{selection_prompt}\n\nNews titles:\n{titles_text}"
            
            headers = {
                'Authorization': f'Bearer {self.openrouter_api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': self.ai_model,
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 200,
                'temperature': 0.3
            }
            
            response = self.session.post(self.openrouter_api_url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                selected_title = response.json()['choices'][0]['message']['content'].strip()
                selected_title = selected_title.lstrip('- ').strip()
                
                # Find the article with matching title
                for article in articles:
                    if article['title'].strip() == selected_title.strip():
                        self.log(f"AI selected: {selected_title[:50]}...")
                        return article
                
                # If exact match not found, try partial match
                for article in articles:
                    if selected_title.lower() in article['title'].lower() or article['title'].lower() in selected_title.lower():
                        self.log(f"AI selected (partial match): {article['title'][:50]}...")
                        return article
                
                self.log("AI selection didn't match any article, using first one", "WARNING")
                return articles[0]
            else:
                self.log(f"AI selection API error: {response.status_code}", "ERROR")
                return articles[0]
                
        except Exception as e:
            self.log(f"AI selection error: {str(e)}", "ERROR")
            return articles[0] if articles else None
    
    def get_article_content(self, url):
        """Extract article content from URL"""
        try:
            response = self.session.get(url, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()
            
            # Try to find main content
            content_selectors = [
                'article', '.content', '.post-content', '.article-content', 
                '.entry-content', 'main', '[role="main"]'
            ]
            
            content = ""
            for selector in content_selectors:
                elements = soup.select(selector)
                if elements:
                    paragraphs = elements[0].find_all(['p', 'h1', 'h2', 'h3'])
                    content = '\n\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                    if len(content) > 200:
                        break
            
            # Fallback: get all paragraphs
            if len(content) < 200:
                paragraphs = soup.find_all('p')
                content = '\n\n'.join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30])
            
            return content[:10000]  # Limit content length
            
        except Exception as e:
            self.log(f"Content extraction error: {str(e)}", "ERROR")
            return ""
    
    def call_ai_api(self, prompt, content, max_tokens=800):
        """Make API call to AI service"""
        if not self.openrouter_api_key:
            self.log("No OpenRouter API key available", "ERROR")
            return ""
        
        try:
            headers = {
                'Authorization': f'Bearer {self.openrouter_api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': self.ai_model,
                'messages': [
                    {'role': 'user', 'content': f"{prompt}\n\nContent:\n{content}"}
                ],
                'max_tokens': max_tokens,
                'temperature': 0.3
            }
            
            response = self.session.post(self.openrouter_api_url, headers=headers, json=payload, timeout=45)
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'].strip()
            else:
                self.log(f"AI API error: {response.status_code} - {response.text}", "ERROR")
                return ""
                
        except Exception as e:
            self.log(f"AI API call error: {str(e)}", "ERROR")
            return ""
    
    def is_persian_text(self, text):
        """Check if text contains Persian characters"""
        persian_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        total_chars = len(re.sub(r'\s', '', text))
        return (persian_chars / max(total_chars, 1)) > 0.3
    
    def process_article(self, article):
        """Process article: summarize and translate if needed"""
        self.log(f"Processing article: {article['title'][:50]}...")
        
        # Get article content
        content = self.get_article_content(article['link'])
        if not content:
            self.log("No content extracted, using title only", "WARNING")
            return article['title'], article['link']
        
        # Summarize content
        summary_prompt = os.getenv('AI_SUMMARIZATION_PROMPT', 
            'Create a concise summary of this news article in 2-3 sentences.')
        
        summary = self.call_ai_api(summary_prompt, content)
        if not summary:
            self.log("Summarization failed, using title", "WARNING")
            return article['title'], article['link']
        
        # Translate to Persian if needed
        if not self.is_persian_text(summary):
            translation_prompt = os.getenv('AI_TRANSLATION_PROMPT',
                'Translate the following text to Persian (Farsi). Return only the translated text.')
            
            translated = self.call_ai_api(translation_prompt, summary)
            if translated:
                summary = translated
        
        return summary, article['link']
    
    def send_to_telegram(self, title, content, link):
        """Send message to Telegram channel"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            self.log("Telegram credentials missing", "ERROR")
            return False
        
        try:
            text = f"<b>{title}</b>\n\n{content}\n\n<a href=\"{link}\">Read more</a>"
            
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = {
                'chat_id': self.telegram_chat_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            
            response = self.session.post(url, data=data, timeout=30)
            
            if response.status_code == 200:
                self.log("Successfully sent to Telegram", "SUCCESS")
                return True
            else:
                self.log(f"Telegram API error: {response.status_code} - {response.text}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Telegram send error: {str(e)}", "ERROR")
            return False
    
    def commit_and_push(self):
        """Commit and push last_link.txt to repository"""
        try:
            # Check if we're in a git repository
            result = subprocess.run(['git', 'rev-parse', '--git-dir'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                self.log("Not in a git repository, skipping git operations", "WARNING")
                return
            
            # Add, commit and push
            subprocess.run(['git', 'add', 'last_link.txt'], check=True)
            subprocess.run(['git', 'commit', '-m', f'Update last_link.txt - {datetime.now().strftime("%Y-%m-%d %H:%M")}'], check=True)
            subprocess.run(['git', 'push'], check=True)
            
            self.log("Successfully pushed last_link.txt to repository", "SUCCESS")
            
        except subprocess.CalledProcessError as e:
            self.log(f"Git operation failed: {str(e)}", "ERROR")
        except Exception as e:
            self.log(f"Unexpected error during git operations: {str(e)}", "ERROR")
    
    def run(self):
        """Main execution function"""
        self.log("Starting news processing...")
        
        # Get sites to process
        sites = self.get_sites()
        if not sites:
            self.log("No sites configured in SITES environment variable or SITES_FILE", "ERROR")
            return
        
        self.log(f"Processing {len(sites)} sites: {', '.join(sites)}")
        
        # Use AI to select one best new article
        article = self.select_best_new_article_with_ai(sites)
        if not article:
            self.log("No new articles found", "WARNING")
            return
        
        # Process the article
        try:
            content, link = self.process_article(article)
            
            # Send to Telegram
            if self.send_to_telegram(article['title'], content, link):
                # Save the processed title (not link)
                self.save_last_title(article['title'])
                self.log(f"Saved last title: {article['title'][:50]}...")
                
                # Commit and push to repository
                self.commit_and_push()
                
                self.log("News processing completed successfully!", "SUCCESS")
            else:
                self.log("Failed to send to Telegram", "ERROR")
                
        except Exception as e:
            self.log(f"Error processing article: {str(e)}", "ERROR")

if __name__ == "__main__":
    processor = NewsProcessor()
    processor.run()