import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'

interface PinPadProps {
  length?: number
  onComplete: (pin: string) => void
  disabled?: boolean
  error?: string | null
  label?: string
}

export function PinPad({
  length = 4,
  onComplete,
  disabled = false,
  error,
  label = 'Enter PIN',
}: PinPadProps) {
  const [value, setValue] = useState('')

  // Route onComplete through a ref so the "fire when full" effect below
  // depends only on `value` / `length`. Callers almost always pass an
  // inline arrow function, which would otherwise re-trigger the effect
  // on every parent re-render and cause duplicate submits (the race
  // that produced the post-PIN white screen).
  const onCompleteRef = useRef(onComplete)
  useEffect(() => {
    onCompleteRef.current = onComplete
  })

  useEffect(() => {
    if (value.length === length) {
      onCompleteRef.current(value)
    }
  }, [value, length])

  useEffect(() => {
    if (error) setValue('')
  }, [error])

  function press(d: string) {
    if (disabled) return
    setValue((v) => (v.length < length ? v + d : v))
  }

  function backspace() {
    if (disabled) return
    setValue((v) => v.slice(0, -1))
  }

  return (
    <div className="w-full max-w-md mx-auto flex flex-col items-center gap-6 font-display">
      <div className="flex items-center gap-3 text-fluid-lg font-black text-brand-900">
        <span aria-hidden className="text-fluid-xl">🔒</span>
        {label}
      </div>

      <div className="flex gap-3">
        {Array.from({ length }, (_, i) => (
          <div
            key={i}
            className={clsx(
              'size-16 sm:size-20 rounded-2xl grid place-items-center text-fluid-xl font-black shadow-pop transition-transform',
              i < value.length
                ? 'bg-brand-600 text-white scale-[1.02] animate-pop-in'
                : 'bg-white text-brand-900 border-2 border-brand-100',
            )}
          >
            {i < value.length ? '•' : ''}
          </div>
        ))}
      </div>

      {error && (
        <div
          className="text-fluid-sm font-bold text-rose-600 animate-wiggle"
          role="alert"
        >
          {error}
        </div>
      )}

      <div className="grid grid-cols-3 gap-3 w-full">
        {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => press(d)}
            disabled={disabled}
            className="pin-key press min-h-touch rounded-2xl bg-white text-brand-900 shadow-card text-fluid-xl font-black disabled:opacity-50"
          >
            {d}
          </button>
        ))}
        <button
          type="button"
          onClick={backspace}
          disabled={disabled || value.length === 0}
          className="pin-key press min-h-touch rounded-2xl bg-brand-50 text-brand-700 shadow-card text-fluid-lg font-bold disabled:opacity-50"
          aria-label="backspace"
        >
          ⌫
        </button>
        <button
          type="button"
          onClick={() => press('0')}
          disabled={disabled}
          className="pin-key press min-h-touch rounded-2xl bg-white text-brand-900 shadow-card text-fluid-xl font-black disabled:opacity-50"
        >
          0
        </button>
        <button
          type="button"
          onClick={() => setValue('')}
          disabled={disabled || value.length === 0}
          className="pin-key press min-h-touch rounded-2xl bg-brand-50 text-brand-700 shadow-card text-fluid-sm font-bold disabled:opacity-50"
        >
          clear
        </button>
      </div>
    </div>
  )
}
