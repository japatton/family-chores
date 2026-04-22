import { useEffect, useState } from 'react'
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

  useEffect(() => {
    if (value.length === length) {
      onComplete(value)
    }
  }, [value, length, onComplete])

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
    <div className="w-full max-w-md mx-auto flex flex-col items-center gap-6">
      <div className="text-fluid-lg font-black text-brand-900">{label}</div>

      <div className="flex gap-3">
        {Array.from({ length }, (_, i) => (
          <div
            key={i}
            className={clsx(
              'size-14 sm:size-16 rounded-2xl border-2 grid place-items-center text-fluid-xl font-black',
              i < value.length
                ? 'bg-brand-600 border-brand-600 text-white'
                : 'bg-white border-brand-100 text-brand-900',
            )}
          >
            {i < value.length ? '•' : ''}
          </div>
        ))}
      </div>

      {error && (
        <div className="text-fluid-sm font-semibold text-rose-600" role="alert">
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
            className="pin-key min-h-touch rounded-2xl bg-white text-brand-900 shadow-card text-fluid-xl font-black active:scale-[0.98] disabled:opacity-50"
          >
            {d}
          </button>
        ))}
        <button
          type="button"
          onClick={backspace}
          disabled={disabled || value.length === 0}
          className="pin-key min-h-touch rounded-2xl bg-brand-50 text-brand-700 shadow-card text-fluid-base font-bold active:scale-[0.98] disabled:opacity-50"
          aria-label="backspace"
        >
          ⌫
        </button>
        <button
          type="button"
          onClick={() => press('0')}
          disabled={disabled}
          className="pin-key min-h-touch rounded-2xl bg-white text-brand-900 shadow-card text-fluid-xl font-black active:scale-[0.98] disabled:opacity-50"
        >
          0
        </button>
        <button
          type="button"
          onClick={() => setValue('')}
          disabled={disabled || value.length === 0}
          className="pin-key min-h-touch rounded-2xl bg-brand-50 text-brand-700 shadow-card text-fluid-sm font-bold active:scale-[0.98] disabled:opacity-50"
        >
          clear
        </button>
      </div>
    </div>
  )
}
