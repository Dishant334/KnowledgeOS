import { api } from './client'

// The backend's document routes. A document looks like:
// { id, filename, mime_type, file_size, status: 'pending'|'processing'|'ready'|'failed', created_at, updated_at,
//   failure_reason: null | "a friendly reason (only when failed)" }

// Upload one file (multipart). onProgress(fraction 0..1) follows the bytes sent. No timeout: a 20 MB file on a slow
// connection can take longer than the client's default 30 s. Returns the document (an existing one if you already
// uploaded the same file: the backend de-duplicates per user).
export async function uploadDocument(file, { onProgress, signal } = {}) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/documents', form, {
    timeout: 0,
    signal,
    onUploadProgress: (event) => {
      if (event.total) onProgress?.(event.loaded / event.total)
    },
  })
  return data
}

// All your documents, newest first.
export async function listDocuments() {
  const { data } = await api.get('/documents')
  return data
}

export async function getDocument(id) {
  const { data } = await api.get(`/documents/${id}`)
  return data
}

// Deletes the file, its text chunks and its search vectors.
export async function deleteDocument(id) {
  await api.delete(`/documents/${id}`)
}
