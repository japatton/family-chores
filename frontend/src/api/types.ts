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
}
