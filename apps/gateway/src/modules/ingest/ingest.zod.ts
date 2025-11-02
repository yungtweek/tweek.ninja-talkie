import { z } from 'zod';
import { createZodDto } from 'nestjs-zod';
import { FileStatusZ, FileVisibilityZ } from '@talkie/types-zod';

const MAX_BYTES = 50 * 1024 * 1024;
const CT_ALLOWED = /^(image\/|application\/pdf|text\/plain)/;

// --- Base & State-based Schemas -------------------------------------------------
export const BaseMetaZ = z.object({
  bucket: z.string().min(1, 'bucket is required'),
  key: z.string().min(1, 'key is required'),
  filename: z.string().min(1).max(255),
  extension: z.string().min(1).max(10).optional().nullable(),
  ownerId: z.uuid(),

  // visibility defaults to private if not provided (input layer)
  visibility: FileVisibilityZ.default('private').optional(),

  // optional operational fields
  uploadedAt: z.coerce.date().optional().nullable(),
  modifiedAt: z.coerce.date().optional().nullable(),

  // integrity / expectations
  sizeExpected: z.number().int().positive().max(MAX_BYTES).optional().nullish(),
  checksumSha256Expected: z.string().length(44).optional().nullish(),

  // arbitrary metadata for pipeline/debug
  meta: z.record(z.string(), z.any()).optional(),
});

// --- Upsert (initial pending insert) -------------------------------------------
export const FileMetadataRegisterZ = z.object({
  bucket: BaseMetaZ.shape.bucket,
  key: BaseMetaZ.shape.key,
  filename: BaseMetaZ.shape.filename,
  extension: BaseMetaZ.shape.extension,
  ownerId: BaseMetaZ.shape.ownerId,
  visibility: FileVisibilityZ.default('private').optional(),
  contentType: z.string().regex(CT_ALLOWED, 'unsupported content type'),
  status: FileStatusZ.default('pending'),
  meta: BaseMetaZ.shape.meta,
});
export type FileMetadataRegister = z.infer<typeof FileMetadataRegisterZ>;

// --- Update (patch for any status) --------------------------------------------
// bucket/key는 식별자라 필수, 나머지는 패치 가능
export const FileMetadataUpsertZ = z
  .object({
    bucket: BaseMetaZ.shape.bucket,
    key: BaseMetaZ.shape.key,
    filename: BaseMetaZ.shape.filename,
    // patchable fields
    status: FileStatusZ.optional(),
    visibility: FileVisibilityZ.optional(),
    contentType: z.string().regex(CT_ALLOWED, 'unsupported content type').optional(),
    size: z.number().int().positive().max(MAX_BYTES).optional(),
    etag: z.string().min(1).optional(),
    uploadedAt: z.coerce.date().optional().nullable(),
    modifiedAt: z.coerce.date().optional().nullable(),
    meta: BaseMetaZ.shape.meta,
  })
  .superRefine((v, ctx) => {
    // 상태가 ready로 설정되는 경우, size/etag가 필수
    if (v.status === 'ready') {
      if (v.size == null) {
        ctx.addIssue({
          code: 'custom',
          path: ['size'],
          message: 'size is required when status is ready',
        });
      }
      if (!v.etag) {
        ctx.addIssue({
          code: 'custom',
          path: ['etag'],
          message: 'etag is required when status is ready',
        });
      }
    }
    // 상태가 pending으로 설정되면 contentType이 반드시 있어야 함
    if (v.status === 'pending') {
      if (!v.contentType) {
        ctx.addIssue({
          code: 'custom',
          path: ['contentType'],
          message: 'contentType is required when status is pending',
        });
      }
    }
  });
export type FileMetadataUpsert = z.infer<typeof FileMetadataUpsertZ>;

// NOTE: createZodDto requires a ZodObject, not a union. Use the common base for implements/shape.
export class FileMetadataZDto extends createZodDto(BaseMetaZ) {}
export class FileMetadataRegisterZDto extends createZodDto(FileMetadataRegisterZ) {}
export class FileMetadataUpsertZDto extends createZodDto(FileMetadataUpsertZ) {}
