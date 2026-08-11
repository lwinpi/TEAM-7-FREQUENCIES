import { useEffect, useRef } from 'react'

const COLORS = {
  NOTE: [56, 232, 255],
  CHORD: [255, 204, 74],
  FX: [255, 79, 198],
}

export default function DynamicBackground({ mode, playing, pulse }) {
  const canvasRef = useRef(null)
  const modeRef = useRef(mode)
  const playingRef = useRef(playing)
  const burstsRef = useRef([])

  useEffect(() => {
    modeRef.current = mode
    playingRef.current = playing
  }, [mode, playing])

  useEffect(() => {
    if (!pulse) return
    burstsRef.current.push({
      x: 0.32 + Math.random() * 0.36,
      y: 0.22 + Math.random() * 0.4,
      age: 0,
    })
  }, [pulse])

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context) return undefined

    let width = 0
    let height = 0
    let frame = 0
    let animationFrame = 0
    const particles = Array.from({ length: 68 }, () => ({
      x: Math.random(),
      y: Math.random(),
      vx: (Math.random() - 0.5) * 0.00055,
      vy: (Math.random() - 0.5) * 0.00055,
      radius: 0.7 + Math.random() * 2.1,
      phase: Math.random() * Math.PI * 2,
    }))

    function resize() {
      const bounds = canvas.getBoundingClientRect()
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      width = bounds.width
      height = bounds.height
      canvas.width = Math.max(1, Math.floor(width * ratio))
      canvas.height = Math.max(1, Math.floor(height * ratio))
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
    }

    function draw() {
      frame += 1
      context.clearRect(0, 0, width, height)

      const [red, green, blue] = COLORS[modeRef.current] ?? COLORS.NOTE
      const energy = playingRef.current ? 1 : 0.08
      const speed = 1 + energy * 5
      const glow = context.createRadialGradient(
        width * 0.5,
        height * 0.34,
        0,
        width * 0.5,
        height * 0.34,
        Math.max(width, height) * 0.62,
      )

      glow.addColorStop(0, `rgba(${red}, ${green}, ${blue}, ${0.07 + energy * 0.12})`)
      glow.addColorStop(1, 'rgba(0, 0, 0, 0)')
      context.fillStyle = glow
      context.fillRect(0, 0, width, height)

      particles.forEach((particle, first) => {
        particle.x += particle.vx * speed
        particle.y += particle.vy * speed
        if (particle.x < -0.03) particle.x = 1.03
        if (particle.x > 1.03) particle.x = -0.03
        if (particle.y < -0.03) particle.y = 1.03
        if (particle.y > 1.03) particle.y = -0.03

        const x = particle.x * width
        const y = particle.y * height
        const shimmer = 0.35 + Math.sin(frame * 0.025 + particle.phase) * 0.2
        context.beginPath()
        context.arc(x, y, particle.radius + energy * 0.7, 0, Math.PI * 2)
        context.fillStyle = `rgba(${red}, ${green}, ${blue}, ${shimmer})`
        context.fill()

        for (let second = first + 1; second < particles.length; second += 1) {
          const neighbor = particles[second]
          const dx = (neighbor.x - particle.x) * width
          const dy = (neighbor.y - particle.y) * height
          const distance = Math.sqrt(dx * dx + dy * dy)
          if (distance >= 105) continue
          context.beginPath()
          context.moveTo(x, y)
          context.lineTo(neighbor.x * width, neighbor.y * height)
          context.strokeStyle = `rgba(${red}, ${green}, ${blue}, ${(1 - distance / 105) * (0.04 + energy * 0.08)})`
          context.lineWidth = 0.7
          context.stroke()
        }
      })

      burstsRef.current = burstsRef.current.filter((burst) => burst.age < 1)
      burstsRef.current.forEach((burst) => {
        burst.age += 0.018
        const radius = 20 + burst.age * Math.min(width, height) * 0.55
        context.beginPath()
        context.arc(burst.x * width, burst.y * height, radius, 0, Math.PI * 2)
        context.strokeStyle = `rgba(${red}, ${green}, ${blue}, ${0.55 * (1 - burst.age)})`
        context.lineWidth = 1.5 + (1 - burst.age) * 2.5
        context.stroke()
      })

      animationFrame = requestAnimationFrame(draw)
    }

    resize()
    window.addEventListener('resize', resize)
    animationFrame = requestAnimationFrame(draw)

    return () => {
      window.removeEventListener('resize', resize)
      cancelAnimationFrame(animationFrame)
    }
  }, [])

  return <canvas className="dynamicCanvas" ref={canvasRef} aria-hidden="true" />
}
