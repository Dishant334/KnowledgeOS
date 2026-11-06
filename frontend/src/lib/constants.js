// Settings that come from frontend/.env (see .env.example). Vite only exposes names that start with VITE_.

// Where the backend API runs.
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Clerk's publishable key (safe to ship to a browser). Empty = the app shows a setup message.
export const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || ''
