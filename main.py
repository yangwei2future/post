import requests
from bs4 import BeautifulSoup
import os
from openai import OpenAI
import json
from datetime import datetime
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# 配置OpenAI API
# 请将下面的"your_actual_api_key_here"替换为您从deepseek获取的实际API密钥
API_KEY = "sk-e9c92f4884e742c1a533d17c1ab729d0"
client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com/")

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

def get_ai_news(url):
    """从指定URL获取AI新闻"""
    try:
        # 设置Chrome选项
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # 无头模式
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        # 初始化WebDriver
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)
        
        # 等待页面加载完成
        wait = WebDriverWait(driver, 10)
        
        # 等待新闻内容加载完成
        # 根据网站的实际结构，等待特定元素出现
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "home__left-body")))
        
        # 获取页面源码
        page_source = driver.page_source
        driver.quit()
        
        # 使用BeautifulSoup解析页面
        soup = BeautifulSoup(page_source, "html.parser")
        articles = []
        
        # 查找新闻条目 - 尝试多种选择器以获取更多新闻
        # 1. 首先尝试body-title类
        news_items = soup.find_all("a", class_="body-title")
        
        # 2. 如果没找到足够的新闻，尝试其他可能的类名
        if len(news_items) < 5:
            more_items = soup.find_all("a", class_=["article-item", "news-item", "post-title", "title"])
            news_items.extend(more_items)
        
        # 3. 如果还是没找到足够的新闻，尝试更通用的方法
        if len(news_items) < 5:
            # 查找所有可能包含新闻标题的元素
            potential_titles = soup.find_all(["h1", "h2", "h3", "h4"], class_=re.compile(r"title|heading|headline"))
            # 或者查找所有链接
            more_items = soup.find_all("a", href=re.compile(r"articles|news|post|reference"))
            news_items.extend(more_items)
        
        # 4. 如果还是没找到足够的新闻，查找包含AI相关关键词的链接
        if len(news_items) < 5:
            # 查找所有链接并筛选包含AI相关关键词的链接
            all_links = soup.find_all("a", href=True)
            ai_links = []
            for link in all_links:
                text = link.get_text(strip=True)
                if len(text) > 10 and ("ai" in text.lower() or "机器" in text or "智能" in text or "AI" in text):
                    ai_links.append(link)
            news_items.extend(ai_links)
        
        if news_items:
            for item in news_items:
                title = item.get_text(strip=True)
                # 确保标题有足够的长度
                if len(title) < 5:
                    continue
                    
                link = item.get("href", "")
                # 确保链接是完整的URL
                if link:
                    if not link.startswith("http"):
                        if link.startswith("/"):
                            link = "https://www.jiqizhixin.com" + link
                        else:
                            link = "https://www.jiqizhixin.com/" + link
                else:
                    # 如果href为空，尝试从onclick或其他属性获取链接
                    onclick = item.get("onclick", "")
                    if onclick:
                        # 尝试从onclick中提取链接
                        # 匹配更广泛的URL模式
                        match = re.search(r"'(https?://[^']+)'", onclick)
                        if match:
                            link = match.group(1)
                        else:
                            # 尝试匹配相对路径
                            match = re.search(r"'(/articles/[^']+)'", onclick)
                            if match:
                                link = "https://www.jiqizhixin.com" + match.group(1)
                    # 如果还是没有链接，使用item的父元素中的data-href属性或其他可能的属性
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
                
                # 跳过没有链接的条目
                if not link:
                    continue
                
                # 尝试获取日期信息
                date = datetime.now().strftime("%m月%d日")  # 默认日期
                
                # 查找父元素中的日期信息
                parent = item.find_parent()
                if parent:
                    # 查找日期元素
                    date_elements = parent.find_all(string=re.compile(r"\d{1,2}月\d{1,2}日"))
                    if date_elements:
                        date_match = re.search(r"\d{1,2}月\d{1,2}日", str(date_elements[0]))
                        if date_match:
                            date = date_match.group(0)
                
                articles.append({"title": title, "link": link, "date": date})
        else:
            # 如果找不到特定的新闻元素，尝试通用方法
            # 查找所有链接作为可能的新闻
            links = soup.find_all("a", href=True)
            for link in links:
                title = link.get_text(strip=True)
                href = link.get("href", "")
                # 筛选可能是新闻的链接
                if title and len(title) > 10 and (href.startswith("/articles/") or "jiqizhixin.com" in href):
                    if not href.startswith("http"):
                        href = "https://www.jiqizhixin.com" + href
                    
                    # 尝试获取日期信息
                    date = datetime.now().strftime("%m月%d日")  # 默认日期
                    
                    articles.append({"title": title, "link": href, "date": date})
        
        # 去重 - 优先基于标题去重，避免重复内容
        seen_titles = set()
        unique_articles = []
        for article in articles:
            # 清理标题，去除多余空格和特殊字符
            clean_title = article["title"].strip()
            # 使用标题作为去重的主要依据
            if clean_title not in seen_titles and len(clean_title) > 10:
                seen_titles.add(clean_title)
                unique_articles.append(article)
        
        # 限制返回的新闻数量
        return unique_articles[:15]  # 返回前15条新闻
        
    except Exception as e:
        print(f"获取新闻时出错 {url}: {e}")
        return []

def summarize_news(news_list):
    """使用AI对新闻列表进行摘要"""
    try:
        news_text = "\n".join([f'标题: {news["title"]} (日期: {news["date"]})' for news in news_list])
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": f"请总结以下AI新闻，提取关键信息和趋势:\n{news_text}"}
            ],
            max_tokens=1000
        )
        print(f"API响应: {response}") # Debugging line
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"生成摘要时出错: {e}")
        return "无法生成摘要。"

def send_to_feishu(webhook_url, summary, news_list, image_key=None):
    """发送消息到飞书群聊，支持富文本和图片"""
    try:
        headers = {
            "Content-Type": "application/json"
        }
        
        # 构建富文本消息内容
        post_content = []
        
        # 添加标题行
        post_content.append([
            {
                "tag": "text",
                "text": "📊 今日AI热点摘要:\n"
            }
        ])
        
        # 处理摘要内容，移除Markdown格式并转换为飞书富文本格式
        # 移除标题标记和特殊符号
        clean_summary = summary.replace('**', '')  # 移除所有粗体标记
        clean_summary = clean_summary.replace('### ', '')  # 移除标题标记
        clean_summary = clean_summary.replace('#### ', '')  # 移除子标题标记
        
        # 按段落分割
        summary_paragraphs = clean_summary.split('\n\n')
        for paragraph in summary_paragraphs:
            if paragraph.strip():
                # 处理段落中的换行
                lines = paragraph.split('\n')
                formatted_lines = []
                for line in lines:
                    if line.strip():
                        formatted_lines.append(line.strip())
                
                formatted_paragraph = '\n'.join(formatted_lines)
                
                # 为段落添加统一的格式处理
                # 如果段落以数字开头，认为是小节标题
                if formatted_paragraph.strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                    # 提取标题内容并添加格式化标记
                    title_content = formatted_paragraph.strip()
                    formatted_paragraph = f"\n【{title_content}】"
                # 如果段落较短且包含冒号，可能是小节标题
                elif len(formatted_paragraph.strip()) < 50 and ':' in formatted_paragraph:
                    title_content = formatted_paragraph.strip()
                    formatted_paragraph = f"\n【{title_content}】"
                # 如果段落以"关键信息"、"核心趋势"等关键词开头，添加标记
                elif any(keyword in formatted_paragraph for keyword in ['关键信息', '核心趋势', '总结']):
                    title_content = formatted_paragraph.strip()
                    formatted_paragraph = f"【{title_content}】"
                
                # 处理列表项格式，添加适当的缩进
                final_lines = []
                paragraph_lines = formatted_paragraph.split('\n')
                for line in paragraph_lines:
                    if line.strip().startswith(('-', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                        # 为列表项添加缩进
                        final_lines.append('  ' + line.strip())
                    else:
                        final_lines.append(line)
                
                formatted_paragraph = '\n'.join(final_lines)
                
                post_content.append([
                    {
                        "tag": "text",
                        "text": formatted_paragraph + "\n\n"
                    }
                ])
        
        # 添加新闻列表标题
        post_content.append([
            {
                "tag": "text",
                "text": "📰 详细新闻列表:\n"
            }
        ])
        
        # 添加新闻条目，每个条目作为独立的富文本元素
        for i, news in enumerate(news_list, 1):
            # 添加新闻序号和标题（作为超链接）
            post_content.append([
                {
                    "tag": "text",
                    "text": f"{i}. "
                },
                {
                    "tag": "a",
                    "text": news["title"],
                    "href": news["link"]
                },
                {
                    "tag": "text",
                    "text": f" (日期: {news['date']})\n"
                }
            ])
        
        if image_key:
            # 构建富文本消息，包含图片
            data = {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": "🤖 AI日报 - {}".format(datetime.now().strftime("%Y年%m月%d日")),
                            "content": [
                                [
                                    {
                                        "tag": "img",
                                        "image_key": image_key,
                                        "width": 600,
                                        "height": 300
                                    }
                                ]
                            ] + post_content
                        }
                    }
                }
            }
        else:
            # 仅发送文本消息，使用post格式以支持更好的显示效果
            data = {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": "🤖 AI日报 - {}".format(datetime.now().strftime("%Y年%m月%d日")),
                            "content": post_content
                        }
                    }
                }
            }
            
        response = requests.post(webhook_url, headers=headers, data=json.dumps(data, ensure_ascii=False).encode('utf-8'))
        response.raise_for_status()
        print("消息已成功发送到飞书")
        return True
    except Exception as e:
        print(f"发送到飞书时出错: {e}")
        return False

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
    """主函数"""
    print("开始执行AI日报任务 - {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    # 飞书应用凭证
    feishu_app_id = "cli_a8ef4e27bd85900b"
    feishu_app_secret = "By4Y7Z2NpQvovyJ0Efp2CgyOF8dAC7bV"
    
    # 获取tenant_access_token
    access_token = get_tenant_access_token(feishu_app_id, feishu_app_secret)
    if not access_token:
        print("无法获取access_token，退出任务。")
        return

    # 新闻源URL
    news_source_url = "https://www.jiqizhixin.com/"
    
    # 获取AI新闻
    print("正在获取AI新闻...")
    ai_news = get_ai_news(news_source_url)
    
    if ai_news:
        print(f"成功获取 {len(ai_news)} 条新闻")
        
        # 生成摘要
        print("正在生成新闻摘要...")
        summary = summarize_news(ai_news)
        
        print("生成的日报摘要:")
        print(summary)
        
        # 飞书webhook URL
        feishu_webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/9f92c19d-9dc1-46f2-b5fa-117860a4eea5"
        
        # 上传主题图片并发送
        # 检查图片文件是否存在，如果不存在则跳过图片上传
        image_path = "/home/ubuntu/upload/search_images/QkPqdKuxZOlT.jpg" # 选择一张AI相关的图片
        image_key = None
        if os.path.exists(image_path):
            image_key = upload_image_to_feishu(image_path, access_token)
        else:
            print(f"图片文件不存在: {image_path}，将跳过图片上传")
        
        if image_key:
            send_to_feishu(feishu_webhook, summary, ai_news, image_key)
        else:
            send_to_feishu(feishu_webhook, summary, ai_news) # 如果图片上传失败，则只发送文本
        
    else:
        print("未能获取AI新闻")

if __name__ == "__main__":
    main()

