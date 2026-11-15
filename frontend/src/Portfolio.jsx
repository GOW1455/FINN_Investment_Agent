import { useEffect, useState } from 'react'
import { api, post, remove, Sheet, Spinner } from './ui.jsx'

/* See and edit the holdings the Today tab watches. A symbol is checked against screener.in before it is
   added, so the feed never carries a company the rest of the app cannot fetch. */
export default function Portfolio({ onClose, onChanged, onResearch }) {
  const [list, setList] = useState(null)
  const [symbol, setSymbol] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const load = () => api('/portfolio').then((d) => setList(d.portfolio)).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const add = (event) => {
    event.preventDefault()
    const value = symbol.trim().toUpperCase().replace(/\.NS$/, '')
    if (!value || busy) return
    setBusy('add'); setError('')
    post('/portfolio', { symbol: value })
      .then(() => { setSymbol(''); return load().then(onChanged) })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(''))
  }

  const drop = (holding) => {
    if (!window.confirm(`Stop watching ${holding.name}?`)) return
    setBusy(holding.symbol); setError('')
    remove(`/portfolio/${holding.symbol}`)
      .then(() => load().then(onChanged))
      .catch((e) => setError(e.message))
      .finally(() => setBusy(''))
  }

  return (
    <Sheet title="Your portfolio" kicker={list ? `${list.length} holding${list.length === 1 ? '' : 's'}` : 'Holdings'} onClose={onClose}>
      <p className="muted">These are the companies the Today tab watches for filings and unusual moves.</p>

      <form className="ask" onSubmit={add}>
        <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="NSE symbol, e.g. HAVELLS"
          autoCapitalize="characters" autoCorrect="off" spellCheck="false" maxLength="20" aria-label="NSE symbol" />
        <button type="submit" disabled={!symbol.trim() || busy === 'add'}>{busy === 'add' ? 'Adding…' : 'Add'}</button>
      </form>
      {error && <p className="error">{error}</p>}

      {!list && <Spinner label="Loading your holdings" />}
      {list && (
        <div className="holdings">
          {list.map((holding) => (
            <div className="holding" key={holding.symbol}>
              <span className="holding-body">
                <b>{holding.name}</b>
                <span>{holding.symbol}{holding.researched && ' · researched'}</span>
              </span>
              <button className="link" onClick={() => onResearch(holding.symbol)}>Research</button>
              <button className="link danger" disabled={busy === holding.symbol} onClick={() => drop(holding)}>
                {busy === holding.symbol ? '…' : 'Remove'}
              </button>
            </div>
          ))}
          {list.length === 0 && <p className="muted">No holdings yet. Add an NSE symbol above to start watching it.</p>}
        </div>
      )}
      <p className="fine">Saved on this app's server. Research already done for a company is kept even if you remove it.</p>
    </Sheet>
  )
}
