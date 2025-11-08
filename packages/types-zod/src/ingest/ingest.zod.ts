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

/**
 * Ingest presign request
 * - Used when requesting a presigned URL for file upload.
 * - Validates metadata of the file before generating the URL.
 */
const MIME_RE = /^[\w.+-]+\/[\w.+-]+$/;
const SHA256_HEX_RE = /^[a-f0-9]{64}$/i;
const BASE64_RE = /^[A-Za-z0-9+/]+={0,2}$/;
const MAX_UPLOAD_BYTES = 1024 * 1024 * 1024; // 1 GiB

export const PresignRequestZ = z.object({
  filename: z.string().trim().min(1, 'filename is required').max(255, 'filename too long'),
  checksum: z
    .string()
    .trim()
    .refine(
      s => SHA256_HEX_RE.test(s) || (BASE64_RE.test(s) && s.length >= 43 && s.length <= 44),
      'checksum must be sha256 (hex64 or base64)',
    ),
  contentType: z.string().trim().regex(MIME_RE, 'invalid content type'),
  size: z.coerce
    .number() // "12345" 도 숫자로 변환
    .int()
    .nonnegative()
    // .finite()
    .refine(Number.isSafeInteger, 'size must be a safe integer')
    .max(MAX_UPLOAD_BYTES, 'file too large (max 1GB)'),
});

export type PresignRequest = z.infer<typeof PresignRequestZ>;

/**
 * Presign response
 * - Returned by the server when issuing a presigned PUT URL.
 * - Contains the target location and upload contract fields.
 */
const S3_BUCKET_RE = /^(?!\d+\.)[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/; // relaxed, S3-like

export const PresignResponseZ = z.object({
  url: z.string().url('invalid URL'),
  bucket: z
    .string()
    .trim()
    .min(3, 'bucket too short')
    .max(63, 'bucket too long')
    .regex(S3_BUCKET_RE, 'invalid bucket name'),
  key: z.string().trim().min(1, 'key is required').max(1024, 'key too long'),
  expiresIn: z.number().int().positive('expiresIn must be > 0 (seconds)'),
  extension: z.string().trim().min(1, 'extension is required').max(16, 'extension too long'),
  contentType: z.string().trim().regex(MIME_RE, 'invalid content type'),
});

export type PresignResponse = z.infer<typeof PresignResponseZ>;

/**
 * Upload complete request
 * - Called after a successful upload to MinIO (S3-compatible).
 * - Notifies the server that the file is now available for indexing.
 */
export const CompleteRequestZ = z.object({
  bucket: z
    .string()
    .trim()
    .min(3, 'bucket too short')
    .max(63, 'bucket too long')
    .regex(S3_BUCKET_RE, 'invalid bucket name'),
  key: z.string().trim().min(1, 'key is required').max(1024, 'key too long'),
  filename: z.string().trim().min(1, 'filename is required').max(255, 'filename too long'),
});

export type CompleteRequest = z.infer<typeof CompleteRequestZ>;

export const CompleteResponseZ = z.object({
  message: z.string(),
  record: z.union([
    z.object({
      key: z.string(),
      status: z.string(),
      updatedAt: z.coerce.date(),
    }),
    z.object({}).strict(),
  ]),
});
export type CompleteResponse = z.infer<typeof CompleteResponseZ>;
