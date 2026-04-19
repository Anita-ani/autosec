import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'

const COLORS: Record<string, string> = {
  critical: '#e74c3c',
  high: '#e67e22',
  medium: '#f1c40f',
  low: '#2ecc71',
}

const DEFAULT_COLOR = '#95a5a6'

interface Props {
  data: Record<string, number>
}

export function SeverityPieChart({ data }: Props) {
  const entries = Object.entries(data).map(([name, value]) => ({ name, value }))

  if (entries.length === 0) {
    return <div className="empty-state">No alert data</div>
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={entries}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          outerRadius={90}
          label={({ name, percent }: { name?: string; percent?: number }) =>
            name ? `${name} ${((percent ?? 0) * 100).toFixed(0)}%` : ''
          }
        >
          {entries.map((entry) => (
            <Cell
              key={entry.name}
              fill={COLORS[entry.name.toLowerCase()] ?? DEFAULT_COLOR}
            />
          ))}
        </Pie>
        <Tooltip formatter={(val) => [val, 'alerts']} />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  )
}
