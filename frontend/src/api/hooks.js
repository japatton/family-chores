import { useMutation, useQuery, useQueryClient, } from '@tanstack/react-query';
import { apiFetch } from './client';
import { useParentStore } from '../store/parent';
// ─── read hooks ────────────────────────────────────────────────────────────
export function useInfo() {
    return useQuery({
        queryKey: ['info'],
        queryFn: () => apiFetch('/info'),
        refetchInterval: 60_000,
        staleTime: 30_000,
    });
}
export function useWhoami() {
    return useQuery({
        queryKey: ['whoami'],
        queryFn: () => apiFetch('/auth/whoami'),
        staleTime: 5_000,
    });
}
export function useToday() {
    return useQuery({
        queryKey: ['today'],
        queryFn: () => apiFetch('/today'),
        staleTime: 5_000,
    });
}
export function useMembers() {
    return useQuery({
        queryKey: ['members'],
        queryFn: () => apiFetch('/members'),
    });
}
export function useMember(slug) {
    return useQuery({
        queryKey: ['member', slug],
        queryFn: () => apiFetch(`/members/${slug}`),
        enabled: !!slug,
    });
}
export function useChores() {
    return useQuery({
        queryKey: ['chores'],
        queryFn: () => apiFetch('/chores'),
    });
}
export function usePendingApprovals() {
    return useQuery({
        queryKey: ['instances', 'pending_approvals'],
        queryFn: () => apiFetch('/instances?state=done_unapproved&limit=200'),
        staleTime: 5_000,
    });
}
export function useActivityLog(limit = 50, offset = 0) {
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    return useQuery({
        queryKey: ['activity', limit, offset],
        queryFn: () => apiFetch(`/admin/activity?limit=${limit}&offset=${offset}`, { parentToken: token }),
        enabled: !!token,
    });
}
// ─── kid-facing mutations (no parent token) ───────────────────────────────
function invalidateOnInstanceChange(qc) {
    return () => {
        qc.invalidateQueries({ queryKey: ['today'] });
        qc.invalidateQueries({ queryKey: ['instances'] });
        qc.invalidateQueries({ queryKey: ['members'] });
        qc.invalidateQueries({ queryKey: ['member'] });
    };
}
export function useCompleteInstance() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (id) => apiFetch(`/instances/${id}/complete`, { method: 'POST' }),
        onSuccess: invalidateOnInstanceChange(qc),
    });
}
export function useUndoInstance() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (id) => apiFetch(`/instances/${id}/undo`, { method: 'POST' }),
        onSuccess: invalidateOnInstanceChange(qc),
    });
}
// ─── parent-token mutations ────────────────────────────────────────────────
export function useSetPin() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (body) => apiFetch('/auth/pin/set', { method: 'POST', json: body }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['whoami'] }),
    });
}
export function useVerifyPin() {
    const qc = useQueryClient();
    const setToken = useParentStore((s) => s.setToken);
    return useMutation({
        mutationFn: (pin) => apiFetch('/auth/pin/verify', {
            method: 'POST',
            json: { pin },
        }),
        onSuccess: (data) => {
            setToken(data.token, data.expires_at);
            qc.invalidateQueries({ queryKey: ['whoami'] });
        },
    });
}
export function useRefreshParent() {
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    const setToken = useParentStore((s) => s.setToken);
    return useMutation({
        mutationFn: () => apiFetch('/auth/refresh', {
            method: 'POST',
            parentToken: token,
        }),
        onSuccess: (data) => setToken(data.token, data.expires_at),
    });
}
export function useCreateMember() {
    const qc = useQueryClient();
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    return useMutation({
        mutationFn: (body) => apiFetch('/members', {
            method: 'POST',
            parentToken: token,
            json: body,
        }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['members'] });
            qc.invalidateQueries({ queryKey: ['today'] });
        },
    });
}
export function useUpdateMember(slug) {
    const qc = useQueryClient();
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    return useMutation({
        mutationFn: (body) => apiFetch(`/members/${slug}`, {
            method: 'PATCH',
            parentToken: token,
            json: body,
        }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['members'] });
            qc.invalidateQueries({ queryKey: ['member', slug] });
            qc.invalidateQueries({ queryKey: ['today'] });
        },
    });
}
export function useDeleteMember() {
    const qc = useQueryClient();
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    return useMutation({
        mutationFn: (slug) => apiFetch(`/members/${slug}`, {
            method: 'DELETE',
            parentToken: token,
        }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['members'] });
            qc.invalidateQueries({ queryKey: ['today'] });
        },
    });
}
export function useCreateChore() {
    const qc = useQueryClient();
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    return useMutation({
        mutationFn: (body) => apiFetch('/chores', {
            method: 'POST',
            parentToken: token,
            json: body,
        }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['chores'] });
            qc.invalidateQueries({ queryKey: ['today'] });
        },
    });
}
export function useDeleteChore() {
    const qc = useQueryClient();
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    return useMutation({
        mutationFn: (id) => apiFetch(`/chores/${id}`, {
            method: 'DELETE',
            parentToken: token,
        }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['chores'] });
            qc.invalidateQueries({ queryKey: ['today'] });
        },
    });
}
export function useApproveInstance() {
    const qc = useQueryClient();
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    return useMutation({
        mutationFn: (id) => apiFetch(`/instances/${id}/approve`, {
            method: 'POST',
            parentToken: token,
        }),
        onSuccess: invalidateOnInstanceChange(qc),
    });
}
export function useRejectInstance() {
    const qc = useQueryClient();
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    return useMutation({
        mutationFn: ({ id, reason }) => apiFetch(`/instances/${id}/reject`, {
            method: 'POST',
            parentToken: token,
            json: { reason },
        }),
        onSuccess: invalidateOnInstanceChange(qc),
    });
}
export function useSkipInstance() {
    const qc = useQueryClient();
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    return useMutation({
        mutationFn: ({ id, reason }) => apiFetch(`/instances/${id}/skip`, {
            method: 'POST',
            parentToken: token,
            json: { reason },
        }),
        onSuccess: invalidateOnInstanceChange(qc),
    });
}
export function useAdjustPoints() {
    const qc = useQueryClient();
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    return useMutation({
        mutationFn: ({ memberId, delta, reason, }) => apiFetch(`/members/${memberId}/points/adjust`, {
            method: 'POST',
            parentToken: token,
            json: { delta, reason },
        }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['members'] });
            qc.invalidateQueries({ queryKey: ['today'] });
        },
    });
}
export function useRebuildStats() {
    const qc = useQueryClient();
    const token = useParentStore((s) => (s.isActive() ? s.token : null));
    return useMutation({
        mutationFn: () => apiFetch('/admin/rebuild-stats', {
            method: 'POST',
            parentToken: token,
        }),
        onSuccess: () => qc.invalidateQueries(),
    });
}
