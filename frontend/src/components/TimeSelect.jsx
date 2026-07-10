const TIMES = Array.from({ length: 68 }, (_, i) => {
  const totalMins = 360 + i * 15  // 06:00 to 22:45
  const h = Math.floor(totalMins / 60).toString().padStart(2, '0')
  const m = (totalMins % 60).toString().padStart(2, '0')
  return `${h}:${m}`
})

export default function TimeSelect({ value, onChange, className = '' }) {
  return (
    <select value={value} onChange={onChange} className={className}>
      {TIMES.map(t => <option key={t} value={t}>{t}</option>)}
    </select>
  )
}
