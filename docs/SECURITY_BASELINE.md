# sm-api-gateway（API 网关）安全基线

> 适用范围：sm-api-gateway 微服务，容器端口 8008，数据库 sm_api_gateway。
> 本文档对应《SM-* 企业化资产模板规范 v1.0》第 103-112 节。

## 1. 安全基线概述

sm-api-gateway 是 SM 安全运维平台的API 网关组件。安全基线覆盖容器运行时、网络暴露面、密钥管理、数据保护与审计五个方面，满足等保 2.0 三级与 ISO 27001 要求。容器以非 root（UID 1000）运行，根文件系统只读，去除全部 Linux capabilities，禁止提权。

## 2. 等保 2.0 三级控制映射

| 控制点 | 实现方式 | 证据 |
| --- | --- | --- |
| 身份鉴别 | 内部调用统一 SM_INTERNAL_API_KEY，外部经 API 网关 JWT 校验 | helm/templates/secret.yaml、NetworkPolicy |
| 访问控制 | RBAC + Namespace 隔离，仅 sm-prod/ingress-nginx 可入站 | helm/templates/networkpolicy.yaml |
| 安全审计 | 全量请求写入审计日志中心，保留 ≥180 天 | SM-Audit-Log-Center 接入 |
| 入侵防范 | NetworkPolicy 默认拒绝，只读根文件系统、drop ALL capabilities | deployment.yaml securityContext |
| 数据保密性 | 敏感字段 SM4 加密（SM4_KEY_HEX），传输 TLS | ExternalSecret、Ingress TLS |
| 剩余信息保护 | Pod 销毁即回收，DB 字段级加密 | 定时任务 |

## 3. ISO 27001 控制映射（关键项）

| 控制域 | 条款 | 实现 |
| --- | --- | --- |
| A.5 组织安全 | A.5.15 访问控制策略 | NetworkPolicy + RBAC |
| A.8 资产 | A.8.2 信息分类 | 见第 4 节数据分级 |
| A.8 资产 | A.8.25 开发测试与运行隔离 | dev/staging/prod 分环境 values |
| A.9 访问控制 | A.9.4 访问限制 | 内部 API Key + JWT |
| A.10 密码 | A.10.1.1 密码控制 | SM4 字段加密、TLS |
| A.12 运营 | A.12.4 日志与监控 | Promtail→Loki，告警接值班 |
| A.13 通信 | A.13.1 网络控制 | NetworkPolicy 入/出站白名单 |
| A.18 合规 | A.18.1 合规 | 漏洞扫描、SBOM、签名 |

## 4. 数据分类分级

| 级别 | 字段示例 | 处理要求 |
| --- | --- | --- |
| 公开 | 服务名、版本、健康检查结果 | 明文 |
| 内部 | 业务配置、非敏感列表 | 内部网络可见 |
| 机密 | API 调用记录、操作日志 | 加密存储、访问留痕 |
| 绝密 | SM_INTERNAL_API_KEY、SM_DATABASE_URL、SM4_KEY | 仅 Vault，不落镜像/代码 |

## 5. RBAC 权限矩阵

| 角色 | 资源 | 操作 | 权限 |
| --- | --- | --- | --- |
| 开发 | dev namespace | 部署/调试 | 允许 |
| 值班 SRE | sm-prod Pod | 查看/重启 | 允许（只读 + rollout） |
| 运维 | Helm Release | upgrade/rollback | 经 CAB 审批 |
| 审计 | 日志 | 只读 | 允许，禁止删除 |
| 外部调用方 | HTTP / | 仅经 API 网关 | 允许 |

## 6. 认证与授权机制

- 东西向：服务间通过 SM_INTERNAL_API_KEY 双向校验，密钥来自 Vault。
- 南北向：外部请求统一经 sm-api-gateway 校验 JWT 后转发。
- 授权：基于服务角色的 ABAC/RBAC，最小权限原则。

## 7. 审计日志要求

- 记录字段：时间、调用方、接口、入参摘要、结果、 trace_id。
- 输出 JSON 结构化日志，由 Promtail 采集至 Loki。
- 留存 ≥180 天，审计角色只读不可改。

## 8. 漏洞管理流程

1. 依赖锁定：requirements.lock，Trivy 镜像扫描。
2. CI 门禁：高危漏洞阻断发布。
3. 修复 SLA：紧急 7 天、高危 30 天、中危 90 天。
4. 复扫闭环并更新 SBOM。
