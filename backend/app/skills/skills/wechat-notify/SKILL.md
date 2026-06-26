---
name: wechat-notify
description: 向企业微信群发送通知、提醒、告警消息。当用户需要推送消息到企业微信时触发此技能。支持文本和Markdown格式消息。
---

# 企业微信通知

## 使用说明
通过企业微信机器人 Webhook 发送消息通知。支持 text 和 markdown 两种消息类型。

## 参数
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| webhook_url | string | 否 | 环境变量 WECHAT_WEBHOOK_URL | 机器人 Webhook 地址 |
| content | string | 是 | - | 消息内容 |
| msg_type | string | 否 | markdown | 消息类型: text / markdown |

## 示例
- "把这个查询结果发送到企业微信群"
- "当销售额低于目标时通知我"
- "每天9点推送昨日销售报表到企业微信"
- "发送告警：数据库连接池使用率超过80%"

## 准则
- webhook_url 优先级：调用参数 > 环境变量 WECHAT_WEBHOOK_URL
- 发送失败时最多重试 2 次，间隔 1 秒
- markdown 消息内容超过 4096 字符时自动截断并追加 "...(已截断)"
- 返回发送状态和消息ID供后续追踪
