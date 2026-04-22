import confetti from 'canvas-confetti'

/**
 * Imperative confetti burst — we never mount Confetti into the React tree
 * because canvas-confetti creates/destroys its own DOM nodes. Called from
 * handlers that already ran through the server round-trip so we know the
 * completion actually stuck.
 */
export function fireConfetti({
  accent,
  particles = 120,
}: {
  accent?: string | null
  particles?: number
} = {}): void {
  const palette =
    accent && /^#[0-9a-f]{6}$/i.test(accent)
      ? [accent, '#ffffff', '#ffe97a']
      : ['#6366f1', '#f97316', '#22c55e', '#ec4899', '#eab308']
  // Two quick bursts feel more celebratory than a single cone.
  confetti({
    particleCount: Math.max(30, Math.round(particles * 0.6)),
    spread: 80,
    origin: { y: 0.62, x: 0.3 },
    colors: palette,
    disableForReducedMotion: true,
  })
  confetti({
    particleCount: Math.max(30, Math.round(particles * 0.6)),
    spread: 80,
    origin: { y: 0.62, x: 0.7 },
    colors: palette,
    disableForReducedMotion: true,
  })
}
