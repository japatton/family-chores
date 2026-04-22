import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useApproveInstance, useMembers, useChores, usePendingApprovals, useRejectInstance, } from '../../api/hooks';
export function ApprovalQueue() {
    const pending = usePendingApprovals();
    const members = useMembers();
    const chores = useChores();
    const approve = useApproveInstance();
    const reject = useRejectInstance();
    if (pending.isLoading || members.isLoading || chores.isLoading) {
        return _jsx("p", { className: "text-brand-700", children: "Loading\u2026" });
    }
    const items = pending.data ?? [];
    if (items.length === 0) {
        return (_jsxs("div", { className: "rounded-xl4 bg-white p-8 text-center shadow-card", children: [_jsx("div", { className: "text-fluid-2xl", "aria-hidden": true, children: "\u2705" }), _jsx("div", { className: "mt-3 text-fluid-lg font-black text-brand-900", children: "Nothing waiting" }), _jsx("p", { className: "mt-2 text-fluid-sm text-brand-700", children: "Approvals show up here when kids with \"requires approval\" tap done." })] }));
    }
    const byMember = new Map(members.data?.map((m) => [m.id, m]));
    const byChore = new Map(chores.data?.map((c) => [c.id, c]));
    return (_jsx("ul", { className: "space-y-3", children: items.map((inst) => {
            const m = byMember.get(inst.member_id);
            const c = byChore.get(inst.chore_id);
            return (_jsxs("li", { className: "rounded-xl4 bg-white p-5 shadow-card flex items-center gap-4", children: [_jsxs("div", { className: "min-w-0 flex-1", children: [_jsx("div", { className: "text-fluid-base font-black truncate", children: c?.name ?? 'Unknown chore' }), _jsxs("div", { className: "text-fluid-sm font-semibold text-brand-700/80", children: [m?.name ?? `member ${inst.member_id}`, " \u00B7 ", inst.date, " \u00B7", ' ', c?.points ?? 0, " pt"] })] }), _jsx("button", { type: "button", onClick: () => reject.mutate({ id: inst.id, reason: undefined }), className: "min-h-touch px-5 rounded-2xl bg-rose-100 text-rose-900 font-bold", disabled: reject.isPending, children: "Reject" }), _jsx("button", { type: "button", onClick: () => approve.mutate(inst.id), className: "min-h-touch px-5 rounded-2xl bg-emerald-500 text-white font-black", disabled: approve.isPending, children: "Approve" })] }, inst.id));
        }) }));
}
