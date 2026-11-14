import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

const Experience = lazy(() => import('./experience/Experience'))
const App = lazy(() => import('./App.tsx'))
const isConsole = window.location.pathname.startsWith('/console')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={<div style={{ minHeight: '100vh', background: '#050d0f' }} />}>
      {isConsole ? <App /> : <Experience />}
    </Suspense>
  </StrictMode>,
)
