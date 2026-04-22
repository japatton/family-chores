/**
 * family-chores-card — at-a-glance Lovelace card for the Family Chores
 * add-on. Reads HA entities only; never talks to the add-on's HTTP API.
 *
 * Config schema:
 *   type: custom:family-chores-card
 *   title: 'Family Chores'              # optional
 *   members:                             # optional list of member slugs
 *     - alice
 *     - bob
 *   show_pending_approvals: true         # default true
 *   tap_action:                          # default: navigate to Ingress
 *     action: navigate
 *     navigation_path: /hassio/ingress/local_family_chores
 */

import { LitElement, html, css, type PropertyValues, type TemplateResult } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import './family-chores-card-editor'

interface HassState {
  state: string
  attributes: Record<string, unknown>
  entity_id: string
}

interface HomeAssistant {
  states: Record<string, HassState>
}

interface TapAction {
  action: 'navigate' | 'none'
  navigation_path?: string
}

export interface FamilyChoresCardConfig {
  type: string
  title?: string
  members?: string[]
  show_pending_approvals?: boolean
  tap_action?: TapAction
}

interface MemberRow {
  slug: string
  name: string
  points_total: number
  points_this_week: number
  streak: number
  progress_pct: number
}

const POINTS_ENTITY_PREFIX = 'sensor.family_chores_'
const POINTS_ENTITY_SUFFIX = '_points'
const PENDING_APPROVALS_ENTITY = 'sensor.family_chores_pending_approvals'
const DEFAULT_NAV = '/hassio/ingress/local_family_chores'

function intAttr(state: HassState, key: string, fallback = 0): number {
  const v = state.attributes[key]
  if (typeof v === 'number') return Math.trunc(v)
  if (typeof v === 'string') {
    const n = Number.parseInt(v, 10)
    return Number.isNaN(n) ? fallback : n
  }
  return fallback
}

function strAttr(state: HassState, key: string, fallback: string): string {
  const v = state.attributes[key]
  return typeof v === 'string' && v.length > 0 ? v : fallback
}

function discoverMembers(hass: HomeAssistant): MemberRow[] {
  const rows: MemberRow[] = []
  for (const entityId of Object.keys(hass.states)) {
    if (!entityId.startsWith(POINTS_ENTITY_PREFIX)) continue
    if (!entityId.endsWith(POINTS_ENTITY_SUFFIX)) continue
    const state = hass.states[entityId]
    const slug = entityId.slice(
      POINTS_ENTITY_PREFIX.length,
      entityId.length - POINTS_ENTITY_SUFFIX.length,
    )
    const points_total = Number.parseInt(state.state, 10) || 0
    rows.push({
      slug,
      name: strAttr(state, 'name', slug),
      points_total,
      points_this_week: intAttr(state, 'points_this_week'),
      streak: intAttr(state, 'streak'),
      progress_pct: intAttr(state, 'today_progress_pct'),
    })
  }
  rows.sort((a, b) => a.name.localeCompare(b.name))
  return rows
}

@customElement('family-chores-card')
export class FamilyChoresCard extends LitElement {
  @property({ attribute: false }) hass?: HomeAssistant

  @state() private _config?: FamilyChoresCardConfig

  static get styles() {
    return css`
      ha-card {
        padding: 16px;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 12px;
        gap: 12px;
      }
      .title {
        font-weight: 700;
        font-size: 1.1rem;
      }
      .badge {
        display: inline-flex;
        align-items: center;
        padding: 2px 10px;
        border-radius: 999px;
        background: var(--warning-color, #ff9800);
        color: white;
        font-weight: 700;
        font-size: 0.85rem;
      }
      .members {
        display: grid;
        gap: 8px;
      }
      .row {
        display: grid;
        grid-template-columns: 1fr auto auto;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        border-radius: 12px;
        background: var(--secondary-background-color, #fafafa);
        cursor: pointer;
        user-select: none;
      }
      .row:hover {
        background: var(--divider-color, #eeeeee);
      }
      .row .name {
        font-weight: 700;
      }
      .row .meta {
        color: var(--secondary-text-color);
        font-size: 0.8rem;
      }
      .points {
        font-weight: 800;
        min-width: 3ch;
        text-align: right;
      }
      .ring {
        --size: 34px;
        width: var(--size);
        height: var(--size);
        border-radius: 50%;
        display: grid;
        place-items: center;
        font-size: 0.7rem;
        font-weight: 800;
        color: var(--primary-text-color);
        background:
          conic-gradient(var(--primary-color) calc(var(--pct) * 1%), var(--divider-color) 0);
      }
      .ring::after {
        content: '';
        position: absolute;
        width: calc(var(--size) - 6px);
        height: calc(var(--size) - 6px);
        border-radius: 50%;
        background: var(--card-background-color, white);
      }
      .ring-wrap {
        position: relative;
        display: grid;
        place-items: center;
      }
      .ring-wrap span {
        position: relative;
        z-index: 1;
      }
      .empty {
        color: var(--secondary-text-color);
        font-style: italic;
        text-align: center;
        padding: 12px;
      }
    `
  }

  static async getConfigElement(): Promise<HTMLElement> {
    await import('./family-chores-card-editor')
    return document.createElement('family-chores-card-editor')
  }

  static getStubConfig(): FamilyChoresCardConfig {
    return {
      type: 'custom:family-chores-card',
      show_pending_approvals: true,
    }
  }

  setConfig(config: FamilyChoresCardConfig): void {
    if (!config) {
      throw new Error('family-chores-card: missing configuration')
    }
    this._config = {
      show_pending_approvals: true,
      ...config,
    }
  }

  getCardSize(): number {
    return 3
  }

  protected shouldUpdate(changedProps: PropertyValues): boolean {
    return changedProps.has('_config') || changedProps.has('hass')
  }

  render(): TemplateResult {
    if (!this.hass || !this._config) {
      return html`<ha-card><div class="empty">Loading…</div></ha-card>`
    }

    const filterSet = this._config.members && this._config.members.length > 0
      ? new Set(this._config.members)
      : null
    const rows = discoverMembers(this.hass).filter(
      (m) => !filterSet || filterSet.has(m.slug),
    )

    const pending = this.hass.states[PENDING_APPROVALS_ENTITY]
    const pendingCount = pending ? Number.parseInt(pending.state, 10) || 0 : 0

    return html`
      <ha-card>
        <div class="header">
          <span class="title">${this._config.title ?? 'Family Chores'}</span>
          ${this._config.show_pending_approvals && pendingCount > 0
            ? html`<span class="badge" title="Pending parent approvals">
                ${pendingCount} to approve
              </span>`
            : null}
        </div>
        ${rows.length === 0
          ? html`<div class="empty">
              No <code>sensor.family_chores_*_points</code> entities found.
              Check that the add-on is running and has created at least one
              family member.
            </div>`
          : html`<div class="members">
              ${rows.map((m) => this._renderRow(m))}
            </div>`}
      </ha-card>
    `
  }

  private _renderRow(m: MemberRow): TemplateResult {
    return html`
      <div class="row" @click=${() => this._onTap()}>
        <div>
          <div class="name">${m.name}</div>
          <div class="meta">
            🔥 ${m.streak} day${m.streak === 1 ? '' : 's'} ·
            ⭐ ${m.points_this_week} this week
          </div>
        </div>
        <div class="ring-wrap">
          <div
            class="ring"
            style=${`--pct: ${m.progress_pct};`}
          ></div>
          <span>${m.progress_pct}%</span>
        </div>
        <div class="points">⭐ ${m.points_total}</div>
      </div>
    `
  }

  private _onTap(): void {
    const action = this._config?.tap_action
    if (action && action.action === 'none') return
    const path = action?.navigation_path ?? DEFAULT_NAV
    history.pushState(null, '', path)
    window.dispatchEvent(new Event('location-changed'))
  }
}

// Register with HA's custom-card picker.
declare global {
  interface Window {
    customCards?: Array<{
      type: string
      name: string
      description: string
      preview?: boolean
    }>
  }
}
window.customCards = window.customCards || []
if (!window.customCards.some((c) => c.type === 'family-chores-card')) {
  window.customCards.push({
    type: 'family-chores-card',
    name: 'Family Chores',
    description: 'At-a-glance points, streaks and progress for Family Chores.',
    preview: false,
  })
}
