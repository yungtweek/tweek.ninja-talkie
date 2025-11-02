import { z } from 'zod';

/**
 * Shared literals (single source of truth)
 * - Other layers (GraphQL, events, web) can import these to avoid value drift.
 */
export const FILE_STATUS = [
  'pending',
  'ready',
  'failed',
  'deleted',
  'indexed',
  'vectorized',
] as const;
export type FileStatusValue = (typeof FILE_STATUS)[number];

export const FILE_VISIBILITY = ['private', 'followers', 'department', 'public'] as const;
export type FileVisibilityValue = (typeof FILE_VISIBILITY)[number];

/**
 * Zod enums
 */
export const FileStatusZ = z.enum(FILE_STATUS);
export type FileStatus = z.infer<typeof FileStatusZ>;

export const FileVisibilityZ = z.enum(FILE_VISIBILITY);
export type FileVisibility = z.infer<typeof FileVisibilityZ>;

/**
 * Enum-like value namespaces for DX (runtime values)
 * - Keep using `FileStatus.Ready` while type remains `'ready' | ...`
 * - IMPORTANT: when importing the type, use `import type { FileStatus }` to avoid value/type collisions.
 */
export const FileStatus = {
  Pending: 'pending',
  Ready: 'ready',
  Failed: 'failed',
  Deleted: 'deleted',
  Indexed: 'indexed',
  Vectorized: 'vectorized',
} as const satisfies Record<Capitalize<FileStatusValue>, FileStatusValue>;

export const FileVisibility = {
  Private: 'private',
  Followers: 'followers',
  Department: 'department',
  Public: 'public',
} as const satisfies Record<Capitalize<FileVisibilityValue>, FileVisibilityValue>;

/**
 * (Optional) Narrow type guards for runtime checks without throwing
 */
export const isFileStatus = (v: unknown): v is FileStatusValue =>
  typeof v === 'string' && (FILE_STATUS as readonly string[]).indexOf(v) !== -1;

export const isFileVisibility = (v: unknown): v is FileVisibilityValue =>
  typeof v === 'string' && (FILE_VISIBILITY as readonly string[]).indexOf(v) !== -1;
