import { useEffect, useMemo, useRef, useState } from 'react'
import { api, PersonRow, Sheet, Spinner } from './ui.jsx'
import Ask from './Ask.jsx'

const AGENTS = {
  desk: { name: 'Desk', role: 'Collects the primary sources' },
  numbers: { name: 'Numbers Analyst', role: 'Reads the reported financials' },
  guidance: { name: 'Guidance Analyst', role: 'Reads what management promised' },
  skeptic: { name: 'Skeptic', role: 'Tests promises against delivery' },
  moderator: { name: 'Moderator', role: 'Weighs both sides' },
}
const VERDICTS = { delivered: 'Delivered', partly: 'Partly', missed: 'Missed', too_early: 'Too early' }

/* A citation chip. Tapping it shows the exact evidence, so nothing has to be taken on trust. */
function Cites({ ids, onOpen }) {
  if (!ids?.length) return null
  return (
    <span className="cites">
      {ids.map((id) => <button key={id} className="cite" onClick={(e) => { e.stopPropagation(); onOpen(id) }}>{id}</button>)}
    </span>
  )
}

function Point({ point, onCite }) {
  return <li>{point.text} <Cites ids={point.cites} onOpen={onCite} /></li>
}

function EvidenceSheet({ id, result, onClose }) {
  const fact = result.facts?.find((f) => f.id === id)
  const promise = result.guidance?.find((g) => g.id === id)
  const [tag, page] = id.split(':')
  const source = result.sources?.find((s) => s.id === (promise ? promise.cite.split(':')[0] : tag))
  const pageNumber = promise ? promise.cite.split(':')[1] : page
  return (
    <Sheet title={fact ? 'Reported number' : promise ? 'Management said' : source?.label || 'Source'} kicker={`Evidence ${id}`} onClose={onClose}>
      {fact && <p className="evidence">{fact.text}</p>}
      {promise && (
        <>
          <blockquote>“{promise.quote}”</blockquote>
          <p className="muted">{promise.statement} Horizon: {promise.horizon || 'not stated'}.</p>
        </>
      )}
      {source && (
        <p>
          {source.label}{pageNumber ? `, page ${pageNumber}` : ''}.{' '}
          {source.url && <a href={`${source.url}${pageNumber ? `#page=${pageNumber}` : ''}`} target="_blank" rel="noreferrer">Open the document</a>}
        </p>
      )}
      {fact && <p className="fine">Computed in code from the company's reported financials, as standardised by screener.in. {result.sources?.[0]?.url && <a href={result.sources[0].url} target="_blank" rel="noreferrer">Open the tables</a>}</p>}
    </Sheet>
  )
}

function Debate({ events, live }) {
  const end = useRef(null)
  useEffect(() => { if (live) end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [events.length, live])
  return (
    <ol className="debate">
      {events.map((event, i) => {
        const agent = AGENTS[event.agent] || { name: event.agent }
        const kind = event.status === 'challenge' ? `challenges the ${AGENTS[event.data?.to]?.name || 'analyst'}`
          : event.status === 'rebuttal' ? (event.data?.concede ? 'concedes' : 'holds the point')
            : event.status === 'working' ? 'is working' : ''
        return (
          <li key={i} className={`turn a-${event.agent} s-${event.status}`}>
            <span className="who">{agent.name}{kind && <em> {kind}</em>}</span>
            <span className="said">{event.text}{event.status === 'working' && live && i === events.length - 1 && <i className="dots" />}</span>
          </li>
        )
      })}
      <li ref={end} className="end" />
    </ol>
  )
}

/* Which model produced a report, in plain words. One name when every step used the same model. */
function modelsUsed(result) {
  const { extraction, reasoning } = result.audit?.models || {}
  if (!extraction && !reasoning) return 'an unknown model'
  return extraction === reasoning || !reasoning ? extraction : `${extraction} for reading, ${reasoning} for reasoning`
}

function Report({ result, onPerson }) {
  const [cite, setCite] = useState(null)
  const [tab, setTab] = useState('bull')
  const verdict = result.verdict
  const sections = [['trajectory', 'Trajectory'], ['balance_sheet', 'Balance sheet'], ['cash_quality', 'Cash quality'], ['snapshot', 'Snapshot']]
  const ratios = Object.entries(result.top_ratios || {}).filter(([k]) => ['Market Cap', 'Stock P/E', 'ROCE', 'ROE'].includes(k))

  if (result.status !== 'complete') {
    return (
      <div className="report">
        <p className="note">{result.message}</p>
        {result.who_to_call?.length > 0 && (
          <>
            <h3>Who you know who can help</h3>
            {result.who_to_call.map((p) => <PersonRow key={p.id} person={p} onOpen={onPerson} />)}
          </>
        )}
        <h3>Reported numbers</h3>
        <ul className="facts">{result.facts.map((f) => <li key={f.id}><b>{f.id}</b> {f.text}</li>)}</ul>
      </div>
    )
  }
  return (
    <div className="report">
      <p className="headline">{verdict.headline}</p>
      <div className="facts-row four">
        {ratios.map(([k, v]) => <div key={k}><span>{k}</span><b>{v.replace(' Cr.', ' cr')}</b></div>)}
      </div>

      {verdict.narrative_vs_numbers && (
        <section className="block">
          <h3>Narrative vs numbers</h3>
          <p>{verdict.narrative_vs_numbers.text} <Cites ids={verdict.narrative_vs_numbers.cites} onOpen={setCite} /></p>
        </section>
      )}

      {result.scorecard.length > 0 && (
        <section className="block">
          <h3>Promised vs delivered</h3>
          <div className="tally">
            {Object.entries(VERDICTS).map(([key, label]) => result.tally[key] > 0 && (
              <span key={key} className={`v-${key}`}><b>{result.tally[key]}</b> {label.toLowerCase()}</span>
            ))}
          </div>
          {result.scorecard.map((row) => (
            <article className={`score v-${row.verdict}`} key={row.guidance}>
              <header>
                <span className="verdict">{VERDICTS[row.verdict]}</span>
                <span className="when">said {row.said_in}{row.horizon ? ` · for ${row.horizon}` : ''}</span>
              </header>
              <p className="promise">{row.promise} <Cites ids={[row.guidance]} onOpen={setCite} /></p>
              <p className="delivered">{row.delivered} <Cites ids={row.cites} onOpen={setCite} /></p>
            </article>
          ))}
        </section>
      )}

      <section className="block">
        <div className="segmented two">
          <button className={tab === 'bull' ? 'on bull' : ''} onClick={() => setTab('bull')}>Bull case</button>
          <button className={tab === 'bear' ? 'on bear' : ''} onClick={() => setTab('bear')}>Bear case</button>
        </div>
        <ol className={`case ${tab}`}>
          {verdict[tab].map((point, i) => <Point key={i} point={point} onCite={setCite} />)}
        </ol>
      </section>

      <Ask kind="research" symbol={result.symbol} onPerson={onPerson}
        starters={['What did management say about margins?', 'How has debt changed, and why?', 'What are analysts most worried about?']} />

      {result.divergences.length > 0 && (
        <section className="block">
          <h3>Where story and numbers part ways</h3>
          <ul className="bullets">{result.divergences.map((d, i) => <Point key={i} point={d} onCite={setCite} />)}</ul>
        </section>
      )}

      {result.who_to_call.length > 0 && (
        <section className="block">
          <h3>Who you know who can pressure-test this</h3>
          {result.who_to_call.map((p) => <PersonRow key={p.id} person={p} onOpen={onPerson} />)}
        </section>
      )}

      {verdict.ask_management.length > 0 && (
        <section className="block">
          <h3>Worth asking management</h3>
          <ol className="questions">{verdict.ask_management.map((q, i) => <li key={i}>{q}</li>)}</ol>
        </section>
      )}

      {result.business && (
        <section className="block">
          <h3>The business</h3>
          {result.business.what && <p>{result.business.what.text} <Cites ids={result.business.what.cites} onOpen={setCite} /></p>}
          <ul className="bullets">
            {result.business.segments.map((s, i) => <li key={i}><b>{s.name}.</b> {s.text} <Cites ids={s.cites} onOpen={setCite} /></li>)}
          </ul>
        </section>
      )}

      {sections.map(([key, label]) => result.numbers[key]?.length > 0 && (
        <details className="block fold" key={key} open={key === 'trajectory'}>
          <summary>{label}</summary>
          <ul className="bullets">{result.numbers[key].map((p, i) => <Point key={i} point={p} onCite={setCite} />)}</ul>
        </details>
      ))}

      {result.calls?.length > 0 && (
        <details className="block fold">
          <summary>Management tone, call by call</summary>
          <ul className="bullets">
            {result.calls.map((c) => (
              <li key={c.tag}><b>{c.date}.</b> {c.tone}
                {c.pressure?.map((p, i) => <span className="pressure" key={i}>Analysts pushed on: {p.text} <Cites ids={p.cites} onOpen={setCite} /></span>)}
              </li>
            ))}
          </ul>
        </details>
      )}

      <details className="block fold">
        <summary>How the debate went</summary>
        <Debate events={result.events || []} />
        {Object.entries(result.rebuttals || {}).map(([who, r]) => r && (
          <p className="fine" key={who}>{AGENTS[who].name}'s evidence: <Cites ids={r.cites} onOpen={setCite} /></p>
        ))}
      </details>

      <footer className="audit">
        <b>{result.audit.claims - result.audit.dropped} claims, each traced to a source.</b>{' '}
        {result.audit.dropped > 0 && `${result.audit.dropped} dropped because the citation could not be verified. `}
        Sources: {result.sources.map((s, i) => <span key={s.id}>{i > 0 && ', '}<a href={s.url} target="_blank" rel="noreferrer">{s.label}</a></span>)}.
        No news, broker notes or model memory. Generated {result.generated_at} in {result.audit.seconds}s.{' '}
        Model: {modelsUsed(result)}.
      </footer>
      {cite && <EvidenceSheet id={cite} result={result} onClose={() => setCite(null)} />}
    </div>
  )
}

export default function Research({ symbol, setSymbol, onPerson }) {
  const [catalog, setCatalog] = useState(null)
  const [input, setInput] = useState('')
  const [events, setEvents] = useState([])
  const [result, setResult] = useState(null)
  const [state, setState] = useState('idle') // idle | running | done | error
  const [error, setError] = useState('')
  const [fromCache, setFromCache] = useState(false)
  const [models, setModels] = useState([])
  const [model, setModel] = useState(() => { try { return localStorage.getItem('finn.model') || '' } catch { return '' } })
  const [running, setRunning] = useState('')
  const source = useRef(null)

  useEffect(() => {
    api('/models').then((d) => {
      setModels(d.choices)
      // Keep the saved choice only if it is still offered; otherwise fall back to the default model.
      setModel((current) => (d.choices.some((c) => c.id === current) ? current : d.default))
    }).catch(() => {})
  }, [])
  const pickModel = (id) => { setModel(id); try { localStorage.setItem('finn.model', id) } catch { /* private mode */ } }
  const modelName = (models.find((c) => c.id === model)?.name) || model.split('/').pop()

  useEffect(() => { api('/portfolio').then(setCatalog).catch(() => {}) }, [state])

  const run = (target, refresh = false) => {
    source.current?.close()
    setEvents([]); setResult(null); setError(''); setState('running'); setFromCache(false); setRunning('')
    const query = new URLSearchParams()
    if (refresh) query.set('refresh', 'true')
    if (model) query.set('model', model)
    const stream = new EventSource(`/api/pull/${encodeURIComponent(target)}/stream?${query}`)
    source.current = stream
    stream.onmessage = (message) => {
      const event = JSON.parse(message.data)
      if (event.type === 'model') setRunning(event.model)
      if (event.type === 'agent') setEvents((list) => [...list, event])
      if (event.type === 'result') { setResult(event.data); setFromCache(!!event.cached); setState('done'); stream.close() }
      if (event.type === 'error') { setError(event.text); setState('error'); stream.close() }
    }
    stream.onerror = () => {
      stream.close()
      setState((current) => { if (current === 'running') { setError('The connection dropped. Try again.'); return 'error' } return current })
    }
  }

  useEffect(() => { if (symbol) run(symbol) }, [symbol])
  useEffect(() => () => source.current?.close(), [])

  const submit = (event) => {
    event.preventDefault()
    const value = input.trim().toUpperCase().replace(/\.NS$/, '')
    if (value) { setSymbol(value); if (value === symbol) run(value) }
  }
  const names = useMemo(() => Object.fromEntries((catalog?.portfolio || []).map((c) => [c.symbol, c.name])), [catalog])

  return (
    <main className="screen">
      <header className="masthead">
        <div>
          <div className="kicker">Research · primary sources only</div>
          <h1>{symbol ? (result?.name || names[symbol] || symbol) : 'Dig into a company'}</h1>
          {!symbol && <p className="sub">Four analysts read the annual report and the last four earnings calls, then argue it out.</p>}
        </div>
      </header>

      <form className="ask" onSubmit={submit}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Any NSE symbol, e.g. KPITTECH"
          autoCapitalize="characters" autoCorrect="off" spellCheck="false" aria-label="NSE symbol" />
        <button type="submit">Research</button>
      </form>
      {models.length > 0 && (
        <label className="model-pick">
          <span>Model for new research</span>
          <select value={model} onChange={(e) => pickModel(e.target.value)} disabled={state === 'running'}>
            {models.map((c) => <option key={c.id} value={c.id}>{c.name}{c.default ? ' (default)' : ''}</option>)}
          </select>
        </label>
      )}

      {state === 'idle' && catalog && (
        <>
          <h2 className="section">Outside your portfolio</h2>
          <div className="chips">
            {catalog.research_demo.map((c) => <button key={c.symbol} className={c.researched ? 'ready' : ''} onClick={() => setSymbol(c.symbol)}>{c.symbol}</button>)}
          </div>
          <h2 className="section">Your holdings</h2>
          <div className="chips">
            {catalog.portfolio.map((c) => <button key={c.symbol} className={c.researched ? 'ready' : ''} onClick={() => setSymbol(c.symbol)}>{c.name}</button>)}
          </div>
          <p className="fine">A dot marks companies already researched; they open instantly. Others take about a minute.</p>
        </>
      )}

      {state === 'running' && (
        <section className="live">
          {running && <p className="running-on">Running every step on <b>{running}</b></p>}
          <Debate events={events} live />
          {events.length === 0 && <Spinner label="Opening the files" />}
        </section>
      )}
      {state === 'error' && (
        <div className="empty">
          <p className="error">{error}</p>
          <button className="button ghost" onClick={() => run(symbol)}>Try again</button>
        </div>
      )}
      {state === 'done' && result && (
        <>
          <Report result={result} onPerson={onPerson} />
          <div className="links">
            <button className="button ghost" onClick={() => run(symbol, true)}>Run the debate again{modelName ? ` on ${modelName}` : ''}</button>
            <button className="button ghost" onClick={() => { setSymbol(''); setState('idle'); setInput('') }}>Another company</button>
          </div>
          {fromCache && <p className="fine">Showing saved research from {result.generated_at}, made with {modelsUsed(result)}. The model picker applies to new runs.</p>}
        </>
      )}
    </main>
  )
}
