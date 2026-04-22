import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useInfo } from '../api/hooks';
import { useWSConnected } from '../ws/provider';
import { Banner } from '../components/Banner';
export function AppShell() {
    const info = useInfo();
    const connected = useWSConnected();
    const loc = useLocation();
    const bootstrapBanner = info.data?.bootstrap?.banner ?? null;
    const haBanner = info.data && info.data.ha_connected === false
        ? 'Home Assistant bridge not connected — chores still work, but mirroring to HA is paused.'
        : null;
    return (_jsxs("div", { className: "min-h-screen flex flex-col", children: [_jsxs("header", { className: "flex items-center justify-between px-6 py-4 sm:px-10 sm:py-6 border-b border-brand-100 bg-white/70 backdrop-blur sticky top-0 z-10", children: [_jsxs(Link, { to: "/", className: "flex items-center gap-3 text-fluid-lg font-black text-brand-700", children: [_jsx("span", { "aria-hidden": true, className: "text-fluid-xl", children: "\uD83E\uDDF9" }), _jsx("span", { children: "Family Chores" })] }), _jsxs("nav", { className: "flex items-center gap-3", children: [!connected && (_jsx("span", { className: "px-3 py-1 rounded-full text-fluid-xs font-semibold text-amber-800 bg-amber-100", "aria-live": "polite", children: "reconnecting\u2026" })), _jsx(Link, { to: "/parent", className: 'min-h-touch px-5 rounded-2xl font-bold grid place-items-center ' +
                                    (loc.pathname.startsWith('/parent')
                                        ? 'bg-brand-600 text-white'
                                        : 'bg-brand-50 text-brand-700 hover:bg-brand-100'), children: "Parent" })] })] }), (bootstrapBanner || haBanner) && (_jsxs("div", { className: "px-6 sm:px-10 pt-4 space-y-2", children: [bootstrapBanner && _jsx(Banner, { variant: "warn", children: bootstrapBanner }), haBanner && _jsx(Banner, { variant: "info", children: haBanner })] })), _jsx("main", { className: "flex-1 px-6 sm:px-10 py-6 sm:py-10", children: _jsx(Outlet, {}) })] }));
}
