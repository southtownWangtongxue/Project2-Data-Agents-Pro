---
name: scheduled-report
description: 创建并管理定时报表任务，按 cron 周期执行 SQL 并推送结果
icon: 📊
modes: [task]
is_global: false
---
# 定时报告技能

当用户希望按固定周期（如每天/每周）自动生成数据报表并推送到指定渠道时，使用本技能。

## 使用场景
- 每日销售数据汇总推送
- 每周运营指标报告
- 周期性数据健康检查

## 执行方式
调用 `create_scheduled_report(name, sql, cron, channel, recipients)`：
- name: 任务名称
- sql: 要执行的查询语句
- cron: cron 表达式（如 "0 9 * * 1-5" 工作日 9 点）
- channel: 推送渠道（wechat / email）
- recipients: 接收人列表
