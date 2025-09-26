import os,requests,sqlite3,subprocess,time,re,json
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime
from urllib.parse import urljoin,urlparse
from config import *

load_dotenv()

class NewsScraper:
    def __init__(self):
        self.s=requests.Session()
        self.s.headers.update({'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        self.rss_paths=DEFAULT_RSS_PATHS
        self.title_selectors=TITLE_SELECTORS
        self.api_url=os.getenv('OPENROUTER_API_URL','https://openrouter.ai/api/v1/chat/completions')
        self.api_key=os.getenv('OPENROUTER_API_KEY')
        self.model=os.getenv('AI_MODEL','google/gemini-2.0-flash-exp:free')
        self.tg_token=os.getenv('TELEGRAM_BOT_TOKEN')
        self.tg_chat=os.getenv('TELEGRAM_CHAT_ID')
        self.selection_prompt=os.getenv('AI_SELECTION_PROMPT',DEFAULT_PROMPTS['selection'])
        self.summarization_prompt=os.getenv('AI_SUMMARIZATION_PROMPT',DEFAULT_PROMPTS['summarization'])
        self.translation_prompt=os.getenv('AI_TRANSLATION_PROMPT',DEFAULT_PROMPTS['translation'])
        self.init_db()
    
    def init_db(self):
        self.db=sqlite3.connect('news.db')
        self.db.execute('CREATE TABLE IF NOT EXISTS sent_news (id INTEGER PRIMARY KEY, title TEXT UNIQUE, sent_date TEXT, source TEXT)')
        self.db.commit()
    
    def _log(self,msg,level="info"):
        print(f"{LOG_ICONS.get(level,'ℹ️')} {msg}")
    
    def _get_sites(self):
        return [os.getenv(f'NEWS_SITE_{i}') for i in range(1,21) if os.getenv(f'NEWS_SITE_{i}')]
    
    def _is_persian(self,text):
        return len(re.findall(r'[\u0600-\u06FF]',text))/max(len(re.sub(r'\s','',text)),1)>PERSIAN_TEXT_THRESHOLD
    
    def _try_rss(self,url):
        base=f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        for path in self.rss_paths:
            try:
                r=self.s.get(base+path,timeout=5)
                if r.status_code==200 and any(tag in r.text.lower() for tag in ['<rss','<feed','<item>']):
                    return self._parse_rss(r.content,base)
            except:continue
        try:
            r=self.s.get(url,timeout=5)
            soup=BeautifulSoup(r.content,'html.parser')
            for link in soup.find_all('link',{'type':['application/rss+xml','application/atom+xml']}):
                href=link.get('href')
                if href:
                    try:
                        rss_r=self.s.get(urljoin(base,href),timeout=5)
                        if rss_r.status_code==200:return self._parse_rss(rss_r.content,base)
                    except:continue
        except:pass
        return[]
    
    def _parse_rss(self,xml_content,base_url):
        try:
            soup=BeautifulSoup(xml_content,'xml')
            news=[]
            for item in soup.find_all('item')[:15]:
                title=item.title.text.strip()if item.title else''
                if len(title)>5:
                    news.append({'title':title,'link':urljoin(base_url,item.link.text.strip())if item.link else '','description':(item.description.text.strip()[:200]if item.description else''),'pub_date':item.pubDate.text.strip()if item.pubDate else'','source':urlparse(base_url).netloc,'method':'RSS'})
            return news
        except:return[]
    
    def _scrape_direct(self,url):
        try:
            r=self.s.get(url,timeout=8)
            soup=BeautifulSoup(r.content,'html.parser')
            news,found=[],[]
            for selector in self.title_selectors:
                for elem in soup.select(selector)[:10]:
                    title=elem.get_text(strip=True)
                    if len(title)>10 and title not in found:
                        found.append(title)
                        link=elem.get('href','')if elem.name=='a'else(elem.find('a').get('href','')if elem.find('a')else'')
                        desc=''
                        parent=elem.find_parent(['article','div','section'])
                        if parent:
                            desc_elem=parent.find(['p','.excerpt','.summary'])
                            desc=desc_elem.get_text(strip=True)[:200]if desc_elem else''
                        news.append({'title':title,'link':urljoin(url,link)if link else'','description':desc,'pub_date':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'source':urlparse(url).netloc,'method':'Direct'})
                if news:break
            return news
        except:return[]
    
    def get_news_titles(self,url):
        self._log(f"Processing: {url}","process")
        rss_news=self._try_rss(url)
        if rss_news:
            self._log(f"{len(rss_news)} titles via RSS","success")
            return rss_news
        self._log("No RSS, trying direct scrape","warning")
        direct_news=self._scrape_direct(url)
        if direct_news:self._log(f"{len(direct_news)} titles via scrape","success")
        else:self._log("No news found","error")
        return direct_news
    
    def is_duplicate(self,title):
        cursor=self.db.execute('SELECT COUNT(*) FROM sent_news WHERE title=?',(title,))
        return cursor.fetchone()[0]>0
    
    def select_best_news_with_ai(self,all_news):
        if not self.api_key or not all_news:return[]
        unique_news=[news for news in all_news if not self.is_duplicate(news['title'])]
        if not unique_news:
            self._log("All news are duplicates","warning")
            return[]
        titles_text="\n".join([f"- {news['title']}"for news in unique_news])
        self._log("AI selecting best titles...","process")
        try:
            headers={'Authorization':f'Bearer {self.api_key}','Content-Type':'application/json'}
            payload={'model':self.model,'messages':[{'role':'user','content':f"{self.selection_prompt}\n\nNews titles:\n{titles_text}"}],'max_tokens':500,'temperature':0.3}
            response=requests.post(self.api_url,headers=headers,json=payload,timeout=30)
            if response.status_code==200:
                selected_titles=response.json()['choices'][0]['message']['content'].strip().split('\n')
                selected_titles=[title.strip().lstrip('- ').strip()for title in selected_titles if title.strip()]
                self._log(f"AI selected {len(selected_titles)} titles","success")
                selected_news=[]
                for selected_title in selected_titles:
                    for news in unique_news:
                        if news['title'].strip()==selected_title.strip():
                            selected_news.append(news)
                            break
                return selected_news
            else:
                self._log(f"AI API error: {response.status_code}","error")
                return[]
        except Exception as e:
            self._log(f"AI selection error: {str(e)}","error")
            return[]
    
    def _make_api_call(self,prompt,content,max_tokens=800):
        try:
            # Add delay between API calls to avoid rate limiting
            time.sleep(RATE_LIMITS['api_call_delay'])
            headers={'Authorization':f'Bearer {self.api_key}','Content-Type':'application/json'}
            payload={'model':self.model,'messages':[{'role':'user','content':f"{prompt}\n\nContent:\n{content}"}],'max_tokens':max_tokens,'temperature':0.3}
            response=requests.post(self.api_url,headers=headers,json=payload,timeout=45)
            if response.status_code==200:return response.json()['choices'][0]['message']['content'].strip()
            else:self._log(f"API error: {response.status_code} - {response.text}","error");return""
        except Exception as e:self._log(f"API call error: {str(e)}","error");return""
    
    def _get_full_content(self,url):
        try:
            self._log(f"Fetching content from: {url[:50]}...","process")
            r=self.s.get(url,timeout=10)
            soup=BeautifulSoup(r.content,'html.parser')
            for tag in soup(['script','style','nav','header','footer','aside','advertisement']):tag.decompose()
            content_selectors=['article','.content','.post-content','.article-content','.entry-content','.news-content','main','.main-content','[role="main"]']
            content=''
            for selector in content_selectors:
                elements=soup.select(selector)
                if elements:
                    paragraphs=elements[0].find_all(['p','h1','h2','h3','h4'])
                    content='\n\n'.join([p.get_text(strip=True)for p in paragraphs if p.get_text(strip=True)])
                    if len(content)>200:break
            if len(content)<200:
                paragraphs=soup.find_all('p')
                content='\n\n'.join([p.get_text(strip=True)for p in paragraphs if len(p.get_text(strip=True))>50])
            return content[:20000]
        except Exception as e:self._log(f"Content extraction error: {str(e)}","error");return''
    
    def _extract_image(self,url):
        try:
            r=self.s.get(url,timeout=10)
            soup=BeautifulSoup(r.content,'html.parser')
            selectors=['article img','.featured-image img','.post-image img','.article-image img','meta[property="og:image"]','meta[name="twitter:image"]']
            for selector in selectors:
                if 'meta' in selector:
                    img=soup.select_one(selector)
                    if img and img.get('content'):return urljoin(url,img['content'])
                else:
                    img=soup.select_one(selector)
                    if img and img.get('src'):
                        src=img['src']
                        if src.startswith('http')or src.startswith('//'):return urljoin(url,src)
                        return urljoin(url,src)
            return None
        except:return None
    
    # def _send_to_telegram(self,title,summary,link,img_url=None):
    #     if not self.tg_token or not self.tg_chat:return False
    #     try:
    #         text=f"<b>{title}</b>\n\n{summary}\n\n<a href=\"{link}\">ادامه مطلب</a>"
    #         if img_url:
    #             data={'chat_id':self.tg_chat,'photo':img_url,'caption':text,'parse_mode':'HTML'}
    #             url=f"https://api.telegram.org/bot{self.tg_token}/sendPhoto"
    #         else:
    #             data={'chat_id':self.tg_chat,'text':text,'parse_mode':'HTML','disable_web_page_preview':True}
    #             url=f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
    #         response=requests.post(url,data=data,timeout=30)
    #         return response.status_code==200
    #     except:return False

    def _send_to_telegram(self, title, summary, link, img_url=None):
        if not self.tg_token or not self.tg_chat:
            return False
        try:
            import html
            text=f"<b>{title}</b>\n\n{summary}\n\n<a href=\"{link}\">بیشتر بخوانید</a>"

            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            data = {
                "chat_id": self.tg_chat,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }

            response = requests.post(url, data=data, timeout=30)
            if response.status_code != 200:
                self._log(f"Telegram error: {response.text}", "error")
                return False
            return True
        except Exception as e:
            self._log(f"Telegram exception: {str(e)}", "error")
            return False
    
    def _save_to_db(self,title,source):
        try:
            self.db.execute('INSERT OR IGNORE INTO sent_news (title,sent_date,source) VALUES (?,?,?)',(title,datetime.now().strftime('%Y-%m-%d %H:%M:%S'),source))
            self.db.commit()
        except:pass
    
    def _git_push_db(self):
        try:
            # Check if we're in a git repository
            result = subprocess.run(['git', 'rev-parse', '--git-dir'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                self._log("Not in a git repository, skipping git operations","info")
                return
                
            subprocess.run(['git','add','news.db'],check=True)
            subprocess.run(['git','commit','-m',f'Update news.db - {datetime.now().strftime("%Y-%m-%d %H:%M")}'],check=True)
            subprocess.run(['git','push'],check=True)
            self._log("Database pushed to git","success")
        except Exception as e:
            self._log(f"Git push failed: {str(e)}","warning")
    
    def process_and_send(self,selected_news):
        sent_count=0
        for i,news in enumerate(selected_news,1):
            self._log(f"Processing {i}/{len(selected_news)}: {news['title'][:50]}...","process")
            if news['link']:
                content=self._get_full_content(news['link'])
                if content:
                    summary=self._make_api_call(self.summarization_prompt,content,800)
                    if summary and not self._is_persian(summary):
                        summary=self._make_api_call(self.translation_prompt,summary,800)
                    if summary:
                        img_url=self._extract_image(news['link'])
                        if self._send_to_telegram(news['title'],summary,news['link'],img_url):
                            self._save_to_db(news['title'],news['source'])
                            sent_count+=1
                            self._log(f"Sent: {news['title'][:30]}...","success")
                        else:self._log("Telegram send failed","error")
                    else:self._log("Summary generation failed","error")
                else:self._log("No content found","warning")
            if i<len(selected_news):time.sleep(RATE_LIMITS['news_process_delay'])
        return sent_count
    
    def run(self):
        sites=self._get_sites()
        if not sites:self._log("No sites in .env!","error");return
        self._log(f"Collecting from {len(sites)} sites","info")
        all_news=[]
        for i,site in enumerate(sites,1):
            self._log(f"[{i}/{len(sites)}]","process")
            news=self.get_news_titles(site)
            all_news.extend(news)
            if i<len(sites):time.sleep(RATE_LIMITS['site_scrape_delay'])
        unique_news={}
        for news in all_news:
            key=news['title'].strip()
            if key not in unique_news:unique_news[key]=news
        all_unique_news=list(unique_news.values())
        self._log(f"Found {len(all_unique_news)} unique titles","info")
        if all_unique_news:
            selected_news=self.select_best_news_with_ai(all_unique_news)
            if selected_news:
                self._log("Processing and sending to Telegram...","info")
                sent_count=self.process_and_send(selected_news)
                if sent_count>0:
                    self._log(f"Successfully sent {sent_count} news to Telegram","success")
                    self._git_push_db()
                else:self._log("No news sent successfully","warning")
            else:self._log("No suitable news found","warning")
        else:self._log("No news collected!","error")
        self.db.close()

if __name__=="__main__":
    scraper=NewsScraper()
    scraper.run()
