# sm-api-gateway 多环境矩阵

| 维度 | dev | staging | prod |
| --- | --- | --- | --- |
| namespace | sm-dev | sm-staging | sm-prod |
| 副本数 | 1 | 2 | 3 |
| 镜像 tag | dev | staging | (Chart.AppVersion) |
| requests.cpu | 50m | 100m | 200m |
| requests.memory | 64Mi | 128Mi | 256Mi |
| limits.cpu | 200m | 500m | 1 |
| limits.memory | 128Mi | 256Mi | 512Mi |
| HPA min/max | 1/3 | 2/5 | 3/10 |
| 日志级别 | debug | info | warn |
| 域名 | sm-api-gateway.dev.sm.example.com | sm-api-gateway.staging.sm.example.com | sm-api-gateway.sm.example.com |
| TLS | 关闭 | sm-staging-tls | sm-tls |
| 数据库 | sm_api_gateway（dev 实例） | sm_api_gateway（staging 实例） | sm_api_gateway（primary） |
| 自动同步 | 否 | 否 | ArgoCD automated |
