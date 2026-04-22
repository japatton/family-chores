import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './AppShell';
import { MemberView } from '../views/MemberView';
import { ParentView } from '../views/ParentView';
import { TodayView } from '../views/TodayView';
export function AppRoutes() {
    return (_jsx(Routes, { children: _jsxs(Route, { element: _jsx(AppShell, {}), children: [_jsx(Route, { path: "/", element: _jsx(TodayView, {}) }), _jsx(Route, { path: "/member/:slug", element: _jsx(MemberView, {}) }), _jsx(Route, { path: "/parent/*", element: _jsx(ParentView, {}) }), _jsx(Route, { path: "*", element: _jsx(Navigate, { to: "/", replace: true }) })] }) }));
}
