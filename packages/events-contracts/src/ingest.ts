import { z } from 'zod';
import { FILE_STATUS, FILE_VISIBILITY } from '@talkie/types-zod';
export const IngestEventVersion = 1 as const;

// derive local zod enums from shared literals to keep contracts runtime-agnostic and typed
const FileStatusZ = z.enum(FILE_STATUS);
const FileVisibilityZ = z.enum(FILE_VISIBILITY);

export const IngestEventType = {
  REGISTERED: 'file.registered',
  STATUS_CHANGED: 'file.status.changed',
  VISIBILITY_CHANGED: 'file.visibility.changed',
  DELETED: 'file.deleted',
} as const;

// Use a tuple assertion so z.enum receives [string, ...string[]]
export const IngestEventTypeZ = z.enum(Object.values(IngestEventType) as [string, ...string[]]);
export type IngestEventType = z.infer<typeof IngestEventTypeZ>;

export const IngestEventBaseZ = z.object({
  v: z.literal(IngestEventVersion),
  ts: z.number().int().nonnegative(),
  type: IngestEventTypeZ,
  correlationId: z.string().optional(),
  from: z.enum(['gateway', 'worker', 'api']).optional(),
});

export const FileRegisteredEventZ = IngestEventBaseZ.extend({
  type: z.literal('file.registered'),
  payload: z.object({
    id: z.uuid(),
    filename: z.string(),
    contentType: z.string().nullable(),
    size: z.number().int().nonnegative().nullable().optional(),
    visibility: FileVisibilityZ,
    uploadedAt: z.union([z.string(), z.date()]),
    createdAt: z.union([z.string(), z.date()]),
    status: FileStatusZ,
    meta: z.record(z.string(), z.any()).optional(),
  }),
});

export const FileStatusChangedEventZ = IngestEventBaseZ.extend({
  type: z.literal('file.status.changed'),
  payload: z.object({
    id: z.uuid(),
    prev: FileStatusZ,
    next: FileStatusZ,
  }),
});

export const FileVisibilityChangedEventZ = IngestEventBaseZ.extend({
  type: z.literal('file.visibility.changed'),
  payload: z.object({
    id: z.uuid(),
    prev: FileVisibilityZ,
    next: FileVisibilityZ,
  }),
});

export const FileDeletedEventZ = IngestEventBaseZ.extend({
  type: z.literal('file.deleted'),
  payload: z.object({
    id: z.uuid(),
    deletedAt: z.string(),
    vectorsDeleted: z.number().int().nonnegative().optional(),
  }),
});

export const IngestEventZ = z.discriminatedUnion('type', [
  FileRegisteredEventZ,
  FileStatusChangedEventZ,
  FileVisibilityChangedEventZ,
  FileDeletedEventZ,
]);

// TS types
export type IngestEvent = z.infer<typeof IngestEventZ>;
// ---- Typed aliases per event -------------------------------------------------
export type IngestEventBase = z.infer<typeof IngestEventBaseZ>;

export type FileRegisteredEvent = z.infer<typeof FileRegisteredEventZ>;
export type FileStatusChangedEvent = z.infer<typeof FileStatusChangedEventZ>;
export type FileVisibilityChangedEvent = z.infer<typeof FileVisibilityChangedEventZ>;
export type FileDeletedEvent = z.infer<typeof FileDeletedEventZ>;

// Payload-only helpers
export type FileRegisteredPayload = FileRegisteredEvent['payload'];
export type FileStatusChangedPayload = FileStatusChangedEvent['payload'];
export type FileVisibilityChangedPayload = FileVisibilityChangedEvent['payload'];
export type FileDeletedPayload = FileDeletedEvent['payload'];

// ---- Discriminated union helpers --------------------------------------------
export type ExtractEvent<TType extends IngestEvent['type']> = Extract<IngestEvent, { type: TType }>;
export type PayloadOf<TType extends IngestEvent['type']> = ExtractEvent<TType>['payload'];

// Type guards for convenient narrowing in consumers (web/gateway)
export const isStatusChanged = (e: IngestEvent): e is FileStatusChangedEvent =>
  e.type === IngestEventType.STATUS_CHANGED;

export const isVisibilityChanged = (e: IngestEvent): e is FileVisibilityChangedEvent =>
  e.type === IngestEventType.VISIBILITY_CHANGED;

export const isFileRegistered = (e: IngestEvent): e is FileRegisteredEvent =>
  e.type === IngestEventType.REGISTERED;

export const isFileDeleted = (e: IngestEvent): e is FileDeletedEvent =>
  e.type === IngestEventType.DELETED;

// optional: pure helpers
// Note: Web-only helpers (e.g., dedupeKey with Apollo types) should live in the web app,
// not in contracts. Keep contracts runtime-agnostic.
export const topicForUserFiles = (userId: string) => `user:${userId}:files`;
