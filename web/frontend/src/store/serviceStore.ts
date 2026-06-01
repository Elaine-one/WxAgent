import { create } from 'zustand'
import { getStatus, startService, stopService, restartService } from '../api/client'

interface ServiceState {
  status: { running: boolean; pid: number | null; uptime: number | null } | null
  loading: boolean
  fetchStatus: () => Promise<void>
  start: () => Promise<void>
  stop: () => Promise<void>
  restart: () => Promise<void>
}

export const useServiceStore = create<ServiceState>((set) => ({
  status: null,
  loading: false,
  fetchStatus: async () => {
    try {
      const data = await getStatus()
      set({ status: data })
    } catch {
      set({ status: { running: false, pid: null, uptime: null } })
    }
  },
  start: async () => {
    set({ loading: true })
    await startService()
    set({ loading: false })
  },
  stop: async () => {
    set({ loading: true })
    await stopService()
    set({ loading: false })
  },
  restart: async () => {
    set({ loading: true })
    await restartService()
    set({ loading: false })
  },
}))
