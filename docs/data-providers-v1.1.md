# v1.1 数据 Provider 运行说明

## 架构与固定路由

每次请求先由一次有界结构化模型调用生成自包含问题、唯一标的、证据类别、时间范围和
澄清状态。应用代码而非模型决定路由：`price_daily` 只调用 Tushare `pro.daily`；
`financial`、`valuation`、`ownership`、`pledge`、`corporate_event` 与 `index_context`
只调用豆包 Search Custom HTTPS API。各类别独立判定充分、部分或不可用。

Tushare SDK 固定为 `1.4.29`，已在 CPython 3.12 验证免费账户日线字段：`ts_code`、
`trade_date`、OHLC、`pre_close`、`change`、`pct_chg`、`vol`、`amount`。网关只暴露日线，
校验代码、日期、数值、顺序、重复和最小样本，并将 `vol × 100` 转为股、`amount × 1000`
转为人民币元。同步 SDK 运行在限容工作线程中，超时结果会被放弃。

豆包客户端只允许 Bearer 认证的
`POST https://open.feedcoopapi.com/search_api/web_search`，固定 Web 搜索并限制查询长度、
结果数（默认 5）、全局并发（默认 4）和重试。仅接收 `Result.WebResults` 中可引用、类别
相关的结果，不把原始正文交给模型。优先官方、监管、交易所和上市公司来源，并保留可信
冲突。错误 `10406` 表示额度不可用且不重试；`700429` 只做有界重试并暴露限流状态。

## 缓存、来源与安全

版本化缓存键包含 Provider、类别、标的/查询、日期范围和请求整形版本。默认 TTL：日线
6 小时、公司事件 30 分钟、其他股票金融搜索 24 小时、指数背景 1 小时；每个缓存最多
512 项并按 LRU 淘汰。应用重启即清空。

市场证据记录 Tushare 接口、规范股票代码、覆盖区间、截止日、获取时间和单位。Web
证据记录标题、目标 URL、发布者/域名、发布时间、获取时间及权威性。密钥使用
`SecretStr`，错误、健康检查、测试夹具和冒烟输出不得包含 token、Authorization 或原始
上游载荷。

## 兼容性和维护

HTTP chat 请求和 SSE 的 `accepted`、`status`、`answer-delta`、`answer-complete`、`error`
事件保持兼容；类别限制和引用通过既有回答结构传递。升级 Tushare、HTTP 客户端或上游
响应适配器时，必须重新运行 Provider 夹具契约、单位测试、静态检查、Compose 验收和
两个单请求真实冒烟，并刷新 `apps/api/requirements.lock` 与本记录。
