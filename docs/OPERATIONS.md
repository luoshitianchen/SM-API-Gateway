# sm-api-gateway（API 网关）运维手册

## 1. 服务概述与依赖

sm-api-gateway 为 SM 平台API 网关，监听容器端口 8008。
依赖：PostgreSQL（postgres-primary.sm-prod:5432）、Vault（密钥）、Loki（日志）、API 网关（入口）。

## 2. SLO 定义

| 指标 | 目标 |
| --- | --- |
| 可用性 | ≥ 99.9%（月） |
| P99 延迟 | < 1s |
| 错误率 | < 0.1% |

## 3. 错误预算

月度错误预算 = 1 - 99.9% = 0.1%，即约 43.2 分钟不可用。
消耗跟踪：以 Grafana SLO Panel 为准；预算消耗 50% 告警，80% 冻结非紧急发布。

## 4. 变更管理流程（CAB）

- 常规变更：周二/周四变更窗口，提前 1 个工作日提交 CAB。
- 紧急变更：值班负责人审批，事后 24h 补审。
- 变更记录：关联工单、commit、helm revision。

## 5. 发布审批流程（门禁）

dev（自动部署）→ staging（冒烟通过）→ prod（CAB + 双人复核）。
prod 发布需满足：测试覆盖率 ≥80%、安全扫描无高危、性能回归无劣化。

## 6. 回滚流程

1. `helm history sm-api-gateway` 查看版本。
2. `helm rollback sm-api-gateway <上一版本>`。
3. 等待 Pod Ready，验证 /health 与 /readyz。
4. 观察监控与错误率 15 分钟。
RTO 目标 ≤ 5 分钟。

## 7. 值班与告警响应

- On-call 轮值一级，30 分钟未响应升级二级（值班负责人），1 小时升级平台负责人。
- 告警通道：企业微信/电话；P1 立即响应。

## 8. 日常运维操作

- 扩缩容：优先由 HPA 自动完成，手动 `kubectl scale` 需记录原因。
- 日志排查：`kubectl logs -l app.kubernetes.io/instance=sm-api-gateway` 或 Loki 按 job=sm-api-gateway 检索。
- 配置变更：修改 values 走 GitOps，禁止 kubectl edit 直接改 prod。
