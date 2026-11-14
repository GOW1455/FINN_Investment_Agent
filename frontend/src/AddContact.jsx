import { useState } from 'react'
import { post, Sheet } from './ui.jsx'

const emptyRole = () => ({ company: '', title: '', from: '', to: '' })
const emptySchool = () => ({ school: '', degree: '', year: '' })
const year = (value) => (String(value).trim() === '' ? null : Number(value))
const today = () => new Date().toISOString().slice(0, 10)

/* A short form to add one person to the network. Only the name is required; the more career detail
   is given, the more often FINN can connect this person to a company or to someone in a filing. */
export default function AddContact({ onClose, onAdded }) {
  const [form, setForm] = useState({ name: '', relation: '', strength: 3, last_contact: today(), expertise: '', notes: '' })
  const [career, setCareer] = useState([emptyRole()])
  const [education, setEducation] = useState([emptySchool()])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value })
  const setRow = (rows, setRows, index, key) => (event) =>
    setRows(rows.map((row, i) => (i === index ? { ...row, [key]: event.target.value } : row)))

  const badYear = [...career.flatMap((r) => [r.from, r.to]), ...education.map((e) => e.year)]
    .some((v) => String(v).trim() !== '' && !(Number(v) >= 1950 && Number(v) <= 2100))
  const canSave = form.name.trim().length >= 2 && !badYear && !saving

  const save = (event) => {
    event.preventDefault()
    if (!canSave) return
    setSaving(true); setError('')
    post('/network/people', {
      name: form.name.trim(),
      relation: form.relation.trim(),
      strength: Number(form.strength),
      last_contact: form.last_contact,
      notes: form.notes.trim(),
      expertise: form.expertise.split(',').map((t) => t.trim()).filter(Boolean),
      career: career.filter((r) => r.company.trim()).map((r) => ({ company: r.company.trim(), title: r.title.trim(), from: year(r.from), to: year(r.to) })),
      education: education.filter((e) => e.school.trim()).map((e) => ({ school: e.school.trim(), degree: e.degree.trim(), year: year(e.year) })),
    })
      .then((person) => { onAdded(person); onClose() })
      .catch((e) => { setError(e.message); setSaving(false) })
  }

  return (
    <Sheet title="Add a contact" kicker="Your network" onClose={onClose}>
      <form className="contact-form" onSubmit={save}>
        <label>Name
          <input value={form.name} onChange={set('name')} maxLength="80" autoComplete="off" required />
        </label>
        <label>How you know them
          <input value={form.relation} onChange={set('relation')} maxLength="120" placeholder="e.g. Former colleague at Kotak" />
        </label>
        <div className="two">
          <label>Closeness
            <select value={form.strength} onChange={set('strength')}>
              <option value="5">5 · very close</option><option value="4">4 · close</option><option value="3">3 · friendly</option>
              <option value="2">2 · acquaintance</option><option value="1">1 · met once</option>
            </select>
          </label>
          <label>Last spoke
            <input type="date" value={form.last_contact} max={today()} onChange={set('last_contact')} />
          </label>
        </div>

        <h3>Where they have worked</h3>
        <p className="muted">Leave "To" empty for a current job. Company names are how FINN links this person to your holdings.</p>
        {career.map((role, i) => (
          <div className="group" key={i}>
            <input value={role.company} onChange={setRow(career, setCareer, i, 'company')} maxLength="80" placeholder="Company" aria-label={`Company ${i + 1}`} />
            <input value={role.title} onChange={setRow(career, setCareer, i, 'title')} maxLength="80" placeholder="Title" aria-label={`Title ${i + 1}`} />
            <div className="two">
              <input value={role.from} onChange={setRow(career, setCareer, i, 'from')} inputMode="numeric" placeholder="From (year)" aria-label={`From year ${i + 1}`} />
              <input value={role.to} onChange={setRow(career, setCareer, i, 'to')} inputMode="numeric" placeholder="To (year)" aria-label={`To year ${i + 1}`} />
            </div>
            {career.length > 1 && <button type="button" className="link" onClick={() => setCareer(career.filter((_, j) => j !== i))}>Remove this job</button>}
          </div>
        ))}
        <button type="button" className="link" onClick={() => setCareer([...career, emptyRole()])}>Add another job</button>

        <h3>Where they studied</h3>
        {education.map((school, i) => (
          <div className="group" key={i}>
            <input value={school.school} onChange={setRow(education, setEducation, i, 'school')} maxLength="80" placeholder="School or college" aria-label={`School ${i + 1}`} />
            <div className="two">
              <input value={school.degree} onChange={setRow(education, setEducation, i, 'degree')} maxLength="80" placeholder="Degree" aria-label={`Degree ${i + 1}`} />
              <input value={school.year} onChange={setRow(education, setEducation, i, 'year')} inputMode="numeric" placeholder="Year finished" aria-label={`Year finished ${i + 1}`} />
            </div>
            {education.length > 1 && <button type="button" className="link" onClick={() => setEducation(education.filter((_, j) => j !== i))}>Remove this school</button>}
          </div>
        ))}
        <button type="button" className="link" onClick={() => setEducation([...education, emptySchool()])}>Add another school</button>

        <h3>What they know</h3>
        <label>Expertise, separated by commas
          <input value={form.expertise} onChange={set('expertise')} placeholder="e.g. paints, dealer distribution" />
        </label>
        <label>Notes
          <textarea rows="2" value={form.notes} onChange={set('notes')} maxLength="400" placeholder="Anything worth remembering about them" />
        </label>

        {badYear && <p className="error">Years must be four digits, such as 2019.</p>}
        {error && <p className="error">Could not save: {error}</p>}
        <button className="button" type="submit" disabled={!canSave}>{saving ? 'Saving…' : 'Add to my network'}</button>
        <p className="fine">Saved on this app's server and used straight away in "who should I call" and filing cards.</p>
      </form>
    </Sheet>
  )
}
