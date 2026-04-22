import type { ReactNode } from 'react'
import clsx from 'clsx'

interface BannerProps {
  variant?: 'info' | 'warn' | 'success'
  children: ReactNode
}

export function Banner({ variant = 'info', children }: BannerProps) {
  return (
    <div
      role="status"
      className={clsx(
        'rounded-2xl px-5 py-3 text-fluid-sm font-semibold shadow-card',
        variant === 'info' && 'bg-brand-50 text-brand-700 border border-brand-100',
        variant === 'warn' && 'bg-amber-50 text-amber-900 border border-amber-200',
        variant === 'success' &&
          'bg-emerald-50 text-emerald-900 border border-emerald-200',
      )}
    >
      {children}
    </div>
  )
}
