/**
 * Lovelace GUI editor for family-chores-card. Presents a checkbox per
 * discovered family member plus a toggle for the pending-approvals badge
 * and an override for the navigation path.
 */

import { LitElement, html, css, type TemplateResult } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import type { FamilyChoresCardConfig } from './family-chores-card'

interface HassState {
  state: string
  attributes: Record<string, unknown>
  entity_id: string
}

interface HomeAssistant {
  states: Record<string, HassState>
}

const PREFIX = 'sensor.family_chores_'
const SUFFIX = '_points'

@customElement('family-chores-card-editor')
export class FamilyChoresCardEditor extends LitElement {
  @property({ attribute: false }) hass?: HomeAssistant
  @state() private _config?: FamilyChoresCardConfig

  static get styles() {
    return css`
      .editor {
        padding: 12px 0;
        display: grid;
        gap: 16px;
      }
      label.field {
        display: grid;
        gap: 4px;
      }
      label.check {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      input[type='text'] {
        padding: 6px 8px;
        font-size: 0.95rem;
        border: 1px solid var(--divider-color);
        border-radius: 6px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
      }
      h3 {
        margin: 0 0 4px;
        font-size: 0.9rem;
        color: var(--primary-text-color);
      }
      .hint {
        color: var(--secondary-text-color);
        font-size: 0.8rem;
      }
      .member-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
        gap: 4px;
      }
    `
  }

  setConfig(config: FamilyChoresCardConfig): void {
    this._config = { ...config }
  }

  private _discoverMemberSlugs(): { slug: string; name: string }[] {
    if (!this.hass) return []
    const out: { slug: string; name: string }[] = []
    for (const entityId of Object.keys(this.hass.states)) {
      if (!entityId.startsWith(PREFIX) || !entityId.endsWith(SUFFIX)) continue
      const slug = entityId.slice(PREFIX.length, entityId.length - SUFFIX.length)
      const name = (this.hass.states[entityId].attributes.name as string) ?? slug
      out.push({ slug, name })
    }
    return out.sort((a, b) => a.name.localeCompare(b.name))
  }

  private _patch(patch: Partial<FamilyChoresCardConfig>): void {
    const next: FamilyChoresCardConfig = {
      type: 'custom:family-chores-card',
      ...this._config,
      ...patch,
    }
    this._config = next
    this.dispatchEvent(
      new CustomEvent('config-changed', {
        detail: { config: next },
        bubbles: true,
        composed: true,
      }),
    )
  }

  private _toggleMember(slug: string, on: boolean): void {
    const current = new Set(this._config?.members ?? [])
    if (on) current.add(slug)
    else current.delete(slug)
    this._patch({ members: current.size === 0 ? undefined : Array.from(current) })
  }

  render(): TemplateResult {
    if (!this._config) return html``
    const members = this._discoverMemberSlugs()
    const selectedSet = new Set(this._config.members ?? [])
    const selectingAll = !this._config.members || this._config.members.length === 0

    return html`
      <div class="editor">
        <label class="field">
          <h3>Title</h3>
          <input
            type="text"
            .value=${this._config.title ?? ''}
            @input=${(e: Event) =>
              this._patch({
                title: (e.target as HTMLInputElement).value || undefined,
              })}
          />
          <span class="hint">Leave blank for "Family Chores"</span>
        </label>

        <label class="check">
          <input
            type="checkbox"
            .checked=${this._config.show_pending_approvals !== false}
            @change=${(e: Event) =>
              this._patch({
                show_pending_approvals: (e.target as HTMLInputElement).checked,
              })}
          />
          Show pending-approvals badge
        </label>

        <label class="field">
          <h3>Navigation path on tap</h3>
          <input
            type="text"
            .value=${this._config.tap_action?.navigation_path ?? ''}
            placeholder="/hassio/ingress/local_family_chores"
            @input=${(e: Event) => {
              const v = (e.target as HTMLInputElement).value.trim()
              this._patch({
                tap_action: v
                  ? { action: 'navigate', navigation_path: v }
                  : undefined,
              })
            }}
          />
          <span class="hint">
            Leave blank for the default Ingress path.
          </span>
        </label>

        <div>
          <h3>Members to show</h3>
          <span class="hint">
            ${selectingAll
              ? 'Showing all family members (default)'
              : `Showing ${selectedSet.size} of ${members.length}`}
          </span>
          <div class="member-grid">
            ${members.length === 0
              ? html`<span class="hint"
                  >No family members discovered yet.</span
                >`
              : members.map(
                  (m) => html`
                    <label class="check">
                      <input
                        type="checkbox"
                        .checked=${selectingAll || selectedSet.has(m.slug)}
                        @change=${(e: Event) =>
                          this._toggleMember(
                            m.slug,
                            (e.target as HTMLInputElement).checked,
                          )}
                      />
                      ${m.name}
                      <span class="hint">(${m.slug})</span>
                    </label>
                  `,
                )}
          </div>
        </div>
      </div>
    `
  }
}
