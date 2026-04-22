import { afterEach, describe, expect, it, vi } from 'vitest'
import { APIError, apiFetch } from './client'

const originalFetch = global.fetch

afterEach(() => {
  global.fetch = originalFetch
  vi.restoreAllMocks()
})

function mockFetch(response: Response): void {
  global.fetch = vi.fn().mockResolvedValue(response) as unknown as typeof fetch
}

describe('apiFetch', () => {
  it('parses JSON on 2xx', async () => {
    mockFetch(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const data = await apiFetch<{ ok: boolean }>('/health')
    expect(data.ok).toBe(true)
  })

  it('returns undefined on 204', async () => {
    mockFetch(new Response(null, { status: 204 }))
    const data = await apiFetch<void>('/something', { method: 'DELETE' })
    expect(data).toBeUndefined()
  })

  it('throws APIError with fields from error body', async () => {
    // Use vi.fn so we can stream distinct Response objects (a Response body
    // can only be read once — reusing the same instance drains it).
    const makeResponse = () =>
      new Response(
        JSON.stringify({
          error: 'not_found',
          detail: 'member ghost not found',
          request_id: 'abc123',
        }),
        {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        },
      )
    global.fetch = vi
      .fn()
      .mockImplementation(() => Promise.resolve(makeResponse())) as unknown as typeof fetch

    let caught: unknown
    try {
      await apiFetch('/members/ghost')
    } catch (e) {
      caught = e
    }
    expect(caught).toBeInstanceOf(APIError)
    const err = caught as APIError
    expect(err.status).toBe(404)
    expect(err.errorCode).toBe('not_found')
    expect(err.detail).toBe('member ghost not found')
    expect(err.requestId).toBe('abc123')
  })

  it('falls back to http_error on non-JSON error body', async () => {
    mockFetch(new Response('<html>oops</html>', { status: 500 }))
    try {
      await apiFetch('/anything')
    } catch (e) {
      const err = e as APIError
      expect(err.errorCode).toBe('http_error')
      expect(err.status).toBe(500)
    }
  })

  it('attaches Bearer header when parentToken is supplied', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    global.fetch = fetchSpy as unknown as typeof fetch
    await apiFetch('/admin/activity', { parentToken: 'tok-xyz' })

    const call = fetchSpy.mock.calls[0]
    const headers = (call[1] as RequestInit).headers as Record<string, string>
    expect(headers['Authorization']).toBe('Bearer tok-xyz')
  })

  it('serialises `json` option into a POST body + content-type', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    global.fetch = fetchSpy as unknown as typeof fetch
    await apiFetch('/members', { method: 'POST', json: { slug: 'alice' } })

    const call = fetchSpy.mock.calls[0]
    const init = call[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"slug":"alice"}')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe(
      'application/json',
    )
  })
})
