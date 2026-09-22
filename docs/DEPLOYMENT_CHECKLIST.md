# sm-api-gateway（API 网关）上线检查清单

## 1. 上线前检查

- [ ] 代码审查已合入 main，无未解决评论。
- [ ] 单元/集成测试通过，覆盖率 ≥ 80%。
- [ ] Trivy 镜像扫描无高危/严重漏洞。
- [ ] 性能基准回归：P99 不劣化超过 10%。
- [ ] SBOM 已生成并归档。

## 2. 配置检查

- [ ] 环境变量 SM_ENV/SM_LOG_LEVEL 符合目标环境 values。
- [ ] 数据库 sm_api_gateway 已创建，迁移（alembic）已在 staging 验证。
- [ ] Vault 中 secret/sm/sm-api-gateway/ 下密钥齐全（internal-api-key、sm4-key、database-url）。
- [ ] Ingress 域名与 TLS 证书就绪。

## 3. 部署步骤

1. `helm upgrade --install sm-api-gateway ./helm/sm-api-gateway -f helm/sm-api-gateway/values-prod.yaml -n sm-prod`。
2. ArgoCD Application sm-api-gateway 同步为 Healthy/Synced。
3. 等待 rollout 完成：`kubectl rollout status deploy/sm-api-gateway -n sm-prod`。

## 4. 验证步骤

- [ ] `kubectl get pods -n sm-prod -l app.kubernetes.io/instance=sm-api-gateway` 全部 Running。
- [ ] 冒烟测试：健康检查、核心接口 200。
- [ ] Grafana 监控面板有数据，Promtail 日志已入 Loki。
- [ ] 业务方确认功能可用。

## 5. 回滚触发条件与步骤

触发：错误率 >1%、P99 >2s、核心接口不可用超过 5 分钟。
步骤：见 OPERATIONS.md 第 6 节，RTO ≤ 5 分钟。

## 6. SBOM 与供应链策略

- 依赖锁定 requirements.lock；镜像签名（cosign）。
- 仅从 ghcr.io/luoshitianchen/sm-api-gateway 拉取，imagePullPolicy=IfNotPresent。
- 漏洞扫描接入 CI，高危阻断发布。
