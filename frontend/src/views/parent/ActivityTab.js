import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useActivityLog } from '../../api/hooks';
export function ActivityTab() {
    const log = useActivityLog(50, 0);
    if (log.isLoading)
        return _jsx("p", { className: "text-brand-700", children: "Loading\u2026" });
    if (log.error)
        return _jsx("p", { className: "text-rose-700 font-semibold", children: "Couldn't load activity." });
    const entries = log.data?.entries ?? [];
    if (entries.length === 0) {
        return (_jsx("p", { className: "text-brand-700/80 text-fluid-sm", children: "No activity yet. Actions here will include member/chore changes, completions, approvals, and manual point adjustments." }));
    }
    return (_jsx("ul", { className: "space-y-2", children: entries.map((e) => (_jsxs("li", { className: "rounded-2xl bg-white px-4 py-3 shadow-card text-fluid-sm", children: [_jsxs("div", { className: "flex items-baseline justify-between gap-4", children: [_jsx("span", { className: "font-black text-brand-900", children: e.action }), _jsx("span", { className: "text-brand-700/70 font-mono text-fluid-xs", children: new Date(e.ts).toLocaleString() })] }), _jsx("div", { className: "text-brand-700/80 font-semibold", children: e.actor }), Object.keys(e.payload).length > 0 && (_jsx("pre", { className: "mt-1 text-xs font-mono whitespace-pre-wrap text-brand-700/80", children: JSON.stringify(e.payload, null, 0) }))] }, e.id))) }));
}
