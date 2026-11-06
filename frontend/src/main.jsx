import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import ClerkWithRouter from './auth/ClerkWithRouter.jsx'
import { CLERK_PUBLISHABLE_KEY } from './lib/constants'
import MissingConfigPage from './pages/MissingConfigPage.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {CLERK_PUBLISHABLE_KEY ? (
      <BrowserRouter>
        <ClerkWithRouter>
          <App />
        </ClerkWithRouter>
      </BrowserRouter>
    ) : (
      <MissingConfigPage />
    )}
  </StrictMode>,
)
