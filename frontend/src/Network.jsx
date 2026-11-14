import { useEffect, useState } from 'react'
import { ago, api, Avatar, NETWORK_CHANGED, PersonRow, Spinner } from './ui.jsx'
import AddContact from './AddContact.jsx'

const PROMPTS = ['Who do I know at Asian Paints?', 'specialty chemicals', 'rural lending', 'semiconductors', 'Who can explain HDFC Bank?', 'governance']

export default function Network({ onPerson }) {
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState(null)
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState('')
  const [people, setPeople] = useState(null)
  const [nudges, setNudges] = useState(null)
  const [sort, setSort] = useState('cold')
  const [adding, setAdding] = useState(false)
  const loadPeople = () => api('/network/people').then(setPeople).catch((e) => setError(e.message))
  useEffect(() => {
    window.addEventListener(NETWORK_CHANGED, loadPeople)
    return () => window.removeEventListener(NETWORK_CHANGED, loadPeople)
  }, [])

  useEffect(() => {
    loadPeople()
    api('/push/digest?hours=168').then((d) => setNudges(d.nudges)).catch(() => setNudges([]))
  }, [])

  const ask = (text) => {
    const q = text.trim()
    if (q.length < 2) return
    setQuery(q); setAsking(true); setError('')
    api(`/network/ask?q=${encodeURIComponent(q)}`).then(setAnswer).catch((e) => setError(e.message)).finally(() => setAsking(false))
  }

  const sorted = [...(people?.people || [])].sort((a, b) =>
    sort === 'cold' ? (b.days_since_contact ?? 0) - (a.days_since_contact ?? 0)
      : sort === 'close' ? b.strength - a.strength || a.name.localeCompare(b.name)
        : a.name.localeCompare(b.name))

  return (
    <main className="screen">
      <header className="masthead">
        <div>
          <div className="kicker">Your network · private to you</div>
          <h1>Who can help me understand this?</h1>
        </div>
      </header>

      <form className="ask" onSubmit={(e) => { e.preventDefault(); ask(query) }}>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="A company, a person or a theme" aria-label="Ask your network" />
        <button type="submit">Ask</button>
      </form>
      <div className="chips scroll">
        {PROMPTS.map((p) => <button key={p} onClick={() => ask(p)}>{p}</button>)}
      </div>

      {asking && <Spinner label="Looking through your network" />}
      {error && <p className="error">{error}</p>}
      {answer && !asking && (
        <section className="answer">
          <h2 className="section">{answer.title}</h2>
          {answer.results.length === 0 && <p className="muted">Try a company in your portfolio, a sector, or a past employer.</p>}
          {answer.results.map((p) => <PersonRow key={p.id} person={p} onOpen={onPerson} />)}
        </section>
      )}

      {nudges?.length > 0 && (
        <section>
          <h2 className="section">A reason to reconnect <span>this week</span></h2>
          {nudges.map((n) => (
            <button className="nudge" key={n.id} onClick={() => onPerson(n.id)}>
              <b>{n.name}</b><span>{n.reason}</span>
            </button>
          ))}
        </section>
      )}

      {people && (
        <section>
          <button className="add-contact" onClick={() => setAdding(true)}>
            <b>+</b> Add a contact
          </button>
          <h2 className="section">{people.people.length} people
            <span className="sorts">
              {[['cold', 'Going cold'], ['close', 'Closest'], ['name', 'A–Z']].map(([key, label]) => (
                <button key={key} className={sort === key ? 'on' : ''} onClick={() => setSort(key)}>{label}</button>
              ))}
            </span>
          </h2>
          <div className="roster">
            {sorted.map((p) => (
              <button className="roster-row" key={p.id} onClick={() => onPerson(p.id)}>
                <Avatar name={p.name} strength={p.strength} />
                <span className="roster-body"><b>{p.name}{p.added && <em className="mine">added by you</em>}</b><span>{p.headline}</span></span>
                <span className={`roster-meta ${p.days_since_contact > 180 ? 'cold' : ''}`}>
                  {ago(p.days_since_contact)}
                  {p.portfolio_companies.length > 0 && <em>{p.portfolio_companies.slice(0, 2).join(' ')}</em>}
                </span>
              </button>
            ))}
          </div>
          <p className="fine">The starting profiles are synthetic and were created for this demo; employers are real so the network overlaps the portfolio. Contacts you add are marked.</p>
        </section>
      )}
      {adding && (
        <AddContact onClose={() => setAdding(false)}
          onAdded={(person) => { window.dispatchEvent(new Event(NETWORK_CHANGED)); onPerson(person.id) }} />
      )}
    </main>
  )
}
