import { create } from 'zustand'
import { getStatus, startService, stopService, restartService } from '../api/client'

interface ServiceState {
  status: { running: boolean; pid: number | null; uptime: number | null; ready: boolean } | null
  loading: boolean
  startError: string | null
  fetchStatus: () => Promise<void>
  start: () => Promise<void>
  stop: () => Promise<void>
  restart: () => Promise<void>
}

export const useServiceStore = create<ServiceState>((set) => ({
  status: null,
  loading: false,
  startError: null,
  fetchStatus: async () => {
    try {
      const data = await getStatus()
      set({ status: data })
    } catch {
      set({ status: { running: false, pid: null, uptime: null, ready: false } })
    }
  },
  start: async () => {
    set({ loading: true, startError: null })
    try {
      await startService()
      set({ loading: false })
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || '启动失败'
      set({ loading: false, startError: detail })
      throw e
    }
  },
  stop: async () => {
    set({ loading: true, startError: null })
    await stopService()
    set({ loading: false })
  },
  restart: async () => {
    set({ loading: true, startError: null })
    await restartService()
    set({ loading: false })
  },
}))
