import type { BlockedIp } from '../types'

interface Props {
  ips: BlockedIp[]
}

export function BlockedIpsTable({ ips }: Props) {
  if (ips.length === 0) {
    return <div className="empty-state">No blocked IPs</div>
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>IP</th>
            <th>Reason</th>
            <th>Triggered by</th>
            <th>Blocked at</th>
          </tr>
        </thead>
        <tbody>
          {ips.map((ip) => (
            <tr key={ip.ip + ip.blocked_at}>
              <td>
                <code>{ip.ip}</code>
              </td>
              <td>{ip.reason ?? '—'}</td>
              <td>{ip.triggered_by ?? '—'}</td>
              <td className="ts">
                {ip.blocked_at
                  ? new Date(ip.blocked_at).toLocaleString()
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
