import { authStore } from '@/features/auth/auth.store';

describe('authStore', () => {
  beforeEach(() => {
    // Initialize to isolate state for each test
    const s = authStore.getState();
    if (typeof s.reset === 'function') s.reset();
  });

  it('should set and reset user state', () => {
    const s = authStore.getState();

    // Initial value: user should be null
    expect(s.user).toBeNull();

    // Set user with setUser
    s.setUser({ username: 'tester', pns: 'test', role: 'user' });
    expect(authStore.getState().user).toEqual({ username: 'tester', pns: 'test', role: 'user' });

    // Reset to initial state
    s.reset();
    expect(authStore.getState().user).toBeNull();
  });

  it('can toggle loading and set error (if provided by store)', () => {
    const s = authStore.getState();

    // Test only if setLoading exists
    if (typeof s.setLoading === 'function') {
      s.setLoading(true);
      expect(authStore.getState().loading).toBe(true);
      s.setLoading(false);
      expect(authStore.getState().loading).toBe(false);
    }

    // Test only if setError exists
    if (typeof s.setError === 'function') {
      s.setError('login failed');
      expect(authStore.getState().error).toBe('login failed');
    }
  });
});
