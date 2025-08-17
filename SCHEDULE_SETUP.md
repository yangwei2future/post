# AI日报机器人定时任务设置指南

## 功能说明
AI日报机器人已经配置好多webhook支持，现在需要设置定时任务，让它每天上午9点自动执行。

## 设置方法

### 方法一：使用系统cron（推荐）

1. **打开终端，编辑cron配置文件：**
   ```bash
   crontab -e
   ```
   
* * * * * /Users/yangwei/anaconda3/bin/python /Users/yangwei/Desktop/post/ai_daily_robot/main.py >> /Users/yangwei/Desktop/post/ai_daily_robot/logs/post.log 2>&1


2. **添加以下行到文件末尾：**
   ```bash
   0 9 * * * /usr/bin/python3 /path/to/your/ai_daily_robot.py >> /path/to/your/cron.log 2>&1
   ```

3. **替换路径：**
   - `/path/to/your/ai_daily_robot.py` 替换为您的实际脚本路径
   - `/path/to/your/cron.log` 替换为您希望保存日志的路径

4. **保存并退出：**
   - 如果是vi编辑器，按 `ESC`，输入 `:wq`，回车
   - 如果是nano编辑器，按 `Ctrl+X`，然后按 `Y`，回车

### 方法二：使用systemd timer（Linux系统）

1. **创建服务文件：**
   ```bash
   sudo nano /etc/systemd/system/ai-daily-robot.service
   ```

2. **添加以下内容：**
   ```ini
   [Unit]
   Description=AI Daily Robot
   After=network.target

   [Service]
   Type=oneshot
   ExecStart=/usr/bin/python3 /path/to/your/ai_daily_robot.py
   User=your_username
   WorkingDirectory=/path/to/your/project
   ```

3. **创建定时器文件：**
   ```bash
   sudo nano /etc/systemd/system/ai-daily-robot.timer
   ```

4. **添加以下内容：**
   ```ini
   [Unit]
   Description=Run AI Daily Robot daily at 9 AM
   Requires=ai-daily-robot.service

   [Timer]
   OnCalendar=*-*-* 09:00:00
   Persistent=true

   [Install]
   WantedBy=timers.target
   ```

5. **启用并启动定时器：**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable ai-daily-robot.timer
   sudo systemctl start ai-daily-robot.timer
   ```

## 验证定时任务

### 检查cron任务：
```bash
crontab -l
```

### 检查systemd定时器：
```bash
systemctl list-timers --all
```

### 查看日志：
```bash
tail -f /path/to/your/cron.log
```

## 常见问题解决

### 1. Python路径问题
确保cron中的Python路径正确，可以使用以下命令查找：
```bash
which python3
```

### 2. 权限问题
确保脚本有执行权限：
```bash
chmod +x /path/to/your/ai_daily_robot.py
```

### 3. 环境变量问题
cron任务可能缺少环境变量，可以在脚本开头添加：
```python
import os
os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin'
```

### 4. 依赖包问题
确保所有依赖包都已安装：
```bash
pip install -r requirements.txt
```

## 其他时间设置示例

### 每天上午9点：
```bash
0 9 * * *
```

### 每周一至周五上午9点：
```bash
0 9 * * 1-5
```

### 每天上午9点和下午6点：
```bash
0 9,18 * * *
```

### 每6小时：
```bash
0 */6 * * *
```

## 注意事项

1. **时区设置**：确保服务器时区设置正确（脚本使用Asia/Shanghai时区）
2. **日志监控**：定期检查日志文件，确保任务正常运行
3. **错误处理**：脚本已包含完善的错误处理和日志记录
4. **资源清理**：脚本执行完成后会自动退出，不会占用系统资源

## 联系方式
如果遇到问题，请检查日志文件或联系技术支持。