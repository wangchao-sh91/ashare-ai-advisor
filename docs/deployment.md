# 本地部署指南

## 前置条件与凭据

需要 Docker Engine 24+、Docker Compose v2、至少 4 GB 可用内存，以及可访问模型、
Tushare 和豆包搜索上游的网络。复制配置并只在被 Git 忽略的文件中填写密钥：

```bash
cp apps/api/.env.example apps/api/.env
```

```dotenv
PROVIDER_MODE=real
DEEPSEEK_API_KEY=your-model-key
DEEPSEEK_BASE_URL=https://your-provider.example/v1
DEEPSEEK_MODEL=your-wire-model-id
TUSHARE_TOKEN=your-tushare-token
DOUBAO_SEARCH_API_KEY=your-search-api-key
```

三个密钥用途独立，均只注入 API 容器。不要写入 Web 环境变量、Compose 文件、镜像层、
命令行参数或仓库。豆包端点固定为官方 HTTPS 地址；更改端点会导致配置校验失败。
`PROVIDER_MODE=fake` 仅用于离线测试和部署验收。

## 构建、启动与验证

```bash
docker compose config
docker compose build
docker compose up -d --wait
curl -fsS http://127.0.0.1:8080/
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"
```

Web 默认仅发布到 `127.0.0.1:8080`，API 端口不发布，由 Nginx `/api` 代理 SSE。
可用 `WEB_PORT=18080` 改 Web 端口，或用 `API_ENV_FILE` 指向另一份服务端配置。

`/health` 只验证进程存活。`/ready` 不消耗搜索配额，验证必要配置、编排器和当前
Provider 状态；`providers` 会显示 Tushare 配置状态及豆包搜索的 `configured`、
`usable`、`rate_limited`、`quota_unavailable` 或 `unavailable` 状态。配额耗尽和永久不可用
会令就绪失败，短期限流可由带缓存的部分回答继续降级处理。

无真实凭据的容器验收：

```bash
make compose-integration
```

它构建干净镜像，检查端口隔离、就绪响应、反向代理、SSE 事件、典型问答、重启和优雅
停止。真实 Provider 冒烟必须显式选择：

```bash
cd apps/api
LIVE_PROVIDER_SMOKE=1 .venv/bin/python scripts/tushare_daily_smoke.py
LIVE_PROVIDER_SMOKE=1 .venv/bin/python scripts/doubao_search_smoke.py
```

每个脚本只做一个有界请求，不打印密钥或原始响应。全套模型与 Provider 检查可用
`make smoke-live`；发布门禁可额外设置 `LIVE_SMOKE_STRICT=1`。

## 监控、故障排查与降级

持续监控 `/health`、`/ready`、请求错误率和延迟，并按 Provider/证据类别聚合以下状态：
Tushare 认证、超时、空结果或结构错误；豆包 `10406` 配额耗尽、`700429` 限流、超时和
不可引用结果；完整、部分及证据不足回答比例。日志只能保留错误码、类别、耗时和请求
关联 ID，不记录 token、Bearer 头、完整问题或原始搜索文档。

- Tushare 失败：价格类别直接证据不足，绝不以搜索价格替代；其他搜索类别可继续。
- 豆包失败：受影响的财务、估值、股权、质押、公告或指数类别不足；有效日线仍可回答。
- `/ready` 缺少 `TUSHARE_TOKEN` 或 `DOUBAO_SEARCH_API_KEY`：修正 API 环境文件并重启。
- 页面可用但流中断：检查 Nginx/API 日志和上游延迟；SSE 不支持从断点续传。
- 端口冲突：调整 `WEB_PORT`，不要绕过代理发布 API 端口。

缓存默认值为：价格 6 小时、公司事件 30 分钟、其他股票金融类别 24 小时、指数背景
1 小时，每个 Provider 最多 512 项。它们保护免费配额但可能增加可见陈旧度；回答必须
展示实际数据截止或发布时间。修改 TTL 后重启服务，内存缓存无需迁移。

## 发布与回滚

发布前保存上一版不可变镜像标签和与其配套的环境配置快照（密钥存于密钥管理系统，
不要复制进仓库）。先运行离线质量套件和 Compose 验收，再运行两个单请求真实冒烟，
最后观察就绪、延迟、Provider 错误和部分回答比例。

回滚必须把“上一版镜像 + 上一版配置”作为一组恢复：停止当前栈，将 Compose 镜像标签
切回已验证版本，恢复对应环境变量，然后 `docker compose up -d --wait` 并复查 `/ready`
和一条 SSE 请求。内存缓存随容器重建自动清空，无数据库迁移或缓存回填。若仅一个
Provider 故障，优先保留当前版本的类别级降级能力，而不是切换到未经验证的数据替代源。
