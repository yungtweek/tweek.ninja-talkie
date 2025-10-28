// src/modules/users/dto/user.zod.ts/
import { z } from 'zod';

export const UserSchema = z.object({
  id: z.uuid(),
  username: z.string().min(1).max(50),
  email: z.email().nullable(),
  pwd_shadow: z.string().nullable(),
  public_ns: z.string().min(1),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});

export type UserRow = z.infer<typeof UserSchema>;
