import { useState, useCallback } from 'react'

export function useEditMode() {
  const [editing, setEditing] = useState(false)
  const startEdit = useCallback(() => setEditing(true), [])
  const cancelEdit = useCallback(() => setEditing(false), [])
  const saveAndExit = useCallback(async (saveFn: () => Promise<void>) => {
    await saveFn()
    setEditing(false)
  }, [])
  return { editing, startEdit, cancelEdit, saveAndExit }
}
