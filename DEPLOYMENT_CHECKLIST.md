# 生产部署检查清单

## 密钥与配置

- [ ] 通过 KMS/HSM 注入 `SM4_KEY_HEX`（16 字节十六进制）
- [ ] 设置强随机 `SM_INTERNAL_API_KEY` 与 `SM_JWT_SECRET`
- [ ] 配置 `SM_AUDIT_CENTER_URL` 指向集中审计中心
- [ ] 配置 `SM_DATABASE_PATH` 指向持久化卷
- [ ] `SM_ALLOWED_HOSTS` 不含通配主机

## 网络

- [ ] 服务仅绑定内网地址或置于 VPN/零信任网关之后
- [ ] 通过反向代理启用 HTTPS 与 HSTS
- [ ] 不直接开放容器端口到公网

## 运行

- [ ] 健康检查与就绪探针通过
- [ ] 依赖服务（IAM、审计中心等）已启动
- [ ] 接入 Prometheus 抓取 `/metrics`
- [ ] 审计日志已接入集中审计中心并验证留痕
- [ ] 容器以非 root 运行、只读根文件系统、能力剥离
