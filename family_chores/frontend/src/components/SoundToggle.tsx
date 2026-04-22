import { useUIStore } from '../store/ui'

export function SoundToggle() {
  const enabled = useUIStore((s) => s.soundEnabled)
  const set = useUIStore((s) => s.setSoundEnabled)
  return (
    <button
      type="button"
      onClick={() => set(!enabled)}
      className="min-h-touch min-w-touch grid place-items-center rounded-2xl text-fluid-lg bg-brand-50 text-brand-700 hover:bg-brand-100"
      aria-label={enabled ? 'Mute completion chime' : 'Enable completion chime'}
      aria-pressed={enabled}
      title={enabled ? 'Sound on' : 'Sound off'}
    >
      <span aria-hidden>{enabled ? '🔔' : '🔕'}</span>
    </button>
  )
}
