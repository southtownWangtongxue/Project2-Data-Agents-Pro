<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goToChat() { router.push('/chat') }
const DOCS_BASE = 'http://localhost:5174'
function openDocs() { window.open(DOCS_BASE + '/', '_blank') }

const features = [
  {
    icon: 'chat', title: '自然语言交互',
    desc: '使用日常语言描述数据分析需求，无需编写 SQL 代码，AI 自动理解并执行查询。',
    gradient: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
  },
  {
    icon: 'zap', title: '实时流式体验',
    desc: 'SQL 生成、数据分析全程逐字流式输出，任务清单实时显示每步进度，完成后自动折叠。',
    gradient: 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)',
  },
  {
    icon: 'shield', title: '企业级安全',
    desc: '高危 SQL 自动审批 + 数据脱敏保护，正则+LLM 双重审计，确保业务数据安全无忧。',
    gradient: 'linear-gradient(135deg, #22c55e 0%, #10b981 100%)',
  },
  {
    icon: 'brain', title: 'Multi-Agent 协同',
    desc: '8 个专职 Agent 通过 13 节点 LangGraph 工作流协同，Plan-and-Execute + ReAct 质量评估。',
    gradient: 'linear-gradient(135deg, #8b5cf6 0%, #d946ef 100%)',
  },
  {
    icon: 'chart', title: '智能可视化',
    desc: '自动生成 ECharts 图表配置，支持柱状图、饼图、折线图等，数据导出 CSV/Excel。',
    gradient: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)',
  },
  {
    icon: 'database', title: '多数据源适配',
    desc: '支持 MySQL、PostgreSQL、Oracle、SQL Server 四种方言，新增数据库仅需配置。',
    gradient: 'linear-gradient(135deg, #ef4444 0%, #f97316 100%)',
  },
]

const statPanels = [
  { label: 'Agent 数', value: '8' },
  { label: '工作流节点', value: '13' },
  { label: 'SSE 事件', value: '14' },
  { label: 'SQL 方言', value: '4' },
]
</script>

<template>
  <div class="home-page">
    <!-- ── Hero ── -->
    <section class="hero">
      <div class="hero-text">
        <div class="hero-badge">
          <span class="badge-dot"></span>
          AI-powered Data Analytics
        </div>
        <h1 class="hero-title">
          用自然语言<br/>
          <span class="title-gradient">探索数据洞察</span>
        </h1>
        <p class="hero-desc">
          DataAgent Pro 是基于 Multi-Agent 协同架构的智能数据分析平台，
          让非技术用户通过自然语言安全、高效地获取数据洞察与可视化报告。
        </p>
        <div class="hero-actions">
          <button class="btn-primary" @click="goToChat">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            开始对话
          </button>
          <button class="btn-secondary" @click="openDocs">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
            </svg>
            查看文档
          </button>
        </div>
      </div>

      <div class="hero-visual">
        <div class="visual-card">
          <div class="visual-header">
            <div class="visual-dots"><span></span><span></span><span></span></div>
            <span class="visual-title">任务清单</span>
          </div>
          <div class="visual-body">
            <div class="vis-task done"><span class="vis-check">✓</span> 意图分析</div>
            <div class="vis-task done"><span class="vis-check">✓</span> 加载表结构</div>
            <div class="vis-task done"><span class="vis-check">✓</span> 生成SQL</div>
            <div class="vis-task done"><span class="vis-check">✓</span> 执行查询</div>
            <div class="vis-task running"><span class="vis-spinner"></span> 数据分析</div>
            <div class="vis-task pending"><span class="vis-pending"></span> 生成图表</div>
          </div>
        </div>
        <div class="floating el-1">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        </div>
        <div class="floating el-2">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
        </div>
      </div>
    </section>

    <!-- ── Stats ── -->
    <section class="stats">
      <div v-for="s in statPanels" :key="s.label" class="stat-item">
        <span class="stat-value">{{ s.value }}</span>
        <span class="stat-label">{{ s.label }}</span>
      </div>
    </section>

    <!-- ── Features ── -->
    <section class="features">
      <div class="section-head">
        <h2>核心能力</h2>
        <p>为业务人员设计的智能数据分析平台</p>
      </div>
      <div class="features-grid">
        <div v-for="f in features" :key="f.title" class="feature-card">
          <div class="fc-icon" :style="{ background: f.gradient }">
            <svg v-if="f.icon==='chat'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            <svg v-else-if="f.icon==='zap'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            <svg v-else-if="f.icon==='shield'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <svg v-else-if="f.icon==='brain'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M12 2a4 4 0 0 0 0 8M12 2a4 4 0 0 1 0 8M12 14a4 4 0 0 0 0 8M12 14a4 4 0 0 1 0 8M2 12a4 4 0 0 0 4-4M2 12a4 4 0 0 1 4 4M22 12a4 4 0 0 0-4-4M22 12a4 4 0 0 1-4 4M12 6v12"/></svg>
            <svg v-else-if="f.icon==='chart'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
            <svg v-else-if="f.icon==='database'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
          </div>
          <h3>{{ f.title }}</h3>
          <p>{{ f.desc }}</p>
        </div>
      </div>
    </section>

    <!-- ── Documentation Links ── -->
    <section class="docs-section">
      <div class="section-head">
        <h2>开发者文档</h2>
        <p>深入了解架构设计、API 接口与二次开发指南</p>
      </div>
      <div class="docs-grid">
        <a :href="DOCS_BASE + '/guide/quick-start.html'" target="_blank" class="doc-card">
          <div class="doc-icon" style="background: rgba(99,102,241,.12);color:#818cf8">🚀</div>
          <div><h4>快速开始</h4><p>环境搭建、配置 .env、启动前后端服务</p></div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </a>
        <a :href="DOCS_BASE + '/guide/architecture.html'" target="_blank" class="doc-card">
          <div class="doc-icon" style="background: rgba(139,92,246,.12);color:#a78bfa">🏗️</div>
          <div><h4>架构设计</h4><p>六层架构、Agent 拓扑、技术选型</p></div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </a>
        <a :href="DOCS_BASE + '/guide/workflow.html'" target="_blank" class="doc-card">
          <div class="doc-icon" style="background: rgba(34,197,94,.12);color:#22c55e">🔄</div>
          <div><h4>工作流详解</h4><p>13 节点拓扑、SSE 事件时序、审批流</p></div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </a>
        <a :href="DOCS_BASE + '/api/chat-api.html'" target="_blank" class="doc-card">
          <div class="doc-icon" style="background: rgba(245,158,11,.12);color:#f59e0b">📡</div>
          <div><h4>API 文档</h4><p>SSE 流式对话、会话管理、审批回调</p></div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </a>
        <a :href="DOCS_BASE + '/develop/agent-dev.html'" target="_blank" class="doc-card">
          <div class="doc-icon" style="background: rgba(6,182,212,.12);color:#06b6d4">🧩</div>
          <div><h4>Agent 开发</h4><p>新增 Agent、注册 Graph、SSE 事件规范</p></div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </a>
        <a :href="DOCS_BASE + '/develop/frontend-dev.html'" target="_blank" class="doc-card">
          <div class="doc-icon" style="background: rgba(239,68,68,.12);color:#ef4444">🎨</div>
          <div><h4>前端开发</h4><p>Vue 组件、SSE 消费、任务清单机制</p></div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </a>
      </div>
    </section>

    <!-- ── Footer ── -->
    <footer class="footer">
      <span>DataAgent Pro v0.2.0</span>
      <span class="footer-divider">·</span>
      <span>基于 LangGraph + FastAPI + Vue 3 构建</span>
    </footer>
  </div>
</template>

<style scoped>
.home-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--space-10) var(--space-6) var(--space-16);
}

/* ── Hero ── */
.hero {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-16);
  align-items: center;
  padding: var(--space-8) 0 var(--space-16);
}
.hero-text { animation: fadeUp .6s ease-out; }
@keyframes fadeUp { from { opacity:0; transform:translateY(20px) } to { opacity:1; transform:none } }

.hero-badge {
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: rgba(99,102,241,.1); border: 1px solid rgba(99,102,241,.3);
  border-radius: var(--radius-full); font-size: 13px; font-weight: 500;
  color: var(--color-primary-light); margin-bottom: var(--space-6);
}
.badge-dot { width:8px; height:8px; background: linear-gradient(135deg,#6366f1,#818cf8); border-radius:50%; animation: pulse 2s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity:1; transform:scale(1) } 50% { opacity:.6; transform:scale(.9) } }

.hero-title { font-size: 52px; font-weight: 700; line-height: 1.1; letter-spacing: -.03em; color: var(--color-text-primary); margin-bottom: var(--space-5); }
.title-gradient { background: linear-gradient(135deg,#6366f1 0%,#818cf8 50%,#a78bfa 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
.hero-desc { font-size: 17px; line-height: 1.7; color: var(--color-text-secondary); margin-bottom: var(--space-8); }
.hero-actions { display: flex; gap: var(--space-4); }

.btn-primary {
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: var(--space-3) var(--space-6); background: linear-gradient(135deg,#6366f1,#818cf8);
  border: none; border-radius: var(--radius-lg); font-size: 15px; font-weight: 600;
  color: white; cursor: pointer; transition: all var(--transition-fast);
  box-shadow: 0 4px 14px rgba(99,102,241,.4);
}
.btn-primary:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(99,102,241,.5); }
.btn-secondary {
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: var(--space-3) var(--space-6); background: transparent;
  border: 1px solid var(--color-border); border-radius: var(--radius-lg);
  font-size: 15px; font-weight: 500; color: var(--color-text-secondary); cursor: pointer;
  transition: all var(--transition-fast);
}
.btn-secondary:hover { background: var(--color-surface); border-color: var(--color-border-light); color: var(--color-text-primary); }

/* ── Hero Visual ── */
.hero-visual { position: relative; animation: fadeUp .6s ease-out .2s both; }
.visual-card { background: var(--color-surface); border:1px solid var(--color-border); border-radius: var(--radius-xl); overflow: hidden; box-shadow: var(--shadow-lg); }
.visual-header { display:flex; align-items:center; justify-content:space-between; padding: var(--space-3) var(--space-4); background: rgba(255,255,255,.02); border-bottom:1px solid var(--color-border); }
.visual-dots { display:flex; gap: var(--space-2); }
.visual-dots span { width:10px; height:10px; border-radius:50%; }
.visual-dots span:nth-child(1){ background:#ef4444 }
.visual-dots span:nth-child(2){ background:#f59e0b }
.visual-dots span:nth-child(3){ background:#22c55e }
.visual-title { font-size:12px; color:var(--color-text-muted); }
.visual-body { padding: var(--space-4) var(--space-5) var(--space-5); display:flex; flex-direction:column; gap: var(--space-2); }

.vis-task { display:flex; align-items:center; gap: var(--space-2); font-size:13px; padding: var(--space-1) 0; }
.vis-check { display:flex; align-items:center; justify-content:center; width:20px; height:20px; border-radius:50%; background: rgba(34,197,94,.12); color:#22c55e; font-size:10px; font-weight:700; }
.vis-spinner { width:20px; height:20px; border-radius:50%; border:2px solid rgba(99,102,241,.2); border-top-color:#6366f1; animation: spin .8s linear infinite; }
.vis-pending { width:20px; height:20px; border-radius:50%; border:1.5px solid var(--color-border); }
@keyframes spin { to { transform:rotate(360deg) } }
.vis-task.done { color: var(--color-text-secondary); }
.vis-task.running { color: var(--color-text-primary); }
.vis-task.pending { color: var(--color-text-muted); }

.floating { position:absolute; display:flex; align-items:center; justify-content:center; width:44px; height:44px; background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-lg); box-shadow:var(--shadow-md); animation: float 3s ease-in-out infinite; }
.el-1 { top:-20px; right:-20px; }
.el-2 { bottom:30px; left:-24px; animation-delay:1s; }
@keyframes float { 0%,100% { transform:translateY(0) } 50% { transform:translateY(-10px) } }

/* ── Stats ── */
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-4); padding: var(--space-10) 0; }
.stat-item { text-align: center; padding: var(--space-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.stat-value { display: block; font-size: 36px; font-weight: 700; background: linear-gradient(135deg,#6366f1,#a78bfa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
.stat-label { font-size: 13px; color: var(--color-text-muted); margin-top: var(--space-2); }

/* ── Features ── */
.features { padding: var(--space-12) 0; }
.section-head { text-align: center; margin-bottom: var(--space-10); }
.section-head h2 { font-size: 32px; font-weight: 700; color: var(--color-text-primary); margin-bottom: var(--space-3); }
.section-head p { font-size: 16px; color: var(--color-text-secondary); }
.features-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-5); }

.feature-card { padding: var(--space-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-xl); transition: all var(--transition-normal); }
.feature-card:hover { border-color: var(--color-border-light); transform: translateY(-4px); box-shadow: var(--shadow-lg); }
.fc-icon { display: flex; align-items: center; justify-content: center; width: 44px; height: 44px; border-radius: var(--radius-lg); margin-bottom: var(--space-4); }
.feature-card h3 { font-size: 16px; font-weight: 600; color: var(--color-text-primary); margin-bottom: var(--space-2); }
.feature-card p { font-size: 13px; line-height: 1.6; color: var(--color-text-secondary); }

/* ── Docs ── */
.docs-section { padding: var(--space-12) 0; }
.docs-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); }
.doc-card {
  display: flex; align-items: center; gap: var(--space-3);
  padding: var(--space-4); background: var(--color-surface);
  border: 1px solid var(--color-border); border-radius: var(--radius-lg);
  text-decoration: none; transition: all var(--transition-fast);
}
.doc-card:hover { border-color: var(--color-border-light); background: var(--color-surface-elevated); }
.doc-icon { display: flex; align-items: center; justify-content: center; width: 40px; height: 40px; border-radius: var(--radius-md); font-size: 18px; flex-shrink: 0; }
.doc-card div:last-of-type { flex:1; min-width:0; }
.doc-card h4 { font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 2px; }
.doc-card p { font-size: 12px; color: var(--color-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.doc-card svg { color: var(--color-text-muted); flex-shrink: 0; }

/* ── Footer ── */
.footer { text-align: center; padding: var(--space-8) 0 0; font-size: 13px; color: var(--color-text-muted); }
.footer-divider { margin: 0 var(--space-2); opacity: .4; }

/* ── Responsive ── */
@media (max-width: 1024px) {
  .hero { grid-template-columns: 1fr; text-align: center; gap: var(--space-10); }
  .hero-actions { justify-content: center; }
  .hero-visual { max-width: 480px; margin: 0 auto; }
  .floating { display: none; }
  .hero-title { font-size: 40px; }
  .features-grid, .docs-grid { grid-template-columns: repeat(2, 1fr); }
  .stats { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
  .hero-title { font-size: 32px; }
  .features-grid, .docs-grid { grid-template-columns: 1fr; }
}
</style>
