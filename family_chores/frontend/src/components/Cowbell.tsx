/**
 * Cartoon 3D cowbell — replaces the bell emoji on the sound toggle.
 * Pure SVG so it inherits text colour, respects `currentColor`, and
 * scales cleanly across phone / tablet / 32" displays.
 */

interface CowbellProps {
  muted?: boolean
  size?: number
  className?: string
}

export function Cowbell({ muted = false, size = 44, className }: CowbellProps) {
  // Unique gradient IDs per instance so multiple cowbells on a page
  // don't collide (currently only one, but cheap to future-proof).
  const gradId = `fc-cowbell-metal-${muted ? 'off' : 'on'}`
  const shineId = `fc-cowbell-shine-${muted ? 'off' : 'on'}`

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={className}
      aria-hidden
      style={{
        filter: muted
          ? 'grayscale(0.8) drop-shadow(0 2px 0 rgba(0,0,0,0.15))'
          : 'drop-shadow(0 3px 0 rgba(0,0,0,0.22))',
        opacity: muted ? 0.65 : 1,
        transition: 'opacity 200ms ease, filter 200ms ease',
      }}
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fde68a" />
          <stop offset="45%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#7c2d12" />
        </linearGradient>
        <linearGradient id={shineId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="50%" stopColor="#ffffff" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Leather strap loop at top */}
      <path
        d="M22 4 C22 -2 42 -2 42 4 L42 11 L22 11 Z"
        fill="#5b2c0a"
      />
      <path
        d="M24 4 C24 0 40 0 40 4 L40 9 L24 9 Z"
        fill="#7c3a10"
      />
      <line
        x1="24"
        y1="7"
        x2="40"
        y2="7"
        stroke="#a65a20"
        strokeWidth="1"
        strokeDasharray="2 2"
      />

      {/* Top strap band across the bell */}
      <rect
        x="18"
        y="10"
        width="28"
        height="5"
        rx="1.5"
        fill="#5b2c0a"
      />

      {/* Bell body — trapezoidal with rounded bottom curve */}
      <path
        d="M17 15
           L47 15
           L53 52
           Q32 60 11 52 Z"
        fill={`url(#${gradId})`}
        stroke="#5b2c0a"
        strokeWidth="2"
        strokeLinejoin="round"
      />

      {/* Highlight streak for 3D shine */}
      <path
        d="M22 19 Q21 34 24 50"
        fill="none"
        stroke={`url(#${shineId})`}
        strokeWidth="3.5"
        strokeLinecap="round"
      />

      {/* Rim line to suggest bell opening */}
      <path
        d="M13 50 Q32 58 51 50"
        fill="none"
        stroke="#5b2c0a"
        strokeWidth="2"
        strokeLinecap="round"
      />

      {/* Clapper peeking out the bottom */}
      <ellipse cx="32" cy="54" rx="4" ry="3" fill="#3b1808" />
      <circle cx="32" cy="52.5" r="1.6" fill="#5b2c0a" />

      {/* "Ring" squiggles when unmuted — suggest sound */}
      {!muted && (
        <g stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" fill="none">
          <path d="M5 20 Q9 22 8 27" />
          <path d="M59 20 Q55 22 56 27" />
          <path d="M2 32 L6 32" />
          <path d="M58 32 L62 32" />
        </g>
      )}

      {/* Muted: diagonal slash across the bell */}
      {muted && (
        <line
          x1="8"
          y1="8"
          x2="56"
          y2="56"
          stroke="#dc2626"
          strokeWidth="4"
          strokeLinecap="round"
        />
      )}
    </svg>
  )
}
