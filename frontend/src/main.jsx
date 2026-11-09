import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@fontsource-variable/fraunces' // the serif used for headings and the wordmark (font-display)
import './index.css'
import App from './App.jsx'
import ClerkWithRouter from './auth/ClerkWithRouter.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import { CLERK_PUBLISHABLE_KEY } from './lib/constants'
import MissingConfigPage from './pages/MissingConfigPage.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      {CLERK_PUBLISHABLE_KEY ? (
        <BrowserRouter>
          <ClerkWithRouter>
            <App />
          </ClerkWithRouter>
        </BrowserRouter>
      ) : (
        <MissingConfigPage />
      )}
    </ErrorBoundary>
  </StrictMode>,
)
