# SM-API-Gateway

企业 API 网关：路由、鉴权、限流、熔断、灰度与请求审计。

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

- 动态路由
- 熔断器
- 灰度权重
- 请求审计
- `/health` 健康探针、`/readyz` 就绪探针
- `/api/overview` 业务概览、`/api/ops/metrics` 运维指标、`/metrics` Prometheus 指标
- `/api/integration/manifest` 服务契约、`/api/security/baseline` 安全基线
- 国密 SM3 / SM4-CBC（带 SM3 MAC 完整性校验，防密文篡改）
- 安全响应头、CSP、TrustedHost、限流、请求体限制、内部写入令牌
- 审计事件本地落库并异步转发集中审计中心
- Docker 只读文件系统、能力剥离、进程限制
- GitHub Actions CI 与安全扫描（pip-audit / bandit / ruff / SBOM / gitleaks）

## 安全说明

- SM4 密钥仅允许通过环境变量 `SM4_KEY_HEX`（或企业 KMS/HSM）注入，禁止写入代码或数据库。
- 生产环境（`SM_ENV=production`）未配置任何凭据时，受保护接口一律拒绝（fail-closed）。
- 写接口必须携带 `X-Internal-Token`（对应 `SM_INTERNAL_API_KEY`）。

## 质量门禁

```powershell
.\quality.ps1
```

## 企业维护资料

- [安全基线](SECURITY_BASELINE.md)
- [运维与可观测性](OPERATIONS.md)
- [应急响应手册](INCIDENT_RESPONSE.md)
- [生产部署检查清单](DEPLOYMENT_CHECKLIST.md)
- [变更记录](CHANGELOG.md)
- [版本号](VERSION)
