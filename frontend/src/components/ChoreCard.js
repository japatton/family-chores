import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import clsx from 'clsx';
const STATE_LABEL = {
    pending: 'Tap when done',
    done_unapproved: '⏳ Waiting for parent',
    done: '✓ Done',
    skipped: '↷ Skipped',
    missed: '— Missed',
};
export function ChoreCard({ instance, onTap, disabled }) {
    const finished = ['done', 'done_unapproved', 'skipped', 'missed'].includes(instance.state);
    return (_jsxs("button", { type: "button", onClick: onTap, disabled: disabled || finished, className: clsx('chore-card w-full min-h-touch rounded-xl4 p-6 sm:p-8 text-left flex items-center gap-5 sm:gap-8 shadow-card transition', finished
            ? 'bg-white/80 text-brand-700/70 opacity-80'
            : 'bg-white text-brand-900 active:scale-[0.99]', instance.state === 'missed' && 'line-through'), style: { borderLeft: '8px solid var(--accent)' }, children: [_jsx("span", { "aria-hidden": true, className: "text-[clamp(2.25rem,5vw,4rem)] leading-none shrink-0", children: instance.chore_icon ?? '✨' }), _jsxs("div", { className: "min-w-0 flex-1", children: [_jsx("div", { className: "text-fluid-lg font-black truncate", children: instance.chore_name }), _jsxs("div", { className: "mt-1 text-fluid-sm font-semibold text-brand-700/80", children: [instance.points, " pt", instance.points === 1 ? '' : 's', " \u00B7", ' ', STATE_LABEL[instance.state]] })] }), !finished && (_jsx("span", { "aria-hidden": true, className: "text-fluid-lg font-black text-brand-600 shrink-0", children: "\u2192" }))] }));
}
