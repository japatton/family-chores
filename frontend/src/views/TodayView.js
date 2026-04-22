import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useToday } from '../api/hooks';
import { MemberTile } from '../components/MemberTile';
export function TodayView() {
    const today = useToday();
    if (today.isLoading) {
        return (_jsx("div", { className: "grid place-items-center min-h-[40vh] text-fluid-base text-brand-700", children: "Loading\u2026" }));
    }
    if (today.error) {
        return (_jsx("div", { className: "grid place-items-center min-h-[40vh] text-fluid-base text-rose-700", children: "Couldn't reach the backend." }));
    }
    const members = today.data?.members ?? [];
    if (members.length === 0) {
        return (_jsx("div", { className: "grid place-items-center min-h-[50vh] text-center max-w-xl mx-auto", children: _jsxs("div", { children: [_jsx("div", { className: "text-fluid-3xl mb-4", "aria-hidden": true, children: "\uD83D\uDC6A" }), _jsx("div", { className: "text-fluid-xl font-black text-brand-900", children: "Add your first family member" }), _jsxs("p", { className: "mt-4 text-fluid-base text-brand-700", children: ["Tap ", _jsx("span", { className: "font-bold", children: "Parent" }), " at the top to set a PIN, then add members and chores. Kids tap their tile to see what's up today."] })] }) }));
    }
    return (_jsxs("div", { className: "mx-auto max-w-[100rem]", children: [_jsx("h1", { className: "text-fluid-xl font-black text-brand-900 mb-6 sm:mb-10", children: "Today" }), _jsx("div", { className: "grid gap-6 sm:gap-8 grid-cols-1 md:grid-cols-2", children: members.map((m) => (_jsx(MemberTile, { member: m }, m.id))) })] }));
}
