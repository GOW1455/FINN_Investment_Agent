import { useEffect, useState } from 'react'
import { api, post, remove, Sheet, Spinner } from './ui.jsx'

function putWeights(weights) {
  return fetch('/api/portfolio/weights', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ weights }),
  }).then((r) => { if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || r.statusText) }); return r.json() })
}

/** Change one weight and scale all others proportionally so the total stays at 100. */
function rebalance(list, symbol, newW) {
  const clamped = Math.max(0, Math.min(100, newW))
  const others = list.filter((h) => h.symbol !== symbol)
  const otherSum = others.reduce((s, h) => s + (h.weight || 0), 0)
  const remaining = 100 - clamped
  let updated
  if (otherSum > 0 && remaining >= 0) {
    const scale = remaining / otherSum
    updated = list.map((h) =>
      h.symbol === symbol ? { ...h, weight: clamped }
        : { ...h, weight: Math.round(h.weight * scale * 10) / 10 }
    )
    // Fix floating-point drift so total is exactly 100
    const drift = Math.round((100 - updated.reduce((s, h) => s + h.weight, 0)) * 10) / 10
    if (drift !== 0) {
      const largest = [...updated].filter((h) => h.symbol !== symbol).sort((a, b) => b.weight - a.weight)[0]
      updated = updated.map((h) =>
        h.symbol === largest.symbol ? { ...h, weight: Math.round((h.weight + drift) * 10) / 10 } : h
      )
    }
  } else {
    updated = list.map((h) => h.symbol === symbol ? { ...h, weight: clamped } : h)
  }
  return updated
}

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

  const changeWeight = (symbol, raw) => {
    const w = Math.max(0, Math.min(100, Number(raw) || 0))
    setList((prev) => rebalance(prev, symbol, w))
  }

  const saveWeights = (currentList) => {
    const weights = Object.fromEntries(currentList.map((h) => [h.symbol, h.weight || 0]))
    putWeights(weights).catch((e) => setError(e.message))
  }

  const totalWeight = list ? Math.round(list.reduce((s, h) => s + (h.weight || 0), 0) * 10) / 10 : 0

  return (
    <Sheet title="Your portfolio" kicker={list ? `${list.length} holding${list.length === 1 ? '' : 's'}` : 'Holdings'} onClose={onClose}>
      <p className="muted">The weight you give each company boosts how its filings rank in Today.</p>

      <form className="ask" onSubmit={add}>
        <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="NSE symbol, e.g. HAVELLS"
          autoCapitalize="characters" autoCorrect="off" spellCheck="false" maxLength="20" aria-label="NSE symbol" />
        <button type="submit" disabled={!symbol.trim() || busy === 'add'}>{busy === 'add' ? 'Adding…' : 'Add'}</button>
      </form>
      {error && <p className="error">{error}</p>}

      {!list && <Spinner label="Loading your holdings" />}
      {list && (
        <>
          <div className="holdings">
            {list.map((holding) => (
              <div className="holding" key={holding.symbol}>
                <span className="holding-body">
                  <b>{holding.name}</b>
                  <span>{holding.symbol}{holding.researched && ' · researched'}</span>
                </span>
                <label className="weight-field" aria-label={`${holding.name} portfolio weight`}>
                  <input type="number" min="0" max="100" step="0.1"
                    value={holding.weight ?? 10}
                    onChange={(e) => changeWeight(holding.symbol, e.target.value)}
                    onBlur={() => saveWeights(list)} />
                  <span>%</span>
                </label>
                <button className="link" onClick={() => onResearch(holding.symbol)}>Research</button>
                <button className="link danger" disabled={busy === holding.symbol} onClick={() => drop(holding)}>
                  {busy === holding.symbol ? '…' : 'Remove'}
                </button>
              </div>
            ))}
            {list.length === 0 && <p className="muted">No holdings yet. Add an NSE symbol above.</p>}
          </div>
          {list.length > 0 && (
            <p className={`fine ${Math.abs(totalWeight - 100) > 0.5 ? 'warn' : ''}`}>
              Total: {totalWeight}%{totalWeight === 100 ? ' ✓' : ` — ${Math.round((100 - totalWeight) * 10) / 10}% unallocated`}.
              {' '}Filings from larger positions rank higher in Today.
            </p>
          )}
        </>
      )}
      <p className="fine">Saved on this app's server. Research already done for a company is kept even if you remove it.</p>
    </Sheet>
  )
}
