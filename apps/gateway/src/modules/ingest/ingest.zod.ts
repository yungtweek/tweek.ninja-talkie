import { z } from 'zod';
import { createZodDto } from 'nestjs-zod';

const MAX_BYTES = 50 * 1024 * 1024;
const CT_ALLOWED = /^(image\/|application\/pdf|text\/plain)/;

export const FileMetadataSchema = z
  .object({
    bucket: z.string().min(1, 'bucket is required'),
    key: z.string().min(1, 'key is required'),
    filename: z.string().min(1).max(255),
    extension: z.string().min(1).max(10).optional().nullable(),
    contentType: z.string().regex(CT_ALLOWED, 'unsupported content type').optional(),
    sizeExpected: z.number().int().positive().max(MAX_BYTES).optional().nullish(),
    checksumSha256Expected: z.string().length(44).optional().nullish(),
    size: z.number().int().positive().max(MAX_BYTES).optional().nullish(),
    etag: z.string().min(1).optional().nullable(),
    status: z
      .enum(['pending', 'ready', 'failed', 'deleted', 'indexed', 'vectorized'])
      .default('pending')
      .optional(),
    visibility: z
      .enum(['private', 'followers', 'department', 'public'])
      .default('private')
      .optional(),
    ownerId: z.uuid(),
    uploadedAt: z.coerce.date().optional().nullable(),
    modifiedAt: z.coerce.date().optional().nullable(),
  })
  .superRefine((v, ctx) => {
    if (v.status === 'pending') {
      for (const f of ['bucket', 'key', 'filename', 'extension', 'contentType'] as const) {
        if (!v[f]) {
          ctx.addIssue({
            code: 'custom',
            path: [f],
            message: `${f} is required in pending`,
          });
        }
        if (v.sizeExpected && !(v.sizeExpected > 0)) {
          ctx.addIssue({
            code: 'custom',
            path: ['sizeExpected'],
            message: `must be > 0`,
          });
        }
      }
    }

    if (v.status === 'ready') {
      for (const f of ['size', 'etag', 'contentType'] as const) {
        if (v[f] == null || (typeof v[f] === 'string' && v[f].length === 0)) {
          ctx.addIssue({
            code: 'custom',
            path: [f],
            message: 'required in uploaded',
          });
        }
      }
    }
  });

export class FileMetadataZDto extends createZodDto(FileMetadataSchema) {}
