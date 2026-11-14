import { useEffect, useState } from 'react'
import { api, PersonRow, post, Spinner } from './ui.jsx'

const read = (key) => { try { return localStorage.getItem(key) || '' } catch { return '' } }
const write = (key, value) => { try { localStorage.setItem(key, value) } catch { /* private mode */ } }

/* Ask a question about one filing or one research report.
   The answer comes only from that context, every point is cited, and it is framed by the investor's own focus. */
export default function Ask({ kind, symbol, itemId = '', starters = [], onPerson, autoFocus = false }) {
  const [focus, setFocus] = useState(() => read('finn.focus'))
  const [editingFocus, setEditingFocus] = useState(false)
  const [models, setModels] = useState([])
  const [model, setModel] = useState(() => read('finn.model'))
  const [question, setQuestion] = useState('')
  const [thread, setThread] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(null) // "turnIndex:evidenceId" of the citation being shown

  useEffect(() => {
    api('/models').then((d) => {
      setModels(d.choices)
      setModel((current) => (d.choices.some((c) => c.id === current) ? current : d.default))
    }).catch(() => {})
  }, [])
  // A different filing or company is a different conversation.
  useEffect(() => { setThread([]); setError(''); setOpen(null) }, [kind, symbol, itemId])

  const ask = (text) => {
    const q = text.trim()
    if (q.length < 3 || busy) return
    setBusy(true); setError(''); setQuestion('')
    const history = thread.slice(-3).map((t) => ({ q: t.question, a: t.points.map((p) => p.text).join(' ') }))
    post('/ask', { kind, symbol, item_id: itemId, question: q, focus, history, model })
      .then((answer) => setThread((list) => [...list, answer]))
      .catch((e) => { setError(e.message); setQuestion(q) })
      .finally(() => setBusy(false))
  }

  const last = thread[thread.length - 1]
  const suggestions = last?.follow_ups?.length ? last.follow_ups : thread.length === 0 ? starters : []

  return (
    <section className="ask-box">
      <h3>Ask about this {kind === 'filing' ? 'filing' : 'company'}</h3>

      {editingFocus ? (
        <div className="focus-edit">
          <label htmlFor={`focus-${kind}`}>What I'm working on</label>
          <textarea id={`focus-${kind}`} rows="2" maxLength="500" value={focus} autoFocus
            placeholder="e.g. Whether new entrants are hurting paint makers' margins"
            onChange={(e) => setFocus(e.target.value)} />
          <div className="row">
            <button className="button small" onClick={() => { write('finn.focus', focus.trim()); setFocus(focus.trim()); setEditingFocus(false) }}>Save</button>
            {focus && <button className="link" onClick={() => { setFocus(''); write('finn.focus', ''); setEditingFocus(false) }}>Clear</button>}
          </div>
        </div>
      ) : (
        <button className="focus-line" onClick={() => setEditingFocus(true)}>
          {focus ? <><span>Framed for:</span> {focus}</> : <span>Add what you're working on, to get answers framed for it</span>}
          <i>{focus ? 'Edit' : 'Add'}</i>
        </button>
      )}

      {thread.map((turn, index) => (
        <article className="turn-qa" key={index}>
          <p className="q">{turn.question}</p>
          {turn.answered ? (
            <ul className="bullets">
              {turn.points.map((point, i) => (
                <li key={i}>
                  {point.text}{' '}
                  <span className="cites">
                    {point.cites.map((id) => (
                      <button key={id} className={`cite ${open === `${index}:${id}` ? 'on' : ''}`}
                        onClick={() => setOpen(open === `${index}:${id}` ? null : `${index}:${id}`)}>{id}</button>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="not-found">Not in these sources.</p>
          )}
          {turn.missing && <p className="muted small">{turn.missing}</p>}
          {open?.startsWith(`${index}:`) && (() => {
            const id = open.slice(String(index).length + 1)
            const source = turn.evidence[id]
            if (!source) return null
            return (
              <div className="evidence-inline">
                <b>{id} · {source.label}</b>
                {source.text && <p>{source.text}</p>}
                {source.url && (
                  <a href={`${source.url}${source.page ? `#page=${source.page}` : ''}`} target="_blank" rel="noreferrer">
                    Open the document{source.page ? ` at page ${source.page}` : ''}
                  </a>
                )}
              </div>
            )
          })()}
          {!turn.answered && turn.who?.length > 0 && (
            <>
              <h4>Someone who might know</h4>
              {turn.who.map((person) => <PersonRow key={person.id} person={person} onOpen={onPerson} compact />)}
            </>
          )}
          <p className="fine">Answered by {turn.model}, from this {kind === 'filing' ? 'filing' : 'report and its transcripts'} only.</p>
        </article>
      ))}

      {busy && <Spinner label="Reading the sources" />}
      {error && <p className="error">{error}</p>}

      {suggestions.length > 0 && !busy && (
        <div className="chips">
          {suggestions.map((s) => <button key={s} onClick={() => ask(s)}>{s}</button>)}
        </div>
      )}

      <form className="ask" onSubmit={(e) => { e.preventDefault(); ask(question) }}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength="500"
          placeholder={thread.length ? 'Ask a follow-up' : 'Your question'} aria-label="Your question" autoFocus={autoFocus} />
        <button type="submit" disabled={busy || question.trim().length < 3}>Ask</button>
      </form>
      {models.length > 0 && (
        <label className="model-pick">
          <span>Model</span>
          <select value={model} onChange={(e) => { setModel(e.target.value); write('finn.model', e.target.value) }} disabled={busy}>
            {models.map((c) => <option key={c.id} value={c.id}>{c.name}{c.default ? ' (default)' : ''}</option>)}
          </select>
        </label>
      )}
    </section>
  )
}
