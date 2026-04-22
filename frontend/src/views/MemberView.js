import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useCallback, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useCompleteInstance, useMember, useToday, useUndoInstance, } from '../api/hooks';
import { ChoreCard } from '../components/ChoreCard';
import { UndoToast } from '../components/UndoToast';
export function MemberView() {
    const { slug = '' } = useParams();
    const member = useMember(slug);
    const today = useToday();
    const complete = useCompleteInstance();
    const undo = useUndoInstance();
    const [undoTarget, setUndoTarget] = useState(null);
    const clearUndo = useCallback(() => setUndoTarget(null), []);
    if (member.error || today.error) {
        return _jsx("p", { className: "text-rose-700 font-semibold", children: "Couldn't load this member." });
    }
    if (member.isLoading || today.isLoading) {
        return _jsx("p", { className: "text-brand-700", children: "Loading\u2026" });
    }
    if (!member.data)
        return null;
    const m = member.data;
    const todayForMember = today.data?.members.find((x) => x.id === m.id);
    const instances = todayForMember?.instances ?? [];
    const doneCount = instances.filter((i) => ['done', 'done_unapproved', 'skipped'].includes(i.state)).length;
    const allDone = instances.length > 0 && doneCount === instances.length;
    const handleTap = (id) => {
        complete.mutate(id, {
            onSuccess: () => setUndoTarget(id),
        });
    };
    return (_jsxs("div", { className: "mx-auto max-w-5xl", style: { ['--accent']: m.color }, children: [_jsxs("div", { className: "flex items-center gap-4 mb-8", children: [_jsx(Link, { to: "/", className: "min-h-touch min-w-touch px-5 rounded-2xl font-bold bg-brand-50 text-brand-700 grid place-items-center", children: "\u2190 Back" }), _jsxs("div", { className: "themed-soft rounded-xl4 px-6 py-4 flex-1 flex items-center gap-4 shadow-card", children: [_jsx("span", { className: "text-fluid-2xl", "aria-hidden": true, children: m.avatar ?? '🧒' }), _jsxs("div", { className: "min-w-0", children: [_jsx("div", { className: "text-fluid-xl font-black truncate", children: m.name }), _jsxs("div", { className: "text-fluid-sm font-semibold opacity-80", children: ["\uD83D\uDD25 ", m.stats.streak, " day streak \u00B7 \u2B50 ", m.stats.points_this_week, " this week \u00B7 ", m.stats.points_total, " total"] })] })] })] }), instances.length === 0 ? (_jsxs("div", { className: "text-center py-20", children: [_jsx("div", { className: "text-fluid-3xl", "aria-hidden": true, children: "\u2728" }), _jsx("div", { className: "mt-4 text-fluid-xl font-black text-brand-900", children: "No chores today!" })] })) : allDone ? (_jsxs("div", { className: "text-center py-16", children: [_jsx("div", { className: "text-fluid-3xl", "aria-hidden": true, children: "\uD83C\uDF89" }), _jsx("div", { className: "mt-4 text-fluid-xl font-black text-brand-900", children: "All done for today" }), _jsx("p", { className: "mt-3 text-fluid-base text-brand-700", children: "Nice work \u2014 see you tomorrow." })] })) : (_jsx("div", { className: "grid gap-4 sm:gap-6", children: instances.map((inst) => (_jsx(ChoreCard, { instance: inst, onTap: () => handleTap(inst.id), disabled: complete.isPending }, inst.id))) })), undoTarget !== null && (_jsx(UndoToast, { seconds: 4, onUndo: () => {
                    undo.mutate(undoTarget);
                    clearUndo();
                }, onExpire: clearUndo }))] }));
}
