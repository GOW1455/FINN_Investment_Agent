import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import Today from './Today.jsx'
import Research from './Research.jsx'
import Network from './Network.jsx'
import { PersonSheet } from './ui.jsx'
import './styles.css'

const TABS = [
  ['today', 'Today', <path d="M4 6h16M4 12h10M4 18h13" />],
  ['research', 'Research', <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5" /></>],
  ['network', 'Network', <><circle cx="6" cy="7" r="2.5" /><circle cx="18" cy="7" r="2.5" /><circle cx="12" cy="17" r="2.5" /><path d="M8 8.5l3 6.5M16 8.5l-3 6.5M8.5 7h7" /></>],
]

function App() {
  // Deep links: /?tab=research&symbol=KPITTECH or /?tab=network&person=p05
  const params = new URLSearchParams(window.location.search)
  const [tab, setTab] = useState(['today', 'research', 'network'].includes(params.get('tab')) ? params.get('tab') : 'today')
  const [symbol, setSymbol] = useState((params.get('symbol') || '').toUpperCase())
  const [person, setPerson] = useState(params.get('person'))
  const research = (target) => { setSymbol(target); setTab('research') }

  return (
    <>
      {/* All three stay mounted so a running debate or a scrolled feed survives a tab switch. */}
      <div hidden={tab !== 'today'}><Today onPerson={setPerson} onResearch={research} /></div>
      <div hidden={tab !== 'research'}><Research symbol={symbol} setSymbol={setSymbol} onPerson={setPerson} /></div>
      <div hidden={tab !== 'network'}><Network onPerson={setPerson} /></div>

      <nav className="tabbar" aria-label="Sections">
        {TABS.map(([key, label, icon]) => (
          <button key={key} className={tab === key ? 'on' : ''} onClick={() => { setTab(key); window.scrollTo(0, 0) }} aria-current={tab === key}>
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{icon}</svg>
            {label}
          </button>
        ))}
      </nav>
      {person && <PersonSheet id={person} onClose={() => setPerson(null)} />}
    </>
  )
}

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
