// apps/gateway/src/graphql/utils/cursor.ts
import { Buffer } from 'buffer';
/**
 * Convert a numeric index into a Base64-encoded cursor string.
 * Typically used for simple offset-based pagination.
 *
 * @param idx - Numeric index value
 * @returns Base64 cursor string
 */
export const toCursor = (idx: number) => {
  return Buffer.from(String(idx)).toString('base64');
};

/**
 * Decode a Base64 cursor string back into a numeric index.
 *
 * @param c - Base64 cursor string (or null/undefined)
 * @returns Decoded numeric index or undefined if invalid
 */
export const fromCursor = (c?: string | null) => {
  return c ? Number(Buffer.from(c, 'base64').toString()) : undefined;
};

/**
 * Encode any serializable object into a Base64 cursor string.
 * Used for cursor-based pagination.
 *
 * @param obj - Any JSON-serializable data (e.g., { createdAt, id })
 */
export const encodeCursor = <T extends Record<string, any>>(obj: T): string => {
  return Buffer.from(JSON.stringify(obj), 'utf8').toString('base64');
};

/**
 * Decode a Base64 cursor string back into the original object.
 *
 * @param cursor - Base64 string (or null/undefined)
 * @returns Parsed object or null if invalid
 */
export const decodeCursor = <T extends Record<string, any>>(cursor?: string | null): T | null => {
  if (!cursor) return null;
  try {
    const json = Buffer.from(cursor, 'base64').toString('utf8');
    return JSON.parse(json) as T;
  } catch (e) {
    console.error('Failed to decode cursor:', e);
    return null;
  }
};
