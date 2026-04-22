import type { CSSProperties, ReactNode } from 'react'

/**
 * Full-viewport decorative layer. Renders ~12 SVG silhouettes of
 * generic kid-media iconography (wizard hat, rocket, castle, crown,
 * dinosaur, ghost, UFO, controller, sword, magic wand, heart, star)
 * scattered around the edges so the middle stays clear for content.
 *
 * Each shape has its own slow float/drift animation (see globals.css
 * keyframes) with a different duration and delay so they don't sync.
 * Opacity ~0.18 — vivid enough to read as playful from a distance,
 * subtle enough that text stays readable on top.
 *
 * `pointer-events-none` + `aria-hidden` → zero tap-target interference,
 * screen readers skip. Respects `prefers-reduced-motion` via the
 * blanket rule in globals.css.
 */

interface ShapePlacement {
  svg: ReactNode
  size: number
  color: string
  style: CSSProperties
  animation: string
  delayMs: number
}

const V = (children: ReactNode, viewBox = '0 0 100 100') => (
  <svg viewBox={viewBox} xmlns="http://www.w3.org/2000/svg">{children}</svg>
)

const WizardHat = V(
  <g fill="currentColor">
    <path d="M50 8 L30 78 L70 78 Z" />
    <rect x="22" y="76" width="56" height="10" rx="3" />
    <circle cx="45" cy="35" r="2.5" fill="#fff" fillOpacity=".6" />
    <circle cx="55" cy="55" r="1.8" fill="#fff" fillOpacity=".6" />
  </g>,
)
const Rocket = V(
  <g fill="currentColor">
    <path d="M50 8 Q34 38 34 64 L34 76 L66 76 L66 64 Q66 38 50 8 Z" />
    <circle cx="50" cy="44" r="6" fill="#fff" fillOpacity=".55" />
    <path d="M34 70 L22 90 L40 80 Z" />
    <path d="M66 70 L78 90 L60 80 Z" />
    <path d="M44 76 L50 92 L56 76 Z" fillOpacity=".7" />
  </g>,
)
const Castle = V(
  <g fill="currentColor">
    <rect x="15" y="35" width="70" height="55" />
    <path d="M10 35 H22 L22 24 H16 V29 H10 Z" />
    <path d="M40 35 H60 L60 20 H40 Z" />
    <path d="M78 35 H90 L90 24 H84 V29 H78 Z" />
    <rect x="44" y="55" width="12" height="22" rx="6" fill="#fff" fillOpacity=".35" />
    <circle cx="50" cy="16" r="3" />
    <rect x="49" y="16" width="2" height="10" />
  </g>,
)
const Crown = V(
  <g fill="currentColor">
    <path d="M10 70 L18 28 L38 58 L50 22 L62 58 L82 28 L90 70 Z" />
    <rect x="10" y="70" width="80" height="12" rx="3" />
    <circle cx="18" cy="28" r="4" />
    <circle cx="50" cy="22" r="4" />
    <circle cx="82" cy="28" r="4" />
  </g>,
)
const Star = V(
  <path
    fill="currentColor"
    d="M50 5 L62 38 L97 38 L69 60 L80 95 L50 74 L20 95 L31 60 L3 38 L38 38 Z"
  />,
)
const Heart = V(
  <path
    fill="currentColor"
    d="M50 88 C20 68 8 48 8 32 C8 18 18 8 30 8 C40 8 47 14 50 22 C53 14 60 8 70 8 C82 8 92 18 92 32 C92 48 80 68 50 88 Z"
  />,
)
const Dinosaur = V(
  <g fill="currentColor">
    <path d="M14 72 Q14 52 34 48 Q42 24 66 24 Q86 24 92 48 L98 54 L90 58 L86 68 L78 68 L74 56 L50 56 L46 82 L34 82 L40 56 Q26 56 20 72 Z" />
    <circle cx="78" cy="38" r="2.5" fill="#fff" fillOpacity=".7" />
  </g>,
  '0 0 110 100',
)
const Ghost = V(
  <g fill="currentColor">
    <path d="M20 42 Q20 12 50 12 Q80 12 80 42 L80 88 L70 78 L60 88 L50 78 L40 88 L30 78 L20 88 Z" />
    <circle cx="40" cy="42" r="4" fill="#fff" fillOpacity=".85" />
    <circle cx="60" cy="42" r="4" fill="#fff" fillOpacity=".85" />
    <ellipse cx="50" cy="58" rx="6" ry="4" fill="#fff" fillOpacity=".45" />
  </g>,
)
const UFO = V(
  <g fill="currentColor">
    <ellipse cx="50" cy="60" rx="44" ry="8" />
    <path d="M28 60 Q28 32 50 32 Q72 32 72 60 Z" fillOpacity=".8" />
    <circle cx="38" cy="60" r="3" fill="#fff" fillOpacity=".5" />
    <circle cx="50" cy="60" r="3" fill="#fff" fillOpacity=".5" />
    <circle cx="62" cy="60" r="3" fill="#fff" fillOpacity=".5" />
  </g>,
)
const Controller = V(
  <g fill="currentColor">
    <rect x="10" y="30" width="80" height="42" rx="20" />
    <rect x="23" y="46" width="12" height="4" fill="#fff" fillOpacity=".55" />
    <rect x="27" y="42" width="4" height="12" fill="#fff" fillOpacity=".55" />
    <circle cx="68" cy="45" r="4" fill="#fff" fillOpacity=".55" />
    <circle cx="78" cy="55" r="4" fill="#fff" fillOpacity=".55" />
  </g>,
)
const Sword = V(
  <g fill="currentColor">
    <rect x="47" y="8" width="6" height="62" />
    <path d="M47 8 L50 2 L53 8 Z" />
    <rect x="34" y="66" width="32" height="6" rx="2" />
    <rect x="47" y="72" width="6" height="14" />
    <circle cx="50" cy="90" r="5" />
  </g>,
)
const Wand = V(
  <g fill="currentColor">
    <rect
      x="16"
      y="72"
      width="56"
      height="6"
      rx="3"
      transform="rotate(-30 44 75)"
    />
    <path d="M76 16 L82 28 L94 28 L84 36 L88 48 L76 42 L64 48 L68 36 L58 28 L70 28 Z" />
    <circle cx="78" cy="28" r="2" fill="#fff" fillOpacity=".8" />
  </g>,
)

const shapes: ShapePlacement[] = [
  { svg: WizardHat, size: 140, color: '#ec4899', animation: 'fc-float-a', delayMs: 0,   style: { top: '4%', left: '5%', transform: 'rotate(-12deg)' } },
  { svg: Rocket,    size: 120, color: '#3b82f6', animation: 'fc-float-b', delayMs: 1200,style: { top: '8%',  right: '8%', transform: 'rotate(18deg)' } },
  { svg: Star,      size:  90, color: '#f59e0b', animation: 'fc-float-c', delayMs: 400, style: { top: '22%', left: '45%' } },
  { svg: Castle,    size: 160, color: '#f97316', animation: 'fc-float-a', delayMs: 3000,style: { bottom: '14%', left: '3%', transform: 'rotate(-4deg)' } },
  { svg: Crown,     size: 110, color: '#eab308', animation: 'fc-float-b', delayMs: 2000,style: { bottom: '10%', right: '6%', transform: 'rotate(8deg)' } },
  { svg: Heart,     size:  80, color: '#f472b6', animation: 'fc-float-c', delayMs: 1500,style: { top: '55%',  right: '18%', transform: 'rotate(-12deg)' } },
  { svg: Dinosaur,  size: 160, color: '#4f46e5', animation: 'fc-float-a', delayMs: 800, style: { top: '42%',  left: '4%', transform: 'rotate(0deg)' } },
  { svg: Ghost,     size: 110, color: '#60a5fa', animation: 'fc-float-b', delayMs: 2600,style: { top: '68%',  left: '36%', transform: 'rotate(6deg)' } },
  { svg: UFO,       size: 130, color: '#22c55e', animation: 'fc-float-c', delayMs: 1800,style: { top: '32%',  right: '2%', transform: 'rotate(-6deg)' } },
  { svg: Controller,size: 120, color: '#f97316', animation: 'fc-float-a', delayMs: 2200,style: { top: '80%',  left: '58%', transform: 'rotate(-18deg)' } },
  { svg: Sword,     size: 110, color: '#ef4444', animation: 'fc-float-b', delayMs: 900, style: { top: '50%',  left: '68%', transform: 'rotate(22deg)' } },
  { svg: Wand,      size: 120, color: '#a855f7', animation: 'fc-float-c', delayMs: 1400,style: { bottom: '38%', right: '42%', transform: 'rotate(-10deg)' } },
]

export function DecorativeBackground() {
  return (
    <div
      aria-hidden
      className="fixed inset-0 pointer-events-none overflow-hidden z-0 select-none"
    >
      {shapes.map((s, i) => (
        <div
          key={i}
          className="absolute"
          style={{
            ...s.style,
            width: s.size,
            height: s.size,
            color: s.color,
            opacity: 0.18,
            animation: `${s.animation} ${22 + (i % 4) * 6}s ease-in-out ${s.delayMs}ms infinite`,
            filter: 'drop-shadow(0 4px 0 rgba(0,0,0,0.08))',
          }}
        >
          {s.svg}
        </div>
      ))}
    </div>
  )
}
