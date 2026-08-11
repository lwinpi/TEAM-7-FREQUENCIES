import { useEffect, useState } from 'react'
import HomePage from './components/HomePage'
import VisualizerPage from './components/VisualizerPage'
import './App.css'

function currentRoute() {
  return window.location.hash === '#/visualizer' ? 'visualizer' : 'home'
}

function App() {
  const [route, setRoute] = useState(currentRoute)

  useEffect(() => {
    function handleRouteChange() {
      setRoute(currentRoute())
      window.scrollTo({ top: 0, behavior: 'auto' })
    }

    window.addEventListener('hashchange', handleRouteChange)
    return () => window.removeEventListener('hashchange', handleRouteChange)
  }, [])

  return route === 'visualizer' ? <VisualizerPage /> : <HomePage />
}

export default App
