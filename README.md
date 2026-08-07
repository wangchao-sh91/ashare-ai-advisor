# A股 AI 投研助手

本仓库是本地单用户 A 股投研问答 MVP 的 monorepo，包含 Python 3.12/FastAPI 后端和 React/TypeScript/Vite 前端，不使用数据库。

## 本地开发

需要 Python 3.12、Node.js 22+、npm 10+ 和 GNU Make。

```bash
make install
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
make pre-commit
make dev
```

前端默认运行于 `http://127.0.0.1:5173`，API 默认运行于 `http://127.0.0.1:8000`。`make dev-api` 和 `make dev-web` 可分别启动服务。

## 质量命令

- `make check`：执行后端 lint/格式/mypy、前端 lint/格式/TypeScript，以及密钥扫描
- `make test`：执行前后端测试
- `make format`：格式化前后端代码
- `make secrets`：扫描所有已跟踪文件中的疑似密钥

真实 provider 凭据只能写入被 Git 忽略的本地环境文件，不要放入浏览器环境变量或提交到仓库。
