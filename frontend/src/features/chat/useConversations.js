import { useCallback, useEffect, useState } from 'react'
import { deleteConversation, listConversations, renameConversation } from '../../api/conversations'

// The sidebar's conversation list. Loaded once, then refreshed after every saved answer (`refresh`), so a new chat
// appears and the active one moves to the top. Rename is shown at once and undone if the backend refuses;
// delete removes the row only after the backend confirms.
export function useConversations() {
  const [conversations, setConversations] = useState(null) // null = still loading
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      setConversations(await listConversations())
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    let alive = true
    listConversations().then(
      (list) => {
        if (!alive) return
        setConversations(list)
        setError(null)
      },
      (e) => alive && setError(e.message),
    )
    return () => {
      alive = false
    }
  }, [])

  const rename = useCallback(async (id, title) => {
    let before = null
    setConversations((all) =>
      all?.map((c) => {
        if (c.id !== id) return c
        before = c.title
        return { ...c, title }
      }),
    )
    try {
      const saved = await renameConversation(id, title)
      setConversations((all) => all?.map((c) => (c.id === id ? { ...c, title: saved.title } : c)))
    } catch (e) {
      setConversations((all) => all?.map((c) => (c.id === id ? { ...c, title: before } : c)))
      throw e
    }
  }, [])

  const remove = useCallback(async (id) => {
    try {
      await deleteConversation(id)
    } catch (e) {
      if (e.code !== 'not_found') throw e // already gone: just drop the row
    }
    setConversations((all) => all?.filter((c) => c.id !== id))
  }, [])

  return { conversations, error, refresh, rename, remove }
}
