import { api } from './client'

// Long-term memory: short facts about you that every conversation can use as background.
// A fact: { id, text, created_at, source_conversation_id } (source = the chat it was learned from; null if you added it).

export const MAX_MEMORIES = 15 // the backend refuses more (409)
export const MAX_MEMORY_CHARS = 200

export async function listMemories() {
  const { data } = await api.get('/memory')
  return data
}

// The backend refuses (422) text that is empty, looks sensitive (passwords, card numbers...) or looks like an
// instruction to the assistant; its reason comes back as the error message.
export async function addMemory(text) {
  const { data } = await api.post('/memory', { text })
  return data
}

export async function deleteMemory(id) {
  await api.delete(`/memory/${encodeURIComponent(id)}`)
}

export async function forgetEverything() {
  await api.delete('/memory')
}
