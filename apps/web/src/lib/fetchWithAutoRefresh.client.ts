// lib/fetchWithAutoRefresh.client.ts
import { refreshOnce } from './refreshOnce';

export async function fetchWithAutoRefresh(input: RequestInfo, init: RequestInit = {}) {
  const run = () => fetch(input, { ...init });

  const fetchRequest = await run();

  if (fetchRequest.status !== 401) return fetchRequest;

  if (!fetchRequest.headers.get('x-refreshed')) {
    const ok = await refreshOnce();
    if (!ok) {
      return fetchRequest;
    }
  }

  return run();
}
