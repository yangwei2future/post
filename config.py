# 新闻源配置文件
# 可以在这里添加、修改或删除新闻源

NEWS_SOURCES = [
    # 中文新闻源 (优先级: 1-5, 5最高)
    {"url": "https://36kr.com", "name": "36氪", "enabled": True, "priority": 5},
    {"url": "https://www.jiqizhixin.com/", "name": "机器之心", "enabled": True, "priority": 5},
    {"url": "https://www.aminer.cn/topic/ai", "name": "AMiner", "enabled": True, "priority": 4},
    {"url": "https://www.infoq.cn/topic/AI&LLM", "name": "InfoQ", "enabled": True, "priority": 3},  # 暂时禁用，URL可能需要更新
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

# 配置参数
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

# 请求配置
REQUEST_TIMEOUT = 30  # 请求超时时间（秒）
RETRY_COUNT = 3      # 重试次数
RETRY_DELAY = 2      # 重试间隔（秒）