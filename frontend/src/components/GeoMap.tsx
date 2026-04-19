import { useState } from 'react'
import { ComposableMap, Geographies, Geography } from 'react-simple-maps'
import type { Country } from '../types'

// Maps ISO 3166-1 alpha-2 → numeric (as used in countries-110m.json)
const A2_TO_NUM: Record<string, number> = {
  AF:4,AL:8,DZ:12,AO:24,AR:32,AU:36,AT:40,AZ:31,BS:44,BH:48,BD:50,
  BE:56,BJ:204,BT:64,BO:68,BA:70,BW:72,BR:76,BN:96,BG:100,BF:854,
  BI:108,KH:116,CM:120,CA:124,CF:140,TD:148,CL:152,CN:156,CO:170,
  CD:180,CG:178,CR:188,HR:191,CU:192,CY:196,CZ:203,DK:208,DJ:262,
  DO:214,EC:218,EG:818,SV:222,GQ:226,ER:232,EE:233,ET:231,FI:246,
  FR:250,GA:266,GM:270,GE:268,DE:276,GH:288,GR:300,GT:320,GN:324,
  GW:624,GY:328,HT:332,HN:340,HU:348,IN:356,ID:360,IR:364,IQ:368,
  IE:372,IL:376,IT:380,JM:388,JP:392,JO:400,KZ:398,KE:404,KP:408,
  KR:410,KW:414,KG:417,LA:418,LV:428,LB:422,LR:430,LY:434,LT:440,
  LU:442,MK:807,MG:450,MW:454,MY:458,ML:466,MR:478,MX:484,MD:498,
  MN:496,MA:504,MZ:508,MM:104,NA:516,NP:524,NL:528,NZ:554,NI:558,
  NE:562,NG:566,NO:578,OM:512,PK:586,PA:591,PG:598,PY:600,PE:604,
  PH:608,PL:616,PT:620,PR:630,QA:634,RO:642,RU:643,RW:646,SA:682,
  SN:686,SL:694,SO:706,ZA:710,SS:728,ES:724,LK:144,SD:729,SR:740,
  SE:752,CH:756,SY:760,TW:158,TJ:762,TZ:834,TH:764,TG:768,TT:780,
  TN:788,TR:792,TM:795,UG:800,UA:804,AE:784,GB:826,US:840,UY:858,
  UZ:860,VE:862,VN:704,YE:887,ZM:894,ZW:716,HK:344,SG:702,MU:480,
}

// Reverse map built once at module level
const NUM_TO_A2: Record<number, string> = Object.fromEntries(
  Object.entries(A2_TO_NUM).map(([a2, num]) => [num, a2]),
)

interface Props {
  countries: Country[]
}

interface TooltipState {
  x: number
  y: number
  label: string
}

export function GeoMap({ countries }: Props) {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)

  const countByA2 = Object.fromEntries(countries.map(c => [c.country_code, c.count]))
  const maxCount  = Math.max(...Object.values(countByA2), 1)

  function fillFor(numericId: string | number) {
    const a2    = NUM_TO_A2[Number(numericId)]
    const count = a2 ? (countByA2[a2] ?? 0) : 0
    if (count === 0) return 'var(--map-land)'
    const intensity = 0.25 + (count / maxCount) * 0.75
    return `rgba(79, 142, 247, ${intensity.toFixed(2)})`
  }

  return (
    <div className="geo-map-wrap">
      <ComposableMap projectionConfig={{ scale: 140 }}>
        <Geographies geography="/countries-110m.json">
          {({ geographies }) =>
            geographies.map((geo) => {
              const a2    = NUM_TO_A2[Number(geo.id)]
              const count = a2 ? (countByA2[a2] ?? 0) : 0
              const label = a2
                ? `${countries.find(c => c.country_code === a2)?.country ?? a2}: ${count.toLocaleString()} events`
                : ''

              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill={fillFor(geo.id)}
                  stroke="var(--map-border)"
                  strokeWidth={0.4}
                  style={{
                    default: { outline: 'none' },
                    hover:   { outline: 'none', opacity: 0.8 },
                    pressed: { outline: 'none' },
                  }}
                  onMouseMove={(e: React.MouseEvent) => {
                    if (label) setTooltip({ x: e.clientX + 12, y: e.clientY - 28, label })
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />
              )
            })
          }
        </Geographies>
      </ComposableMap>

      {tooltip && (
        <div
          className="geo-tooltip"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.label}
        </div>
      )}
    </div>
  )
}
