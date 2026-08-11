import { useCallback, useEffect, useRef, useState } from 'react'
import guitar from '../assets/guitar-sticker.png'
import DynamicBackground from './DynamicBackground'

const KEYPAD_KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '0', '#']

const FRIENDLY_NAMES = {
  C_MAJOR: 'C Major', D_MINOR: 'D Minor', E_MINOR: 'E Minor', F_MAJOR: 'F Major',
  G_MAJOR: 'G Major', A_MINOR: 'A Minor', B_DIMINISHED: 'B Diminished',
  B_MINOR: 'B Minor', D_MAJOR: 'D Major', F_SHARP_DIMINISHED: 'F# Diminished',
  E_DIMINISHED: 'E Diminished', G_MINOR: 'G Minor', B_FLAT_MAJOR: 'B-flat Major',
  COUNTRY_ROADS: 'Country Roads', NEVER_A: 'Verse A', NEVER_B: 'Verse B',
  STAND_BY_ME: 'Stand By Me',
}

function friendly(value) {
  if (!value) return '—'
  return FRIENDLY_NAMES[value] ?? value.replaceAll('_', ' ')
}

function getWebSocketAddress() {
  if (import.meta.env.VITE_AIRFRET_WS_URL) {
    return import.meta.env.VITE_AIRFRET_WS_URL
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const hostname = window.location.hostname || 'localhost'
  return `${protocol}//${hostname}:8765`
}

export default function VisualizerPage() {
  const [connection, setConnection] = useState('disconnected')
  const [connectionMessage, setConnectionMessage] = useState('Network bridge disconnected')
  const [mode, setMode] = useState('NOTE')
  const [noteFx, setNoteFx] = useState('CLEAN')
  const [activeNote, setActiveNote] = useState('—')
  const [selectedScale, setSelectedScale] = useState('C_MAJOR')
  const [chord, setChord] = useState('C_MAJOR')
  const [effect, setEffect] = useState('WAH')
  const [volume, setVolume] = useState(50)
  const [strumDirection, setStrumDirection] = useState('DOWN')
  const [activeKey, setActiveKey] = useState(null)
  const [activeNav, setActiveNav] = useState(null)
  const [lastEvent, setLastEvent] = useState('Waiting for an AirFret input')
  const [gyroReverse, setGyroReverse] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const [pulse, setPulse] = useState(0)
  const [soundCount, setSoundCount] = useState(0)
  const [showBurst, setShowBurst] = useState(false)

  const socketRef = useRef(null)
  const soundSequenceRef = useRef(0)
  const noteTimerRef = useRef(null)
  const playingTimerRef = useRef(null)
  const keyTimerRef = useRef(null)
  const navTimerRef = useRef(null)

  const socketAddress = getWebSocketAddress()

  const triggerSoundVisual = useCallback((eventLabel, duration = 1600) => {
    soundSequenceRef.current += 1
    setSoundCount(soundSequenceRef.current)
    setPulse((value) => value + 1)
    setShowBurst(true)
    setIsPlaying(true)
    setLastEvent(eventLabel)

    clearTimeout(noteTimerRef.current)
    clearTimeout(playingTimerRef.current)
    noteTimerRef.current = setTimeout(() => setShowBurst(false), 920)
    if (duration !== null) {
      playingTimerRef.current = setTimeout(() => setIsPlaying(false), duration)
    }
  }, [])

  const flashKey = useCallback((key) => {
    setActiveKey(key)
    clearTimeout(keyTimerRef.current)
    keyTimerRef.current = setTimeout(() => setActiveKey(null), 420)
  }, [])

  const flashNavigation = useCallback((direction) => {
    setActiveNav(direction)
    clearTimeout(navTimerRef.current)
    navTimerRef.current = setTimeout(() => setActiveNav(null), 420)
  }, [])

  const handleAirFretLine = useCallback((line) => {
    const cleanLine = line.trim()
    if (!cleanLine.startsWith('AIRFRET|')) return

    const [, eventType, ...values] = cleanLine.split('|')
    const [first, second, third] = values

    switch (eventType) {
      case 'READY':
        setMode(first || 'NOTE')
        setConnectionMessage('AirFret ready — play something')
        setLastEvent('Pico connected and ready')
        break
      case 'MODE':
        setMode(first)
        setIsPlaying(false)
        setLastEvent(friendly(first) + ' mode selected')
        break
      case 'KEY':
        flashKey(first)
        setLastEvent('Key ' + first + ' pressed')
        break
      case 'NAV':
        flashNavigation(first)
        setLastEvent('Joystick ' + friendly(first).toLowerCase())
        break
      case 'NOTE_FX':
        setNoteFx(first)
        setLastEvent('Note effect: ' + friendly(first))
        break
      case 'NOTE_ON':
        setMode('NOTE')
        setActiveNote(first)
        setNoteFx(second || 'CLEAN')
        triggerSoundVisual(first + ' · ' + friendly(second || 'CLEAN'), null)
        break
      case 'NOTE_OFF':
        setActiveNote('—')
        setIsPlaying(false)
        setLastEvent(first + ' released')
        break
      case 'SCALE':
        setSelectedScale(first)
        setLastEvent('Scale: ' + friendly(first))
        break
      case 'CHORD':
        setChord(first)
        setLastEvent('Chord: ' + friendly(first))
        break
      case 'STRUM':
        setMode('CHORD')
        setStrumDirection(first)
        setChord(second)
        setSelectedScale(third)
        triggerSoundVisual(friendly(second) + ' · ' + friendly(first) + ' strum', 3200)
        break
      case 'EFFECT_SELECT':
        setEffect(first)
        setIsPlaying(false)
        setLastEvent('Effect selected: ' + friendly(first))
        break
      case 'EFFECT_PLAY':
        setMode('FX')
        setEffect(first)
        triggerSoundVisual(friendly(first) + ' effect', 1800)
        break
      case 'VOLUME':
        setVolume(Number(first))
        setLastEvent('Volume ' + first + '%')
        break
      case 'GYRO_REVERSE':
        setGyroReverse(first === 'ON')
        setLastEvent('Gyro reverse ' + first.toLowerCase())
        break
      case 'STOP':
        setIsPlaying(false)
        setActiveNote('—')
        setLastEvent('Audio stopped')
        break
      default:
        break
    }
  }, [flashKey, flashNavigation, triggerSoundVisual])

  function connectAirFret() {
    if (socketRef.current) return

    setConnection('connecting')
    setConnectionMessage('Connecting to the AirFret network bridge…')

    const socket = new WebSocket(socketAddress)
    socketRef.current = socket

    socket.addEventListener('open', () => {
      if (socketRef.current !== socket) return
      setConnection('connected')
      setConnectionMessage('Network connected — AirFret is live')
    })

    socket.addEventListener('message', (message) => {
      String(message.data).split(/\r?\n/).forEach(handleAirFretLine)
    })

    socket.addEventListener('error', () => {
      if (socketRef.current !== socket) return
      setConnection('error')
      setConnectionMessage('Could not reach the AirFret bridge')
    })

    socket.addEventListener('close', () => {
      if (socketRef.current !== socket) return
      socketRef.current = null
      setConnection('disconnected')
      setConnectionMessage('Network bridge disconnected')
      setIsPlaying(false)
    })
  }

  function disconnectAirFret() {
    const socket = socketRef.current
    socketRef.current = null
    if (socket) socket.close()
    setConnection('disconnected')
    setConnectionMessage('Network bridge disconnected')
    setIsPlaying(false)
  }

  function runDemo() {
    const nextCount = soundSequenceRef.current + 1
    const demoModes = ['CHORD', 'NOTE', 'FX']
    const nextMode = demoModes[(nextCount - 1) % demoModes.length]

    if (nextMode === 'CHORD') {
      const chords = ['C_MAJOR', 'G_MAJOR', 'A_MINOR', 'F_MAJOR']
      const nextChord = chords[(nextCount - 1) % chords.length]
      const direction = nextCount % 2 === 0 ? 'UP' : 'DOWN'
      setMode('CHORD')
      setChord(nextChord)
      setStrumDirection(direction)
      flashNavigation(nextCount % 2 === 0 ? 'LEFT' : 'RIGHT')
      triggerSoundVisual(friendly(nextChord) + ' · ' + direction + ' demo strum', 2600)
      return
    }

    if (nextMode === 'NOTE') {
      const notes = ['C4', 'E4', 'G4', 'C5']
      const effects = ['CLEAN', 'OCTAVE', 'SYNTH']
      const note = notes[(nextCount - 1) % notes.length]
      const noteEffect = effects[(nextCount - 1) % effects.length]
      setMode('NOTE')
      setActiveNote(note)
      setNoteFx(noteEffect)
      flashKey(String(((nextCount - 1) % 8) + 1))
      triggerSoundVisual(note + ' · ' + noteEffect + ' demo note', 1900)
      return
    }

    const effects = ['WAH', 'PLUCK', 'WHIP']
    const nextEffect = effects[(nextCount - 1) % effects.length]
    setMode('FX')
    setEffect(nextEffect)
    flashNavigation('PRESS')
    triggerSoundVisual(nextEffect + ' demo effect', 1900)
  }

  useEffect(() => () => {
    clearTimeout(noteTimerRef.current)
    clearTimeout(playingTimerRef.current)
    clearTimeout(keyTimerRef.current)
    clearTimeout(navTimerRef.current)
    const socket = socketRef.current
    socketRef.current = null
    if (socket) socket.close()
  }, [])

  const visibleValue = mode === 'NOTE'
    ? activeNote === '—' ? noteFx : activeNote
    : mode === 'FX' ? effect : friendly(chord)

  return (
    <div className={'visualizerPage mode' + mode}>
      <DynamicBackground mode={mode} playing={isPlaying} pulse={pulse} />
      <div className="stageAurora" aria-hidden="true" />
      <div className="gridFloor" aria-hidden="true" />

      <header className="siteHeader visualizerHeader">
        <a className="brand stageBrand" href="#/">
          <span className="brandMark">T7</span>
          <span>Team 7 <b>Frequencies</b></span>
        </a>
        <nav aria-label="Main navigation">
          <a className="stageHomeLink" href="#/">← Home</a>
          <span className="stagePageLabel"><span className="liveDot" /> Live Stage</span>
        </nav>
      </header>

      <main className="stageContent">
        <section className="stageIntro">
          <div><p>REAL-TIME AIRFRET SIGNAL</p><h1>Turn motion into a performance.</h1></div>
          <div className="connectionCluster">
            <div className="connectionCopy">
              <span className={'statusDot ' + connection} />
              <span><small>INSTRUMENT STATUS</small><strong>{connectionMessage}</strong></span>
            </div>
            <button
              type="button"
              className="connectButton"
              onClick={connection === 'connected' ? disconnectAirFret : connectAirFret}
              disabled={connection === 'connecting'}
            >
              {connection === 'connected' ? 'Disconnect' : connection === 'connecting' ? 'Connecting…' : 'Connect live signal'}
            </button>
          </div>
        </section>

        <p className="serialNotice">
          Network feed: <code>{socketAddress}</code> · Demo mode remains available without the instrument.
        </p>

        <section className={'performanceDeck ' + (isPlaying ? 'isPlaying' : 'isIdle')}>
          <div className="deckTopline"><span>CH 07 / AIRFRET</span><span>{isPlaying ? 'SIGNAL DETECTED' : 'STANDBY'}</span><span>22.05 kHz</span></div>
          <div className="deckDisplay">
            <div className="guitarEmitter emitterLeft"><img src={guitar} alt="" /></div>
            <div className="guitarEmitter emitterRight"><img src={guitar} alt="" /></div>

            {showBurst && (
              <div className="stageNoteBurst" key={pulse} aria-hidden="true">
                <span className="stageNote stageNoteOne">♪</span><span className="stageNote stageNoteTwo">♫</span>
                <span className="stageNote stageNoteThree">♩</span><span className="stageNote stageNoteFour">♪</span>
                <span className="stageNote stageNoteFive">♫</span><span className="stageNote stageNoteSix">♩</span>
              </div>
            )}

            <div className="primaryReadout"><span>{mode} MODE</span><strong>{visibleValue}</strong><p>{lastEvent}</p></div>
            <svg className="stageWaveform" viewBox="0 0 1000 260" preserveAspectRatio="none" role="img" aria-label={isPlaying ? 'AirFret sound signal active' : 'AirFret signal idle'}>
              <path className="stageWaveGrid" d="M0 130 H1000 M0 65 H1000 M0 195 H1000" />
              <path className="stageWaveGlow" d="M0 130 C34 130 38 54 72 130 S110 206 144 130 S182 25 216 130 S254 235 288 130 S326 70 360 130 S398 190 432 130 S470 14 504 130 S542 246 576 130 S614 50 648 130 S686 210 720 130 S758 33 792 130 S830 227 864 130 S902 82 936 130 S975 130 1000 130" />
              <path className="stageWaveLine" d="M0 130 C34 130 38 54 72 130 S110 206 144 130 S182 25 216 130 S254 235 288 130 S326 70 360 130 S398 190 432 130 S470 14 504 130 S542 246 576 130 S614 50 648 130 S686 210 720 130 S758 33 792 130 S830 227 864 130 S902 82 936 130 S975 130 1000 130" />
            </svg>
            <div className="stageEqualizer" aria-hidden="true">
              {Array.from({ length: 30 }, (_, index) => <span key={index} style={{ '--bar-index': index, '--bar-level': 25 + ((index * 37) % 72) + '%' }} />)}
            </div>
          </div>
          <div className="deckBottomline"><span>INPUT {String(soundCount).padStart(3, '0')}</span><button type="button" onClick={runDemo}>Trigger demo signal</button><span>{strumDirection} MOTION</span></div>
        </section>

        <section className="stageControls">
          <article className="stageControlCard">
            <div className="controlHeading"><span>01</span><div><p>JOYSTICK MAP</p><h2>Navigate the sound</h2></div></div>
            <div className="stageJoystick" aria-label="Joystick input display">
              <span className="inactiveControl">UP</span><span className={activeNav === 'LEFT' ? 'activeControl' : ''}>LEFT</span>
              <span className={'stickCenter ' + (activeNav === 'PRESS' ? 'activeControl' : '')}>PRESS</span>
              <span className={activeNav === 'RIGHT' ? 'activeControl' : ''}>RIGHT</span><span className="inactiveControl">DOWN</span>
            </div>
            <p className="cardHelp">Left and right select. Press enters or plays performance FX.</p>
          </article>

          <article className="stageControlCard">
            <div className="controlHeading"><span>02</span><div><p>KEYPAD MAP</p><h2>Choose the mode</h2></div></div>
            <div className="stageKeypad" aria-label="Keypad input display">
              {KEYPAD_KEYS.map((key) => <span className={activeKey === key ? 'activeControl' : ''} key={key}>{key}</span>)}
            </div>
            <p className="cardHelp">1–8 play/select · 0 stops · * note mode · # chord mode</p>
          </article>

          <article className="stageControlCard stateCard">
            <div className="controlHeading"><span>03</span><div><p>LIVE STATE</p><h2>Instrument telemetry</h2></div></div>
            <dl className="stageReadouts">
              <div><dt>Mode</dt><dd>{mode}</dd></div><div><dt>Chord</dt><dd>{friendly(chord)}</dd></div>
              <div><dt>Scale</dt><dd>{friendly(selectedScale)}</dd></div><div><dt>Note FX</dt><dd>{friendly(noteFx)}</dd></div>
              <div><dt>Perf. FX</dt><dd>{friendly(effect)}</dd></div><div><dt>Gyro</dt><dd>{strumDirection}{gyroReverse ? ' · REV' : ''}</dd></div>
            </dl>
            <div className="stageVolume"><span>VOLUME</span><div><span style={{ width: volume + '%' }} /></div><strong>{volume}%</strong></div>
          </article>
        </section>
      </main>

      <footer className="stageFooter"><span>AIRFRET VISUAL ENGINE</span><span>TEAM 7 FREQUENCIES · 2026</span></footer>
    </div>
  )
}
