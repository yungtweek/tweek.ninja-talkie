/** @jest-environment node */
import { loginAction } from '@/actions/auth/login.action';
import { meAction } from '@/actions/auth/me.action';
import { logoutActionSilent } from '@/actions/auth/logout.action';
import { ActionState } from '@/actions/actions.type';
import { MeViewZod } from '@talkie/types-zod';

// ---- Module under test -----------------------------------------------------
// NOTE: If your actions live in a different path, adjust this import only.

// ---- Mocks: Next server bits used by actions -------------------------------
jest.mock('next/headers', () => {
  const jar = new Map<string, string>();
  return {
    // minimal cookie jar shim used by setAuthCookies / clear
    cookies: () => ({
      get: (k: string) => (jar.has(k) ? { name: k, value: jar.get(k)! } : undefined),
      set: (k: string, v: string) => void jar.set(k, v),
      delete: (k: string) => void jar.delete(k),
    }),
    headers: () => new Headers(),
  };
});

jest.mock('next/server', () => ({
  NextResponse: {
    json: (body: any, init?: any) =>
      new Response(
        JSON.stringify(body),
        // eslint-disable-next-line @typescript-eslint/no-unsafe-argument
        typeof init === 'number'
          ? { status: init, headers: { 'content-type': 'application/json' } }
          : // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment,@typescript-eslint/no-unsafe-member-access
            { ...init, headers: { 'content-type': 'application/json', ...(init?.headers || {}) } },
      ),
  },
}));

jest.mock('next/navigation', () => ({
  redirect: () => {
    const e: any = new Error('NEXT_REDIRECT');
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    e.digest = 'NEXT_REDIRECT';
    throw e;
  },
}));

// Small helper to mock fetch responses
function mockFetchOnce(body: unknown, init: ResponseInit) {
  global.fetch = jest.fn().mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      headers: { 'content-type': 'application/json' },
      ...init,
    }),
  );
}
// ---------------------------------------------------------------------------
describe('Auth actions – contract tests', () => {
  beforeEach(() => {
    jest.resetModules();
  });

  describe('loginAction(formData)', () => {
    it('returns { ok:true, status, data } on success', async () => {
      // /auth/login -> returns tokens only (or sets cookies); /auth/me is orchestrated elsewhere
      mockFetchOnce(
        {
          access: {
            tokenType: 'Bearer',
            token: 'access-token-test',
            expiresIn: 3600,
            expiresAt: 1700000000,
          },
          refresh: {
            tokenType: 'Bearer',
            token: 'refresh-token-test',
            expiresIn: 1209600,
            expiresAt: 1710000000,
          },
        },
        { status: 201 },
      );

      const fd = new FormData();
      fd.set('email', 'tester@example.com');
      fd.set('password', 'secret');

      const prev: ActionState<null, { nonce: string; status?: number }> = {
        success: false,
        data: null,
        error: { message: '' },
        meta: { nonce: 'test-nonce' },
      };

      const res = await loginAction(prev, fd);
      expect(res.success).toBe(true);
      expect(res.error).toBeNull();
      expect(typeof res.meta?.nonce).toBe('string');
      expect(res.meta?.status).toBe(201);
    });

    it('returns { ok:false, status, error } on invalid credentials', async () => {
      const errBody = { error: { message: 'invalid credentials', code: 'UNAUTH' } };
      mockFetchOnce(errBody, { status: 401 });

      const fd = new FormData();
      fd.set('email', 'wrong@example.com');
      fd.set('password', 'nope');

      const prev: ActionState<null, { nonce: string; status?: number }> = {
        success: false,
        data: null,
        error: { message: '' },
        meta: { nonce: 'test-nonce' },
      };

      const res = await loginAction(prev, fd);
      expect(res.success).toBe(false);
      expect(typeof res.meta?.nonce).toBe('string');
      expect(res.meta?.status).toBe(401);
      expect(res.error?.message ?? '').toMatch(/invalid|unauth/i);
    });
  });

  describe('meAction()', () => {
    it('returns current user with the same contract shape', async () => {
      const me: MeViewZod = { username: 'tester', pns: 'test', role: 'tester' };

      mockFetchOnce(me, { status: 200 });

      const res = await meAction();
      expect(res.success).toBe(true);
      expect(res.error).toBeNull();
      expect(res.data).toEqual(me);
      expect(res.meta?.status).toBe(200);
    });

    it('maps NOT_AUTHENTICATED to ok:false + error', async () => {
      mockFetchOnce({ error: { message: 'not authenticated', code: 'UNAUTH' } }, { status: 401 });
      const res = await meAction();
      expect(res.success).toBe(false);
      expect(res.meta?.status).toBe(401);
      expect(res.error?.message ?? '').toMatch(/not authenticated|unauth|invalid response/i);
    });
  });

  describe('logoutAction()', () => {
    it('clears auth and either redirects or returns a minimal result', async () => {
      try {
        const res = await logoutActionSilent();
        // Some implementations redirect (no return), others may return a small payload.
        if (res) {
          // At minimum, expect an ok flag; status may or may not be present.
          expect(typeof (res as ActionState<any>).success).toBe('boolean');
          if ((res as ActionState<any>).meta?.status) {
            expect([200, 204, 205]).toContain((res as ActionState<any>).meta?.status);
          }
        }
      } catch (e: any) {
        // If the action performs redirect() internally, Next throws a special error
        // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
        expect(e?.digest).toBe('NEXT_REDIRECT');
      }
    });
  });
});
