# 安全策略

## 漏洞报告

如果发现 SM-API-Gateway 的安全漏洞，请通过以下渠道报告：

- 私密报告：GitHub Security Advisory（推荐）
- 邮件：[security@example.invalid](mailto:security@example.invalid)

请勿在公开 Issue 中披露漏洞细节。我们会尽快响应并修复。

## 安全基线

详见 [SECURITY_BASELINE.md](SECURITY_BASELINE.md)。核心控制包括：

- 安全响应头与 CSP
- TrustedHost 与请求体大小限制
- 接口速率限制
- 国密 SM3 / SM4-CBC（SM3 MAC 完整性校验）
- 密钥仅通过环境变量或 KMS/HSM 注入
- 生产环境认证失败时 fail-closed
