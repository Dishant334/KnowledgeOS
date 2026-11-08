import { Navigate, Route, Routes } from 'react-router-dom'
import AuthLayout from './auth/AuthLayout'
import RequireAuth from './auth/RequireAuth'
import SignInPage from './auth/SignInPage'
import SignUpPage from './auth/SignUpPage'
import AppShell from './layout/AppShell'
import ThemeProvider from './theme/ThemeProvider'
import ChatLayout from './features/chat/ChatLayout'
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
            <Route path="chat" element={<ChatLayout />} />
            <Route path="chat/:conversationId" element={<ChatLayout />} />
            {/* documents live in each chat (chips) and memory in a dialog: old addresses go to the chat */}
            <Route path="documents" element={<Navigate to="/chat" replace />} />
            <Route path="memory" element={<Navigate to="/chat" replace />} />
          </Route>
        </Route>
  
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </ThemeProvider>
  )
}
