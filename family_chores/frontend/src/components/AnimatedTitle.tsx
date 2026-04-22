import type { CSSProperties } from 'react'

/**
 * 3D block-letter title with a per-letter colour palette and a ripple
 * wave animation. Each letter is its own `<span>` so `text-shadow` can
 * fake extruded "3D" depth per-letter (a stack of offset copies of the
 * letter in a darker shade), and so each letter can be given a
 * staggered `animation-delay` — the result is a wave passing through
 * the word like a choir singing in sequence.
 *
 * Respects `prefers-reduced-motion` via the blanket rule in globals.css
 * (the `.fc-block-letter` class is listed there).
 */

interface AnimatedTitleProps {
  text: string
  /** Per-letter fill colours; cycled if shorter than `text`. */
  colors?: string[]
  /** CSS Tailwind class for size — defaults to a fluid header size. */
  sizeClass?: string
  /** Base animation delay stagger between letters, ms. */
  stepMs?: number
}

const DEFAULT_COLORS = [
  '#ec4899', // bubblegum
  '#f97316', // candy
  '#f59e0b', // sunshine
  '#22c55e', // mint
  '#3b82f6', // sky
  '#a855f7', // purple
]

export function AnimatedTitle({
  text,
  colors = DEFAULT_COLORS,
  sizeClass = 'text-[clamp(1.75rem,3.2vw,3.25rem)]',
  stepMs = 90,
}: AnimatedTitleProps) {
  return (
    <h1
      className={`fc-block-letters font-display font-bold leading-none select-none ${sizeClass}`}
      aria-label={text}
    >
      {Array.from(text).map((ch, i) => {
        if (ch === ' ') {
          return (
            <span
              key={i}
              aria-hidden
              className="inline-block"
              style={{ width: '0.35em' }}
            />
          )
        }
        const color = colors[i % colors.length]
        const style: CSSProperties = {
          ['--letter' as string]: color,
          ['--letter-shadow' as string]: `color-mix(in srgb, ${color} 55%, black)`,
          animationDelay: `${i * stepMs}ms`,
        }
        return (
          <span
            key={i}
            aria-hidden
            className="fc-block-letter inline-block"
            style={style}
          >
            {ch}
          </span>
        )
      })}
    </h1>
  )
}
