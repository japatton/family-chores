import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { APIError } from '../../api/client';
import { useChores, useCreateChore, useDeleteChore, useMembers } from '../../api/hooks';
const RECURRENCE_OPTIONS = [
    { value: 'daily', label: 'Every day' },
    { value: 'weekdays', label: 'Weekdays' },
    { value: 'weekends', label: 'Weekends' },
    { value: 'specific_days', label: 'Specific days' },
    { value: 'every_n_days', label: 'Every N days' },
    { value: 'monthly_on_date', label: 'Monthly on date' },
    { value: 'once', label: 'Once' },
];
const WEEKDAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export function ChoresTab() {
    const chores = useChores();
    const members = useMembers();
    const create = useCreateChore();
    const del = useDeleteChore();
    const [draft, setDraft] = useState({
        name: '',
        points: 5,
        recurrence_type: 'daily',
        recurrence_config: {},
        assigned_member_ids: [],
        active: true,
    });
    const [specificDays, setSpecificDays] = useState([]);
    const [everyN, setEveryN] = useState('2');
    const [everyAnchor, setEveryAnchor] = useState(new Date().toISOString().slice(0, 10));
    const [monthDay, setMonthDay] = useState('15');
    const [onceDate, setOnceDate] = useState(new Date().toISOString().slice(0, 10));
    const [error, setError] = useState(null);
    if (chores.isLoading || members.isLoading) {
        return _jsx("p", { className: "text-brand-700", children: "Loading\u2026" });
    }
    const buildRecurrenceConfig = () => {
        switch (draft.recurrence_type) {
            case 'specific_days':
                return { days: specificDays };
            case 'every_n_days':
                return { n: Number.parseInt(everyN, 10) || 1, anchor: everyAnchor };
            case 'monthly_on_date':
                return { day: Number.parseInt(monthDay, 10) || 1 };
            case 'once':
                return { date: onceDate };
            default:
                return {};
        }
    };
    const submit = () => {
        setError(null);
        if (!draft.name.trim()) {
            setError('Name is required.');
            return;
        }
        const body = {
            ...draft,
            recurrence_config: buildRecurrenceConfig(),
        };
        create.mutate(body, {
            onSuccess: () => {
                setDraft({
                    name: '',
                    points: 5,
                    recurrence_type: 'daily',
                    recurrence_config: {},
                    assigned_member_ids: [],
                    active: true,
                });
                setSpecificDays([]);
            },
            onError: (e) => {
                if (e instanceof APIError)
                    setError(e.detail);
            },
        });
    };
    return (_jsxs("div", { className: "space-y-6", children: [_jsx("ul", { className: "space-y-3", children: (chores.data ?? []).map((c) => {
                    const assigned = (members.data ?? []).filter((m) => c.assigned_member_ids.includes(m.id));
                    return (_jsxs("li", { className: "rounded-xl4 bg-white p-5 shadow-card flex items-center gap-4 flex-wrap", children: [_jsx("span", { className: "text-fluid-xl", "aria-hidden": true, children: c.icon ?? '✨' }), _jsxs("div", { className: "min-w-0 flex-1", children: [_jsx("div", { className: "text-fluid-lg font-black truncate", children: c.name }), _jsxs("div", { className: "text-fluid-xs font-semibold text-brand-700/80", children: [c.points, " pt \u00B7 ", c.recurrence_type, " \u00B7", ' ', assigned.length > 0
                                                ? assigned.map((m) => m.name).join(', ')
                                                : 'nobody assigned', !c.active && ' · inactive'] })] }), _jsx("button", { type: "button", onClick: () => {
                                    if (confirm(`Delete "${c.name}"?`)) {
                                        del.mutate(c.id);
                                    }
                                }, className: "min-h-touch px-4 rounded-2xl font-bold text-fluid-sm bg-rose-50 text-rose-700", children: "Delete" })] }, c.id));
                }) }), _jsxs("div", { className: "rounded-xl4 bg-white p-5 shadow-card space-y-3", children: [_jsx("div", { className: "text-fluid-base font-black text-brand-900", children: "Add a chore" }), _jsxs("div", { className: "grid gap-3 sm:grid-cols-2", children: [_jsxs("label", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Name" }), _jsx("input", { className: "rounded-xl border border-brand-100 px-4 py-3 text-fluid-base", value: draft.name, onChange: (e) => setDraft({ ...draft, name: e.target.value }) })] }), _jsxs("label", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Icon (emoji)" }), _jsx("input", { className: "rounded-xl border border-brand-100 px-4 py-3 text-fluid-base", value: draft.icon ?? '', onChange: (e) => setDraft({ ...draft, icon: e.target.value || null }) })] }), _jsxs("label", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Points" }), _jsx("input", { type: "number", min: 0, className: "rounded-xl border border-brand-100 px-4 py-3 text-fluid-base", value: draft.points ?? 0, onChange: (e) => setDraft({ ...draft, points: Number.parseInt(e.target.value, 10) || 0 }) })] }), _jsxs("label", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Recurrence" }), _jsx("select", { value: draft.recurrence_type, onChange: (e) => setDraft({
                                            ...draft,
                                            recurrence_type: e.target.value,
                                        }), className: "rounded-xl border border-brand-100 px-4 py-3 text-fluid-base", children: RECURRENCE_OPTIONS.map((o) => (_jsx("option", { value: o.value, children: o.label }, o.value))) })] })] }), draft.recurrence_type === 'specific_days' && (_jsx("div", { className: "flex gap-2 flex-wrap", children: WEEKDAY_NAMES.map((wd, idx) => {
                            const iso = idx + 1;
                            const on = specificDays.includes(iso);
                            return (_jsx("button", { type: "button", onClick: () => setSpecificDays((days) => on ? days.filter((d) => d !== iso) : [...days, iso]), className: 'min-h-touch px-4 rounded-2xl font-bold text-fluid-sm ' +
                                    (on
                                        ? 'bg-brand-600 text-white'
                                        : 'bg-brand-50 text-brand-700'), children: wd }, wd));
                        }) })), draft.recurrence_type === 'every_n_days' && (_jsxs("div", { className: "flex gap-3 flex-wrap items-end", children: [_jsxs("label", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "N" }), _jsx("input", { type: "number", min: 1, className: "rounded-xl border border-brand-100 px-3 py-2 w-20 text-fluid-base", value: everyN, onChange: (e) => setEveryN(e.target.value) })] }), _jsxs("label", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Anchor" }), _jsx("input", { type: "date", className: "rounded-xl border border-brand-100 px-3 py-2 text-fluid-base", value: everyAnchor, onChange: (e) => setEveryAnchor(e.target.value) })] })] })), draft.recurrence_type === 'monthly_on_date' && (_jsxs("label", { className: "flex flex-col gap-1 max-w-[10rem]", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Day (1-31)" }), _jsx("input", { type: "number", min: 1, max: 31, className: "rounded-xl border border-brand-100 px-3 py-2 text-fluid-base", value: monthDay, onChange: (e) => setMonthDay(e.target.value) })] })), draft.recurrence_type === 'once' && (_jsxs("label", { className: "flex flex-col gap-1 max-w-xs", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Date" }), _jsx("input", { type: "date", className: "rounded-xl border border-brand-100 px-3 py-2 text-fluid-base", value: onceDate, onChange: (e) => setOnceDate(e.target.value) })] })), _jsxs("div", { children: [_jsx("div", { className: "text-fluid-xs font-bold text-brand-700 mb-1", children: "Assign to" }), _jsxs("div", { className: "flex flex-wrap gap-2", children: [(members.data ?? []).map((m) => {
                                        const on = (draft.assigned_member_ids ?? []).includes(m.id);
                                        return (_jsxs("button", { type: "button", onClick: () => setDraft({
                                                ...draft,
                                                assigned_member_ids: on
                                                    ? (draft.assigned_member_ids ?? []).filter((x) => x !== m.id)
                                                    : [...(draft.assigned_member_ids ?? []), m.id],
                                            }), className: 'min-h-touch px-4 rounded-2xl font-bold text-fluid-sm ' +
                                                (on
                                                    ? 'text-white'
                                                    : 'bg-brand-50 text-brand-700 border border-brand-100'), style: on ? { backgroundColor: m.color } : undefined, children: [m.avatar ?? '🧒', " ", m.name] }, m.id));
                                    }), (members.data ?? []).length === 0 && (_jsx("span", { className: "text-fluid-sm text-brand-700/70", children: "No members yet \u2014 add one first." }))] })] }), error && (_jsx("div", { role: "alert", className: "text-rose-600 text-fluid-sm font-semibold", children: error })), _jsx("button", { type: "button", onClick: submit, disabled: create.isPending, className: "min-h-touch px-6 rounded-2xl bg-brand-600 text-white font-black text-fluid-base disabled:opacity-50", children: create.isPending ? 'Saving…' : 'Add chore' })] })] }));
}
