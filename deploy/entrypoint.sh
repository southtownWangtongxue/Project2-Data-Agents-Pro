#!/bin/sh
# ==========================================================================
# DataAgent Pro 单体容器入口脚本
#
# 职责：
#   1. 首次启动时，若挂载卷为空，从镜像内默认目录初始化
#      （configs / skills / resources 均为持久化卷）
#   2. 交给 supervisord 同时拉起 nginx + uvicorn
#
# 挂载卷设计（docker-compose.yml 中定义）：
#   agent_configs   -> /app/configs              MCP/LLM/Skill 配置 JSON（watchdog 热更新）
#   agent_skills    -> /app/app/skills/skills    已安装的 Skill 实体目录
#   agent_resources -> /app/resources            资源文件
#   agent_logs      -> /app/app/logs             运行日志
# ==========================================================================
set -e

echo "[entrypoint] DataAgent Pro 容器启动，初始化持久化卷..."

init_volume() {
    # $1 = 挂载目标目录（容器内路径）  $2 = 镜像内默认目录
    if [ -d "$2" ] && [ -z "$(ls -A "$1" 2>/dev/null)" ]; then
        echo "[entrypoint] 初始化卷: $1 <- $2"
        mkdir -p "$1"
        cp -a "$2/." "$1/"
    fi
}

init_volume /app/configs /app/configs.default
init_volume /app/app/skills/skills /app/skills.default
init_volume /app/resources /app/resources.default
mkdir -p /app/app/logs

echo "[entrypoint] 卷初始化完成，启动 supervisord（nginx + uvicorn）..."
exec supervisord -c /etc/supervisor/supervisord.conf
