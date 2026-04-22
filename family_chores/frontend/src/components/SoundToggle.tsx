import { useUIStore } from '../store/ui'
import { Cowbell } from './Cowbell'

export function SoundToggle() {
  const enabled = useUIStore((s) => s.soundEnabled)
  const set = useUIStore((s) => s.setSoundEnabled)
  return (
    <button
      type="button"
      onClick={() => set(!enabled)}
      className="min-h-touch min-w-touch grid place-items-center rounded-2xl bg-brand-50 hover:bg-brand-100 px-2"
      aria-label={enabled ? 'Mute completion chime' : 'Enable completion chime'}
      aria-pressed={enabled}
      title={enabled ? 'Sound on' : 'Sound off'}
    >
      <Cowbell muted={!enabled} size={40} />
    </button>
  )
}
