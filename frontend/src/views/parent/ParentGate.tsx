import { useState } from 'react'
import { APIError } from '../../api/client'
import { useSetPin, useVerifyPin, useWhoami } from '../../api/hooks'
import { PinPad } from '../../components/PinPad'
import { useParentStore } from '../../store/parent'

interface ParentGateProps {
  children: React.ReactNode
}

export function ParentGate({ children }: ParentGateProps) {
  const whoami = useWhoami()
  const isActive = useParentStore((s) => s.isActive())

  if (whoami.isLoading) {
    return (
      <p className="text-fluid-base text-brand-700 text-center">Loading…</p>
    )
  }
  if (!whoami.data) return null

  if (!whoami.data.parent_pin_set) {
    return <FirstPinSetup />
  }

  if (isActive) {
    return <>{children}</>
  }
  return <VerifyPin />
}

function FirstPinSetup() {
  const setPin = useSetPin()
  const verifyPin = useVerifyPin()
  const [stage, setStage] = useState<'choose' | 'confirm'>('choose')
  const [firstPin, setFirstPin] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleChoose = (pin: string) => {
    setFirstPin(pin)
    setStage('confirm')
    setError(null)
  }
  const handleConfirm = (pin: string) => {
    if (pin !== firstPin) {
      setError("PINs didn't match. Try again.")
      setStage('choose')
      setFirstPin('')
      return
    }
    setPin.mutate(
      { pin },
      {
        onSuccess: () => {
          verifyPin.mutate(pin)
        },
        onError: (e) =>
          setError(e instanceof Error ? e.message : 'Failed to set PIN'),
      },
    )
  }

  return (
    <div className="max-w-md mx-auto text-center space-y-6 py-8">
      <h1 className="text-fluid-xl font-black text-brand-900">Set a parent PIN</h1>
      <p className="text-fluid-base text-brand-700">
        Used to unlock parent mode on this tablet. It's a soft lock to keep
        kids out of admin — not a security boundary.
      </p>
      <PinPad
        key={stage}
        label={stage === 'choose' ? 'Choose a 4-digit PIN' : 'Confirm PIN'}
        onComplete={stage === 'choose' ? handleChoose : handleConfirm}
        disabled={setPin.isPending || verifyPin.isPending}
        error={error}
      />
    </div>
  )
}

function VerifyPin() {
  const verify = useVerifyPin()
  const [error, setError] = useState<string | null>(null)
  return (
    <div className="max-w-md mx-auto text-center space-y-6 py-8">
      <h1 className="text-fluid-xl font-black text-brand-900">Parent mode</h1>
      <p className="text-fluid-base text-brand-700">Enter PIN to continue.</p>
      <PinPad
        onComplete={(pin) => {
          setError(null)
          verify.mutate(pin, {
            onError: (e) => {
              if (e instanceof APIError && e.errorCode === 'pin_invalid') {
                setError('Incorrect PIN. Try again.')
              } else {
                setError(e instanceof Error ? e.message : 'Something went wrong')
              }
            },
          })
        }}
        disabled={verify.isPending}
        error={error}
      />
    </div>
  )
}
