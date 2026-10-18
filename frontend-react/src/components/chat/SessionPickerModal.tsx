/**
 * SessionPickerModal.tsx —— 「选择对话」批量删除弹窗(2026-10-18 重做)
 *
 * 替代侧栏内嵌的批量操作条(用户反馈界面混乱、按钮挤压换行、易误点):
 * - 独立弹窗:分组(今天 / 7天内 / 30天内 / 更早)+ 圆形复选 + 底部删除
 * - 每行显示标题 + 时间,同名会话可区分(此前同名会话无法辨别导致"删不掉"的错觉)
 * - 删除走 batchDeleteSessions:成功即时刷新,失败保留选中并给出原因
 * - 不含归档/置顶(用户明确取消归档、无需置顶)
 */
import { useMemo, useState } from 'react'
import { Modal, App as AntApp } from 'antd'
import Icon from '@/components/bits/Icon'
import { useChatStore, type SessionInfo } from '@/stores/chat'

const GROUP_ORDER = ['今天', '7天内', '30天内', '更早'] as const
type GroupName = (typeof GROUP_ORDER)[number]

/** 按创建时间分组(与参考设计一致:今天 / 7天内 / 30天内 / 更早) */
function groupOf(s: SessionInfo): GroupName {
  if (!s.created_at) return '更早'
  const ts = new Date(s.created_at).getTime()
  const now = Date.now()
  const startToday = new Date()
  startToday.setHours(0, 0, 0, 0)
  if (ts >= startToday.getTime()) return '今天'
  if (ts >= now - 7 * 86400_000) return '7天内'
  if (ts >= now - 30 * 86400_000) return '30天内'
  return '更早'
}

/** 行内时间:今天显示时分,其余显示月-日 */
function timeLabel(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const startToday = new Date()
  startToday.setHours(0, 0, 0, 0)
  if (d.getTime() >= startToday.getTime()) {
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  return `${d.getMonth() + 1}-${String(d.getDate()).padStart(2, '0')}`
}

/** 圆形复选框(自绘,贴合参考设计的空心圆 → 实心勾选) */
function CircleCheck({ checked }: { checked: boolean }) {
  return (
    <span
      className="w-[18px] h-[18px] rounded-full flex items-center justify-center flex-shrink-0 transition-colors"
      style={{
        border: checked ? 'none' : '1.5px solid var(--border-light)',
        background: checked ? 'var(--brand)' : 'transparent',
      }}
    >
      {checked && <Icon name="check" size={11} color="#fff" />}
    </span>
  )
}

export default function SessionPickerModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const store = useChatStore()
  const { message } = AntApp.useApp()
  const [selected, setSelected] = useState<string[]>([])
  const [deleting, setDeleting] = useState(false)

  const list = store.sessions
  const grouped = useMemo(() => {
    const map = new Map<GroupName, SessionInfo[]>()
    for (const g of GROUP_ORDER) map.set(g, [])
    for (const s of list) map.get(groupOf(s))!.push(s)
    return map
  }, [list])

  const toggle = (id: string) => {
    setSelected(v => (v.includes(id) ? v.filter(x => x !== id) : [...v, id]))
  }
  const allSelected = list.length > 0 && selected.length === list.length
  const toggleAll = () => setSelected(allSelected ? [] : list.map(s => s.thread_id))

  const close = () => {
    setSelected([])
    onClose()
  }

  const remove = async () => {
    if (selected.length === 0) return
    setDeleting(true)
    try {
      const { deleted, failed, error } = await store.batchDeleteSessions(selected)
      if (failed > 0) {
        message.error(`已删除 ${deleted} 个，${failed} 个失败${error ? `：${error}` : ''}`)
        /* 失败项保留选中,便于重试;重新拉取以反映真实状态 */
        await store.loadSessions()
        setSelected(prev => prev.filter(id => store.sessions.some(s => s.thread_id === id)))
      } else {
        message.success(`已删除 ${deleted} 个对话`)
        setSelected([])
        close()
      }
    } catch (e) {
      message.error(`删除失败：${(e as Error).message || '未知错误'}`)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Modal
      open={open}
      onCancel={close}
      footer={null}
      width={440}
      /* 标题只留文案:右上角是 antd 自带关闭按钮,不能再放操作(2026-10-18 重叠修复) */
      title={<span className="text-[15px] font-semibold text-[var(--text-1)]">选择对话</span>}
      styles={{
        body: { padding: '4px 0 0' },
        header: { paddingBottom: 0, marginBottom: 8 },
      }}
    >
      {/* 分组列表 */}
      <div className="max-h-[52vh] overflow-y-auto -mx-1 px-1">
        {list.length === 0 && (
          <div className="py-10 text-center text-[12.5px] text-[var(--text-3)]">暂无会话</div>
        )}
        {GROUP_ORDER.map(g => {
          const rows = grouped.get(g) || []
          if (rows.length === 0) return null
          return (
            <div key={g} className="mb-3 last:mb-0">
              <div className="text-[12px] text-[var(--text-3)] mb-1.5">{g}</div>
              {rows.map(s => {
                const checked = selected.includes(s.thread_id)
                return (
                  <button
                    key={s.thread_id}
                    type="button"
                    onClick={() => toggle(s.thread_id)}
                    className="w-full flex items-center gap-2.5 px-2 py-2.5 rounded-lg bg-transparent border-none cursor-pointer text-left transition-colors"
                    onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)' }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
                  >
                    <CircleCheck checked={checked} />
                    <span className="flex-1 min-w-0 truncate text-[13.5px] text-[var(--text-1)]">
                      {s.title || '未命名会话'}
                    </span>
                    <span className="mono text-[12px] text-[var(--text-3)] flex-shrink-0">{timeLabel(s.created_at)}</span>
                  </button>
                )
              })}
            </div>
          )
        })}
        {store.sessionsHasMore && (
          <button
            type="button"
            onClick={() => store.loadMoreSessions()}
            disabled={store.sessionsLoadingMore}
            className="w-full py-2 text-[12.5px] text-[var(--text-3)] hover:text-[var(--text-1)] bg-transparent border-none cursor-pointer transition-colors disabled:opacity-50"
          >
            {store.sessionsLoadingMore ? '加载中…' : '加载更多'}
          </button>
        )}
      </div>

      {/* 底部工具栏:左侧 全选 + 已选计数,右侧 取消/删除(无置顶) */}
      <div
        className="flex items-center justify-between gap-2 mt-3 pt-3"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <span className="flex items-center gap-2 min-w-0">
          <button
            type="button"
            onClick={toggleAll}
            className="text-[12.5px] px-2 py-1 rounded-md text-[var(--text-2)] hover:text-[var(--text-1)] hover:bg-white/[0.05] bg-transparent border-none cursor-pointer transition-colors flex-shrink-0"
          >
            {allSelected ? '取消全选' : '全选'}
          </button>
          <span className="text-[12.5px] text-[var(--text-3)] truncate">
            {selected.length > 0 ? `已选 ${selected.length} 个` : '选择要删除的对话'}
          </span>
        </span>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={close}
            className="px-3.5 py-1.5 rounded-lg text-[13px] bg-transparent border cursor-pointer text-[var(--text-2)] hover:text-[var(--text-1)] transition-colors"
            style={{ borderColor: 'var(--border)' }}
          >
            取消
          </button>
          <button
            type="button"
            onClick={remove}
            disabled={selected.length === 0 || deleting}
            className="px-3.5 py-1.5 rounded-lg text-[13px] border-none cursor-pointer transition-colors disabled:opacity-45 disabled:cursor-not-allowed flex items-center gap-1.5"
            style={{ background: 'rgba(248,81,73,0.14)', color: 'var(--danger)' }}
          >
            <Icon name="trash" size={14} />
            {deleting ? '删除中…' : '删除'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
