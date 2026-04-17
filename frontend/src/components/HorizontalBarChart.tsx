import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

interface Props {
  data: Record<string, number>
  color?: string
  label?: string
}

export function HorizontalBarChart({ data, color = '#4f8ef7', label = 'count' }: Props) {
  const entries = Object.entries(data)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  if (entries.length === 0) {
    return <div className="empty-state">No data</div>
  }

  const height = Math.max(180, entries.length * 34)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={entries}
        layout="vertical"
        margin={{ left: 10, right: 20, top: 4, bottom: 4 }}
      >
        <XAxis type="number" tick={{ fontSize: 12 }} allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="name"
          width={160}
          tick={{ fontSize: 11 }}
          tickFormatter={(v: string) =>
            v.length > 22 ? v.slice(0, 21) + '…' : v
          }
        />
        <Tooltip formatter={(val: number) => [val, label]} />
        <Bar dataKey="value" radius={[0, 3, 3, 0]}>
          {entries.map((entry) => (
            <Cell key={entry.name} fill={color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
