// Base HTTP client for the Family Chores API.
// All URLs are relative (`./api/...`) so the app works under Ingress
// regardless of the proxy prefix.
const API_BASE = './api';
export class APIError extends Error {
    status;
    errorCode;
    detail;
    requestId;
    constructor(status, errorCode, detail, requestId) {
        super(`${errorCode}: ${detail}`);
        this.status = status;
        this.errorCode = errorCode;
        this.detail = detail;
        this.requestId = requestId;
    }
}
export async function apiFetch(path, init = {}) {
    const { parentToken, json, headers, ...rest } = init;
    const finalHeaders = {
        Accept: 'application/json',
        ...(headers ?? {}),
    };
    let body = rest.body;
    if (json !== undefined) {
        body = JSON.stringify(json);
        finalHeaders['Content-Type'] = 'application/json';
    }
    if (parentToken) {
        finalHeaders['Authorization'] = `Bearer ${parentToken}`;
    }
    const url = `${API_BASE}${path}`;
    const response = await fetch(url, { ...rest, body, headers: finalHeaders });
    if (!response.ok) {
        let errBody = {};
        try {
            errBody = await response.json();
        }
        catch {
            // not JSON — fall through with default error shape
        }
        throw new APIError(response.status, errBody.error ?? 'http_error', errBody.detail ?? response.statusText, errBody.request_id);
    }
    if (response.status === 204) {
        return undefined;
    }
    return response.json();
}
