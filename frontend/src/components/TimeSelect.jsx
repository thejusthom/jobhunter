const HOURS = Array.from({ length: 17 }, (_, i) => (i + 6).toString().padStart(2, '0')) // 06-22
const MINS = ['00', '15', '30', '45']

export default function TimeSelect({ value, onChange, className = '' }) {
  const [h, m] = (value || '09:00').split(':')

  const emit = (newH, newM) => onChange({ target: { value: `${newH}:${newM}` } })

  return (
    <div className="flex gap-1">
      <select value={h} onChange={e => emit(e.target.value, m)} className={className}>
        {HOURS.map(hr => <option key={hr} value={hr}>{hr}</option>)}
      </select>
      <select value={MINS.includes(m) ? m : '00'} onChange={e => emit(h, e.target.value)} className={className}>
        {MINS.map(mn => <option key={mn} value={mn}>{mn}</option>)}
      </select>
    </div>
  )
}
