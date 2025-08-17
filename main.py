import json
import logging
import os
import re
import sys
from datetime import datetime

import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import (NEWS_SOURCES, MAX_ARTICLES_PER_SOURCE, MAX_TOTAL_ARTICLES, MAX_ARTICLES_PER_PRIORITY,
                    AI_KEYWORDS, REQUEST_TIMEOUT, LOG_CONFIG, MODEL_PROVIDERS, CURRENT_PROVIDER)

# PySpark支持
try:
    from pyspark.sql import SparkSession
    from pyspark import SparkConf
    PYSPARK_AVAILABLE = True
except ImportError:
    PYSPARK_AVAILABLE = False
    print("PySpark not available, running in standalone mode")

# 初始化模型客户端
def get_model_client(provider_name=None, logger=None):
    """获取指定模型供应商的客户端"""
    if provider_name is None:
        provider_name = CURRENT_PROVIDER
    
    if provider_name not in MODEL_PROVIDERS:
        if logger:
            logger.error(f"不支持的模型供应商: {provider_name}")
        else:
            print(f"不支持的模型供应商: {provider_name}")
        return None
    
    provider_config = MODEL_PROVIDERS[provider_name]
    
    if not provider_config.get("enabled", True):
        if logger:
            logger.error(f"模型供应商 {provider_name} 未启用")
        else:
            print(f"模型供应商 {provider_name} 未启用")
        return None
    
    try:
        if provider_name == "deepseek":
            client = OpenAI(
                api_key=provider_config["api_key"],
                base_url=provider_config["base_url"]
            )
        elif provider_name == "kimi":
            client = OpenAI(
                api_key=provider_config["api_key"],
                base_url=provider_config["base_url"]
            )
        elif provider_name == "glm":
            client = OpenAI(
                api_key=provider_config["api_key"],
                base_url=provider_config["base_url"]
            )
        else:
            if logger:
                logger.error(f"不支持的模型供应商: {provider_name}")
            else:
                print(f"不支持的模型供应商: {provider_name}")
            return None
        
        if logger:
            logger.info(f"已初始化 {provider_config['name']} 客户端")
        else:
            print(f"已初始化 {provider_config['name']} 客户端")
        
        return client
    except Exception as e:
        if logger:
            logger.error(f"初始化 {provider_config['name']} 客户端失败: {e}")
        else:
            print(f"初始化 {provider_config['name']} 客户端失败: {e}")
        return None

def setup_pyspark_environment():
    """设置PySpark环境"""
    if not PYSPARK_AVAILABLE:
        return None
    
    try:
        # 配置Spark
        conf = SparkConf()
        conf.set("spark.app.name", "AI_Daily_Robot")
        conf.set("spark.master", "yarn")  # 或者 "local[*]" 用于本地测试
        conf.set("spark.submit.deployMode", "client")
        conf.set("spark.executor.memory", "2g")
        conf.set("spark.driver.memory", "2g")
        conf.set("spark.executor.cores", "2")
        conf.set("spark.task.maxFailures", "4")
        
        # 设置Python环境
        conf.set("spark.yarn.appMasterEnv.PYTHONPATH", ":".join(sys.path))
        conf.set("spark.executorEnv.PYTHONPATH", ":".join(sys.path))
        
        spark = SparkSession.builder.config(conf=conf).getOrCreate()
        logger.info(f"PySpark session created. App ID: {spark.sparkContext.applicationId}")
        return spark
    except Exception as e:
        logger.error(f"Failed to create PySpark session: {e}")
        return None

def get_tenant_access_token(app_id, app_secret, logger):
    """获取飞书应用的tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "app_id": app_id,
        "app_secret": app_secret
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 0:
            token = result["tenant_access_token"]
            logger.info("成功获取tenant_access_token")
            return token
        else:
            logger.error(f"获取tenant_access_token失败: {result.get('msg')}")
            return None
    except Exception as e:
        logger.error(f"获取tenant_access_token时出错: {e}")
        return None

def get_ai_news_from_source(url, source_name="机器之心", logger=None):
    """从指定URL获取AI新闻"""
    try:
        if logger:
            logger.info(f"正在从 {source_name} 获取新闻...")
        
        # 根据不同的数据源使用不同的解析策略
        if source_name == "机器之心":
            return get_jiqizhixin_news(url, source_name, logger)
        elif source_name == "36氪":
            return get_36kr_news(url, source_name, logger)
        elif source_name == "InfoQ":
            return get_infoq_news(url, source_name, logger)
        elif source_name == "AMiner":
            return get_aminer_news(url, source_name, logger)
        elif source_name == "雷锋网":
            return get_leiphone_news(url, source_name, logger)
        elif source_name == "VentureBeat":
            return get_venturebeat_news(url, source_name, logger)
        elif source_name == "TechCrunch":
            return get_techcrunch_news(url, source_name, logger)
        elif source_name.endswith("RSS") or "rss" in source_name.lower():
            return get_rss_news(url, source_name, logger)
        elif source_name.endswith("API") or "api" in source_name.lower():
            return get_api_news(url, source_name, logger)
        else:
            return get_generic_news(url, source_name, logger)
    except Exception as e:
        if logger:
            logger.error(f"从 {source_name} 获取新闻时出错 {url}: {e}")
        return []

def get_jiqizhixin_news(url, source_name, logger=None):
    """获取机器之心新闻"""
    try:
        if logger: logger.debug(f"初始化Chrome浏览器配置...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-dev-tools-bridge")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-javascript-har-promises")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        # 设置二进制路径和驱动
        chrome_options.binary_location = "/usr/bin/google-chrome-stable"
        service = Service(executable_path="/usr/bin/chromedriver")
        
        if logger: logger.debug(f"启动Chrome浏览器...")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        if logger: logger.debug(f"正在访问页面: {url}")
        driver.get(url)
        
        if logger: logger.debug(f"等待页面加载...")
        wait = WebDriverWait(driver, 30)
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "home__left-body")))
        except:
            if logger: logger.warning(f"未找到home__left-body元素，尝试其他选择器")
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        
        if logger: logger.debug(f"获取页面源码...")
        page_source = driver.page_source
        if logger: logger.debug(f"页面源码长度: {len(page_source)} 字符")
        
        if logger: logger.debug(f"关闭浏览器...")
        driver.quit()
        
        soup = BeautifulSoup(page_source, "html.parser")
        articles = []
        
        news_items = soup.find_all("a", class_="body-title")
        
        if len(news_items) < 5:
            more_items = soup.find_all("a", class_=["article-item", "news-item", "post-title", "title"])
            news_items.extend(more_items)
        
        if len(news_items) < 5:
            potential_titles = soup.find_all(["h1", "h2", "h3", "h4"], class_=re.compile(r"title|heading|headline"))
            more_items = soup.find_all("a", href=re.compile(r"articles|news|post|reference"))
            news_items.extend(more_items)
        
        if len(news_items) < 5:
            all_links = soup.find_all("a", href=True)
            ai_links = []
            for link in all_links:
                text = link.get_text(strip=True)
                if len(text) > 10 and ("ai" in text.lower() or "机器" in text or "智能" in text or "AI" in text):
                    ai_links.append(link)
            news_items.extend(ai_links)
        
        for item in news_items:
            title = item.get_text(strip=True)
            if len(title) < 5:
                continue
                
            link = item.get("href", "")
            if link:
                if not link.startswith("http"):
                    if link.startswith("/"):
                        link = "https://www.jiqizhixin.com" + link
                    else:
                        link = "https://www.jiqizhixin.com/" + link
            else:
                onclick = item.get("onclick", "")
                if onclick:
                    match = re.search(r"'(https?://[^']+)'", onclick)
                    if match:
                        link = match.group(1)
                    else:
                        match = re.search(r"'(/articles/[^']+)'", onclick)
                        if match:
                            link = "https://www.jiqizhixin.com" + match.group(1)
                if not link:
                    data_href = item.get("data-href", "")
                    if data_href:
                        if not data_href.startswith("http"):
                            if data_href.startswith("/"):
                                link = "https://www.jiqizhixin.com" + data_href
                            else:
                                link = "https://www.jiqizhixin.com/" + data_href
                        else:
                            link = data_href
            
            if not link:
                continue
            
            date = datetime.now().strftime("%m月%d日")
            parent = item.find_parent()
            if parent:
                date_elements = parent.find_all(string=re.compile(r"\d{1,2}月\d{1,2}日"))
                if date_elements:
                    date_match = re.search(r"\d{1,2}月\d{1,2}日", str(date_elements[0]))
                    if date_match:
                        date = date_match.group(0)
            
            articles.append({"title": title, "link": link, "date": date, "source": source_name})
        
        return articles
    except Exception as e:
        if logger: logger.error(f"获取机器之心新闻时出错: {e}")
        return []

def get_36kr_news(url, source_name, logger=None):
    """获取36氪AI新闻"""
    try:
        # 先尝试使用requests获取
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        articles = []
        
        # 尝试多种可能的类名和选择器
        news_items = []
        
        # 方法1：寻找文章链接
        news_items.extend(soup.find_all("a", class_=["item-title", "article-title", "title", "post-title"]))
        
        # 方法2：寻找包含AI关键词的链接
        if len(news_items) < 5:
            all_links = soup.find_all("a", href=True)
            for link in all_links:
                text = link.get_text(strip=True)
                if len(text) > 10 and any(keyword in text.lower() for keyword in AI_KEYWORDS):
                    news_items.append(link)
        
        # 方法3：寻找特定的文章容器
        if len(news_items) < 5:
            news_items.extend(soup.find_all("div", class_=re.compile(r"item|article|post")))
        
        for item in news_items:
            # 如果是div容器，需要从中提取链接
            if item.name == "div":
                link_element = item.find("a")
                if not link_element:
                    continue
                title = link_element.get_text(strip=True)
                link = link_element.get("href", "")
            else:
                title = item.get_text(strip=True)
                link = item.get("href", "")
            
            if len(title) < 5:
                continue
                
            if link:
                if not link.startswith("http"):
                    if link.startswith("/"):
                        link = "https://36kr.com" + link
                    else:
                        link = "https://36kr.com/" + link
            
            if not link:
                continue
            
            # 筛选AI相关新闻
            if not any(keyword in title.lower() for keyword in AI_KEYWORDS):
                continue
            
            date = datetime.now().strftime("%m月%d日")
            
            # 尝试从父元素获取日期
            parent = item.find_parent()
            if parent:
                time_element = parent.find("time") or parent.find("span", class_=re.compile(r"time|date"))
                if time_element:
                    date_text = time_element.get_text(strip=True)
                    date_match = re.search(r"\d{1,2}月\d{1,2}日", date_text)
                    if date_match:
                        date = date_match.group(0)
            
            articles.append({"title": title, "link": link, "date": date, "source": source_name})
        
        return articles
    except Exception as e:
        if logger: logger.error(f"获取36氪新闻时出错: {e}")
        return []

def get_infoq_news(url, source_name, logger=None):
    """获取InfoQ AI新闻"""
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        articles = []
        
        news_items = soup.find_all("a", class_=["news-title", "article-title", "title"])
        
        for item in news_items:
            title = item.get_text(strip=True)
            if len(title) < 5:
                continue
                
            link = item.get("href", "")
            if link:
                if not link.startswith("http"):
                    if link.startswith("/"):
                        link = "https://www.infoq.cn" + link
                    else:
                        link = "https://www.infoq.cn/" + link
            
            if not link:
                continue
            
            # 筛选AI相关新闻
            if not any(keyword in title.lower() for keyword in AI_KEYWORDS):
                continue
            
            date = datetime.now().strftime("%m月%d日")
            
            articles.append({"title": title, "link": link, "date": date, "source": source_name})
        
        return articles
    except Exception as e:
        if logger: logger.error(f"获取InfoQ新闻时出错: {e}")
        return []

def get_aminer_news(url, source_name, logger=None):
    """获取AMiner AI新闻"""
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        articles = []
        
        news_items = soup.find_all("a", class_=["title", "paper-title", "article-title"])
        
        for item in news_items:
            title = item.get_text(strip=True)
            if len(title) < 5:
                continue
                
            link = item.get("href", "")
            if link:
                if not link.startswith("http"):
                    if link.startswith("/"):
                        link = "https://www.aminer.cn" + link
                    else:
                        link = "https://www.aminer.cn/" + link
            
            if not link:
                continue
            
            # 筛选AI相关新闻
            if not any(keyword in title.lower() for keyword in AI_KEYWORDS):
                continue
            
            date = datetime.now().strftime("%m月%d日")
            
            articles.append({"title": title, "link": link, "date": date, "source": source_name})
        
        return articles
    except Exception as e:
        if logger: logger.error(f"获取AMiner新闻时出错: {e}")
        return []

def get_leiphone_news(url, source_name, logger=None):
    """获取雷锋网AI新闻"""
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        articles = []
        
        news_items = soup.find_all("a", class_=["title", "article-title", "post-title"])
        
        for item in news_items:
            title = item.get_text(strip=True)
            if len(title) < 5:
                continue
                
            link = item.get("href", "")
            if link:
                if not link.startswith("http"):
                    if link.startswith("/"):
                        link = "https://www.leiphone.com" + link
                    else:
                        link = "https://www.leiphone.com/" + link
            
            if not link:
                continue
            
            # 筛选AI相关新闻
            if not any(keyword in title.lower() for keyword in AI_KEYWORDS):
                continue
            
            date = datetime.now().strftime("%m月%d日")
            
            articles.append({"title": title, "link": link, "date": date, "source": source_name})
        
        return articles
    except Exception as e:
        if logger: logger.error(f"获取雷锋网新闻时出错: {e}")
        return []

def get_venturebeat_news(url, source_name, logger=None):
    """获取VentureBeat AI新闻"""
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        articles = []
        
        news_items = soup.find_all("a", class_=["title", "article-title", "entry-title"])
        
        for item in news_items:
            title = item.get_text(strip=True)
            if len(title) < 5:
                continue
                
            link = item.get("href", "")
            if link and not link.startswith("http"):
                if link.startswith("/"):
                    link = "https://venturebeat.com" + link
                else:
                    link = "https://venturebeat.com/" + link
            
            if not link:
                continue
            
            # 筛选AI相关新闻
            if not any(keyword in title.lower() for keyword in AI_KEYWORDS):
                continue
            
            date = datetime.now().strftime("%m月%d日")
            
            articles.append({"title": title, "link": link, "date": date, "source": source_name})
        
        return articles
    except Exception as e:
        if logger: logger.error(f"获取VentureBeat新闻时出错: {e}")
        return []

def get_techcrunch_news(url, source_name, logger=None):
    """获取TechCrunch AI新闻"""
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        articles = []
        
        news_items = soup.find_all("a", class_=["title", "article-title", "entry-title", "post-title"])
        
        for item in news_items:
            title = item.get_text(strip=True)
            if len(title) < 5:
                continue
                
            link = item.get("href", "")
            if link and not link.startswith("http"):
                if link.startswith("/"):
                    link = "https://techcrunch.com" + link
                else:
                    link = "https://techcrunch.com/" + link
            
            if not link:
                continue
            
            # 筛选AI相关新闻
            if not any(keyword in title.lower() for keyword in AI_KEYWORDS):
                continue
            
            date = datetime.now().strftime("%m月%d日")
            
            articles.append({"title": title, "link": link, "date": date, "source": source_name})
        
        return articles
    except Exception as e:
        if logger: logger.error(f"获取TechCrunch新闻时出错: {e}")
        return []

def get_generic_news(url, source_name, logger=None):
    """通用新闻获取方法"""
    try:
        if logger: logger.debug(f"初始化Chrome浏览器配置(通用方法)...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-dev-tools-bridge")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-javascript-har-promises")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        # 设置二进制路径和驱动
        chrome_options.binary_location = "/usr/bin/google-chrome-stable"
        service = Service(executable_path="/usr/bin/chromedriver")
        
        if logger: logger.debug(f"启动Chrome浏览器(通用方法)...")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        if logger: logger.debug(f"正在访问页面(通用方法): {url}")
        driver.get(url)
        
        if logger: logger.debug(f"等待页面加载(通用方法)...")
        wait = WebDriverWait(driver, 30)
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except:
            if logger: logger.warning(f"页面加载超时，继续处理")
        
        if logger: logger.debug(f"获取页面源码(通用方法)...")
        page_source = driver.page_source
        if logger: logger.debug(f"页面源码长度(通用方法): {len(page_source)} 字符")
        
        if logger: logger.debug(f"关闭浏览器(通用方法)...")
        driver.quit()
        
        soup = BeautifulSoup(page_source, "html.parser")
        articles = []
        
        news_items = soup.find_all("a", class_=["title", "article-title", "entry-title", "post-title"])
        
        for item in news_items:
            title = item.get_text(strip=True)
            if len(title) < 5:
                continue
                
            link = item.get("href", "")
            if not link:
                continue
            
            date = datetime.now().strftime("%m月%d日")
            
            articles.append({"title": title, "link": link, "date": date, "source": source_name})
        
        return articles
    except Exception as e:
        if logger: logger.error(f"获取通用新闻时出错: {e}")
        return []

def get_rss_news(url, source_name, logger=None):
    """获取RSS/ATOM新闻"""
    try:
        feed = feedparser.parse(url)
        articles = []
        
        for entry in feed.entries:
            title = entry.get('title', '')
            if not title or len(title.strip()) < 5:
                continue
                
            link = entry.get('link', '')
            if not link:
                continue
            
            # 筛选AI相关新闻
            title_lower = title.lower()
            ai_keywords = ["ai", "artificial intelligence", "machine learning", "deep learning", "neural", 
                          "algorithm", "model", "chatgpt", "openai", "gpt", "transformer", "llm",
                          "人工智能", "机器学习", "深度学习", "智能", "算法", "大模型"]
            
            if not any(keyword in title_lower for keyword in ai_keywords):
                continue
            
            # 获取日期
            date = datetime.now().strftime("%m月%d日")
            if 'published' in entry:
                try:
                    pub_date = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %z')
                    date = pub_date.strftime("%m月%d日")
                except:
                    pass
            
            articles.append({
                "title": title.strip(),
                "link": link,
                "date": date,
                "source": source_name
            })
        
        return articles
    except Exception as e:
        if logger: logger.error(f"获取RSS新闻时出错: {e}")
        return []

def get_api_news(url, source_name, logger=None):
    """获取API新闻"""
    try:
        # 设置请求头
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        articles = []
        
        # 处理不同的API响应格式
        if isinstance(data, dict):
            # 尝试不同的API响应格式
            articles_data = []
            
            # 格式1: {articles: [...]}
            if 'articles' in data:
                articles_data = data['articles']
            # 格式2: {data: [...]}
            elif 'data' in data and isinstance(data['data'], list):
                articles_data = data['data']
            # 格式3: {items: [...]}
            elif 'items' in data:
                articles_data = data['items']
            # 格式4: {results: [...]}
            elif 'results' in data:
                articles_data = data['results']
            # 格式5: {response: {docs: [...]}}
            elif 'response' in data and isinstance(data['response'], dict) and 'docs' in data['response']:
                articles_data = data['response']['docs']
            
            for item in articles_data:
                if isinstance(item, dict):
                    title = item.get('title', item.get('headline', item.get('name', '')))
                    link = item.get('url', item.get('link', item.get('href', '')))
                    
                    if not title or len(title.strip()) < 5:
                        continue
                    
                    if not link:
                        continue
                    
                    # 筛选AI相关新闻
                    title_lower = title.lower()
                    ai_keywords = ["ai", "artificial intelligence", "machine learning", "deep learning", "neural", 
                                  "algorithm", "model", "chatgpt", "openai", "gpt", "transformer", "llm",
                                  "人工智能", "机器学习", "深度学习", "智能", "算法", "大模型"]
                    
                    if not any(keyword in title_lower for keyword in ai_keywords):
                        continue
                    
                    # 获取日期
                    date = datetime.now().strftime("%m月%d日")
                    pub_date = item.get('publishedAt', item.get('published_date', item.get('date', '')))
                    if pub_date:
                        try:
                            # 尝试解析不同的日期格式
                            for date_format in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S']:
                                try:
                                    pub_date_obj = datetime.strptime(pub_date, date_format)
                                    date = pub_date_obj.strftime("%m月%d日")
                                    break
                                except:
                                    continue
                        except:
                            pass
                    
                    articles.append({
                        "title": title.strip(),
                        "link": link,
                        "date": date,
                        "source": source_name
                    })
        
        return articles
    except Exception as e:
        if logger: logger.error(f"获取API新闻时出错: {e}")
        return []

def get_ai_news(logger=None):
    """从多个数据源获取AI新闻，按照优先级排序"""
    all_articles = []
    
    # 从配置文件获取启用的数据源，并按优先级排序
    enabled_sources = [source for source in NEWS_SOURCES if source.get("enabled", True)]
    enabled_sources.sort(key=lambda x: x.get("priority", 3), reverse=True)
    
    # 从每个数据源获取新闻
    for source in enabled_sources:
        logger.info(f"正在从 {source['name']} (优先级: {source.get('priority', 3)}) 获取新闻...")
        articles = get_ai_news_from_source(source["url"], source["name"], logger)
        
        # 为每篇文章添加优先级信息
        priority = source.get("priority", 3)
        for article in articles:
            article["priority"] = priority
        
        # 限制每个源的文章数量
        articles = articles[:MAX_ARTICLES_PER_SOURCE]
        all_articles.extend(articles)
    
    # 去重 - 优先基于标题去重，避免重复内容
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        # 清理标题，去除多余空格和特殊字符
        clean_title = article["title"].strip()
        # 使用标题作为去重的主要依据
        if clean_title not in seen_titles and len(clean_title) > 10:
            seen_titles.add(clean_title)
            unique_articles.append(article)
    
    # 按优先级排序文章
    unique_articles.sort(key=lambda x: x.get("priority", 3), reverse=True)
    
    # 根据优先级限制文章数量
    priority_articles = []
    priority_counts = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    
    for article in unique_articles:
        priority = article.get("priority", 3)
        if priority_counts[priority] < MAX_ARTICLES_PER_PRIORITY.get(priority, 4):
            priority_articles.append(article)
            priority_counts[priority] += 1
        
        # 如果已经获取足够多的文章，提前退出
        if len(priority_articles) >= MAX_TOTAL_ARTICLES:
            break
    
    return priority_articles

def summarize_news(news_list, logger=None, provider_name=None):
    """使用AI对新闻列表进行摘要"""
    try:
        # 获取模型客户端
        client = get_model_client(provider_name, logger)
        if not client:
            if logger:
                logger.error("无法获取模型客户端")
            else:
                print("无法获取模型客户端")
            return "无法生成摘要：模型客户端初始化失败"
        
        # 获取供应商配置
        if provider_name is None:
            provider_name = CURRENT_PROVIDER
        provider_config = MODEL_PROVIDERS[provider_name]
        
        # 构建包含来源信息的新闻文本
        news_items = []
        for news in news_list:
            if "source" in news:
                news_items.append(f'标题: {news["title"]} (来源: {news["source"]}, 日期: {news["date"]})')
            else:
                news_items.append(f'标题: {news["title"]} (日期: {news["date"]})')
        news_text = "\n".join(news_items)
        
        response = client.chat.completions.create(
            model=provider_config["model"],
            messages=[
                {"role": "user", "content": f"请总结以下AI新闻，提取关键信息和趋势:\n{news_text}"}
            ],
            max_tokens=provider_config["max_tokens"]
        )
        if logger:
            logger.debug(f"API响应: {response}")
        return response.choices[0].message.content.strip()
    except Exception as e:
        if logger:
            logger.error(f"生成摘要时出错: {e}")
        else:
            print(f"生成摘要时出错: {e}")
        return "无法生成摘要。"

def send_to_feishu(webhook_url, summary, news_list, image_key=None, logger=None):
    """发送消息到飞书群聊，支持卡片消息格式"""
    try:
        headers = {
            "Content-Type": "application/json"
        }
        
        # 处理摘要内容，保留必要的格式标记
        clean_summary = summary.replace('### **关键信息与趋势总结**', '**关键信息与趋势总结**')  # 特殊处理主标题
        clean_summary = clean_summary.replace('### **核心趋势提炼**', '**核心趋势提炼**')  # 特殊处理核心趋势标题
        clean_summary = clean_summary.replace('### ', '')  # 移除其他主标题标记
        clean_summary = clean_summary.replace('#### ', '')  # 移除子标题标记
        clean_summary = clean_summary.replace('#', '')  # 移除井号标记
        clean_summary = clean_summary.replace('`', '')  # 移除反引号标记
        clean_summary = clean_summary.replace('_', '')  # 移除下划线标记
        clean_summary = clean_summary.replace('~', '')  # 移除波浪线标记
        
        # 构建卡片消息内容
        card_elements = []
        
        # 移除了图片部分，避免可能的图片问题导致消息发送失败
        
        # 移除了重复的日期显示，避免与卡片头部标题重复
        
        # 添加分割线
        card_elements.append({
            "tag": "hr"
        })
        
        # 添加摘要标题
        card_elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**📊 今日AI热点摘要:**"
            }
        })
        
        # 添加摘要内容（优化标题和正文的格式处理）
        # 按段落分割
        summary_paragraphs = clean_summary.split('\n\n')
        for paragraph in summary_paragraphs:
            if paragraph.strip():
                # 处理段落中的换行
                lines = paragraph.split('\n')
                formatted_lines = []
                for line in lines:
                    if line.strip():
                        # 保留原有的粗体标记
                        formatted_lines.append(line.strip())
                
                formatted_paragraph = '\n'.join(formatted_lines)
                
                # 识别并处理标题
                stripped_paragraph = formatted_paragraph.strip()
                if stripped_paragraph.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')) and len(stripped_paragraph) < 100:
                    # 数字开头的短段落，认为是小节标题
                    if not stripped_paragraph.startswith('**'):
                        formatted_paragraph = f"**{stripped_paragraph}**"
                elif stripped_paragraph.startswith("关键信息与趋势总结") or stripped_paragraph.startswith("核心趋势总结"):
                    # 特殊标题处理
                    if not stripped_paragraph.startswith('**'):
                        formatted_paragraph = f"**{stripped_paragraph}**"
                elif len(stripped_paragraph) < 50 and ':' in stripped_paragraph and stripped_paragraph.count(':') <= 1:
                    # 短段落且包含单个冒号，可能是小节标题
                    if not stripped_paragraph.startswith('**'):
                        formatted_paragraph = f"**{stripped_paragraph}**"
                
                card_elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": formatted_paragraph
                    }
                })
        
        # 添加分割线
        card_elements.append({
            "tag": "hr"
        })
        
        # 添加新闻列表标题
        card_elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**📰 详细新闻列表:**"
            }
        })
        
        # 添加新闻条目
        for i, news in enumerate(news_list[:10], 1):  # 限制最多显示10条新闻
            # 构建新闻条目内容，包含来源信息（如果有）
            if "source" in news:
                news_content = f"{i}. [{news['title']}]({news['link']}) 来源: {news['source']} 日期: {news['date']}"
            else:
                news_content = f"{i}. [{news['title']}]({news['link']}) 日期: {news['date']}"
                
            card_elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": news_content
                }
            })
        
        # 构建卡片消息
        data = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True,
                    "enable_forward": True
                },
                "header": {
                    "template": "blue",
                    "title": {
                        "content": "🤖 AI日报 - {}".format(datetime.now().strftime("%Y年%m月%d日")),
                        "tag": "plain_text"
                    }
                },
                "elements": card_elements
            }
        }
            
        response = requests.post(webhook_url, headers=headers, data=json.dumps(data, ensure_ascii=False).encode('utf-8'))
        response.raise_for_status()
        if logger:
            logger.info("消息已成功发送到飞书")
        else:
            print("消息已成功发送到飞书")
        return True
    except Exception as e:
        if logger:
            logger.error(f"发送到飞书时出错: {e}")
        else:
            print(f"发送到飞书时出错: {e}")
        return False

def upload_image_to_feishu(image_path, access_token, logger=None):
    """上传图片到飞书并获取image_key"""
    try:
        upload_url = "https://open.feishu.cn/open-apis/im/v1/images"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
        }
        
        files = {
            "image_type": (None, "message"),
            "image": (os.path.basename(image_path), open(image_path, "rb"), "image/jpeg") 
        }
        
        response = requests.post(upload_url, headers=headers, files=files)
        response.raise_for_status()
        
        result = response.json()
        if result.get("code") == 0:
            image_key = result["data"]["image_key"]
            if logger:
                logger.info(f"图片上传成功，image_key: {image_key}")
            else:
                print(f"图片上传成功，image_key: {image_key}")
            return image_key
        else:
            if logger:
                logger.error(f"图片上传失败: {result.get('msg')}")
            else:
                print(f"图片上传失败: {result.get('msg')}")
            return None
    except Exception as e:
        if logger:
            logger.error(f"上传图片到飞书时出错: {e}")
        else:
            print(f"上传图片到飞书时出错: {e}")
        return None

# 多webhook配置
WEBHOOK_CONFIGS = [
    {
        "name": "主群聊",
        "url": "https://open.feishu.cn/open-apis/bot/v2/hook/02880094-6e28-4dea-a815-ff02fea49072",
        "enabled": True,
        "send_image": True
    },
    {
        "name": "测试群聊", 
        "url": "https://open.feishu.cn/open-apis/bot/v2/hook/your_test_webhook_url_here",
        "enabled": False,
        "send_image": False
    },
    {
        "name": "备份群聊",
        "url": "https://open.feishu.cn/open-apis/bot/v2/hook/your_backup_webhook_url_here", 
        "enabled": False,
        "send_image": False
    }
]

def print_model_provider_configs(logger=None):
    """打印当前模型供应商配置状态"""
    if logger:
        logger.info("\n" + "="*50)
        logger.info("当前模型供应商配置状态:")
        logger.info("="*50)
        
        for provider_name, config in MODEL_PROVIDERS.items():
            status = "✅ 启用" if config.get("enabled", True) else "❌ 禁用"
            current = "👉 当前使用" if provider_name == CURRENT_PROVIDER else ""
            logger.info(f"🤖 {config['name']} ({provider_name}): {status} {current}")
            logger.info(f"   模型: {config['model']}")
            logger.info(f"   最大Token: {config['max_tokens']}")
            logger.info("-" * 30)
        
        logger.info(f"📊 当前使用: {MODEL_PROVIDERS[CURRENT_PROVIDER]['name']}")
        logger.info("="*50 + "\n")
    else:
        print("\n" + "="*50)
        print("当前模型供应商配置状态:")
        print("="*50)
        
        for provider_name, config in MODEL_PROVIDERS.items():
            status = "✅ 启用" if config.get("enabled", True) else "❌ 禁用"
            current = "👉 当前使用" if provider_name == CURRENT_PROVIDER else ""
            print(f"🤖 {config['name']} ({provider_name}): {status} {current}")
            print(f"   模型: {config['model']}")
            print(f"   最大Token: {config['max_tokens']}")
            print("-" * 30)
        
        print(f"📊 当前使用: {MODEL_PROVIDERS[CURRENT_PROVIDER]['name']}")
        print("="*50 + "\n")

def print_webhook_configs(logger=None):
    """打印当前webhook配置状态"""
    if logger:
        logger.info("\n" + "="*50)
        logger.info("当前Webhook配置状态:")
        logger.info("="*50)
        
        enabled_count = 0
        for config in WEBHOOK_CONFIGS:
            status = "✅ 启用" if config["enabled"] else "❌ 禁用"
            image_status = "✅ 发送" if config["send_image"] else "❌ 不发送"
            logger.info(f"📌 {config['name']}: {status}")
            logger.info(f"   URL: {config['url']}")
            logger.info(f"   图片: {image_status}")
            logger.info("-" * 30)
            if config["enabled"]:
                enabled_count += 1
        
        logger.info(f"📊 总计: {enabled_count}/{len(WEBHOOK_CONFIGS)} 个webhook已启用")
        logger.info("="*50 + "\n")
    else:
        # 如果没有logger，使用print作为后备
        print("\n" + "="*50)
        print("当前Webhook配置状态:")
        print("="*50)
        
        enabled_count = 0
        for config in WEBHOOK_CONFIGS:
            status = "✅ 启用" if config["enabled"] else "❌ 禁用"
            image_status = "✅ 发送" if config["send_image"] else "❌ 不发送"
            print(f"📌 {config['name']}: {status}")
            print(f"   URL: {config['url']}")
            print(f"   图片: {image_status}")
            print("-" * 30)
            if config["enabled"]:
                enabled_count += 1
        
        print(f"📊 总计: {enabled_count}/{len(WEBHOOK_CONFIGS)} 个webhook已启用")
        print("="*50 + "\n")

def send_to_multiple_webhooks(summary, news_list, image_key=None, logger=None):
    """并发发送消息到多个webhook"""
    import concurrent.futures

    print_webhook_configs(logger)
    
    # 获取启用的webhook
    enabled_webhooks = [config for config in WEBHOOK_CONFIGS if config["enabled"]]
    
    if not enabled_webhooks:
        if logger:
            logger.error("❌ 没有启用的webhook配置")
        else:
            print("❌ 没有启用的webhook配置")
        return False
    
    if logger:
        logger.info(f"🚀 开始并发发送到 {len(enabled_webhooks)} 个webhook...")
    else:
        print(f"🚀 开始并发发送到 {len(enabled_webhooks)} 个webhook...")
    
    success_count = 0
    failure_count = 0
    results = []
    
    # 使用线程池并发发送
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(enabled_webhooks), 5)) as executor:
        # 创建发送任务
        future_to_config = {}
        for config in enabled_webhooks:
            # 根据配置决定是否发送图片
            webhook_image_key = image_key if config["send_image"] else None
            future = executor.submit(send_to_feishu, config["url"], summary, news_list, webhook_image_key, config["name"])
            future_to_config[future] = config
        
        # 等待所有任务完成
        for future in concurrent.futures.as_completed(future_to_config):
            config = future_to_config[future]
            try:
                result = future.result()
                
                # 标准化处理返回值
                if isinstance(result, bool):
                    success = result
                    error_msg = None
                elif isinstance(result, str):
                    success = False
                    error_msg = result
                else:
                    success = False
                    error_msg = f"返回值类型错误: {type(result)}"
                
                results.append({
                    "name": config["name"],
                    "success": success,
                    "error": error_msg
                })
                
                if success:
                    success_count += 1
                    log_msg = f"✅ {config['name']}: 发送成功"
                else:
                    failure_count += 1
                    log_msg = f"❌ {config['name']}: 发送失败"
                    if error_msg:
                        log_msg += f" - {error_msg}"
                
                if logger:
                    logger.info(log_msg)
                else:
                    print(log_msg)
                    
            except Exception as e:
                failure_count += 1
                error_msg = str(e)
                results.append({
                    "name": config["name"],
                    "success": False,
                    "error": error_msg
                })
                log_msg = f"❌ {config['name']}: 发送异常 - {error_msg}"
                if logger:
                    logger.error(log_msg)
                else:
                    print(log_msg)
    
    # 打印最终统计
    if logger:
        logger.info("\n" + "="*50)
        logger.info("📊 发送结果统计:")
        logger.info("="*50)
        logger.info(f"✅ 成功: {success_count}")
        logger.info(f"❌ 失败: {failure_count}")
        logger.info(f"📈 总计: {success_count + failure_count}")
    else:
        print("\n" + "="*50)
        print("📊 发送结果统计:")
        print("="*50)
        print(f"✅ 成功: {success_count}")
        print(f"❌ 失败: {failure_count}")
        print(f"📈 总计: {success_count + failure_count}")
    
    if failure_count > 0:
        if logger:
            logger.warning("\n❌ 失败详情:")
            for result in results:
                if not result["success"]:
                    error_info = result.get('error', '未知错误') if isinstance(result, dict) else '结果格式错误'
                    logger.warning(f"   - {result.get('name', '未知webhook')}: {error_info}")
        else:
            print("\n❌ 失败详情:")
            for result in results:
                if not result["success"]:
                    error_info = result.get('error', '未知错误') if isinstance(result, dict) else '结果格式错误'
                    print(f"   - {result.get('name', '未知webhook')}: {error_info}")
    
    if logger:
        logger.info("="*50 + "\n")
    else:
        print("="*50 + "\n")
    
    # 如果至少有一个成功，就返回True
    return success_count > 0

def setup_logging():
    """设置日志配置"""
    try:
        # 创建日志目录
        log_dir = os.path.dirname(LOG_CONFIG["file"])
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 配置日志
        logging.basicConfig(
            level=getattr(logging, LOG_CONFIG["level"]),
            format=LOG_CONFIG["format"],
            handlers=[
                logging.FileHandler(LOG_CONFIG["file"], encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )

        logger = logging.getLogger(__name__)
        logger.info("日志系统初始化完成")
        return logger
    except Exception as e:
        print(f"日志系统初始化失败: {e}")  # 这里不能使用logger，因为logger还未初始化
        # 返回一个基本的logger
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(__name__)

def main():
    """主函数 - 支持PySpark环境"""
    start_time = datetime.now()
    logger = setup_logging()

    logger.info("=" * 60)
    logger.info(f"[START] 开始执行AI日报任务 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    logger.info(f"日志级别: {LOG_CONFIG['level']}")
    logger.info(f"日志文件: {LOG_CONFIG['file']}")
    
    # 打印模型供应商配置
    print_model_provider_configs(logger)
    
    # 初始化PySpark环境（如果可用）
    spark = None
    if PYSPARK_AVAILABLE:
        logger.info("正在初始化PySpark环境...")
        spark = setup_pyspark_environment()
        if not spark:
            logger.warning("PySpark初始化失败，降级到独立模式运行")
    else:
        logger.info("[INFO] 运行在独立模式（非PySpark环境）")
    
    try:
        # 飞书应用凭证
        feishu_app_id = "cli_a8ef4e27bd85900b"
        feishu_app_secret = "By4Y7Z2NpQvovyJ0Efp2CgyOF8dAC7bV"
        logger.info(f"[INFO] 飞书应用ID: {feishu_app_id}")
        
        # 获取tenant_access_token
        logger.info("[INFO] 正在获取飞书访问令牌...")
        access_token = get_tenant_access_token(feishu_app_id, feishu_app_secret, logger)
        if not access_token:
            logger.error("[ERROR] 无法获取access_token，退出任务。")
            return
        logger.info("[SUCCESS] 成功获取访问令牌")

        # 获取AI新闻（从多个数据源）
        logger.info("[INFO] 开始获取AI新闻...")
        ai_news = get_ai_news(logger)
        
        if ai_news:
            logger.info(f"[SUCCESS] 成功获取 {len(ai_news)} 条新闻")
            
            # 生成摘要
            logger.info("[INFO] 正在生成新闻摘要...")
            summary = summarize_news(ai_news, logger)
            
            logger.info("[SUCCESS] 生成的日报摘要:")
            logger.info("-" * 40)
            logger.info(summary)
            logger.info("-" * 40)
            
            # 上传主题图片并发送
            # 检查图片文件是否存在，如果不存在则跳过图片上传
            image_path = "/home/ubuntu/upload/search_images/QkPqdKuxZOlT.jpg" # 选择一张AI相关的图片
            image_key = None
            if os.path.exists(image_path):
                logger.info("[INFO] 正在上传图片到飞书...")
                image_key = upload_image_to_feishu(image_path, access_token, logger)
            else:
                logger.warning(f"[WARNING] 图片文件不存在: {image_path}，已移除图片以确保消息发送成功")
                # 已移除图片部分，避免可能的图片问题导致消息发送失败
            
            logger.info("[INFO] 正在发送消息到飞书...")
            # 使用多webhook发送功能
            send_success = send_to_multiple_webhooks(summary, ai_news, image_key, logger)
            
            if send_success:
                logger.info("[SUCCESS] AI日报已成功发送到所有配置的webhook")
            else:
                logger.warning("[WARNING] 部分webhook发送失败，请检查日志")
            
        else:
            logger.error("[ERROR] 未能获取AI新闻")
            
    except Exception as e:
        logger.error(f"[ERROR] 主函数执行出错: {e}")
        import traceback
        logger.error(f"[ERROR] 详细错误信息:\n{traceback.format_exc()}")
        
    finally:
        # 清理PySpark资源
        if spark:
            logger.info("正在清理PySpark资源...")
            try:
                spark.stop()
                logger.info("PySpark资源已清理")
            except Exception as e:
                logger.error(f"清理PySpark资源时出错: {e}")
        
        end_time = datetime.now()
        duration = end_time - start_time
        logger.info("=" * 60)
        logger.info(f"[END] AI日报任务完成 - {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"总执行时间: {duration}")
        logger.info("=" * 60)

if __name__ == "__main__":
    main()

