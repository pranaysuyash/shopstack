/**
 * API-contract tests for src/api/client.ts.
 *
 * Evidence tier: T2 (executes real code; network + SecureStore are mocked,
 * so this is a white-box unit test of the /api/v1 request contract the mobile
 * app shares with the FastAPI backend).
 *
 * Per motto_v5 third-layer rule, this exercises ONLY the client layer — no
 * persistence, no real network. `fetch` and `expo-secure-store` are replaced.
 */
import {
  api,
  ApiErrorResponse,
  setCachedToken,
  setCachedBaseUrl,
  getCachedToken,
} from '../client';

// Node 22 provides a global `fetch`; we replace it with a controllable mock.
const mockFetch = jest.fn();
const originalFetch = global.fetch;

function makeResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response;
}

beforeAll(() => {
  // @ts-expect-error - assigning a mock to the global
  global.fetch = mockFetch;
});

afterAll(() => {
  // @ts-expect-error - restore real global
  global.fetch = originalFetch;
});

beforeEach(() => {
  mockFetch.mockReset();
  // Deterministic base URL + no auth token between cases.
  setCachedBaseUrl('http://localhost:7860');
  setCachedToken(null);
});

describe('apiRequest URL + header construction', () => {
  it('builds an absolute URL from the base URL and path', async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { ok: true }));

    await api.get<{ ok: boolean }>('/v1/households');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const calledUrl = mockFetch.mock.calls[0][0];
    expect(calledUrl).toBe('http://localhost:7860/v1/households');
  });

  it('sends Accept: application/json and no Authorization when unauthenticated', async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { ok: true }));

    await api.get<{ ok: boolean }>('/v1/households');

    const init = mockFetch.mock.calls[0][1];
    expect(init.method).toBe('GET');
    expect(init.headers).toMatchObject({ Accept: 'application/json' });
    expect(init.headers).not.toHaveProperty('Authorization');
  });

  it('injects Bearer token from the cached token when authenticated', async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { ok: true }));
    setCachedToken('tok-abc-123');

    await api.get<{ ok: boolean }>('/v1/items');

    const init = mockFetch.mock.calls[0][1];
    expect(init.headers).toMatchObject({ Authorization: 'Bearer tok-abc-123' });
  });

  it('serializes query params into the search string', async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { ok: true }));

    await api.get<unknown>('/v1/search', { q: 'milk', limit: 10, in_stock: true });

    const calledUrl = mockFetch.mock.calls[0][0];
    const url = new URL(calledUrl);
    expect(url.searchParams.get('q')).toBe('milk');
    expect(url.searchParams.get('limit')).toBe('10');
    expect(url.searchParams.get('in_stock')).toBe('true');
  });

  it('omits undefined params from the search string', async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { ok: true }));

    await api.get<unknown>('/v1/items', { category: 'dairy', store: undefined });

    const calledUrl = mockFetch.mock.calls[0][0];
    const url = new URL(calledUrl);
    expect(url.searchParams.get('category')).toBe('dairy');
    expect(url.searchParams.has('store')).toBe(false);
  });

  it('sets Content-Type and JSON-stringifies the body on POST', async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { created: true }));

    await api.post<unknown>('/v1/inventory/lots', { canonical_name: 'milk', quantity: 2 });

    const init = mockFetch.mock.calls[0][1];
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({ 'Content-Type': 'application/json' });
    expect(init.body).toBe(JSON.stringify({ canonical_name: 'milk', quantity: 2 }));
  });
});

describe('apiRequest response handling', () => {
  it('returns parsed JSON for a 200', async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { household_id: 'h1', name: 'Home' }));

    const data = await api.get<{ household_id: string; name: string }>('/v1/households/active');

    expect(data.household_id).toBe('h1');
    expect(data.name).toBe('Home');
  });

  it('returns undefined for a 204 No Content', async () => {
    mockFetch.mockResolvedValue(makeResponse(204, undefined));

    const data = await api.delete<undefined>('/v1/inventory/lots/l1');

    expect(data).toBeUndefined();
  });

  it('throws ApiErrorResponse with status + code on a non-2xx JSON body', async () => {
    mockFetch.mockResolvedValue(
      makeResponse(404, { code: 'not_found', message: 'Lot missing' }),
    );

    await expect(api.get<unknown>('/v1/inventory/lots/l1')).rejects.toThrow(ApiErrorResponse);

    try {
      await api.get<unknown>('/v1/inventory/lots/l1');
    } catch (err) {
      const e = err as ApiErrorResponse;
      expect(e.status).toBe(404);
      expect(e.code).toBe('not_found');
      expect(e.message).toBe('Lot missing');
    }
  });

  it('clears the cached token on 401 so the next auth gate is accurate', async () => {
    mockFetch.mockResolvedValue(makeResponse(401, { code: 'unauthorized', message: 'Bad token' }));
    setCachedToken('stale-token');

    expect(getCachedToken()).toBe('stale-token');

    await expect(api.get<unknown>('/v1/secure')).rejects.toThrow(ApiErrorResponse);

    // Token cache must be invalidated after a 401.
    expect(getCachedToken()).toBeNull();
  });

  it('falls back to a generic code when the error body is not JSON', async () => {
    const nonJson = {
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('not json')),
    } as unknown as Response;
    mockFetch.mockResolvedValue(nonJson);

    try {
      await api.get<unknown>('/v1/boom');
    } catch (err) {
      const e = err as ApiErrorResponse;
      expect(e.status).toBe(500);
      expect(e.code).toBe('http_500');
    }
  });
});
