import { api } from './client'

// The signed-in user as the backend knows them: { id, clerk_user_id, email, name, created_at, updated_at }.
export async function getMe() {
  const { data } = await api.get('/users/me')
  return data
}
