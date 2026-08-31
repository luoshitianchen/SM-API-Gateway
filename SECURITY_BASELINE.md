# 安全基线

本文件定义 SM-API-Gateway 的安全基线控制项与部署建议。

## 控制项

| 控制项 | 状态 | 说明 |
|---|---|---|
| 安全响应头 | ✅ 已启用 | X-Content-Type-Options / X-Frame-Options / Referrer-Policy / Permissions-Policy / CSP |
| HSTS | ✅ 生产启用 | 生产环境返回 Strict-Transport-Security |
| TrustedHost | ✅ 已启用 | 仅允许配置的主机访问 |
| 请求体大小限制 | ✅ 已启用 | 默认 1 MiB，超限返回 413 |
| 接口速率限制 | ✅ 已启用 | 默认 600 次/分钟，超限返回 429 |
| 内部写入令牌 | ✅ 可选 | 配置后写接口必须携带 X-Internal-Token |
| JWT 鉴权 | ✅ 可选 | 配置后受保护接口要求 Bearer JWT |
| 国密 SM3 | ✅ 已启用 | 摘要接口与审计完整性 |
| 国密 SM4 | ✅ 已启用 | 加密使用 SM4-CBC + SM3 MAC，防篡改 |
| 密钥注入 | ✅ 环境变量 | SM4_KEY_HEX 仅环境/KMS，禁止落库 |
| 审计落库 | ✅ 已启用 | 本地持久化 + 异步转发集中审计中心 |
| 容器加固 | ✅ 已启用 | 只读根文件系统、能力剥离、非 root、进程限制 |

## 部署建议

- 生产环境通过 KMS/HSM 注入 SM4 密钥与内部令牌。
- 服务置于企业 VPN 或零信任网关之后，不直接暴露公网。
- 启用 HTTPS 并配置 HSTS。
- 接入集中审计中心，保留审计日志至少 365 天。
- 使用 Kubernetes 时采用非 root、只读根文件系统、seccomp 与 NetworkPolicy。
