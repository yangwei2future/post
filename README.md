# AI日报机器人

这是一个AI日报机器人，能够每天从多个新闻源拉取AI热点新闻，进行摘要总结，并通过飞书webhook发送到指定的群聊，支持富文本消息和主题图片。

## 最新优化

### v1.1 - 新闻源大扩展
- **多源新闻支持**: 新增7个中文/英文新闻源
- **RSS/ATOM支持**: 支持RSS和ATOM格式新闻源
- **API数据源**: 支持通过API获取新闻（如NewsAPI）
- **配置化管理**: 新增config.py配置文件
- **智能过滤**: 基于AI关键词的智能过滤系统
- **模块化设计**: 每个新闻源独立的解析函数

### v1.0 - 基础功能
- 飞书消息格式优化，支持更美观的卡片消息显示
- 新闻标题作为超链接，可直接点击访问
- 摘要内容格式化处理，去除Markdown标记
- 统一的格式处理方式，适应每日变化的内容
- 使用飞书交互式卡片，支持更好的视觉效果和用户体验
- 支持图片显示和更宽的卡片布局
- 添加了卡片头部标题和蓝色主题样式

## 功能特点

### 新闻收集
- **多源新闻**: 支持7个中文/英文新闻源，包括机器之心、36氪、VentureBeat等
- **RSS/ATOM支持**: 支持RSS和ATOM格式的新闻源
- **API数据源**: 支持通过API获取新闻（如NewsAPI、GNews等）
- **智能过滤**: 基于AI关键词的智能过滤系统
- **去重处理**: 自动去除重复新闻内容

### 智能处理
- **AI摘要**: 使用DeepSeek API对新闻进行摘要，提取关键信息和趋势
- **内容分类**: 自动识别和分类AI相关新闻
- **日期提取**: 智能提取新闻发布日期
- **链接标准化**: 自动处理相对链接和绝对链接

### 飞书集成
- **卡片消息**: 支持交互式卡片消息格式
- **富文本**: 支持Markdown格式的富文本内容
- **图片支持**: 支持上传和显示主题图片
- **宽屏模式**: 支持宽屏卡片布局

### 配置管理
- **配置文件**: 通过config.py管理所有配置
- **源管理**: 可启用/禁用特定新闻源
- **参数调整**: 可调整文章数量、关键词等参数
- **错误处理**: 完善的异常处理和重试机制

## 文件结构

```
ai_daily_robot/
├── main.py          # 主程序
├── config.py        # 配置文件
└── requirements.txt # 依赖库
```

- `main.py`: 机器人主程序，包含新闻爬取、摘要、飞书发送等核心逻辑。
- `config.py`: 配置文件，管理新闻源和参数设置。
- `requirements.txt`: 项目所需的Python依赖库。

## 使用方法

### 1. 环境准备

确保您的系统安装了Python 3.x。

### 2. 安装依赖

进入项目目录，安装所需的Python库：

```bash
pip install -r requirements.txt
```

`requirements.txt`内容：
```
requests
beautifulsoup4
openai
selenium
webdriver-manager
feedparser
```

### 3. 配置API Key和飞书信息

- **DeepSeek API Key**: 将您的DeepSeek API Key设置为环境变量`OPENAI_API_KEY`。
  ```bash
  export OPENAI_API_KEY="YOUR_DEEPSEEK_API_KEY"
  ```
- **飞书App ID和App Secret**: 在`main.py`中，修改`feishu_app_id`和`feishu_app_secret`为您的飞书应用凭证。
  ```python
  feishu_app_id = "cli_a8ef4e27bd85900b"
  feishu_app_secret = "By4Y7Z2NpQvovyJ0Efp2CgyOF8dAC7bV"
  ```
- **飞书Webhook URL**: 在`main.py`中，修改`feishu_webhook`为您的飞书群聊Webhook URL。
  ```python
  feishu_webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/9f92c19d-9dc1-46f2-b5fa-117860a4eea5"
  ```
- **主题图片路径**: 在`main.py`中，修改`image_path`为您的主题图片本地路径。请确保该图片存在且可访问。
  ```python
  image_path = "/home/ubuntu/upload/search_images/QkPqdKuxZOlT.jpg" # 示例路径
  ```

### 4. 配置新闻源

编辑`config.py`文件来管理新闻源：

```python
# 启用/禁用新闻源
{"url": "https://www.jiqizhixin.com/", "name": "机器之心", "enabled": True}
{"url": "https://example.com", "name": "Example", "enabled": False}  # 禁用

# 添加新的新闻源
{"url": "https://new-source.com", "name": "新源", "enabled": True}

# 调整参数
MAX_ARTICLES_PER_SOURCE = 10  # 每个源最多获取的文章数量
MAX_TOTAL_ARTICLES = 30       # 总共最多返回的文章数量
```

### 5. 运行机器人

```bash
python3 main.py
```

机器人将执行以下操作：
1. 获取飞书`tenant_access_token`。
2. 从多个新闻源抓取最新的AI新闻。
3. 智能过滤和去重新闻内容。
4. 使用DeepSeek API对新闻进行摘要。
5. 上传主题图片到飞书（如果配置了图片路径）。
6. 将包含摘要和新闻列表的富文本消息发送到飞书群聊。

## 代码概览

### 核心函数
- `get_tenant_access_token(app_id, app_secret)`: 获取飞书应用的访问令牌。
- `get_ai_news()`: 从多个新闻源获取AI新闻。
- `summarize_news(news_list)`: 调用DeepSeek API对新闻列表进行摘要。
- `upload_image_to_feishu(image_path, access_token)`: 上传本地图片到飞书，并返回`image_key`。
- `send_to_feishu(webhook_url, summary, news_list, image_key=None)`: 发送富文本消息到飞书群聊。
- `main()`: 主函数，协调整个日报生成和发送流程。

### 新闻源函数
- `get_jiqizhixin_news(url, source_name)`: 获取机器之心新闻。
- `get_36kr_news(url, source_name)`: 获取36氪新闻。
- `get_infoq_news(url, source_name)`: 获取InfoQ新闻。
- `get_aminer_news(url, source_name)`: 获取AMiner新闻。
- `get_leiphone_news(url, source_name)`: 获取雷锋网新闻。
- `get_venturebeat_news(url, source_name)`: 获取VentureBeat新闻。
- `get_techcrunch_news(url, source_name)`: 获取TechCrunch新闻。
- `get_rss_news(url, source_name)`: 获取RSS/ATOM新闻。
- `get_api_news(url, source_name)`: 获取API新闻。
- `get_generic_news(url, source_name)`: 通用新闻获取方法。

## 注意事项

- **爬虫稳定性**: 网页结构可能发生变化，导致新闻获取函数失效，需要定期检查和更新。
- **API Key安全**: 请妥善保管您的API Key和App Secret，不要直接暴露在公共代码库中。
- **飞书权限**: 确保您的飞书应用具有发送消息和上传图片的权限。
- **图片路径**: 确保`image_path`指向的图片文件存在且可读。
- **网络访问**: 某些新闻源可能需要特殊网络环境才能访问。

## 扩展建议

### 添加新的新闻源
1. 在`config.py`中添加新闻源配置
2. 在`main.py`中添加对应的解析函数
3. 更新`get_ai_news_from_source`函数的路由逻辑

### 支持的新闻源类型
- **HTML网页**: 使用BeautifulSoup解析
- **RSS/ATOM**: 使用feedparser库
- **JSON API**: 直接解析JSON响应

### 推荐的新闻源
- **中文**: 虎嗅网、钛媒体、亿欧网、智东西
- **英文**: The Verge、Wired、Ars Technica、MIT Technology Review
- **RSS**: Google News、Reddit AI communities、ArXiv CS.AI
- **API**: NewsData.io、Mediastack、NewsCatcher

### 高级功能建议
- 内容缓存机制
- 增量更新
- 用户自定义关键词
- 多语言支持
- 内容质量评分
- 新闻分类和标签

## 部署

您可以将此脚本部署到服务器上，并结合`cron`等工具设置定时任务，实现每日自动发送AI日报。

### 定时任务示例
```bash
# 每天早上9点运行
0 9 * * * /usr/bin/python3 /path/to/ai_daily_robot/main.py
```

### Docker部署
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

