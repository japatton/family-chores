import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import clsx from 'clsx';
export function PinPad({ length = 4, onComplete, disabled = false, error, label = 'Enter PIN', }) {
    const [value, setValue] = useState('');
    useEffect(() => {
        if (value.length === length) {
            onComplete(value);
        }
    }, [value, length, onComplete]);
    useEffect(() => {
        if (error)
            setValue('');
    }, [error]);
    function press(d) {
        if (disabled)
            return;
        setValue((v) => (v.length < length ? v + d : v));
    }
    function backspace() {
        if (disabled)
            return;
        setValue((v) => v.slice(0, -1));
    }
    return (_jsxs("div", { className: "w-full max-w-md mx-auto flex flex-col items-center gap-6", children: [_jsx("div", { className: "text-fluid-lg font-black text-brand-900", children: label }), _jsx("div", { className: "flex gap-3", children: Array.from({ length }, (_, i) => (_jsx("div", { className: clsx('size-14 sm:size-16 rounded-2xl border-2 grid place-items-center text-fluid-xl font-black', i < value.length
                        ? 'bg-brand-600 border-brand-600 text-white'
                        : 'bg-white border-brand-100 text-brand-900'), children: i < value.length ? '•' : '' }, i))) }), error && (_jsx("div", { className: "text-fluid-sm font-semibold text-rose-600", role: "alert", children: error })), _jsxs("div", { className: "grid grid-cols-3 gap-3 w-full", children: [['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (_jsx("button", { type: "button", onClick: () => press(d), disabled: disabled, className: "pin-key min-h-touch rounded-2xl bg-white text-brand-900 shadow-card text-fluid-xl font-black active:scale-[0.98] disabled:opacity-50", children: d }, d))), _jsx("button", { type: "button", onClick: backspace, disabled: disabled || value.length === 0, className: "pin-key min-h-touch rounded-2xl bg-brand-50 text-brand-700 shadow-card text-fluid-base font-bold active:scale-[0.98] disabled:opacity-50", "aria-label": "backspace", children: "\u232B" }), _jsx("button", { type: "button", onClick: () => press('0'), disabled: disabled, className: "pin-key min-h-touch rounded-2xl bg-white text-brand-900 shadow-card text-fluid-xl font-black active:scale-[0.98] disabled:opacity-50", children: "0" }), _jsx("button", { type: "button", onClick: () => setValue(''), disabled: disabled || value.length === 0, className: "pin-key min-h-touch rounded-2xl bg-brand-50 text-brand-700 shadow-card text-fluid-sm font-bold active:scale-[0.98] disabled:opacity-50", children: "clear" })] })] }));
}
