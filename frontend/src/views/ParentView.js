import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import clsx from 'clsx';
import { useParentStore } from '../store/parent';
import { ActivityTab } from './parent/ActivityTab';
import { ApprovalQueue } from './parent/ApprovalQueue';
import { ChoresTab } from './parent/ChoresTab';
import { MembersTab } from './parent/MembersTab';
import { ParentGate } from './parent/ParentGate';
export function ParentView() {
    const clearToken = useParentStore((s) => s.clear);
    return (_jsx(ParentGate, { children: _jsxs("div", { className: "mx-auto max-w-6xl space-y-6", children: [_jsxs("header", { className: "flex items-center justify-between gap-4 flex-wrap", children: [_jsx("h1", { className: "text-fluid-xl font-black text-brand-900", children: "Parent mode" }), _jsx("button", { type: "button", onClick: clearToken, className: "min-h-touch px-5 rounded-2xl font-bold text-fluid-sm bg-brand-50 text-brand-700", children: "Lock" })] }), _jsxs("nav", { className: "flex gap-2 flex-wrap", children: [_jsx(ParentTabLink, { to: "approvals", children: "Approvals" }), _jsx(ParentTabLink, { to: "members", children: "Members" }), _jsx(ParentTabLink, { to: "chores", children: "Chores" }), _jsx(ParentTabLink, { to: "activity", children: "Activity" })] }), _jsxs(Routes, { children: [_jsx(Route, { path: "approvals", element: _jsx(ApprovalQueue, {}) }), _jsx(Route, { path: "members", element: _jsx(MembersTab, {}) }), _jsx(Route, { path: "chores", element: _jsx(ChoresTab, {}) }), _jsx(Route, { path: "activity", element: _jsx(ActivityTab, {}) }), _jsx(Route, { path: "*", element: _jsx(Navigate, { to: "approvals", replace: true }) })] })] }) }));
}
function ParentTabLink({ to, children }) {
    return (_jsx(NavLink, { to: to, className: ({ isActive }) => clsx('min-h-touch px-5 rounded-2xl font-bold text-fluid-sm grid place-items-center', isActive
            ? 'bg-brand-600 text-white'
            : 'bg-brand-50 text-brand-700 hover:bg-brand-100'), children: children }));
}
