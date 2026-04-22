import { jsx as _jsx } from "react/jsx-runtime";
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './app/App';
import './styles/globals.css';
const container = document.getElementById('root');
if (!container) {
    throw new Error('#root element not found');
}
createRoot(container).render(_jsx(StrictMode, { children: _jsx(App, {}) }));
