import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { apiFetch } from './client'
import type {
  ActivityPage,
  Chore,
  ChoreCreate,
  ChoreCreateResult,
  InfoResponse,
  Instance,
  Member,
  MemberCreate,
  MemberPinVerifyResponse,
  MemberStats,
  MemberUpdate,
  Redemption,
  RedemptionCreate,
  RedemptionState,
  Reward,
  RewardCreate,
  RewardUpdate,
  Suggestion,
  SuggestionCreate,
  SuggestionFilters,
  SuggestionResetResult,
  SuggestionUpdate,
  TodayView,
  TokenResponse,
  WhoAmI,
} from './types'
import { useParentStore } from '../store/parent'

// ─── read hooks ────────────────────────────────────────────────────────────

export function useInfo() {
  return useQuery({
    queryKey: ['info'],
    queryFn: () => apiFetch<InfoResponse>('/info'),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useWhoami() {
  return useQuery({
    queryKey: ['whoami'],
    queryFn: () => apiFetch<WhoAmI>('/auth/whoami'),
    staleTime: 5_000,
  })
}

export function useToday() {
  return useQuery({
    queryKey: ['today'],
    queryFn: () => apiFetch<TodayView>('/today'),
    staleTime: 5_000,
  })
}

export function useMembers() {
  return useQuery({
    queryKey: ['members'],
    queryFn: () => apiFetch<Member[]>('/members'),
  })
}

export function useMember(slug: string | undefined) {
  return useQuery({
    queryKey: ['member', slug],
    queryFn: () => apiFetch<Member>(`/members/${slug}`),
    enabled: !!slug,
  })
}

export function useChores() {
  return useQuery({
    queryKey: ['chores'],
    queryFn: () => apiFetch<Chore[]>('/chores'),
  })
}

export function usePendingApprovals() {
  return useQuery({
    queryKey: ['instances', 'pending_approvals'],
    queryFn: () =>
      apiFetch<Instance[]>('/instances?state=done_unapproved&limit=200'),
    staleTime: 5_000,
  })
}

export function useActivityLog(limit = 50, offset = 0) {
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useQuery({
    queryKey: ['activity', limit, offset],
    queryFn: () =>
      apiFetch<ActivityPage>(
        `/admin/activity?limit=${limit}&offset=${offset}`,
        { parentToken: token },
      ),
    enabled: !!token,
  })
}

// ─── kid-facing mutations (no parent token) ───────────────────────────────

function invalidateOnInstanceChange(qc: ReturnType<typeof useQueryClient>) {
  return () => {
    qc.invalidateQueries({ queryKey: ['today'] })
    qc.invalidateQueries({ queryKey: ['instances'] })
    qc.invalidateQueries({ queryKey: ['members'] })
    qc.invalidateQueries({ queryKey: ['member'] })
  }
}

export function useCompleteInstance() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<Instance>(`/instances/${id}/complete`, { method: 'POST' }),
    onSuccess: invalidateOnInstanceChange(qc),
  })
}

export function useUndoInstance() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<Instance>(`/instances/${id}/undo`, { method: 'POST' }),
    onSuccess: invalidateOnInstanceChange(qc),
  })
}

// ─── parent-token mutations ────────────────────────────────────────────────

export function useSetPin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { pin: string; current_pin?: string }) =>
      apiFetch<WhoAmI>('/auth/pin/set', { method: 'POST', json: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['whoami'] }),
  })
}

export function useVerifyPin() {
  const qc = useQueryClient()
  const setToken = useParentStore((s) => s.setToken)
  return useMutation({
    mutationFn: (pin: string) =>
      apiFetch<TokenResponse>('/auth/pin/verify', {
        method: 'POST',
        json: { pin },
      }),
    onSuccess: (data) => {
      setToken(data.token, data.expires_at)
      qc.invalidateQueries({ queryKey: ['whoami'] })
    },
  })
}

export function useRefreshParent() {
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  const setToken = useParentStore((s) => s.setToken)
  return useMutation({
    mutationFn: () =>
      apiFetch<TokenResponse>('/auth/refresh', {
        method: 'POST',
        parentToken: token,
      }),
    onSuccess: (data) => setToken(data.token, data.expires_at),
  })
}

export function useCreateMember() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (body: MemberCreate) =>
      apiFetch<Member>('/members', {
        method: 'POST',
        parentToken: token,
        json: body,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['members'] })
      qc.invalidateQueries({ queryKey: ['today'] })
    },
  })
}

export function useUpdateMember(slug: string) {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (body: MemberUpdate) =>
      apiFetch<Member>(`/members/${slug}`, {
        method: 'PATCH',
        parentToken: token,
        json: body,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['members'] })
      qc.invalidateQueries({ queryKey: ['member', slug] })
      qc.invalidateQueries({ queryKey: ['today'] })
    },
  })
}

// ─── per-kid PIN (DECISIONS §17) ──────────────────────────────────────────

export function useSetMemberPin(slug: string) {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (pin: string) =>
      apiFetch<Member>(`/members/${slug}/pin/set`, {
        method: 'POST',
        parentToken: token,
        json: { pin },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['members'] })
      qc.invalidateQueries({ queryKey: ['member', slug] })
    },
  })
}

export function useClearMemberPin(slug: string) {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: () =>
      apiFetch<Member>(`/members/${slug}/pin/clear`, {
        method: 'POST',
        parentToken: token,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['members'] })
      qc.invalidateQueries({ queryKey: ['member', slug] })
    },
  })
}

/**
 * Kid-facing PIN verify — does NOT require parent auth. The verified_until
 * timestamp goes into the kidPinStore so the SPA can show the PIN gate
 * again when the unlock window expires.
 */
export function useVerifyMemberPin(slug: string) {
  return useMutation({
    mutationFn: (pin: string) =>
      apiFetch<MemberPinVerifyResponse>(`/members/${slug}/pin/verify`, {
        method: 'POST',
        json: { pin },
      }),
  })
}

export function useDeleteMember() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (slug: string) =>
      apiFetch<void>(`/members/${slug}`, {
        method: 'DELETE',
        parentToken: token,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['members'] })
      qc.invalidateQueries({ queryKey: ['today'] })
    },
  })
}

export function useCreateChore() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (body: ChoreCreate) =>
      apiFetch<ChoreCreateResult>('/chores', {
        method: 'POST',
        parentToken: token,
        json: body,
      }),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['chores'] })
      qc.invalidateQueries({ queryKey: ['today'] })
      // Invalidate suggestions too — POST may have created a new one
      // alongside the chore (template_created=true).
      if (result.template_created) {
        qc.invalidateQueries({ queryKey: ['suggestions'] })
      }
    },
  })
}

// ─── suggestions (DECISIONS §13) ──────────────────────────────────────────

function buildSuggestionsQuery(filters?: SuggestionFilters): string {
  if (!filters) return ''
  const params = new URLSearchParams()
  if (filters.category) params.set('category', filters.category)
  if (filters.age !== undefined) params.set('age', String(filters.age))
  if (filters.source && filters.source !== 'all')
    params.set('source', filters.source)
  if (filters.q) params.set('q', filters.q)
  const s = params.toString()
  return s ? `?${s}` : ''
}

export function useSuggestions(
  filters?: SuggestionFilters,
  opts: { enabled?: boolean } = {},
) {
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useQuery({
    queryKey: ['suggestions', filters ?? null],
    queryFn: () =>
      apiFetch<Suggestion[]>(`/suggestions${buildSuggestionsQuery(filters)}`, {
        parentToken: token,
      }),
    enabled: !!token && (opts.enabled ?? true),
    staleTime: 30_000,
  })
}

export function useCreateSuggestion() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (body: SuggestionCreate) =>
      apiFetch<Suggestion>('/suggestions', {
        method: 'POST',
        parentToken: token,
        json: body,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['suggestions'] }),
  })
}

/**
 * Update an arbitrary suggestion. The id flows through the mutation
 * variables (not a closure) so the same hook instance can patch any
 * suggestion in a list — used by the Manage Suggestions view.
 */
export function useUpdateSuggestion() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: SuggestionUpdate }) =>
      apiFetch<Suggestion>(`/suggestions/${id}`, {
        method: 'PATCH',
        parentToken: token,
        json: body,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['suggestions'] }),
  })
}

export function useDeleteSuggestion() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/suggestions/${id}`, {
        method: 'DELETE',
        parentToken: token,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['suggestions'] }),
  })
}

// ─── rewards + redemptions ────────────────────────────────────────────────

export function useRewards(opts: { active?: boolean } = {}) {
  return useQuery({
    queryKey: ['rewards', opts.active ?? null],
    queryFn: () => {
      const q =
        opts.active === undefined
          ? ''
          : `?active=${opts.active ? 'true' : 'false'}`
      return apiFetch<Reward[]>(`/rewards${q}`)
    },
    staleTime: 15_000,
  })
}

export function useCreateReward() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (body: RewardCreate) =>
      apiFetch<Reward>('/rewards', {
        method: 'POST',
        parentToken: token,
        json: body,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rewards'] }),
  })
}

export function useUpdateReward() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: RewardUpdate }) =>
      apiFetch<Reward>(`/rewards/${id}`, {
        method: 'PATCH',
        parentToken: token,
        json: body,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rewards'] }),
  })
}

export function useDeleteReward() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/rewards/${id}`, {
        method: 'DELETE',
        parentToken: token,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rewards'] }),
  })
}

export function useMemberRedemptions(slug: string | undefined) {
  return useQuery({
    queryKey: ['member', slug, 'redemptions'],
    queryFn: () => apiFetch<Redemption[]>(`/members/${slug}/redemptions`),
    enabled: !!slug,
    staleTime: 5_000,
  })
}

/**
 * Kid-facing — no parent JWT required. Insufficient balance + cap
 * errors come back as APIError(409); the calling component surfaces
 * the .detail string.
 */
export function useCreateRedemption(slug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: RedemptionCreate) =>
      apiFetch<Redemption>(`/members/${slug}/redemptions`, {
        method: 'POST',
        json: body,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['member', slug] })
      qc.invalidateQueries({ queryKey: ['member', slug, 'redemptions'] })
      qc.invalidateQueries({ queryKey: ['today'] })
      qc.invalidateQueries({ queryKey: ['redemptions'] })
    },
  })
}

export function useRedemptions(
  opts: { state?: RedemptionState; memberId?: number } = {},
) {
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useQuery({
    queryKey: ['redemptions', opts.state ?? null, opts.memberId ?? null],
    queryFn: () => {
      const params = new URLSearchParams()
      if (opts.state) params.set('state', opts.state)
      if (opts.memberId) params.set('member_id', String(opts.memberId))
      const qs = params.toString()
      return apiFetch<Redemption[]>(
        `/redemptions${qs ? `?${qs}` : ''}`,
        { parentToken: token },
      )
    },
    enabled: !!token,
    staleTime: 5_000,
  })
}

export function useApproveRedemption() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<Redemption>(`/redemptions/${id}/approve`, {
        method: 'POST',
        parentToken: token,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['redemptions'] })
      qc.invalidateQueries({ queryKey: ['member'] })
    },
  })
}

export function useDenyRedemption() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      apiFetch<Redemption>(`/redemptions/${id}/deny`, {
        method: 'POST',
        parentToken: token,
        json: { reason },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['redemptions'] })
      qc.invalidateQueries({ queryKey: ['members'] })
      qc.invalidateQueries({ queryKey: ['member'] })
      qc.invalidateQueries({ queryKey: ['today'] })
    },
  })
}

export function useResetSuggestions() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: () =>
      apiFetch<SuggestionResetResult>('/suggestions/reset', {
        method: 'POST',
        parentToken: token,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['suggestions'] }),
  })
}

export function useDeleteChore() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/chores/${id}`, {
        method: 'DELETE',
        parentToken: token,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chores'] })
      qc.invalidateQueries({ queryKey: ['today'] })
    },
  })
}

export function useApproveInstance() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<Instance>(`/instances/${id}/approve`, {
        method: 'POST',
        parentToken: token,
      }),
    onSuccess: invalidateOnInstanceChange(qc),
  })
}

export function useRejectInstance() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
      apiFetch<Instance>(`/instances/${id}/reject`, {
        method: 'POST',
        parentToken: token,
        json: { reason },
      }),
    onSuccess: invalidateOnInstanceChange(qc),
  })
}

export function useSkipInstance() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
      apiFetch<Instance>(`/instances/${id}/skip`, {
        method: 'POST',
        parentToken: token,
        json: { reason },
      }),
    onSuccess: invalidateOnInstanceChange(qc),
  })
}

export function useAdjustPoints() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: ({
      memberId,
      delta,
      reason,
    }: {
      memberId: number
      delta: number
      reason?: string
    }) =>
      apiFetch<MemberStats>(`/members/${memberId}/points/adjust`, {
        method: 'POST',
        parentToken: token,
        json: { delta, reason },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['members'] })
      qc.invalidateQueries({ queryKey: ['today'] })
    },
  })
}

export function useRebuildStats() {
  const qc = useQueryClient()
  const token = useParentStore((s) => (s.isActive() ? s.token : null))
  return useMutation({
    mutationFn: () =>
      apiFetch<{ members_updated: number }>('/admin/rebuild-stats', {
        method: 'POST',
        parentToken: token,
      }),
    onSuccess: () => qc.invalidateQueries(),
  })
}
