import { useEffect, useRef, useState } from 'react'

export async function api(path) {
  const response = await fetch(`/api${path}`)
  if (!response.ok) {
    let detail = ''
    try { detail = (await response.json()).detail } catch { /* not JSON */ }
    throw new Error(detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export async function post(path, body) {
  const response = await fetch(`/api${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = ''
    try { detail = (await response.json()).detail } catch { /* not JSON */ }
    throw new Error(typeof detail === 'string' && detail ? detail : `Request failed (${response.status})`)
  }
  return response.json()
}

export async function remove(path) {
  const response = await fetch(`/api${path}`, { method: 'DELETE' })
  if (!response.ok) {
    let detail = ''
    try { detail = (await response.json()).detail } catch { /* not JSON */ }
    throw new Error(typeof detail === 'string' && detail ? detail : `Request failed (${response.status})`)
  }
  return response.json()
}

/* Tell every open screen that the network changed, so lists and rankings reload. */
export const NETWORK_CHANGED = 'finn:network-changed'

export const crore = (value) =>
  value == null ? '–' : Number(value).toLocaleString('en-IN', { maximumFractionDigits: Math.abs(value) < 100 ? 1 : 0 })

export function Delta({ value, suffix = '%' }) {
  if (value == null) return <span className="delta flat">–</span>
  const cls = value > 0 ? 'up' : value < 0 ? 'down' : 'flat'
  return <span className={`delta ${cls}`}>{value > 0 ? '+' : ''}{value}{suffix}</span>
}

export function ago(days) {
  if (days == null) return ''
  if (days < 1) return 'today'
  if (days < 45) return `${days}d ago`
  if (days < 365) return `${Math.round(days / 30)} mo ago`
  return `${(days / 365).toFixed(1)} yr ago`
}

export function timeLabel(stamp) {
  // 'YYYY-MM-DD HH:MM:SS' in exchange time (IST)
  if (!stamp) return ''
  const [date, time] = stamp.split(' ')
  const [, month, day] = date.split('-')
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${Number(day)} ${months[Number(month) - 1]}, ${time.slice(0, 5)}`
}

const initials = (name) => name.split(' ').map((part) => part[0]).slice(0, 2).join('')

export function Avatar({ name, strength }) {
  return (
    <span className="avatar" aria-hidden="true">
      {initials(name)}
      {strength != null && <i className={`ring s${strength}`} />}
    </span>
  )
}

/* One contact, with the reason they matter. The reason is the product; the name is secondary. */
export function PersonRow({ person, onOpen, compact }) {
  const cold = person.days_since_contact != null && person.days_since_contact > 180
  return (
    <button className={`person ${compact ? 'compact' : ''}`} onClick={() => onOpen?.(person.id)}>
      <Avatar name={person.name} strength={person.strength} />
      <span className="person-body">
        <span className="person-top">
          <b>{person.name}</b>
          {person.angle && <em className={`angle ${person.angle.replace(' ', '-')}`}>{person.angle}</em>}
          {person.link && <em className={`angle link-${person.link}`}>{person.link} link</em>}
        </span>
        {person.why && <span className="person-why">{person.why}</span>}
        {!compact && person.links?.map((link, i) => <span className="person-why" key={i}>{link.detail}</span>)}
        {!compact && person.knows && <span className="person-knows">{person.knows}</span>}
        {!compact && (
          <span className="person-meta">
            {person.relation}
            {person.days_since_contact != null && (
              <span className={cold ? 'cold' : ''}> · last spoke {ago(person.days_since_contact)}</span>
            )}
          </span>
        )}
      </span>
    </button>
  )
}

export function Sheet({ title, kicker, onClose, children }) {
  useEffect(() => {
    const onKey = (event) => event.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])
  return (
    <div className="sheet-wrap" onClick={onClose}>
      <section className="sheet" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <div>
            {kicker && <div className="kicker">{kicker}</div>}
            <h2>{title}</h2>
          </div>
          <button className="close" onClick={onClose} aria-label="Close">×</button>
        </header>
        <div className="sheet-body">{children}</div>
      </section>
    </div>
  )
}

export function PersonSheet({ id, onClose }) {
  const [person, setPerson] = useStateSafe(null)
  useEffect(() => { api(`/network/person/${id}`).then(setPerson).catch(() => setPerson({ error: true })) }, [id])
  if (!person) return <Sheet title="Loading" onClose={onClose}><p className="muted">One moment.</p></Sheet>
  if (person.error) return <Sheet title="Not found" onClose={onClose}><p className="muted">This contact could not be loaded.</p></Sheet>
  return (
    <Sheet title={person.name} kicker={person.relation} onClose={onClose}>
      <p className="lede">{person.headline}</p>
      <div className="facts-row">
        <div><span>Closeness</span><b>{'●'.repeat(person.strength)}<i>{'●'.repeat(5 - person.strength)}</i></b></div>
        <div><span>Last spoke</span><b>{ago(person.days_since_contact) || '–'}</b></div>
        <div><span>Covers</span><b>{person.portfolio_companies.length ? person.portfolio_companies.join(', ') : '–'}</b></div>
      </div>
      {person.notes && <p className="note">“{person.notes}”</p>}
      {person.shared_with_you.length > 0 && (
        <p className="shared">{person.shared_with_you.join(' · ')}</p>
      )}
      <h3>Career</h3>
      <ol className="timeline">
        {[...person.career].reverse().map((role, i) => (
          <li key={i}>
            <b>{role.title}</b>, {role.company}
            <span>{role.from}–{role.to || 'now'}</span>
            {role.knows && <em>{role.knows}</em>}
          </li>
        ))}
      </ol>
      <h3>Education</h3>
      <ol className="timeline">
        {person.education.map((school, i) => (
          <li key={i}><b>{school.school}</b>, {school.degree}<span>{school.year}</span></li>
        ))}
      </ol>
      <div className="tags">{person.expertise.map((tag) => <span key={tag}>{tag}</span>)}</div>
      {person.added ? (
        <div className="links">
          <p className="fine">You added this contact.</p>
          <button className="button ghost danger" onClick={() => {
            if (!window.confirm(`Remove ${person.name} from your network?`)) return
            remove(`/network/person/${person.id}`)
              .then(() => { window.dispatchEvent(new Event(NETWORK_CHANGED)); onClose() })
              .catch((e) => window.alert(`Could not remove: ${e.message}`))
          }}>Remove from my network</button>
        </div>
      ) : (
        <p className="fine">Synthetic profile, created for this demo.</p>
      )}
    </Sheet>
  )
}

/* setState that ignores updates after unmount, for fetches that outlive a closed sheet. */
export function useStateSafe(initial) {
  const [value, setValue] = useState(initial)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false }
  }, [])
  return [value, (next) => alive.current && setValue(next)]
}

export function Spinner({ label }) {
  return <div className="spinner" role="status"><i />{label}</div>
}
