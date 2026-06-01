import { create } from 'zustand'
import { getConfig, updateConfig as apiUpdateConfig } from '../api/client'

interface ConfigState {
  config: Record<string, any>
  loading: boolean
  saving: boolean
  fetchConfig: (module?: string) => Promise<void>
  updateConfig: (module: string, data: any) => Promise<void>
}

export const useConfigStore = create<ConfigState>((set) => ({
  config: {},
  loading: false,
  saving: false,
  fetchConfig: async (module) => {
    set({ loading: true })
    try {
      const data = await getConfig(module)
      set({ config: module ? { ...data } : data, loading: false })
    } catch (e: any) {
      set({ loading: false })
    }
  },
  updateConfig: async (module, data) => {
    set({ saving: true })
    try {
      await apiUpdateConfig(module, data)
      const freshData = await getConfig(module)
      set({ config: module ? { ...freshData } : freshData, saving: false })
    } catch (e: any) {
      set({ saving: false })
      throw e
    }
  },
}))
