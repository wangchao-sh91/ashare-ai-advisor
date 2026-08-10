# A股 AI 投研助手

本仓库是本地单用户 A 股投研问答 MVP：Python 3.12/FastAPI 后端、
React/TypeScript/Vite 前端，以及用于本地部署的 Docker Compose。系统不使用数据库，
对话只保存在当前浏览器页面内存中。

## 本地开发

需要 Python 3.12、Node.js 22+、npm 10+ 和 GNU Make。

```bash
make install
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
make pre-commit
make dev
```

前端默认运行于 `http://127.0.0.1:5173`，API 默认运行于
`http://127.0.0.1:8000`。开发服务器会把浏览器发往 `/api` 的请求代理到 API；
`make dev-api` 和 `make dev-web` 可分别启动服务。

真实运行必须在 `apps/api/.env` 中配置 DeepSeek 和豆包搜索凭据。后端启动时会
初始化官方豆包 MCP 子进程并加载 AKShare 股票目录；`/ready` 返回 200 后才表示问答
链路已就绪。

## Docker Compose

```bash
cp apps/api/.env.example apps/api/.env
# 编辑 apps/api/.env
docker compose up --build -d --wait
```

浏览器入口默认为 `http://127.0.0.1:8080`。只有 Web 端口发布到宿主机，API 仅在
Compose 网络中可访问。完整部署步骤见 [本地部署指南](docs/deployment.md)。

## 质量与验证

- `make check`：后端 lint/格式/Mypy、前端 lint/格式/TypeScript 和密钥扫描
- `make test`：全部后端及前端测试
- `make compose-integration`：无真实凭据的干净镜像、MCP 生命周期、代理流式和验收场景
- `make smoke-live`：明确选择后运行 AKShare、DeepSeek、豆包搜索真实冒烟检查
- `make format`：格式化前后端代码
- `make secrets`：扫描疑似密钥

支持范围、来源含义与风险边界见 [使用指南](docs/user-guide.md)。真实 Provider 凭据
只能写入被 Git 忽略的本地环境文件，不能放入浏览器环境变量或提交到仓库。
