# AgentBuddy Server 部署指南

## 一键运行

### Linux / macOS

```bash
# 1. 拉代码（国内服务器推荐从 Gitee 拉取）
git clone https://gitee.com/kyll/AgentBuddy.git
cd AgentBuddy/server

# 2. 赋予执行权限（首次）
chmod +x run.sh

# 3. 前台运行
./run.sh

# 4. 后台运行（推荐生产环境）
./run.sh -d

# 5. 其他命令
./run.sh status    # 查看状态
./run.sh stop      # 停止
./run.sh restart   # 重启
./run.sh update    # 更新代码并重启（自动从 Gitee 拉取）
./run.sh log       # 查看实时日志
```

### Windows

```bat
cd AgentBuddy\server
run.bat            :: 前台运行
run.bat -d         :: 后台运行
run.bat stop       :: 停止
run.bat status     :: 查看状态
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AGENTBUDDY_SERVER_HOST` | `0.0.0.0` | 监听地址 |
| `AGENTBUDDY_SERVER_PORT` | `5001` | 监听端口 |
| `AGENTBUDDY_DATA_DIR` | `./data` | 数据目录（marketplace 索引 + 插件包） |
| `AGENTBUDDY_LLM_CONFIG` | `./config/llm/llm.yaml` | LLM 配置文件路径 |

示例：
```bash
AGENTBUDDY_SERVER_PORT=8080 ./run.sh -d
```

## 脚本做了什么

1. 检查 Python 3.8+
2. 创建虚拟环境 `.venv`（首次）
3. 安装 `requirements.txt` 依赖（首次或依赖缺失时）
4. 启动 `app.py`

## 验证

```bash
curl http://localhost:5001/api/health
# {"ok":true,"service":"AgentBuddy Server"}
```

## 客户端配置

在 AgentBuddy 桌面应用 Header 右上角点击 Server 设置按钮，填入：
```
http://your-server-ip:5001
```

## 生产部署建议

### Nginx 反向代理

```nginx
server {
    listen 443 ssl;
    server_name agentbuddy.your-domain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

### systemd 服务

```ini
# /etc/systemd/system/agentbuddy-server.service
[Unit]
Description=AgentBuddy Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/AgentBuddy/server
ExecStart=/opt/AgentBuddy/server/.venv/bin/python app.py
Restart=always
RestartSec=5
Environment=AGENTBUDDY_SERVER_PORT=5001

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable agentbuddy-server
sudo systemctl start agentbuddy-server
```
