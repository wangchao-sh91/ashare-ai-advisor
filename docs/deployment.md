# 本地部署指南

## 前置条件

- Docker Engine 24 或更高版本
- Docker Compose v2（使用 `docker compose` 命令）
- 至少 4 GB 可用内存和可访问 AKShare、模型及搜索上游的网络
- 一个 DeepSeek 兼容 API 凭据和一个独立的豆包 SearchInfinity 凭据

使用以下命令确认环境：

```bash
docker --version
docker compose version
docker info
```

## 环境配置

复制后端模板：

```bash
cp apps/api/.env.example apps/api/.env
```

编辑 `apps/api/.env`，至少填写：

```dotenv
PROVIDER_MODE=real
DEEPSEEK_API_KEY=your-model-key
DEEPSEEK_BASE_URL=https://your-provider.example/v1
DEEPSEEK_MODEL=your-exact-wire-model-id

# 豆包认证方式一：API Key
DOUBAO_SEARCH_API_KEY=your-search-key
DOUBAO_SEARCH_ACCESS_KEY=
DOUBAO_SEARCH_SECRET_KEY=
```

或者清空 `DOUBAO_SEARCH_API_KEY`，同时填写豆包
`DOUBAO_SEARCH_ACCESS_KEY` 与 `DOUBAO_SEARCH_SECRET_KEY`。两种方式互斥，DeepSeek
凭据不能复用为豆包搜索凭据。

`.env` 已被 Git 和两个 Docker build context 排除。密钥只在 API 容器运行时注入，
不会进入 Web 构建参数或镜像层。`PROVIDER_MODE=fake` 仅用于自动化验收，不能作为
真实使用配置。

可选变量：

- `WEB_PORT=8080`：宿主机 Web 端口
- `API_ENV_FILE=./apps/api/.env`：Compose 加载的 API 环境文件
- `LOG_LEVEL=INFO`：API 日志级别
- 超时、重试、缓存和 CORS 设置见 `apps/api/.env.example`

## 构建与启动

```bash
docker compose config
docker compose build
docker compose up -d --wait
```

打开 `http://127.0.0.1:8080`。若要改端口：

```bash
WEB_PORT=18080 docker compose up -d --wait
```

Compose 只发布 `127.0.0.1:<WEB_PORT>`。API 的 8000 端口仅通过内部服务网络暴露，
浏览器请求由 Nginx 的 `/api` 反向代理转发。该代理禁用响应和请求缓冲，并为流式回答
设置 300 秒读写超时。

## 健康与就绪

Web 访问检查：

```bash
curl -fsS http://127.0.0.1:8080/
```

API 进程健康和完整就绪检查：

```bash
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"
```

`/health` 只表示 API 进程存活。`/ready` 还检查 Provider 配置、官方豆包 MCP
子进程握手、`web_search` 工具及受控编排器。就绪前页面可以加载，但问答可能返回可重试
错误。API 启动和停止期间由 FastAPI lifespan 管理唯一的 MCP stdio 子进程；Compose
使用 init 转发信号并提供 30 秒优雅停止窗口。

## 日志、重启与停止

```bash
docker compose ps
docker compose logs -f api web
docker compose restart api
docker compose down
```

本项目不定义持久卷。`docker compose down` 会停止当前服务，对话本来只存在于页面
内存，API 内存缓存也会随进程消失。

代码或依赖变化后重建：

```bash
docker compose build --no-cache
docker compose up -d --wait
```

## 自动化部署验收

```bash
make compose-integration
```

该命令创建临时、非真实凭据配置，执行无缓存镜像构建，启动官方 MCP 子进程并验证
就绪、Web 访问、`/api` 代理、SSE 事件、API 无宿主机端口、服务重启和子进程随容器
停止。脚本结束后自动清理容器和临时文件。

## 真实 Provider 冒烟检查

```bash
make smoke-live
```

命令必须显式执行才会访问外部 Provider。缺少凭据或网络不可用时相应检查安全跳过，
不会输出密钥或原始响应。CI 或发布验收需要把不可用视为失败时：

```bash
cd apps/api
LIVE_PROVIDER_SMOKE=1 LIVE_SMOKE_STRICT=1 .venv/bin/python scripts/live_smoke.py
```

## 故障排查

- `/ready` 报 `DEEPSEEK_*`：检查模型密钥、兼容 base URL 和精确 wire model ID。
- `/ready` 报 `DOUBAO_SEARCH_AUTH`：配置 API Key 或完整 AK/SK，不能同时配置。
- `/ready` 报 `DOUBAO_SEARCH_MCP`：查看 API 日志，确认官方 MCP 包已安装且凭据类型正确。
- `/ready` 报 `ORCHESTRATOR`：通常是 AKShare 股票目录不可达或 Provider 初始化失败；
  检查网络后重启 API。
- 页面能打开但流式请求失败：确认访问的是 Web 入口而非 API 端口，并检查 Nginx/API
  日志。
- 端口冲突：设置其他 `WEB_PORT`，不要发布 API 端口绕过代理。
- AKShare 数据不完整：这是公开上游限制；系统应展示部分数据或证据不足，而不是补造。
