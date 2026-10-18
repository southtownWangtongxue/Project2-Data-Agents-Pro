/**
 * WelcomePanel.tsx —— 空态欢迎页
 *
 * 对齐官方独立式样板间:antdx Welcome(variant=borderless) + 双列 Prompts
 * (热门问题 / 使用指南),点击任意条目直接发起对话。
 * 动效:TypeText 打字机标题 + Aurora 呼吸背景(仅欢迎页)。
 */
import { Prompts, Welcome } from '@ant-design/x'
import { Button } from 'antd'
import Icon, { type IconName } from '@/components/bits/Icon'
import Aurora from '@/components/bits/Aurora'
import TypeText from '@/components/bits/TypeText'
import { useChatStore } from '@/stores/chat'

const TITLE = '你好,我是 DataAgent'
const SUBTITLE = '自然语言 → SQL → 图表 → 洞察,一句话完成业务数据探索'

const GUIDE = [
  { key: 'g1', icon: 'database' as IconName, label: '数据探查', description: '统计各表的数据量与数据库整体概况' },
  { key: 'g2', icon: 'chart' as IconName, label: '指标分析', description: '分析各区域销售额的同比与环比变化' },
  { key: 'g3', icon: 'fileChart' as IconName, label: '研究报告', description: '生成一份季度经营分析报告并给出结论' },
  { key: 'g4', icon: 'target' as IconName, label: '口径检索', description: '查询知识库中「活跃客户」的指标定义' },
]

export default function WelcomePanel() {
  const store = useChatStore()

  const hot = store.suggestions.length
    ? store.suggestions.slice(0, 5)
    : ['统计各表的数据量', '查看数据库中所有的表', '帮我分析数据库整体概况']

  const openDocs = () => {
    window.open(`http://${window.location.hostname}:5174/`, '_blank')
  }

  return (
    <div className="relative w-full h-full flex items-center justify-center px-6 overflow-hidden">
      <Aurora />
      <div className="relative w-full rise-in" style={{ maxWidth: 840 }}>
        <Welcome
          variant="borderless"
          style={{ width: '100%' }}
          icon={
            <span className="inline-flex w-12 h-12 rounded-2xl items-center justify-center text-white"
              style={{ background: 'linear-gradient(135deg,#7056F8,#8B6FFF)' }}>
              <Icon name="sparkles" size={22} />
            </span>
          }
          title={
            <span className="text-[26px] font-semibold bg-clip-text text-transparent"
              style={{ backgroundImage: 'linear-gradient(135deg,#8B6FFF,#7056F8)' }}>
              <TypeText text={TITLE} speed={85} />
            </span>
          }
          description={
            <span className="text-[13px] text-[var(--text-3)]">
              <TypeText text={SUBTITLE} speed={32} cursorClassName="opacity-0" />
            </span>
          }
          extra={
            <span className="flex items-center gap-2">
              <Button size="small" icon={<Icon name="refresh" size={16} />} onClick={() => store.loadSuggestions(true)}>
                换一批问题
              </Button>
              <Button size="small" icon={<Icon name="bookMarked" size={16} />} onClick={openDocs}>
                查看文档
              </Button>
            </span>
          }
        />

        <div className="flex gap-4 w-full mt-6 max-[900px]:flex-col">
          <Prompts
            className="flex-1 min-w-0"
            title="热门问题"
            items={[{ key: 'hot', label: '试试这些问题', children: hot.map(q => ({ key: q, description: q })) }]}
            onItemClick={info => store.sendMessage(String(info.data.description || ''))}
          />
          <Prompts
            className="flex-1 min-w-0"
            title="使用指南"
            items={[{
              key: 'guide',
              label: '按场景开始',
              children: GUIDE.map(g => ({ key: g.key, description: g.description, icon: <Icon name={g.icon} size={16} /> })),
            }]}
            onItemClick={info => store.sendMessage(String(info.data.description || ''))}
          />
        </div>
      </div>
    </div>
  )
}