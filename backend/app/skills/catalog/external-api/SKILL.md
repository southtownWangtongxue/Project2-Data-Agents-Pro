---
name: external-api
description: 调用外部 HTTP API（GET/POST/PUT/DELETE），获取实时数据或触发第三方系统
icon: 🌐
modes: [all]
is_global: true
---
# 外部 API 调用技能

当用户需要调用第三方 HTTP 接口获取实时数据（如天气、股价、业务系统查询）或触发外部操作时使用本技能。

## 使用场景
- 查询外部业务系统的数据
- 调用 Webhook / 开放平台接口
- 推送消息到外部服务

## 执行方式
调用 `call_external_api(url, method, headers, body, timeout)`：
- 默认启用 ALLOWED_EXTERNAL_URLS 白名单校验（环境变量配置）
- 自动脱敏 Authorization / X-API-Key 头用于日志
- 响应体超过 500KB 自动截断
- 超时与异常均返回结构化错误，便于 Agent 重试或降级
