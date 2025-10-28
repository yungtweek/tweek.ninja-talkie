// src/common/utils/case.util.ts

// ---------- Type helpers ----------
export type CamelCase<S extends string> = S extends `${infer H}_${infer T}`
  ? `${H}${Capitalize<CamelCase<T>>}`
  : S;

export type SnakeCase<S extends string> = S extends `${infer H}${infer T}`
  ? T extends Uncapitalize<T>
    ? `${Lowercase<H>}${SnakeCase<T>}`
    : `${Lowercase<H>}_${SnakeCase<T>}`
  : S;

export type WithCamelKeys<T extends object> = {
  [K in keyof T as K extends string ? CamelCase<K> : K]: T[K];
};

export type WithSnakeKeys<T extends object> = {
  [K in keyof T as K extends string ? SnakeCase<K> : K]: T[K];
};

// ---------- Runtime helpers ----------
const toSnake = (s: string) =>
  s.replace(/[A-Z]/g, (l) => `_${l.toLowerCase()}`);
const toCamel = (s: string) =>
  s.replace(/_([a-z])/g, (_: string, l: string) => l.toUpperCase());

/**
 * Convert object keys from camelCase to snake_case (value types preserved)
 */
export function toSnakeCase<T extends object>(obj: T): WithSnakeKeys<T> {
  const mapped = Object.entries(obj as Record<string, unknown>).map(
    ([k, v]) => [toSnake(k), v] as const,
  );
  return Object.fromEntries(mapped) as WithSnakeKeys<T>;
}

/**
 * Convert object keys from snake_case to camelCase (value types preserved)
 */
export function toCamelCase<T extends object>(obj: T): WithCamelKeys<T> {
  const mapped = Object.entries(obj as Record<string, unknown>).map(
    ([k, v]) => [toCamel(k), v] as const,
  );
  return Object.fromEntries(mapped) as WithCamelKeys<T>;
}
