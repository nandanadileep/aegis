import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Onboarding from './pages/Onboarding'
import Chat from './pages/Chat'
import Graph from './pages/Graph'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/onboarding" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/memory" element={<Graph />} />
      </Routes>
    </BrowserRouter>
  )
}
