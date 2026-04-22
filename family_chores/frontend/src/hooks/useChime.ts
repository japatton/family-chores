import { useCallback, useRef } from 'react'
import { useUIStore } from '../store/ui'

/**
 * Completion chime — synthesised via Web Audio so the add-on ships no
 * audio binary. A short two-note bell: A5 → C#6 (major third up) with
 * exponential decay, runs ~500 ms. Silent failure if the browser has
 * blocked AudioContext (happens when the first tap in a session hasn't
 * landed yet — the next tap will work).
 */
export function useChime(): () => void {
  const enabled = useUIStore((s) => s.soundEnabled)
  const ctxRef = useRef<AudioContext | null>(null)

  return useCallback(() => {
    if (!enabled) return
    try {
      const AudioCtor =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext
      if (!AudioCtor) return
      if (!ctxRef.current) {
        ctxRef.current = new AudioCtor()
      }
      const ctx = ctxRef.current
      if (ctx.state === 'suspended') void ctx.resume()

      const now = ctx.currentTime
      const osc = ctx.createOscillator()
      osc.type = 'sine'
      osc.frequency.setValueAtTime(880, now) // A5
      osc.frequency.setValueAtTime(1108.73, now + 0.11) // C#6

      const gain = ctx.createGain()
      gain.gain.setValueAtTime(0.0001, now)
      gain.gain.exponentialRampToValueAtTime(0.35, now + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.55)

      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start(now)
      osc.stop(now + 0.6)
    } catch {
      // Audio blocked or unsupported — silently skip.
    }
  }, [enabled])
}
