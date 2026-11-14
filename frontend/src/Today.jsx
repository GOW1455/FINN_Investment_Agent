import { useEffect, useRef, useState } from 'react'
import { api, crore, Delta, PersonRow, Sheet, Spinner, timeLabel, useStateSafe } from './ui.jsx'
import Ask from './Ask.jsx'

const WINDOWS = [[24, '24h'], [72, '3 days'], [168, '7 days'], [720, '30 days']]
const MAX_HOURS = 24 * 90     // the server keeps about 120 days of filings; 90 is the widest window it accepts
const windowLabel = (hours) => (hours % 24 === 0 ? `${hours / 24} day${hours === 24 ? '' : 's'}` : `${hours}h`)
function ResultsTable({ results, dense }) {
  if (!results) return null
  return (
    <div className={`results ${dense ? 'dense' : ''}`}>
      <div className="results-grid">
        <span className="rh">{results.period}</span><span className="rh num">{results.unit}</span>
        <span className="rh num">QoQ</span><span className="rh num">YoY</span>
        {results.metrics.map((m) => (
          <div className="results-row" key={m.name}>
            <span>{m.name}</span>
            <span className="num strong">{crore(m.value)}</span>
            <span className="num"><Delta value={m.qoq} /></span>
            <span className="num"><Delta value={m.yoy} /></span>
          </div>
        ))}
      </div>
      {!dense && (
        <p className="fine">
          {results.basis && `${results.basis[0].toUpperCase()}${results.basis.slice(1)}. `}
          QoQ vs {results.prev_period || 'previous quarter'}; YoY vs {results.year_ago_period || 'a year ago'}. {results.note}{' '}
          Source: {results.source_url ? <a href={results.source_url} target="_blank" rel="noreferrer">{results.source}</a> : results.source}.
        </p>
      )}
    </div>
  )
}

function FilingCard({ item, onOpen, onAsk }) {
  const canAsk = item.url?.toLowerCase().endsWith('.pdf')
  const contact = item.network?.[0]
  return (
    <article className={`card tier-${item.tier}`} onClick={() => onOpen(item)}>
      <header>
        <span className={`tag cat-${item.category.replace(/\W/g, '')}`}>{item.label}</span>
        <b className="co">{item.company}</b>
        <time>{timeLabel(item.time)}</time>
      </header>
      <p className="summary">{item.summary}</p>
      {item.reaction && (
        <p className="reaction">
          Stock <Delta value={item.reaction.change_pct} /> on {item.reaction.volume_x}× volume when this came out
        </p>
      )}
      {item.results && <ResultsTable results={item.results} dense />}
      {(contact || canAsk || item.related?.length > 0) && (
        <footer>
          {contact && (
            <span className="chip-person">
              <i>{contact.name.split(' ').map((p) => p[0]).join('')}</i>
              Ask {contact.name.split(' ')[0]} <em>· {contact.angle}</em>
            </span>
          )}
          {item.related?.length > 0 && <span className="related">+{item.related.length} related filing{item.related.length > 1 ? 's' : ''}</span>}
          {canAsk && (
            <button className="ask-pill" onClick={(e) => { e.stopPropagation(); onAsk(item) }} aria-label={`Ask FINN about this ${item.label} filing`}>
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" /></svg>
              Ask FINN
            </button>
          )}
        </footer>
      )}
    </article>
  )
}

function FilingSheet({ item, onClose, onPerson, startAtAsk }) {
  const askRef = useRef(null)
  // Opened from a card's "Ask FINN": go straight to the question box.
  useEffect(() => { if (startAtAsk) askRef.current?.scrollIntoView({ block: 'start' }) }, [startAtAsk])
  const [detail, setDetail] = useStateSafe(null)
  const [error, setError] = useStateSafe('')
  useEffect(() => {
    api(`/push/item/${item.symbol}/${item.id}`).then(setDetail).catch((e) => setError(e.message))
  }, [item.symbol, item.id])
  const data = detail || item
  return (
    <Sheet title={data.company} kicker={`${data.label} · ${timeLabel(data.time)}`} onClose={onClose}>
      <p className="lede">{data.text || data.subject}</p>
      {item.why?.length > 0 && (
        <details className="why">
          <summary>Why this ranks {item.priority} of 100</summary>
          <ul>{item.why.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
        </details>
      )}
      {!detail && !error && <Spinner label="Reading the filing" />}
      {error && <p className="error">Could not load the details: {error}</p>}

      {detail?.results && (<><h3>Headline numbers</h3><ResultsTable results={detail.results} /></>)}
      {detail?.results_pending && (
        <p className="muted">The headline numbers for this quarter are not in the standardised tables yet. Open the filing for the full statement.</p>
      )}

      {detail?.brief && (
        <>
          <h3>What happened</h3>
          <p>{detail.brief.what}</p>
          {detail.brief.facts?.length > 0 && <ul className="bullets">{detail.brief.facts.map((f, i) => <li key={i}>{f}</li>)}</ul>}
          {detail.brief.watch && <p className="watch">{detail.brief.watch}</p>}
        </>
      )}

      {detail?.people?.map((person, i) => (
        <div className="incoming" key={i}>
          <h3>{person.name}</h3>
          <p className="role">
            {person.change}{person.role ? ` · ${person.role}` : ''}{person.effective ? ` · effective ${person.effective}` : ''}
          </p>
          {person.bio && <p>{person.bio}</p>}
          {person.reason && <p className="muted">Stated reason: {person.reason}</p>}
          {person.career?.length > 0 && (
            <ol className="timeline small">
              {person.career.slice(0, 5).map((r, j) => (
                <li key={j}><b>{r.title || 'Role'}</b>, {r.company}{(r.from || r.to) && <span>{r.from || ''}–{r.to || ''}</span>}</li>
              ))}
            </ol>
          )}
          <h4>In your network</h4>
          {person.network?.length > 0
            ? person.network.map((p) => <PersonRow key={p.id} person={p} onOpen={onPerson} />)
            : <p className="muted">No one in your network overlaps with {person.name.replace(/^(Mr|Mrs|Ms|Dr|Shri|Smt)\.? /, '')}{person.career?.length ? '' : '. The filing gives no career history to match against'}.</p>}
          {!person.bio && <p className="fine">Background comes only from the filing itself. This filing carries no profile.</p>}
        </div>
      ))}
      {detail && detail.category === 'management_change' && !detail.people?.length && (
        <p className="muted">The exchange summary does not name the person. Open the filing for details.</p>
      )}

      {detail?.who_to_call?.length > 0 && (
        <>
          <h3>Who can explain this</h3>
          {detail.who_to_call.map((p) => <PersonRow key={p.id} person={p} onOpen={onPerson} />)}
        </>
      )}

      {data.url?.toLowerCase().endsWith('.pdf') && (
        <div ref={askRef} className="ask-anchor">
        <Ask kind="filing" symbol={item.symbol} itemId={item.id} onPerson={onPerson} autoFocus={startAtAsk}
          starters={['What exactly changed, and from when?', 'Are any amounts or dates given?', 'What should a shareholder watch next?']} />
        </div>
      )}

      <div className="links">
        {data.url && <a className="button" href={data.url} target="_blank" rel="noreferrer">Open the filing</a>}
        {item.related?.map((r) => (
          <a key={r.id} href={r.url} target="_blank" rel="noreferrer" className="related-link">{r.subject} · {timeLabel(r.time)}</a>
        ))}
      </div>
    </Sheet>
  )
}

function SettingsSheet({ settings, scoring, onChange, onClose }) {
  const tierOf = (score) => (score >= scoring.tiers.material ? 'material' : score >= scoring.tiers.notable ? 'notable' : 'routine')
  const setWeight = (id, value, base) => {
    const weights = { ...settings.weights }
    if (value === base) delete weights[id]
    else weights[id] = value
    onChange({ ...settings, weights })
  }
  const changed = Object.keys(settings.weights).length
  return (
    <Sheet title="What matters to you" kicker="You decide. FINN watches." onClose={onClose}>
      <h3>Unusual moves</h3>
      <label className="slider">
        <span>Volume above <b>{settings.volume_multiple}×</b> its {settings.lookback_days}-day average</span>
        <input type="range" min="1.2" max="6" step="0.1" value={settings.volume_multiple}
          onChange={(e) => onChange({ ...settings, volume_multiple: Number(e.target.value) })} />
      </label>
      <label className="slider">
        <span>Price move beyond <b>±{settings.price_move_pct}%</b> in a day</span>
        <input type="range" min="1" max="12" step="0.5" value={settings.price_move_pct}
          onChange={(e) => onChange({ ...settings, price_move_pct: Number(e.target.value) })} />
      </label>
      <label className="slider">
        <span>Compare with the last <b>{settings.lookback_days}</b> trading days</span>
        <input type="range" min="5" max="60" step="5" value={settings.lookback_days}
          onChange={(e) => onChange({ ...settings, lookback_days: Number(e.target.value) })} />
      </label>
      <p className="fine">
        A filing that comes out with an unusual move by these same measures ranks {scoring.market_reaction_points} points higher.
      </p>

      <h3>How much each kind of filing matters</h3>
      <p className="muted">
        Each filing starts at its type's score. {scoring.tiers.material} or more shows as a card, {scoring.tiers.notable} or more as a line, the rest is collapsed.
        {changed > 0 && <> <button className="link" onClick={() => onChange({ ...settings, weights: {} })}>Reset all</button></>}
      </p>
      <div className="weights">
        {scoring.categories.filter((c) => c.id !== 'unclassified').map((c) => {
          const value = settings.weights[c.id] ?? c.base
          return (
            <label className={`weight ${value !== c.base ? 'changed' : ''}`} key={c.id}>
              <span>{c.label}</span>
              <input type="range" min="0" max="100" step="2" value={value} aria-label={`${c.label} score`}
                onChange={(e) => setWeight(c.id, Number(e.target.value), c.base)} />
              <b>{value}</b>
              <em className={`t-${tierOf(value)}`}>{tierOf(value)}</em>
            </label>
          )
        })}
      </div>
    </Sheet>
  )
}

export default function Today({ onPerson, onResearch }) {
  // A link can open a specific window: /?hours=168
  const [hours, setHours] = useState(() => {
    const asked = Number(new URLSearchParams(window.location.search).get('hours'))
    return Number.isInteger(asked) && asked >= 1 && asked <= MAX_HOURS ? asked : 24
  })
  const [customOpen, setCustomOpen] = useState(false)
  const [custom, setCustom] = useState({ amount: '2', unit: 'hours' })
  const isPreset = WINDOWS.some(([value]) => value === hours)
  const customHours = Math.round(Number(custom.amount) * (custom.unit === 'days' ? 24 : 1))
  const customValid = Number.isFinite(customHours) && customHours >= 1 && customHours <= MAX_HOURS
  // Reset clears the entry and goes back to the default window; the row stays open for a new entry.
  const resetWindow = () => { setHours(24); setCustom({ amount: '', unit: 'hours' }); setCustomOpen(true) }
  const applyCustom = (event) => {
    event.preventDefault()
    if (customValid) { setHours(customHours); setCustomOpen(true) }   // keep the row, so Reset is at hand
  }
  const [settings, setSettings] = useState(() => {
    const base = { volume_multiple: 2, price_move_pct: 4, lookback_days: 20, weights: {} }
    try {
      const saved = JSON.parse(localStorage.getItem('finn.settings') || '{}')
      return { ...base, ...saved, weights: saved.weights || {} }
    } catch { return base }
  })
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(null)
  const [openAtAsk, setOpenAtAsk] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showRoutine, setShowRoutine] = useState(false)
  const [move, setMove] = useState(null)
  const [scoring, setScoring] = useState(null)
  useEffect(() => { api('/push/settings').then(setScoring).catch(() => {}) }, [])

  useEffect(() => {
    try { localStorage.setItem('finn.settings', JSON.stringify(settings)) } catch { /* private mode */ }
    let cancelled = false
    setLoading(true)
    const query = new URLSearchParams({
      hours, volume_multiple: settings.volume_multiple, price_move_pct: settings.price_move_pct,
      lookback_days: settings.lookback_days, weights: Object.entries(settings.weights).map(([id, value]) => `${id}:${value}`).join(','),
    })
    const timer = setTimeout(() => {
      api(`/push/digest?${query}`)
        .then((d) => { if (!cancelled) { setData(d); setError('') } })
        .catch((e) => !cancelled && setError(e.message))
        .finally(() => !cancelled && setLoading(false))
    }, 250) // debounce slider drags
    return () => { cancelled = true; clearTimeout(timer) }
  }, [hours, settings])

  const counts = data?.counts
  const material = data?.items.filter((i) => i.tier === 'material') || []
  const notable = data?.items.filter((i) => i.tier === 'notable') || []

  return (
    <main className="screen">
      <header className="masthead">
        <div>
          <div className="kicker">{(data?.snapshot ? new Date(data.generated_at.replace(' ', 'T')) : new Date()).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}{data?.snapshot ? ' · saved snapshot' : ''}</div>
          <h1>
            {!counts ? 'Today' : material.length + (data.alerts.length)
              ? <>{material.length + data.alerts.length} thing{material.length + data.alerts.length > 1 ? 's need' : ' needs'} you</>
              : 'Nothing needs you'}
          </h1>
          {counts && (
            <p className="sub">
              {counts.total} filing{counts.total === 1 ? '' : 's'} across 18 holdings · {counts.routine + counts.folded} set aside as routine or duplicate
            </p>
          )}
        </div>
        <button className="icon-button" onClick={() => setShowSettings(true)} aria-label="Alert settings">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></svg>
        </button>
      </header>

      <nav className="segmented" aria-label="Time window">
        {WINDOWS.map(([value, label]) => (
          <button key={value} className={hours === value ? 'on' : ''}
            onClick={() => { setHours(value); setCustomOpen(false) }}>{label}</button>
        ))}
        <button className={!isPreset ? 'on' : ''} onClick={() => setCustomOpen(!customOpen)} aria-expanded={customOpen || !isPreset}>
          {!isPreset ? windowLabel(hours) : 'Custom'}
        </button>
      </nav>
      {(customOpen || !isPreset) && (
        <form className="custom-window" onSubmit={applyCustom}>
          <span>Last</span>
          <input type="number" inputMode="numeric" min="1" step="1" value={custom.amount} aria-label="Amount"
            onChange={(e) => setCustom({ ...custom, amount: e.target.value })} />
          <select value={custom.unit} aria-label="Unit" onChange={(e) => setCustom({ ...custom, unit: e.target.value })}>
            <option value="hours">hours</option>
            <option value="days">days</option>
          </select>
          <button type="submit" disabled={!customValid}>Show</button>
          <button type="button" className="reset" onClick={resetWindow}>Reset</button>
          {!customValid && custom.amount !== '' && <em>Between 1 hour and 90 days.</em>}
        </form>
      )}

      {loading && !data && <Spinner label="Reading the exchange" />}
      {error && <p className="error">Could not load the digest: {error}</p>}

      {data && (
        <div className={loading ? 'stale' : ''}>
          {data.alerts.length > 0 && (
            <section>
              <h2 className="section">Unusual moves <span>latest close</span></h2>
              <div className="alerts">
                {data.alerts.map((a) => (
                  <button className="alert" key={a.symbol} onClick={() => setMove(a)}>
                    <b>{a.symbol}</b>
                    <Delta value={a.change_pct} />
                    <span className={a.triggered.includes('volume') ? 'hot' : ''}>{a.volume_x}× volume</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {material.length > 0 && (
            <section>
              <h2 className="section">Material</h2>
              {material.map((item) => (
                <FilingCard key={item.id} item={item}
                  onOpen={(it) => { setOpenAtAsk(false); setOpen(it) }}
                  onAsk={(it) => { setOpenAtAsk(true); setOpen(it) }} />
              ))}
            </section>
          )}

          {data.nudges.length > 0 && (
            <section>
              <h2 className="section">A reason to reconnect</h2>
              {data.nudges.map((n) => (
                <button className="nudge" key={n.id} onClick={() => onPerson(n.id)}>
                  <b>{n.name}</b>
                  <span>{n.reason}</span>
                </button>
              ))}
            </section>
          )}

          {notable.length > 0 && (
            <section>
              <h2 className="section">Worth a glance</h2>
              <div className="compact-list">
                {notable.map((item) => (
                  <button className="line" key={item.id} onClick={() => setOpen(item)}>
                    <span className={`dot cat-${item.category.replace(/\W/g, '')}`} />
                    <span className="line-body"><b>{item.company}</b> <em>{item.label}</em><br />{item.summary}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {material.length === 0 && data.alerts.length === 0 && (
            <div className="empty">
              <p>No material filings and no unusual moves in this window.</p>
              {hours < 168 && <button className="button ghost" onClick={() => setHours(168)}>Look back 7 days</button>}
            </div>
          )}

          {counts.routine > 0 && (
            <section>
              <button className="routine-toggle" onClick={() => setShowRoutine(!showRoutine)}>
                {counts.routine} routine filing{counts.routine > 1 ? 's' : ''} hidden
                <span>{data.routine.map((g) => `${g.count} ${g.label.toLowerCase()}`).slice(0, 3).join(' · ')}</span>
                <i>{showRoutine ? 'Hide' : 'Show'}</i>
              </button>
              {showRoutine && (
                <div className="compact-list faded">
                  {data.routine.flatMap((g) => g.items).map((item) => (
                    <a className="line" key={item.id} href={item.url} target="_blank" rel="noreferrer">
                      <span className="dot" />
                      <span className="line-body"><b>{item.company}</b> <em>{item.subject}</em></span>
                    </a>
                  ))}
                </div>
              )}
            </section>
          )}
          {data.failed_symbols.length > 0 && <p className="fine">No fresh data for: {data.failed_symbols.join(', ')}.</p>}
          <p className="fine">
            Filings from NSE. Prices from Yahoo Finance, end of day.{' '}
            {data.snapshot ? `Demo mode: showing a saved snapshot as of ${data.generated_at} IST, not live data.` : `Updated ${data.generated_at} IST.`}
          </p>
        </div>
      )}

      {open && <FilingSheet item={open} startAtAsk={openAtAsk} onClose={() => { setOpen(null); setOpenAtAsk(false) }} onPerson={onPerson} />}
      {showSettings && scoring && <SettingsSheet settings={settings} scoring={scoring} onChange={setSettings} onClose={() => setShowSettings(false)} />}
      {move && (
        <Sheet title={move.company} kicker={`Unusual move · ${move.date}`} onClose={() => setMove(null)}>
          <div className="facts-row">
            <div><span>Close</span><b>₹{move.close.toLocaleString('en-IN')}</b></div>
            <div><span>Day change</span><b><Delta value={move.change_pct} /></b></div>
            <div><span>Volume</span><b>{move.volume_x}× avg</b></div>
          </div>
          <p className="muted">
            Flagged because {move.triggered.map((t) => t === 'volume'
              ? `volume was above your ${data.thresholds.volume_multiple}× threshold`
              : `the move was beyond your ±${data.thresholds.price_move_pct}% threshold`).join(' and ')}.
          </p>
          {data.items.filter((i) => i.symbol === move.symbol).length > 0 && (
            <>
              <h3>Filings in this window</h3>
              <div className="compact-list">
                {data.items.filter((i) => i.symbol === move.symbol).map((item) => (
                  <button className="line" key={item.id} onClick={() => { setMove(null); setOpen(item) }}>
                    <span className="dot" /><span className="line-body"><em>{item.label}</em><br />{item.summary}</span>
                  </button>
                ))}
              </div>
            </>
          )}
          <button className="button" onClick={() => { setMove(null); onResearch(move.symbol) }}>Research {move.symbol}</button>
        </Sheet>
      )}
    </main>
  )
}
