# 应急响应手册

## 告警来源

- 健康/就绪探针失败、错误率上升、平均延迟超阈值、审计转发失败。

## 处置步骤

1. **确认**：查看 `/health`、`/readyz` 与 `/api/ops/metrics`，确认服务状态。
2. **定位**：检索请求日志（`X-Request-Id`），确认故障类型（配置 / 依赖 / 数据 / 性能）。
3. **缓解**：回滚最近发布；检查依赖服务（IAM、审计中心）状态；确认密钥注入可用。
4. **恢复**：重启容器或扩容副本；验证健康检查恢复。
5. **复盘**：记录时间线、根因与改进项，更新本文档与 CHANGELOG。

## 关键命令

```powershell
Invoke-RestMethod http://127.0.0.1:PORT/health
Invoke-RestMethod http://127.0.0.1:PORT/readyz
Invoke-RestMethod http://127.0.0.1:PORT/api/ops/metrics
```

## 联系人

- 服务负责人：SRE 值班组（sre@example.invalid）
