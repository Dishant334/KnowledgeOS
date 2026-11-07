import { Navigate, Route, Routes } from 'react-router-dom'
import AuthLayout from './auth/AuthLayout'
import RequireAuth from './auth/RequireAuth'
import SignInPage from './auth/SignInPage'
import SignUpPage from './auth/SignUpPage'
import AppShell from './layout/AppShell'
import ThemeProvider from './theme/ThemeProvider'
import ChatLayout from './features/chat/ChatLayout'
import ComingSoonPage from './pages/ComingSoonPage'
import NotFoundPage from './pages/NotFoundPage'

// The route table. Sign-in and sign-up share the AuthLayout card; everything inside <RequireAuth> needs a login;
// everything inside <AppShell> gets the top bar.
export default function App() {
  return (
    <ThemeProvider className="h-full">
      <Routes>
        <Route element={<AuthLayout />}>
          <Route path="/sign-in/*" element={<SignInPage />} />
          <Route path="/sign-up/*" element={<SignUpPage />} />
        </Route>
  
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/chat" replace />} />
            <Route path="chat" element={<ChatLayout empty />} />
            <Route path="chat/:conversationId" element={<ChatLayout />} />
            <Route path="documents" element={<ComingSoonPage title="Documents" step={2} />} />
            <Route path="memory" element={<ComingSoonPage title="Memory" step={5} />} />
          </Route>
        </Route>
  
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </ThemeProvider>
  )
}
