# SM API Gateway

企业 API 网关：鉴权、限流、熔断、灰度与请求审计。

## 本地运行

```powershell
git clone https://github.com/luoshitianchen/SM-API-Gateway.git
cd SM-API-Gateway
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8310
```

访问：`http://127.0.0.1:8310/`

## 企业能力

- `/health` 健康探针
- `/readyz` 就绪探针
- `/api/overview` 业务概览
- `/api/items` 资源管理样例
- `/api/ops/metrics` 运维指标
- 安全响应头、CSP、TrustedHost
- Docker 只读文件系统、能力剥离、进程限制
- GitHub Actions CI 与安全扫描

## 质量门禁

```powershell
.\quality.ps1
```


## v1.1 链路联动升级
- 新增 `/api/integration/manifest`，向融合门户和治理系统声明服务依赖、事件类型、健康探针、指标接口和概览接口。
- 版本升级到 `1.1.0`，用于后续统一身份、审计、监控、CMDB 和 AgentOps 的真实链路调用。


## v2.0 大版本安全升级
- 新增全局请求体大小限制 `SM_MAX_REQUEST_BYTES`。
- 新增全局接口速率限制 `SM_RATE_WINDOW_SECONDS` / `SM_RATE_MAX_REQUESTS`。
- 新增可选内部写入令牌 `SM_INTERNAL_API_KEY`，配置后 `POST/PATCH` 写操作必须携带 `X-Internal-Token`。
- 服务契约 `/api/integration/manifest` 版本同步升级到 `2.0.0`。
