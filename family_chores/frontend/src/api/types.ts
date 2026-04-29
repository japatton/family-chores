// TypeScript mirrors of the Pydantic schemas in backend/src/family_chores/api/schemas.py.
// Keep these in lockstep when adding new endpoints.

export type DisplayMode = 'kid_large' | 'kid_standard' | 'teen'

export type RecurrenceType =
  | 'daily'
  | 'weekdays'
  | 'weekends'
  | 'specific_days'
  | 'every_n_days'
  | 'monthly_on_date'
  | 'once'

export type InstanceState =
  | 'pending'
  | 'done_unapproved'
  | 'done'
  | 'skipped'
  | 'missed'

export interface MemberStats {
  points_total: number
  points_this_week: number
  week_anchor: string | null
  streak: number
  last_all_done_date: string | null
}

export interface Member {
  id: number
  name: string
  slug: string
  avatar: string | null
  color: string
  display_mode: DisplayMode
  requires_approval: boolean
  ha_todo_entity_id: string | null
  stats: MemberStats
  // Per-kid PIN (DECISIONS §17). Boolean only — the hash is server-side only.
  pin_set: boolean
}

export interface MemberPinStatus {
  member_id: number
  slug: string
  pin_set: boolean
}

export interface MemberPinVerifyResponse {
  member_id: number
  verified_until: number // unix seconds
}

export interface MemberCreate {
  name: string
  slug: string
  avatar?: string | null
  color?: string
  display_mode?: DisplayMode
  requires_approval?: boolean
  ha_todo_entity_id?: string | null
}

export interface MemberUpdate {
  name?: string
  avatar?: string | null
  color?: string
  display_mode?: DisplayMode
  requires_approval?: boolean
  ha_todo_entity_id?: string | null
}

export interface Chore {
  id: number
  name: string
  icon: string | null
  points: number
  description: string | null
  image: string | null
  active: boolean
  recurrence_type: RecurrenceType
  recurrence_config: Record<string, unknown>
  time_window_start: string | null
  time_window_end: string | null
  assigned_member_ids: number[]
  // Chore-templates feature (DECISIONS §13). Records which suggestion
  // this chore was spawned from, if any. Informational only.
  template_id?: string | null
}

export interface ChoreCreate {
  name: string
  icon?: string | null
  points?: number
  description?: string | null
  image?: string | null
  active?: boolean
  recurrence_type: RecurrenceType
  recurrence_config?: Record<string, unknown>
  time_window_start?: string | null
  time_window_end?: string | null
  assigned_member_ids?: number[]
  // Chore-templates feature (DECISIONS §13).
  // template_id pre-fills the form from a Browse Suggestions tap.
  // save_as_suggestion defaults to true server-side; UI passes the
  // checkbox state (default checked) here.
  template_id?: string | null
  save_as_suggestion?: boolean
}

export interface ChoreCreateResult extends Chore {
  template_created: boolean
}

// ─── suggestions (chore_template) ─────────────────────────────────────────

export type SuggestionSource = 'starter' | 'custom'

export interface Suggestion {
  id: string
  name: string
  icon: string | null
  category: string | null
  age_min: number | null
  age_max: number | null
  points_suggested: number
  default_recurrence_type: RecurrenceType
  default_recurrence_config: Record<string, unknown>
  description: string | null
  source: SuggestionSource
  starter_key: string | null
  created_at: string
  updated_at: string
}

export interface SuggestionCreate {
  name: string
  icon?: string | null
  category?: string | null
  age_min?: number | null
  age_max?: number | null
  points_suggested?: number
  default_recurrence_type: RecurrenceType
  default_recurrence_config?: Record<string, unknown>
  description?: string | null
}

export interface SuggestionUpdate {
  name?: string
  icon?: string | null
  category?: string | null
  age_min?: number | null
  age_max?: number | null
  points_suggested?: number
  default_recurrence_type?: RecurrenceType
  default_recurrence_config?: Record<string, unknown>
  description?: string | null
}

export interface SuggestionResetResult {
  suppressions_cleared: number
  seeded: number
  library_version: number
}

export interface SuggestionFilters {
  category?: string
  age?: number
  source?: 'all' | SuggestionSource
  q?: string
}

export interface Instance {
  id: number
  chore_id: number
  member_id: number
  date: string
  state: InstanceState
  completed_at: string | null
  approved_at: string | null
  approved_by: string | null
  points_awarded: number
  ha_todo_uid: string | null
}

export interface TodayInstance {
  id: number
  chore_id: number
  chore_name: string
  chore_icon: string | null
  points: number
  state: InstanceState
  time_window_start: string | null
  time_window_end: string | null
}

export interface TodayMember {
  id: number
  slug: string
  name: string
  color: string
  avatar: string | null
  display_mode: DisplayMode
  requires_approval: boolean
  stats: MemberStats
  today_progress_pct: number
  instances: TodayInstance[]
}

export interface TodayView {
  date: string
  members: TodayMember[]
}

export interface WhoAmI {
  user: string
  parent_pin_set: boolean
  parent_mode_active: boolean
}

export interface TokenResponse {
  token: string
  expires_at: number
}

export interface ActivityEntry {
  id: number
  ts: string
  actor: string
  action: string
  payload: Record<string, unknown>
}

export interface ActivityPage {
  entries: ActivityEntry[]
  total: number
  limit: number
  offset: number
}

export interface InfoResponse {
  version: string
  log_level: string
  week_starts_on: string
  sound_default: boolean
  timezone: string
  ha_connected: boolean
  bootstrap: { action: string; banner: string | null } | null
  // F-S004: when the addon's startup catch-up rollover throws, the
  // exception summary surfaces here so the SPA can render a banner.
  // null when rollover succeeded (the common case).
  rollover_warning: string | null
}
