# AI日报机器人

这是一个AI日报机器人，能够每天从机器之心网站（或其他指定数据源）拉取AI热点新闻，进行摘要总结，并通过飞书webhook发送到指定的群聊，支持富文本消息和主题图片。

## 最新优化

- 飞书消息格式优化，支持更美观的富文本显示
- 新闻标题作为超链接，可直接点击访问
- 摘要内容格式化处理，去除Markdown标记
- 统一的格式处理方式，适应每日变化的内容

## 功能特点

- **新闻爬取**: 从指定网站（目前配置为机器之心）抓取最新的AI新闻标题、链接和日期。
- **AI摘要**: 使用DeepSeek API对抓取到的新闻进行摘要，提取关键信息和趋势。
- **飞书集成**: 通过飞书Webhook发送日报内容到群聊，支持富文本格式。
- **图片支持**: 支持上传主题图片到飞书，并在日报中展示。
- **灵活配置**: 可配置新闻源URL、飞书App ID、App Secret和Webhook URL。

## 文件结构

```
ai_daily_robot/
├── main.py
└── requirements.txt
```

- `main.py`: 机器人主程序，包含新闻爬取、摘要、飞书发送等核心逻辑。
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

### 4. 运行机器人

```bash
python3 main.py
```

机器人将执行以下操作：
1. 获取飞书`tenant_access_token`。
2. 从机器之心网站抓取最新的AI新闻。
3. 使用DeepSeek API对新闻进行摘要。
4. 上传主题图片到飞书（如果配置了图片路径）。
5. 将包含摘要和新闻列表的富文本消息发送到飞书群聊。

## 代码概览

- `get_tenant_access_token(app_id, app_secret)`: 获取飞书应用的访问令牌。
- `get_ai_news(url)`: 爬取指定URL的新闻内容，目前针对机器之心网站进行解析。
- `summarize_news(news_list)`: 调用DeepSeek API对新闻列表进行摘要。
- `upload_image_to_feishu(image_path, access_token)`: 上传本地图片到飞书，并返回`image_key`。
- `send_to_feishu(webhook_url, content, image_key=None)`: 发送富文本消息到飞书群聊，可选择包含图片。
- `main()`: 主函数，协调整个日报生成和发送流程。

## 注意事项

- **爬虫稳定性**: 网页结构可能发生变化，导致`get_ai_news`函数失效，需要定期检查和更新。
- **API Key安全**: 请妥善保管您的API Key和App Secret，不要直接暴露在公共代码库中。
- **飞书权限**: 确保您的飞书应用具有发送消息和上传图片的权限。
- **图片路径**: 确保`image_path`指向的图片文件存在且可读。

## 部署

您可以将此脚本部署到服务器上，并结合`cron`等工具设置定时任务，实现每日自动发送AI日报。

