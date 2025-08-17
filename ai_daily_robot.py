import requests
from bs4 import BeautifulSoup
import os
from openai import OpenAI
import json
from datetime import datetime
import re
import time
import sys
import logging
import argparse
import signal
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import feedparser

# 尝试导入APScheduler，如果失败则提示用户安装
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    print("[WARNING] APScheduler未安装，定时任务功能不可用。请运行: pip install APScheduler>=3.10.0")

# 配置参数
NEWS_SOURCES = [
    # 中文新闻源 (优先级: 1-5, 5最高)
    {"url": "https://36kr.com", "name": "36氪", "enabled": True, "priority": 5},
    {"url": "https://www.jiqizhixin.com/", "name": "机器之心", "enabled": True, "priority": 5},
    {"url": "https://www.aminer.cn/topic/ai", "name": "AMiner", "enabled": True, "priority": 4},
    {"url": "https://www.infoq.cn/topic/AI&LLM", "name": "InfoQ", "enabled": True, "priority": 3},
    {"url": "https://www.leiphone.com/category/ai", "name": "雷锋网", "enabled": True, "priority": 4},

    # 英文新闻源
    {"url": "https://venturebeat.com/category/ai/", "name": "VentureBeat", "enabled": True, "priority": 4},
    {"url": "https://techcrunch.com/category/artificial-intelligence/", "name": "TechCrunch", "enabled": True, "priority": 4},

    # RSS源 (通常更新频繁，优先级稍低)
    {"url": "https://feeds.feedburner.com/venturebeat/SZYF", "name": "VentureBeat RSS", "enabled": True, "priority": 3},
    {"url": "https://techcrunch.com/feed/", "name": "TechCrunch RSS", "enabled": True, "priority": 3},
    {"url": "https://www.artificialintelligence-news.com/feed/", "name": "AI News RSS", "enabled": True, "priority": 2},
    {"url": "https://www.mit.edu/~jintao/ai_news.xml", "name": "MIT AI News RSS", "enabled": True, "priority": 2},

    # API源 (需要API密钥)
    # {"url": "https://newsapi.org/v2/everything?q=artificial+intelligence&language=en&sortBy=publishedAt&apiKey=YOUR_API_KEY", "name": "NewsAPI", "enabled": False, "priority": 3},
    # {"url": "https://gnews.io/api/v4/search?q=artificial+intelligence&token=YOUR_API_KEY", "name": "GNews API", "enabled": False, "priority": 3},
    # {"url": "https://api.currentsapi.services/v1/search?keywords=artificial+intelligence&apiKey=YOUR_API_KEY", "name": "CurrentsAPI", "enabled": False, "priority": 2},
]

MAX_ARTICLES_PER_SOURCE = 10  # 每个源最多获取的文章数量
MAX_TOTAL_ARTICLES = 30       # 总共最多返回的文章数量
MAX_ARTICLES_PER_PRIORITY = {  # 每个优先级最多返回的文章数量
    5: 8,   # 高优先级源最多8条
    4: 6,   # 中高优先级源最多6条
    3: 4,   # 中优先级源最多4条
    2: 2,   # 低优先级源最多2条
    1: 1    # 最低优先级源最多1条
}
AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "deep learning", "neural", 
    "algorithm", "model", "chatgpt", "openai", "gpt", "transformer", "llm",
    "人工智能", "机器学习", "深度学习", "智能", "算法", "大模型", "神经网络"
]

REQUEST_TIMEOUT = 30  # 请求超时时间（秒）
RETRY_COUNT = 3      # 重试次数
RETRY_DELAY = 2      # 重试间隔（秒）

# 定时任务配置
SCHEDULER_CONFIG = {
    "enabled": False,  # 是否启用定时任务
    "timezone": "Asia/Shanghai",  # 时区设置
    "cron_expression": "0 9 * * *",  # 默认每天上午9点执行
    "max_instances": 1,  # 最大并发实例数
    "misfire_grace_time": 3600,  # 错过执行时间的宽容时间（秒）
}

# 日志配置
LOG_CONFIG = {
    "level": "INFO",  # 日志级别: DEBUG, INFO, WARNING, ERROR
    "file": "ai_daily_robot.log",  # 日志文件路径
    "max_size": 10485760,  # 日志文件最大大小（10MB）
    "backup_count": 5,  # 保留的日志文件数量
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # 日志格式
}

# 多Webhook配置
WEBHOOK_CONFIGS = [
    {
        "name": "主群聊",
        "url": "https://open.feishu.cn/open-apis/bot/v2/hook/4d6b0afa-c34f-4b0f-9bb3-1716bc2ed4a3",
        "enabled": True,
        "send_image": True
    },
    {
        "name": "测试群聊", 
        "url": "https://open.feishu.cn/open-apis/bot/v2/hook/02880094-6e28-4dea-a815-ff02fea49072",
        "enabled": True,
        "send_image": True
    },
    {
        "name": "备份群聊",
        "url": "https://open.feishu.cn/open-apis/bot/v2/hook/your_backup_webhook_url_here", 
        "enabled": False,
        "send_image": False
    }
]

# 配置OpenAI API
# 请将下面的"your_actual_api_key_here"替换为您从deepseek获取的实际API密钥
API_KEY = "sk-e9c92f4884e742c1a533d17c1ab729d0"
client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com/")

# 全局变量
scheduler = None
logger = None
shutdown_event = None

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
        
        global logger
        logger = logging.getLogger(__name__)
        logger.info("日志系统初始化完成")
        return logger
    except Exception as e:
        print(f"日志系统初始化失败: {e}")
        # 返回一个基本的logger
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(__name__)

def signal_handler(signum, frame):
    """信号处理器，用于优雅关闭"""
    global logger, scheduler, shutdown_event
    
    if logger:
        logger.info(f"接收到信号 {signum}，准备关闭程序...")
    else:
        print(f"接收到信号 {signum}，准备关闭程序...")
    
    if shutdown_event:
        shutdown_event.set()
    
    if scheduler:
        scheduler.shutdown(wait=True)
    
    if logger:
        logger.info("程序已安全关闭")
    else:
        print("程序已安全关闭")
    
    sys.exit(0)

def setup_scheduler():
    """设置定时任务调度器"""
    global scheduler
    
    if not APSCHEDULER_AVAILABLE:
        if logger:
            logger.error("APScheduler不可用，无法启动定时任务")
        else:
            print("APScheduler不可用，无法启动定时任务")
        return None
    
    try:
        scheduler = BackgroundScheduler(
            timezone=SCHEDULER_CONFIG["timezone"],
            max_instances=SCHEDULER_CONFIG["max_instances"]
        )
        
        # 添加定时任务
        scheduler.add_job(
            func=execute_scheduled_task,
            trigger=CronTrigger.from_crontab(SCHEDULER_CONFIG["cron_expression"]),
            id='ai_daily_robot_task',
            name='AI日报机器人定时任务',
            replace_existing=True,
            misfire_grace_time=SCHEDULER_CONFIG["misfire_grace_time"]
        )
        
        if logger:
            logger.info(f"定时任务调度器已设置，cron表达式: {SCHEDULER_CONFIG['cron_expression']}")
        else:
            print(f"定时任务调度器已设置，cron表达式: {SCHEDULER_CONFIG['cron_expression']}")
        
        return scheduler
    except Exception as e:
        if logger:
            logger.error(f"设置定时任务调度器失败: {e}")
        else:
            print(f"设置定时任务调度器失败: {e}")
        return None

def execute_scheduled_task():
    """执行定时任务的函数"""
    global logger
    
    try:
        if logger:
            logger.info("=" * 60)
            logger.info(f"[SCHEDULED_TASK] 开始执行定时AI日报任务 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 60)
        else:
            print("=" * 60)
            print(f"[SCHEDULED_TASK] 开始执行定时AI日报任务 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)
        
        # 执行主要的AI日报任务
        execute_ai_robot_task()
        
        if logger:
            logger.info("=" * 60)
            logger.info(f"[SCHEDULED_TASK] 定时AI日报任务完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 60)
        else:
            print("=" * 60)
            print(f"[SCHEDULED_TASK] 定时AI日报任务完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)
            
    except Exception as e:
        if logger:
            logger.error(f"定时任务执行出错: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
        else:
            print(f"定时任务执行出错: {e}")
            import traceback
            print(f"详细错误信息: {traceback.format_exc()}")

def execute_ai_robot_task():
    """执行AI机器人核心任务"""
    global logger
    
    try:
        # 飞书应用凭证
        feishu_app_id = "cli_a8ef4e27bd85900b"
        feishu_app_secret = "By4Y7Z2NpQvovyJ0Efp2CgyOF8dAC7bV"
        
        if logger:
            logger.info(f"飞书应用ID: {feishu_app_id}")
        else:
            print(f"飞书应用ID: {feishu_app_id}")
        
        # 获取tenant_access_token
        if logger:
            logger.info("正在获取飞书访问令牌...")
        else:
            print("正在获取飞书访问令牌...")
        
        access_token = get_tenant_access_token(feishu_app_id, feishu_app_secret)
        if not access_token:
            if logger:
                logger.error("无法获取access_token，任务失败。")
            else:
                print("无法获取access_token，任务失败。")
            return False
        
        if logger:
            logger.info("成功获取访问令牌")
        else:
            print("成功获取访问令牌")

        # 获取AI新闻
        if logger:
            logger.info("开始获取AI新闻...")
        else:
            print("开始获取AI新闻...")
        
        ai_news = get_ai_news()
        
        if ai_news:
            if logger:
                logger.info(f"成功获取 {len(ai_news)} 条新闻")
            else:
                print(f"成功获取 {len(ai_news)} 条新闻")
            
            # 生成摘要
            if logger:
                logger.info("正在生成新闻摘要...")
            else:
                print("正在生成新闻摘要...")
            
            summary = summarize_news(ai_news)
            
            if logger:
                logger.info("生成的日报摘要:")
                logger.info("-" * 40)
                logger.info(summary)
                logger.info("-" * 40)
            else:
                print("生成的日报摘要:")
                print("-" * 40)
                print(summary)
                print("-" * 40)
            
            # 上传主题图片
            image_path = "/home/ubuntu/upload/search_images/QkPqdKuxZOlT.jpg"
            image_key = None
            if os.path.exists(image_path):
                if logger:
                    logger.info(f"找到图片文件，开始上传: {image_path}")
                else:
                    print(f"找到图片文件，开始上传: {image_path}")
                image_key = upload_image_to_feishu(image_path, access_token)
            else:
                if logger:
                    logger.warning(f"图片文件不存在: {image_path}，部分webhook将不包含图片")
                else:
                    print(f"图片文件不存在: {image_path}，部分webhook将不包含图片")
            
            # 显示当前webhook配置
            print_webhook_configs()
            
            # 发送到多个webhook
            if logger:
                logger.info("开始发送消息到多个飞书群聊...")
            else:
                print("开始发送消息到多个飞书群聊...")
            
            success_count, failed_count = send_to_multiple_webhooks(summary, ai_news, image_key)
            
            if logger:
                logger.info(f"Webhook发送结果统计: 成功 {success_count} 个，失败 {failed_count} 个")
            else:
                print(f"Webhook发送结果统计: 成功 {success_count} 个，失败 {failed_count} 个")
            
            return True
        else:
            if logger:
                logger.error("未能获取AI新闻")
            else:
                print("未能获取AI新闻")
            return False
            
    except Exception as e:
        if logger:
            logger.error(f"AI机器人任务执行出错: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
        else:
            print(f"AI机器人任务执行出错: {e}")
            import traceback
            print(f"详细错误信息: {traceback.format_exc()}")
        return False

def get_tenant_access_token(app_id, app_secret):
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
            print("成功获取tenant_access_token")
            return token
        else:
            print("获取tenant_access_token失败: {}".format(result.get("msg")))
            return None
    except Exception as e:
        print(f"获取tenant_access_token时出错: {e}")
        return None

def get_ai_news_from_source(url, source_name="机器之心"):
    """从指定URL获取AI新闻"""
    try:
        print(f"[DEBUG] 开始从 {source_name} 获取新闻...")
        print(f"[DEBUG] 请求URL: {url}")
        
        # 根据不同的数据源使用不同的解析策略
        if source_name == "机器之心":
            return get_jiqizhixin_news(url, source_name)
        elif source_name == "36氪":
            return get_36kr_news(url, source_name)
        elif source_name == "InfoQ":
            return get_infoq_news(url, source_name)
        elif source_name == "AMiner":
            return get_aminer_news(url, source_name)
        elif source_name == "雷锋网":
            return get_leiphone_news(url, source_name)
        elif source_name == "VentureBeat":
            return get_venturebeat_news(url, source_name)
        elif source_name == "TechCrunch":
            return get_techcrunch_news(url, source_name)
        elif source_name.endswith("RSS") or "rss" in source_name.lower():
            return get_rss_news(url, source_name)
        elif source_name.endswith("API") or "api" in source_name.lower():
            return get_api_news(url, source_name)
        else:
            return get_generic_news(url, source_name)
    except Exception as e:
        print(f"[ERROR] 从 {source_name} 获取新闻时出错 {url}: {e}")
        import traceback
        print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
        return []

def get_jiqizhixin_news(url, source_name):
    """获取机器之心新闻"""
    try:
        print(f"[DEBUG] {source_name}: 开始使用Selenium获取新闻...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        print(f"[DEBUG] {source_name}: 正在初始化Chrome WebDriver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print(f"[DEBUG] {source_name}: WebDriver初始化成功，正在访问页面...")
        driver.get(url)
        
        wait = WebDriverWait(driver, 10)
        print(f"[DEBUG] {source_name}: 等待页面元素加载...")
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "home__left-body")))
        print(f"[DEBUG] {source_name}: 页面元素加载成功，获取页面源码...")
        
        page_source = driver.page_source
        print(f"[DEBUG] {source_name}: 页面源码长度: {len(page_source)} 字符")
        driver.quit()
        print(f"[DEBUG] {source_name}: WebDriver已关闭")
        
        soup = BeautifulSoup(page_source, "html.parser")
        articles = []
        
        news_items = soup.find_all("a", class_="body-title")
        print(f"[DEBUG] {source_name}: 找到 {len(news_items)} 个body-title类链接")
        
        if len(news_items) < 5:
            more_items = soup.find_all("a", class_=["article-item", "news-item", "post-title", "title"])
            print(f"[DEBUG] {source_name}: 额外找到 {len(more_items)} 个通用文章链接")
            news_items.extend(more_items)
        
        if len(news_items) < 5:
            potential_titles = soup.find_all(["h1", "h2", "h3", "h4"], class_=re.compile(r"title|heading|headline"))
            more_items = soup.find_all("a", href=re.compile(r"articles|news|post|reference"))
            print(f"[DEBUG] {source_name}: 再找到 {len(more_items)} 个潜在新闻链接")
            news_items.extend(more_items)
        
        if len(news_items) < 5:
            all_links = soup.find_all("a", href=True)
            ai_links = []
            for link in all_links:
                text = link.get_text(strip=True)
                if len(text) > 10 and ("ai" in text.lower() or "机器" in text or "智能" in text or "AI" in text):
                    ai_links.append(link)
            print(f"[DEBUG] {source_name}: 找到 {len(ai_links)} 个AI相关链接")
            news_items.extend(ai_links)
        
        print(f"[DEBUG] {source_name}: 总共找到 {len(news_items)} 个候选链接")
        
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
        
        print(f"[DEBUG] {source_name}: 成功提取 {len(articles)} 篇文章")
        return articles
    except Exception as e:
        print(f"[ERROR] 获取机器之心新闻时出错: {e}")
        import traceback
        print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
        return []

def get_36kr_news(url, source_name):
    """获取36氪AI新闻"""
    try:
        print(f"[DEBUG] {source_name}: 开始使用requests获取新闻...")
        # 先尝试使用requests获取
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        print(f"[DEBUG] {source_name}: 发送HTTP请求...")
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        print(f"[DEBUG] {source_name}: HTTP响应状态码: {response.status_code}")
        print(f"[DEBUG] {source_name}: 响应内容长度: {len(response.text)} 字符")
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        articles = []
        
        # 尝试多种可能的类名和选择器
        news_items = []
        
        # 方法1：寻找文章链接
        news_items.extend(soup.find_all("a", class_=["item-title", "article-title", "title", "post-title"]))
        print(f"[DEBUG] {source_name}: 方法1找到 {len(news_items)} 个标题链接")
        
        # 方法2：寻找包含AI关键词的链接
        if len(news_items) < 5:
            all_links = soup.find_all("a", href=True)
            for link in all_links:
                text = link.get_text(strip=True)
                if len(text) > 10 and any(keyword in text.lower() for keyword in AI_KEYWORDS):
                    news_items.append(link)
            print(f"[DEBUG] {source_name}: 方法2找到 {len([x for x in news_items if soup.find_all('a', href=True)])} 个AI相关链接")
        
        # 方法3：寻找特定的文章容器
        if len(news_items) < 5:
            news_items.extend(soup.find_all("div", class_=re.compile(r"item|article|post")))
            print(f"[DEBUG] {source_name}: 方法3找到 {len([x for x in soup.find_all('div', class_=re.compile(r'item|article|post'))])} 个文章容器")
        
        print(f"[DEBUG] {source_name}: 总共找到 {len(news_items)} 个候选项目")
        
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
        
        print(f"[DEBUG] {source_name}: 成功提取 {len(articles)} 篇AI相关文章")
        return articles
    except Exception as e:
        print(f"[ERROR] 获取36氪新闻时出错: {e}")
        import traceback
        print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
        return []

def get_infoq_news(url, source_name):
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
        print(f"获取InfoQ新闻时出错: {e}")
        return []

def get_aminer_news(url, source_name):
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
        print(f"获取AMiner新闻时出错: {e}")
        return []

def get_leiphone_news(url, source_name):
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
        print(f"获取雷锋网新闻时出错: {e}")
        return []

def get_venturebeat_news(url, source_name):
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
        print(f"获取VentureBeat新闻时出错: {e}")
        return []

def get_techcrunch_news(url, source_name):
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
        print(f"获取TechCrunch新闻时出错: {e}")
        return []

def get_generic_news(url, source_name):
    """通用新闻获取方法"""
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)
        
        wait = WebDriverWait(driver, 10)
        
        page_source = driver.page_source
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
        print(f"获取通用新闻时出错: {e}")
        return []

def get_rss_news(url, source_name):
    """获取RSS/ATOM新闻"""
    try:
        print(f"[DEBUG] {source_name}: 开始解析RSS源...")
        feed = feedparser.parse(url)
        print(f"[DEBUG] {source_name}: RSS源包含 {len(feed.entries)} 个条目")
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
        
        print(f"[DEBUG] {source_name}: 成功提取 {len(articles)} 篇AI相关文章")
        return articles
    except Exception as e:
        print(f"[ERROR] 获取RSS新闻时出错: {e}")
        import traceback
        print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
        return []

def get_api_news(url, source_name):
    """获取API新闻"""
    try:
        print(f"[DEBUG] {source_name}: 开始请求API...")
        # 设置请求头
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        print(f"[DEBUG] {source_name}: API响应状态码: {response.status_code}")
        response.raise_for_status()
        
        data = response.json()
        print(f"[DEBUG] {source_name}: API响应数据类型: {type(data)}")
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
        
        print(f"[DEBUG] {source_name}: 成功提取 {len(articles)} 篇AI相关文章")
        return articles
    except Exception as e:
        print(f"[ERROR] 获取API新闻时出错: {e}")
        import traceback
        print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
        return []

def get_ai_news():
    """从多个数据源获取AI新闻，按照优先级排序"""
    print("[INFO] 开始获取AI新闻...")
    all_articles = []
    
    # 从配置文件获取启用的数据源，并按优先级排序
    enabled_sources = [source for source in NEWS_SOURCES if source.get("enabled", True)]
    enabled_sources.sort(key=lambda x: x.get("priority", 3), reverse=True)
    print(f"[INFO] 启用的新闻源数量: {len(enabled_sources)}")
    
    # 从每个数据源获取新闻
    for source in enabled_sources:
        print(f"[INFO] 正在从 {source['name']} (优先级: {source.get('priority', 3)}) 获取新闻...")
        articles = get_ai_news_from_source(source["url"], source["name"])
        
        # 为每篇文章添加优先级信息
        priority = source.get("priority", 3)
        for article in articles:
            article["priority"] = priority
        
        # 限制每个源的文章数量
        articles = articles[:MAX_ARTICLES_PER_SOURCE]
        all_articles.extend(articles)
        print(f"[INFO] 从 {source['name']} 获取了 {len(articles)} 篇文章")
    
    print(f"[INFO] 总共获取了 {len(all_articles)} 篇文章（包含重复）")
    
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
    
    print(f"[INFO] 去重后剩余 {len(unique_articles)} 篇文章")
    
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
    
    print(f"[INFO] 最终筛选后保留 {len(priority_articles)} 篇文章")
    print(f"[DEBUG] 各优先级文章数量: {priority_counts}")
    
    return priority_articles

def summarize_news(news_list):
    """使用AI对新闻列表进行摘要"""
    try:
        print(f"[INFO] 开始生成新闻摘要，共 {len(news_list)} 篇文章...")
        
        # 构建包含来源信息的新闻文本
        news_items = []
        for news in news_list:
            if "source" in news:
                news_items.append(f'标题: {news["title"]} (来源: {news["source"]}, 日期: {news["date"]})')
            else:
                news_items.append(f'标题: {news["title"]} (日期: {news["date"]})')
        news_text = "\n".join(news_items)
        
        print(f"[DEBUG] 发送给AI的新闻文本长度: {len(news_text)} 字符")
        print(f"[DEBUG] AI API地址: {client.base_url}")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": f"请总结以下AI新闻，提取关键信息和趋势:\n{news_text}"}
            ],
            max_tokens=1000
        )
        print(f"[DEBUG] AI API响应状态: 成功")
        print(f"[DEBUG] AI API响应内容长度: {len(response.choices[0].message.content)} 字符")
        
        summary = response.choices[0].message.content.strip()
        print(f"[INFO] 新闻摘要生成成功")
        return summary
    except Exception as e:
        print(f"[ERROR] 生成摘要时出错: {e}")
        import traceback
        print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
        return "无法生成摘要。"

def send_to_feishu(webhook_url, summary, news_list, image_key=None, webhook_name="未命名"):
    """发送消息到飞书群聊，支持卡片消息格式"""
    try:
        print(f"[INFO] 开始发送消息到飞书 [{webhook_name}]...")
        print(f"[DEBUG] 飞书Webhook URL: {webhook_url[:50]}...")
        print(f"[DEBUG] 摘要长度: {len(summary)} 字符")
        print(f"[DEBUG] 新闻数量: {len(news_list)}")
        
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
            
        print(f"[DEBUG] 构建的飞书消息数据大小: {len(json.dumps(data, ensure_ascii=False).encode('utf-8'))} 字节")
        
        response = requests.post(webhook_url, headers=headers, data=json.dumps(data, ensure_ascii=False).encode('utf-8'))
        print(f"[DEBUG] 飞书API响应状态码: {response.status_code}")
        print(f"[DEBUG] 飞书API响应内容: {response.text}")
        
        response.raise_for_status()
        print(f"[INFO] 消息已成功发送到飞书 [{webhook_name}]")
        return True
    except Exception as e:
        print(f"[ERROR] 发送到飞书 [{webhook_name}] 时出错: {e}")
        import traceback
        print(f"[ERROR] 详细错误信息: {traceback.format_exc()}")
        return False

def print_webhook_configs():
    """打印当前Webhook配置信息"""
    print("[INFO] 当前Webhook配置:")
    for i, config in enumerate(WEBHOOK_CONFIGS, 1):
        status = "启用" if config.get("enabled", True) else "禁用"
        image_support = "支持" if config.get("send_image", False) else "不支持"
        print(f"  {i}. [{config['name']}] - 状态: {status}, 图片: {image_support}")
        print(f"     URL: {config['url'][:50]}...")

def send_to_multiple_webhooks(summary, news_list, image_key=None):
    """发送消息到多个飞书群聊"""
    print(f"[INFO] 开始发送消息到多个Webhook，共 {len(WEBHOOK_CONFIGS)} 个配置")
    
    success_count = 0
    failed_count = 0
    
    for config in WEBHOOK_CONFIGS:
        if not config.get("enabled", True):
            print(f"[INFO] 跳过已禁用的Webhook [{config['name']}]")
            continue
            
        webhook_name = config["name"]
        webhook_url = config["url"]
        send_image = config.get("send_image", False)
        
        print(f"[INFO] 正在发送到Webhook [{webhook_name}]...")
        
        try:
            # 根据配置决定是否发送图片
            current_image_key = image_key if send_image else None
            
            success = send_to_feishu(webhook_url, summary, news_list, current_image_key, webhook_name)
            
            if success:
                success_count += 1
                print(f"[SUCCESS] 成功发送到 [{webhook_name}]")
            else:
                failed_count += 1
                print(f"[ERROR] 发送到 [{webhook_name}] 失败")
                
        except Exception as e:
            failed_count += 1
            print(f"[ERROR] 发送到 [{webhook_name}] 时出现异常: {e}")
    
    print(f"[INFO] 多Webhook发送完成: 成功 {success_count} 个，失败 {failed_count} 个")
    return success_count, failed_count

def upload_image_to_feishu(image_path, access_token):
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
            print(f"图片上传成功，image_key: {image_key}")
            return image_key
        else:
            print("图片上传失败: {}".format(result.get("msg")))
            return None
    except Exception as e:
        print(f"上传图片到飞书时出错: {e}")
        return None

def main():
    """主函数 - 立即执行AI日报任务"""
    # 初始化日志系统
    global logger
    logger = setup_logging()
    
    if logger:
        logger.info("=" * 60)
        logger.info(f"AI日报机器人启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
    else:
        print("=" * 60)
        print(f"AI日报机器人启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
    
    try:
        # 执行AI日报任务
        if logger:
            logger.info("开始执行AI日报任务...")
        else:
            print("开始执行AI日报任务...")
        
        success = execute_ai_robot_task()
        
        if success:
            if logger:
                logger.info("AI日报任务执行完成")
            else:
                print("AI日报任务执行完成")
        else:
            if logger:
                logger.error("AI日报任务执行失败")
            else:
                print("AI日报任务执行失败")
    
    except Exception as e:
        if logger:
            logger.error(f"程序运行出错: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
        else:
            print(f"程序运行出错: {e}")
            import traceback
            print(f"详细错误信息: {traceback.format_exc()}")
    
    if logger:
        logger.info("=" * 60)
        logger.info(f"AI日报机器人结束 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
    else:
        print("=" * 60)
        print(f"AI日报机器人结束 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

if __name__ == "__main__":
    main()