// Base HTTP client for the Family Chores API.
// All URLs are relative (`./api/...`) so the app works under Ingress
// regardless of the proxy prefix.

const API_BASE = './api'

export class APIError extends Error {
  constructor(
    public status: number,
    public errorCode: string,
    public detail: string,
    public requestId?: string,
  ) {
    super(`${errorCode}: ${detail}`)
  }
}

export interface APIFetchInit extends RequestInit {
  parentToken?: string | null
  json?: unknown
}

export async function apiFetch<T = unknown>(
  path: string,
  init: APIFetchInit = {},
): Promise<T> {
  const { parentToken, json, headers, ...rest } = init
  const finalHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...((headers as Record<string, string>) ?? {}),
  }
  let body: BodyInit | null | undefined = rest.body
  if (json !== undefined) {
    body = JSON.stringify(json)
    finalHeaders['Content-Type'] = 'application/json'
  }
  if (parentToken) {
    finalHeaders['Authorization'] = `Bearer ${parentToken}`
  }

  const url = `${API_BASE}${path}`
  const response = await fetch(url, { ...rest, body, headers: finalHeaders })

  if (!response.ok) {
    let errBody: {
      error?: string
      detail?: string
      request_id?: string
    } = {}
    try {
      errBody = await response.json()
    } catch {
      // not JSON — fall through with default error shape
    }
    throw new APIError(
      response.status,
      errBody.error ?? 'http_error',
      errBody.detail ?? response.statusText,
      errBody.request_id,
    )
  }

  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}
