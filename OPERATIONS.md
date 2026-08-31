# 运维与可观测性

## 运行指标

- `GET /api/ops/metrics`：请求总量、错误总量、平均延迟。
- `GET /metrics`：Prometheus 文本指标（`sm_api-gateway_requests_total` 等）。

## 健康检查

- `GET /health`：存活探针（含数据库状态）。
- `GET /readyz`：就绪探针（运行时 / 配置 / 数据库 / 密钥注入状态）。

## 日志

- 结构化 JSON 请求日志（请求 ID、方法、路径、状态、耗时）。
- 通过 `X-Request-Id` / `X-Trace-Id` 关联全链路。

## 建议

- 生产接入 Prometheus + Grafana 采集 `/metrics`。
- 通过融合门户 /api/integration/check 做整体链路巡检。
- 日志与审计事件统一归档至集中审计中心。
