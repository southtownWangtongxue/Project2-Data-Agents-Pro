import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'DataAgent Pro',
  description: '智能业务数据交互平台文档',
  lang: 'zh-CN',
  themeConfig: {
    nav: [
      { text: '首页', link: '/' },
      { text: '开发指南', link: '/guide/quick-start' },
      { text: 'API 文档', link: '/api/introduction' },
      { text: '项目文档', link: '/开发计划' },
    ],
    sidebar: {
      '/guide/': [
        { text: '快速开始', link: '/guide/quick-start' },
        { text: '架构设计', link: '/guide/architecture' },
        { text: '工作流详解', link: '/guide/workflow' },
      ],
      '/api/': [
        { text: '鉴权说明', link: '/api/introduction' },
        { text: '对话与审批接口', link: '/api/chat-api' },
      ],
      '/advanced/': [
        { text: 'RAG 知识库配置', link: '/advanced/rag-config' },
        { text: '接入新数据库', link: '/advanced/database-access' },
        { text: '安全与审批流', link: '/advanced/security' },
      ],
      '/develop/': [
        { text: '前端二次开发', link: '/develop/frontend-dev' },
        { text: 'Agent 开发指南', link: '/develop/agent-dev' },
      ],
      '/': [
        { text: '开发计划', link: '/开发计划' },
        { text: 'V2.0 需求规格说明书', link: '/项目需求规格说明书-V2' },
        { text: 'V2.0 配置体系说明书', link: '/配置体系说明书' },
        { text: '项目需求规格说明书 (V1)', link: '/项目需求规格说明书' },
        { text: '项目审计与改进计划', link: '/项目审计与改进计划' },
      ],
    },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/southtownWangtongxue/Project2-Data-Agents-Pro' },
    ],
  },
})
