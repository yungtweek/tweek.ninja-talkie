async function callRefresh() {
  return await fetch('/api/auth/refresh', {
    method: 'POST',
    credentials: 'include',
    cache: 'no-store',
    headers: { 'content-type': 'application/json' },
  });
}

let inflightRefresh: Promise<boolean> | null = null;

export async function refreshOnce(): Promise<boolean> {
  if (!inflightRefresh) {
    inflightRefresh = (async () => {
      try {
        const res = await callRefresh();
        return res.ok;
      } catch (err) {
        console.error('Refresh failed:', err);
        return false;
      } finally {
        inflightRefresh = null;
      }
    })();
  }
  return inflightRefresh;
}
