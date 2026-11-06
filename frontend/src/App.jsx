import { Navigate, Route, Routes } from 'react-router-dom'
import RequireAuth from './auth/RequireAuth'
import SignInPage from './auth/SignInPage'
import SignUpPage from './auth/SignUpPage'
import AppShell from './layout/AppShell'
import AccountCheckPage from './pages/AccountCheckPage'
import ComingSoonPage from './pages/ComingSoonPage'
import NotFoundPage from './pages/NotFoundPage'

// The route table. Everything inside <RequireAuth> needs a login; everything inside <AppShell> gets the top bar.
export default function App() {
  return (
    <Routes>
      <Route path="/sign-in/*" element={<SignInPage />} />
      <Route path="/sign-up/*" element={<SignUpPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/chat" replace />} />
          <Route path="chat" element={<AccountCheckPage />} />
          <Route path="chat/:conversationId" element={<ComingSoonPage title="Chat" step={3} />} />
          <Route path="documents" element={<ComingSoonPage title="Documents" step={2} />} />
          <Route path="memory" element={<ComingSoonPage title="Memory" step={5} />} />
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
