import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Onboarding from './pages/Onboarding'
import Chat from './pages/Chat'
import Graph from './pages/Graph'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/memory" element={<Graph />} />
      </Routes>
    </BrowserRouter>
  )
}
