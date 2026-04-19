import type { Alert } from '../types'

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#e74c3c',
  high: '#e67e22',
  medium: '#f1c40f',
  low: '#2ecc71',
}

interface Props {
  alerts: Alert[]
  newIds?: Set<string>
}

export function AlertsTable({ alerts, newIds }: Props) {
  if (alerts.length === 0) {
    return <div className="empty-state">No alerts</div>
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>Source IP</th>
            <th>Severity</th>
            <th>Message</th>
            <th>Status</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((a) => (
            <tr key={a.id} className={newIds?.has(a.id) ? 'alert-new' : ''}>
              <td>
                <code>{a.alert_type}</code>
              </td>
              <td>{a.source_ip}</td>
              <td>
                <span
                  className="badge"
                  style={{
                    background:
                      SEVERITY_COLOR[a.severity?.toLowerCase()] ?? '#95a5a6',
                  }}
                >
                  {a.severity}
                </span>
              </td>
              <td className="msg-cell">{a.message}</td>
              <td>
                <span className={`badge ${a.resolved ? 'resolved' : 'open'}`}>
                  {a.resolved ? 'resolved' : 'open'}
                </span>
              </td>
              <td className="ts">
                {a.created_at
                  ? new Date(a.created_at).toLocaleString()
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
