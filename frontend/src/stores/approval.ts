import { defineStore } from 'pinia'
import { ref } from 'vue'
import client from '@/api/client'

/* 审批任务类型 */
export interface ApprovalTask {
  threadId: string
  question: string
  sql: string
  reason: string
  status: 'pending' | 'approved' | 'rejected'
  createdAt: number
  comment?: string
}

/* localStorage 存储键名 */
const STORAGE_KEY = 'approval_tasks'

/* 审批管理 Store */
export const useApprovalStore = defineStore('approval', () => {
  /* 从 localStorage 加载审批任务列表 */
  function loadTasks(): ApprovalTask[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        return JSON.parse(raw) as ApprovalTask[]
      }
    } catch (e) {
      console.error('[Approval] 加载任务列表失败:', e)
    }
    return []
  }

  /* 将任务列表保存到 localStorage */
  function saveTasks(tasks: ApprovalTask[]): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks))
    } catch (e) {
      console.error('[Approval] 保存任务列表失败:', e)
    }
  }

  /* 响应式任务列表 */
  const tasks = ref<ApprovalTask[]>(loadTasks())

  /* 添加待审批任务 */
  function addTask(task: Omit<ApprovalTask, 'status' | 'createdAt' | 'comment'>): void {
    // 避免重复添加相同 threadId 的任务
    const exists = tasks.value.find(t => t.threadId === task.threadId)
    if (exists) return

    const newTask: ApprovalTask = {
      ...task,
      status: 'pending',
      createdAt: Date.now(),
    }
    tasks.value.unshift(newTask)
    saveTasks(tasks.value)
  }

  /* 审批通过 */
  async function approveTask(threadId: string, comment?: string): Promise<void> {
    const task = tasks.value.find(t => t.threadId === threadId)
    if (!task) return

    try {
      await client.post('/approve', {
        task_id: threadId,
        action: 'approve',
        comment: comment || '',
      })

      task.status = 'approved'
      task.comment = comment
      saveTasks(tasks.value)
    } catch (e) {
      console.error('[Approval] 审批请求失败:', e)
      throw e
    }
  }

  /* 审批驳回 */
  async function rejectTask(threadId: string, comment?: string): Promise<void> {
    const task = tasks.value.find(t => t.threadId === threadId)
    if (!task) return

    try {
      await client.post('/approve', {
        task_id: threadId,
        action: 'reject',
        comment: comment || '',
      })

      task.status = 'rejected'
      task.comment = comment
      saveTasks(tasks.value)
    } catch (e) {
      console.error('[Approval] 驳回请求失败:', e)
      throw e
    }
  }

  /* 从列表中移除已完成的任务（已通过或已驳回） */
  function removeTask(threadId: string): void {
    const index = tasks.value.findIndex(t => t.threadId === threadId)
    if (index !== -1) {
      tasks.value.splice(index, 1)
      saveTasks(tasks.value)
    }
  }

  return {
    tasks,
    addTask,
    approveTask,
    rejectTask,
    removeTask,
  }
})
