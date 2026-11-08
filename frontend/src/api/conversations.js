import { api, peekAuthToken } from './client'

// The sidebar list: your conversations that have at least one message, most recently active first.
// Each row: { id, title, created_at, last_message_at, message_count }.
export async function listConversations() {
  const { data } = await api.get('/conversations', { params: { limit: 100 } })
  return data
}

// New title (trimmed by the backend, 1-255 characters). Returns the updated row.
export async function renameConversation(conversationId, title) {
  const { data } = await api.patch(`/conversations/${conversationId}`, { title })
  return data
}

// Deletes the conversation and its messages. Its documents stay in your library.
export async function deleteConversation(conversationId) {
  await api.delete(`/conversations/${conversationId}`)
}

// A new, empty conversation: { id, title: null, created_at, last_message_at, message_count: 0 }.
// It is not listed until it has a message.
export async function createConversation() {
  const { data } = await api.post('/conversations')
  return data
}

// One conversation with all its messages (oldest first), each answer with its saved citations.
export async function getConversation(conversationId) {
  const { data } = await api.get(`/conversations/${conversationId}`)
  return data
}

// The documents attached to a conversation (its questions search only these).
export async function listConversationDocuments(conversationId) {
  const { data } = await api.get(`/conversations/${conversationId}/documents`)
  return data
}

// "I left this chat without asking anything": the backend deletes it together with the files uploaded only into it.
// It refuses (409) once the chat has a message, so a late call can never delete a real conversation.
export async function discardConversation(conversationId) {
  await api.post(`/conversations/${conversationId}/discard`)
}

// The same while the page is closing: a normal request would be cancelled, so this uses fetch with keepalive and the
// most recent token (no time to ask Clerk for a fresh one). If it does not get through, the backend's sweep removes
// the empty chat later.
export function discardConversationOnExit(conversationId) {
  const token = peekAuthToken()
  if (!token) return
  // same base address as every other call; a failure is ignored (the sweep tidies up later)
  fetch(`${api.defaults.baseURL}/conversations/${conversationId}/discard`, {
    method: 'POST',
    keepalive: true,
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => {})
}

// "I am leaving this chat": the backend learns what matters about you from its new messages (one LLM call, in the
// background) and merges it into your long-term memory. Nothing new -> nothing happens. Errors are ignored.
export function rememberConversation(conversationId) {
  api.post(`/conversations/${conversationId}/remember`).catch(() => {})
}

// The same while the page is closing (fetch keepalive with the last token, like discardConversationOnExit).
export function rememberConversationOnExit(conversationId) {
  const token = peekAuthToken()
  if (!token) return
  fetch(`${api.defaults.baseURL}/conversations/${conversationId}/remember`, {
    method: 'POST',
    keepalive: true,
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => {})
}
