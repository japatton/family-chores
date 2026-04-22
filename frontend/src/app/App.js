import { jsx as _jsx } from "react/jsx-runtime";
import { HashRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppRoutes } from './routes';
import { WebSocketProvider } from '../ws/provider';
const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 15_000,
            retry: 1,
            refetchOnWindowFocus: false,
        },
    },
});
export function App() {
    return (_jsx(QueryClientProvider, { client: queryClient, children: _jsx(HashRouter, { children: _jsx(WebSocketProvider, { children: _jsx(AppRoutes, {}) }) }) }));
}
