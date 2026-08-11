import { useEffect, useRef, useState } from 'react'
import jazz from '../assets/teamsevenfreq.png'
import teamphoto from '../assets/teamphoto.jpg'
import paperBackground from '../assets/sheet-music-texture.jpg'
import guitar from '../assets/guitar-sticker.png'
import musicalNote from '../assets/musical-note.webp'
import musicNoteSmall from '../assets/nicubunu_Musical_note.webp'
import newTeamPhoto from '../assets/team-photo-new.jpg'
import prototypePhoto from '../assets/prototype.jpg'
import performanceVideo from '../assets/team7-performance.mp4'

const MEMBERS = [
  {
    name: 'Alejandro Villalta',
    position: 'Top Left',
    intro:
      'Electrical engineering Pre Ops participant from El Camino College. My favorite hobbies are cooking and going to the gym.',
  },
  {
    name: 'Isaac Adegboye',
    position: 'Top Right',
    intro:
      'Incoming Mechanical Engineering transfer from LA Trade Tech College. My favorite hobbies are archery, cars, soccer, and working out.',
  },
  {
    name: 'Htet Lwin',
    position: 'Bottom Left',
    intro:
      'Incoming Computer Engineering transfer from College of San Mateo. My favorite hobbies are music, soccer, and watching horror films.',
  },
  {
    name: 'Sebastian Ruesta',
    position: 'Bottom Right',
    intro:
      'Electrical engineering Pre Ops participant from Pierce College. My favorite hobby is playing video games.',
  },
]

export default function HomePage() {
  const [noteBurst, setNoteBurst] = useState(0)
  const [showNotes, setShowNotes] = useState(false)
  const timerRef = useRef(null)

  function playDemo() {
    setNoteBurst((value) => value + 1)
    setShowNotes(true)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setShowNotes(false), 850)
  }

  useEffect(() => () => clearTimeout(timerRef.current), [])

  return (
    <div
      className="homePage"
      style={{ backgroundImage: `linear-gradient(rgba(226, 196, 142, .88), rgba(238, 216, 174, .91)), url(${paperBackground})` }}
    >
      <div className="homeGrain" aria-hidden="true" />
      <header className="siteHeader homeHeader">
        <a className="brand" href="#/">
          <span className="brandMark">T7</span>
          <span>Team 7 <b>Frequencies</b></span>
        </a>
        <nav aria-label="Main navigation">
          <a className="navLink active" href="#/">Home</a>
          <a className="stageNavLink" href="#/visualizer">
            <span className="liveDot" /> Live Visualizer
          </a>
        </nav>
      </header>

      <main>
        <section className="homeHero">
          <div className="heroCopy">
            <p className="homeKicker"><span /> UCLA HAcK · TEAM 7</p>
            <h1>Battle of The <em>BUILDS!</em></h1>
            <img
  src={newTeamPhoto}
  className="newTeamPhoto"
  alt="Team 7 at UCLA"
/>
<div className="prototypeSection">
  <h2>Our Prototype</h2>

  <img
    src={prototypePhoto}
    className="prototypePhoto"
    alt="Team 7 instrument prototype"
  />
</div>
<div className="performanceSection">
  <h2>Our Performance</h2>

  <video
    className="performanceVideo"
    controls
    playsInline
    preload="metadata"
  >
    <source src={performanceVideo} type="video/mp4" />
    Your browser does not support videos.
  </video>
</div>
            <p className="heroSummary">
              AirFret is our motion-controlled digital instrument. A joystick
              chooses the sound, a gyro reads the strum, and our live stage turns
              every input into a visual performance.
            </p>
            <div className="heroActions">
              <a className="primaryCta" href="#/visualizer">
                Enter the live stage <span aria-hidden="true">↗</span>
              </a>
              <button className="homeDemoButton" onClick={playDemo} type="button">
                Guitar noise {noteBurst}
              </button>
            </div>
            <div className="heroStats" aria-label="Project highlights">
              <div><strong>03</strong><span>Sound modes</span></div>
              <div><strong>08</strong><span>Playable notes</span></div>
              <div><strong>LIVE</strong><span>Motion response</span></div>
            </div>
          </div>

          <div className="homeArtStage">
            <div className="artOrbit orbitOne" aria-hidden="true" />
            <div className="artOrbit orbitTwo" aria-hidden="true" />
            <img className="homeGuitar homeGuitarLeft" src={guitar} alt="" />
            <img className="teamArtwork" src={jazz} alt="Team 7 Frequencies artwork" />
            <img className="homeGuitar homeGuitarRight" src={guitar} alt="" />

            {showNotes && (
              <div className="homeNoteBurst" key={noteBurst} aria-hidden="true">
                <img className="burstNote noteA" src={musicalNote} alt="" />
                <img className="burstNote noteB" src={musicNoteSmall} alt="" />
                <img className="burstNote noteC" src={musicalNote} alt="" />
                <img className="burstNote noteD" src={musicNoteSmall} alt="" />
              </div>
            )}
            <p className="artCaption"><span>●</span> MOTION → MUSIC → LIGHT</p>
          </div>
        </section>

        <section className="projectStrip" aria-label="How AirFret works">
          <article><span>01</span><div><h2>Choose</h2><p>Navigate notes, chords, and effects with the joystick and keypad.</p></div></article>
          <article><span>02</span><div><h2>Move</h2><p>The MPU6050 reads a real wrist strum and triggers the instrument.</p></div></article>
          <article><span>03</span><div><h2>Perform</h2><p>The website turns every unique input into a different live visual.</p></div></article>
        </section>

        <section className="teamStory">
          <div className="sectionHeading">
            <p>MEET THE BUILDERS</p>
            <h2>Four disciplines. One instrument.</h2>
          </div>
          <div className="teamLayout">
            <div className="teamPhotoWrap">
              <img className="teamPhoto" src={teamphoto} alt="The Team 7 Frequencies group" />
              <span>07</span>
            </div>
            <div className="memberList">
              {MEMBERS.map((member, index) => (
                <article className="memberCard" key={member.name}>
                  <span className="memberNumber">0{index + 1}</span>
                  <div>
                    <p>{member.position}</p>
                    <h3>{member.name}</h3>
                    <span>{member.intro}</span>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="stageInvitation">
          <div><p>THE INSTRUMENT IS READY</p><h2>See AirFret come alive.</h2></div>
          <a className="primaryCta darkCta" href="#/visualizer">Open visualizer <span>→</span></a>
        </section>
      </main>

      <footer className="homeFooter">
        <span>TEAM 7 FREQUENCIES</span>
        <span>ENGINEERED WITH MOTION · 2026</span>
      </footer>
    </div>
  )
}
