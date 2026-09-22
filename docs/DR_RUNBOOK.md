# sm-api-gateway（API 网关）容灾恢复手册（DR Runbook）

## 1. 数据库备份与恢复

- 备份：PostgreSQL 每日全量 + WAL 持续归档，库名 sm_api_gateway。
- 恢复：
  1. 确认恢复目标时间点（PITR）。
  2. 在备集群拉起 sm_api_gateway，回放 WAL 至目标时间。
  3. 修改 SM_DATABASE_URL（Vault）指向新主库。
  4. `kubectl rollout restart deploy/sm-api-gateway -n sm-prod`。
  5. 验证连接与核心接口。

## 2. 服务降级方案

- 数据库不可用：返回兜底/只读缓存，错误率告警。
- 下游依赖超时：熔断器打开，限流保护实例。
- 流量激增：HPA 自动扩容至 maxReplicas(10)。

## 3. 跨可用区 / 跨区域切换

- 本服务无状态，切换时在目标 AZ 重新调度（反亲和 + nodeSelector）。
- 跨区域：将 ArgoCD Application 指向灾备集群 values-prod-dr，DNS 切换流量。

## 4. 演练频率与记录

- 每季度执行一次恢复演练（数据库恢复 + 服务切换）。
- 演练记录：时间、RTO/RPO、问题、改进项，归档至运维知识库。
