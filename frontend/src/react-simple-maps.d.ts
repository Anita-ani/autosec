declare module 'react-simple-maps' {
  import type { ComponentType, ReactNode, SVGProps } from 'react'

  interface GeographiesChildrenProps {
    geographies: Array<{ rsmKey: string; id: string | number; [key: string]: unknown }>
  }

  export const ComposableMap: ComponentType<{ projectionConfig?: { scale?: number }; [key: string]: unknown }>
  export const Geographies: ComponentType<{
    geography: string
    children: (props: GeographiesChildrenProps) => ReactNode
    [key: string]: unknown
  }>
  export const Geography: ComponentType<{ geography: unknown; fill?: string; stroke?: string; strokeWidth?: number; style?: { default?: object; hover?: object; pressed?: object }; onMouseMove?: (e: React.MouseEvent) => void; onMouseLeave?: () => void; [key: string]: unknown }>
}
