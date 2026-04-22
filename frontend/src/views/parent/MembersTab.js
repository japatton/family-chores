import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from 'react';
import { APIError } from '../../api/client';
import { useAdjustPoints, useCreateMember, useDeleteMember, useMembers, useUpdateMember, } from '../../api/hooks';
const DEFAULT_COLORS = [
    '#6366f1',
    '#f97316',
    '#14b8a6',
    '#ec4899',
    '#eab308',
    '#22c55e',
    '#ef4444',
    '#8b5cf6',
];
export function MembersTab() {
    const members = useMembers();
    const create = useCreateMember();
    const del = useDeleteMember();
    const [draft, setDraft] = useState({
        name: '',
        slug: '',
        color: DEFAULT_COLORS[0],
        display_mode: 'kid_standard',
        requires_approval: false,
        ha_todo_entity_id: null,
    });
    const [error, setError] = useState(null);
    if (members.isLoading)
        return _jsx("p", { className: "text-brand-700", children: "Loading\u2026" });
    const submit = () => {
        setError(null);
        if (!draft.name || !draft.slug) {
            setError('Name and slug are required.');
            return;
        }
        create.mutate(draft, {
            onSuccess: () => {
                setDraft({
                    name: '',
                    slug: '',
                    color: DEFAULT_COLORS[0],
                    display_mode: 'kid_standard',
                    requires_approval: false,
                    ha_todo_entity_id: null,
                });
            },
            onError: (e) => {
                if (e instanceof APIError)
                    setError(e.detail);
            },
        });
    };
    return (_jsxs("div", { className: "space-y-6", children: [_jsx("ul", { className: "space-y-3", children: (members.data ?? []).map((m) => (_jsx(MemberRow, { member: m, onDelete: () => {
                        if (confirm(`Delete ${m.name}? This removes their instances.`)) {
                            del.mutate(m.slug);
                        }
                    } }, m.id))) }), _jsxs("div", { className: "rounded-xl4 bg-white p-5 shadow-card space-y-3", children: [_jsx("div", { className: "text-fluid-base font-black text-brand-900", children: "Add a family member" }), _jsxs("div", { className: "grid gap-3 sm:grid-cols-2", children: [_jsxs("label", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Name" }), _jsx("input", { className: "rounded-xl border border-brand-100 px-4 py-3 text-fluid-base", value: draft.name, onChange: (e) => setDraft({ ...draft, name: e.target.value }) })] }), _jsxs("label", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Slug (a-z, 0-9, -, _)" }), _jsx("input", { className: "rounded-xl border border-brand-100 px-4 py-3 text-fluid-base", value: draft.slug, onChange: (e) => setDraft({
                                            ...draft,
                                            slug: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''),
                                        }) })] }), _jsxs("label", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Avatar (emoji)" }), _jsx("input", { className: "rounded-xl border border-brand-100 px-4 py-3 text-fluid-base", placeholder: "\uD83E\uDDB8", value: draft.avatar ?? '', onChange: (e) => setDraft({ ...draft, avatar: e.target.value || null }) })] }), _jsxs("label", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "HA Todo entity (optional)" }), _jsx("input", { className: "rounded-xl border border-brand-100 px-4 py-3 text-fluid-sm font-mono", placeholder: "todo.alice_chores", value: draft.ha_todo_entity_id ?? '', onChange: (e) => setDraft({ ...draft, ha_todo_entity_id: e.target.value || null }) })] })] }), _jsxs("div", { className: "flex items-center gap-4 flex-wrap", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Color" }), DEFAULT_COLORS.map((c) => (_jsx("button", { type: "button", onClick: () => setDraft({ ...draft, color: c }), className: "size-9 rounded-full border-4", style: {
                                    backgroundColor: c,
                                    borderColor: draft.color === c ? '#0f172a' : 'transparent',
                                }, "aria-label": `color ${c}` }, c)))] }), _jsxs("label", { className: "flex items-center gap-3", children: [_jsx("input", { type: "checkbox", className: "size-6", checked: draft.requires_approval ?? false, onChange: (e) => setDraft({ ...draft, requires_approval: e.target.checked }) }), _jsx("span", { className: "text-fluid-sm font-semibold", children: "Requires parent approval" })] }), error && (_jsx("div", { role: "alert", className: "text-rose-600 text-fluid-sm font-semibold", children: error })), _jsx("button", { type: "button", onClick: submit, disabled: create.isPending, className: "min-h-touch px-6 rounded-2xl bg-brand-600 text-white font-black text-fluid-base disabled:opacity-50", children: create.isPending ? 'Saving…' : 'Add member' })] })] }));
}
function MemberRow({ member, onDelete }) {
    const update = useUpdateMember(member.slug);
    const adjust = useAdjustPoints();
    const [adjusting, setAdjusting] = useState(false);
    const [adjustDelta, setAdjustDelta] = useState('');
    const [adjustReason, setAdjustReason] = useState('');
    return (_jsxs("li", { className: "rounded-xl4 bg-white p-5 shadow-card flex flex-col gap-3", style: { borderLeft: '6px solid ' + member.color }, children: [_jsxs("div", { className: "flex items-center gap-4 flex-wrap", children: [_jsx("span", { className: "text-fluid-xl", "aria-hidden": true, children: member.avatar ?? '🧒' }), _jsxs("div", { className: "min-w-0 flex-1", children: [_jsx("div", { className: "text-fluid-lg font-black truncate", children: member.name }), _jsxs("div", { className: "text-fluid-xs font-semibold text-brand-700/80", children: [member.slug, " \u00B7 ", member.stats.points_total, " pts \u00B7", ' ', member.stats.streak, "-day streak", member.ha_todo_entity_id && (_jsxs(_Fragment, { children: [' · ', _jsx("span", { className: "font-mono", children: member.ha_todo_entity_id })] }))] })] }), _jsx("button", { type: "button", onClick: () => update.mutate({ requires_approval: !member.requires_approval }), className: 'min-h-touch px-4 rounded-2xl font-bold text-fluid-sm ' +
                            (member.requires_approval
                                ? 'bg-amber-500 text-white'
                                : 'bg-brand-50 text-brand-700'), children: member.requires_approval
                            ? '✓ Approval required'
                            : 'Approval: off' }), _jsx("button", { type: "button", onClick: () => setAdjusting((v) => !v), className: "min-h-touch px-4 rounded-2xl font-bold text-fluid-sm bg-brand-50 text-brand-700", children: "\u00B1 points" }), _jsx("button", { type: "button", onClick: onDelete, className: "min-h-touch px-4 rounded-2xl font-bold text-fluid-sm bg-rose-50 text-rose-700", children: "Delete" })] }), adjusting && (_jsxs("div", { className: "flex items-end gap-3 flex-wrap", children: [_jsxs("label", { className: "flex flex-col gap-1", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Delta (\u00B1)" }), _jsx("input", { type: "number", value: adjustDelta, onChange: (e) => setAdjustDelta(e.target.value), className: "rounded-xl border border-brand-100 px-3 py-2 w-28 text-fluid-base" })] }), _jsxs("label", { className: "flex flex-col gap-1 flex-1 min-w-[8rem]", children: [_jsx("span", { className: "text-fluid-xs font-bold text-brand-700", children: "Reason" }), _jsx("input", { value: adjustReason, onChange: (e) => setAdjustReason(e.target.value), className: "rounded-xl border border-brand-100 px-3 py-2 text-fluid-base" })] }), _jsx("button", { type: "button", onClick: () => {
                            const d = Number.parseInt(adjustDelta, 10);
                            if (Number.isNaN(d))
                                return;
                            adjust.mutate({
                                memberId: member.id,
                                delta: d,
                                reason: adjustReason || undefined,
                            }, {
                                onSuccess: () => {
                                    setAdjusting(false);
                                    setAdjustDelta('');
                                    setAdjustReason('');
                                },
                            });
                        }, disabled: adjust.isPending, className: "min-h-touch px-5 rounded-2xl bg-brand-600 text-white font-black", children: "Apply" })] }))] }));
}
