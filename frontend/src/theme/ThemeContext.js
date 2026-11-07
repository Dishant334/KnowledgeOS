import { createContext } from 'react'

// { theme: 'light' | 'dark', toggle() } — provided by ThemeProvider, read with useTheme().
export const ThemeContext = createContext({ theme: 'light', toggle: () => {} })
