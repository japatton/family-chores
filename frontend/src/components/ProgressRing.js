import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export function ProgressRing({ percent, size = 96, stroke = 10, color = 'currentColor', trackColor = 'rgba(255,255,255,0.25)', label, }) {
    const radius = (size - stroke) / 2;
    const circumference = 2 * Math.PI * radius;
    const clamped = Math.max(0, Math.min(100, percent));
    const offset = circumference - (clamped / 100) * circumference;
    return (_jsxs("svg", { width: size, height: size, viewBox: `0 0 ${size} ${size}`, role: "img", "aria-label": label ?? `${clamped}%`, children: [_jsx("circle", { cx: size / 2, cy: size / 2, r: radius, stroke: trackColor, strokeWidth: stroke, fill: "none" }), _jsx("circle", { cx: size / 2, cy: size / 2, r: radius, stroke: color, strokeWidth: stroke, strokeLinecap: "round", fill: "none", strokeDasharray: circumference, strokeDashoffset: offset, transform: `rotate(-90 ${size / 2} ${size / 2})`, style: { transition: 'stroke-dashoffset 400ms ease-out' } }), _jsxs("text", { x: "50%", y: "50%", textAnchor: "middle", dominantBaseline: "central", style: { fontSize: size * 0.3, fontWeight: 800, fill: color }, children: [Math.round(clamped), "%"] })] }));
}
