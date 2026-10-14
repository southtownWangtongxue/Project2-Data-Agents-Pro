import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'DataAgent Pro',
  description: '智能业务数据交互平台文档',
  lang: 'zh-CN',
  // 归档正文可能含过期相对资源，不参与站点构建；仅保留 archive/README 作索引
  srcExclude: ['archive/reference/**', 'archive/plans/**', 'archive/root/**', 'archive/superpowers/**', 'superpowers/**'],
  ignoreDeadLinks: [
    /^https?:\/\/localhost/,
    '/archive/index',
  ],
  themeConfig: {
    nav: [
      { text: '首页', link: '/' },
      { text: '上手', link: '/guide/quick-start' },
      { text: '理解系统', link: '/guide/architecture' },
      { text: '使用与集成', link: '/api/introduction' },
      { text: '二次开发', link: '/develop/frontend-dev' },
      { text: '质量', link: '/qa/01_功能测试用例集' },
      { text: '归档', link: '/archive/' },
    ],
    sidebar: {
      '/guide/': [
        {
          text: '上手',
          items: [
            { text: '快速开始', link: '/guide/quick-start' },
            { text: 'Docker 部署', link: '/guide/deployment' },
          ],
        },
        {
          text: '理解系统',
          items: [
            { text: '架构设计', link: '/guide/architecture' },
            { text: '工作流详解', link: '/guide/workflow' },
            { text: 'Harness 落地差距分析', link: '/reference/harness-landing-gap-analysis' },
          ],
        },
      ],
      '/reference/': [
        { text: 'Harness 落地差距分析', link: '/reference/harness-landing-gap-analysis' },
        { text: '对话界面对齐官方样板间', link: '/reference/chat-ui-playground-alignment' },
        { text: '归档说明', link: '/archive/' },
      ],
      '/api/': [
        {
          text: '使用与集成',
          items: [
            { text: '鉴权说明', link: '/api/introduction' },
            { text: '对话与审批接口', link: '/api/chat-api' },
            { text: '安全与审批流', link: '/advanced/security' },
            { text: 'RAG 知识库配置', link: '/advanced/rag-config' },
            { text: '接入新数据库', link: '/advanced/database-access' },
          ],
        },
      ],
      '/advanced/': [
        { text: '鉴权说明', link: '/api/introduction' },
        { text: '对话与审批接口', link: '/api/chat-api' },
        { text: '安全与审批流', link: '/advanced/security' },
        { text: 'RAG 知识库配置', link: '/advanced/rag-config' },
        { text: '接入新数据库', link: '/advanced/database-access' },
      ],
      '/develop/': [
        { text: '前端二次开发', link: '/develop/frontend-dev' },
        { text: 'Agent 开发指南', link: '/develop/agent-dev' },
        { text: '对话界面对齐官方样板间', link: '/reference/chat-ui-playground-alignment' },
      ],
      '/qa/': [
        { text: '功能测试用例集', link: '/qa/01_功能测试用例集' },
        { text: '测试执行报告', link: '/qa/02_测试执行报告' },
        { text: '对比分析与改进方案', link: '/qa/03_对比分析与改进方案' },
        { text: '架构专项设计 R12-R23', link: '/qa/04_架构专项设计_R12-R23' },
      ],
      '/archive/': [
        { text: '归档说明', link: '/archive/' },
      ],
    },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/southtownWangtongxue/Project2-Data-Agents-Pro' },
    ],
  },
})
