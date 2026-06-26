---
name: external-api
description: 调用外部 HTTP/HTTPS API 接口。当用户需要对接第三方系统、调用外部服务时触发此技能。支持 GET/POST/PUT/DELETE 方法。
---

# 外部 API 调用

## 使用说明
通用的 HTTP 客户端，支持调用任意外部 API 接口。自动处理认证头、超时、重试和响应解析。

## 参数
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| url | string | 是 | - | API 完整地址 |
| method | string | 否 | GET | HTTP 方法: GET/POST/PUT/DELETE |
| headers | dict | 否 | {} | 自定义请求头 |
| body | dict | 否 | None | 请求体 (JSON) |
| timeout | int | 否 | 30 | 超时秒数 |

## 示例
- "调用气象局API查询明天天气"
- "把这个数据POST到数据中台的接口"
- "从第三方CRM系统拉取客户列表"
- "调用内部监控API获取服务健康状态"

## 准则
- 请求前检查 URL 白名单（生产环境必须配置 ALLOWED_EXTERNAL_URLS 环境变量）
- 所有请求记录日志（URL、状态码、耗时）
- 响应超过 500KB 自动摘要而非返回完整内容
- 敏感请求头（Authorization 等）不在日志中打印
