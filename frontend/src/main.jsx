import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Apply saved theme before render to avoid flash
const saved = localStorage.getItem('aegis-theme') || 'dark'
document.documentElement.setAttribute('data-theme', saved)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
