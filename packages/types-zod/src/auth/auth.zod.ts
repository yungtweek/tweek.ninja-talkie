import {z} from 'zod';

/**
 * 토큰 정보 스키마
 */
export const TokenViewZ = z.object({
    tokenType: z.literal('Bearer'),
    token: z.string().min(10),
    issuedAt: z.number().int().optional(),
    expiresIn: z.number().int(),
    expiresAt: z.number().int(),
});

/**
 * AuthViewZod 스키마 (access + optional refresh)
 */
export const AuthViewZ = z.object({
    access: TokenViewZ,
    refresh: TokenViewZ.omit({issuedAt: true}).optional(),
});

export const MeViewZ = z.object({
    username: z.string(),
    pns: z.string(),
    role: z.string(),
});

export type TokenViewZod = z.infer<typeof TokenViewZ>;
export type AuthViewZod = z.infer<typeof AuthViewZ>;
export type MeViewZod = z.infer<typeof MeViewZ>;