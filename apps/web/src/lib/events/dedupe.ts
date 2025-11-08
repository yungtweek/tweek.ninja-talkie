// apps/web/src/lib/events/dedupe.ts
'use client';

type Options = {
  ttlMs?: number;
  maxKeys?: number;
};

export function createDedupe({ ttlMs = 1500, maxKeys }: Options = {}) {
  const seen = new Map<string, number>();

  const compact = () => {
    if (!maxKeys || seen.size <= maxKeys) return;
    const entries = [...seen.entries()].sort((a, b) => a[1] - b[1]);
    for (let i = 0; i < seen.size - maxKeys; i++) {
      seen.delete(entries[i][0]);
    }
  };

  return (key: string | string[]) => {
    const k = Array.isArray(key) ? key.join('/') : key;
    const now = Date.now();
    const last = seen.get(k) ?? 0;
    if (now - last < ttlMs) return true;
    seen.set(k, now);
    compact();
    return false;
  };
}
