import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
export function UndoToast({ seconds, onUndo, onExpire, label = 'Done!', }) {
    const [remaining, setRemaining] = useState(seconds);
    useEffect(() => {
        if (remaining <= 0) {
            onExpire();
            return;
        }
        const id = window.setTimeout(() => setRemaining((v) => v - 1), 1000);
        return () => window.clearTimeout(id);
    }, [remaining, onExpire]);
    return (_jsxs("div", { role: "alert", className: "fixed inset-x-4 bottom-6 sm:inset-x-auto sm:right-8 sm:bottom-8 sm:max-w-md z-30 rounded-xl4 bg-brand-900 text-white shadow-tile px-6 py-4 flex items-center justify-between gap-4 animate-fade-in", children: [_jsxs("div", { children: [_jsx("div", { className: "text-fluid-base font-black", children: label }), _jsxs("div", { className: "text-fluid-sm opacity-80", children: ["Undo in ", Math.max(0, remaining), "s"] })] }), _jsx("button", { type: "button", onClick: onUndo, className: "min-h-touch px-6 rounded-2xl bg-white text-brand-700 font-black text-fluid-base active:scale-[0.97]", children: "Undo" })] }));
}
