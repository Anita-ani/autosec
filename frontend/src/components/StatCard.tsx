interface Props {
  label: string
  value: number
  accent?: string
}

export function StatCard({ label, value, accent = '#4f8ef7' }: Props) {
  return (
    <div className="stat-card" style={{ borderTop: `3px solid ${accent}` }}>
      <div className="stat-value">{value.toLocaleString()}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}
