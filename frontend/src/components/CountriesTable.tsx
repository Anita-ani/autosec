import type { Country } from '../types'

interface Props {
  countries: Country[]
}

export function CountriesTable({ countries }: Props) {
  if (countries.length === 0) {
    return <div className="empty-state">No geo-enriched events in the last 24h</div>
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Country</th>
            <th>Code</th>
            <th>Events</th>
          </tr>
        </thead>
        <tbody>
          {countries.map((c, i) => (
            <tr key={c.country_code}>
              <td>{i + 1}</td>
              <td>{c.country}</td>
              <td>
                <code>{c.country_code}</code>
              </td>
              <td>{c.count.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
