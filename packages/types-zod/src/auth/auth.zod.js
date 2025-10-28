"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.MeViewZ = exports.AuthViewZ = exports.TokenViewZ = void 0;
var zod_1 = require("zod");
/**
 * 토큰 정보 스키마
 */
exports.TokenViewZ = zod_1.z.object({
    tokenType: zod_1.z.literal('Bearer'),
    token: zod_1.z.string().min(10),
    issuedAt: zod_1.z.number().int().optional(),
    expiresIn: zod_1.z.number().int(),
    expiresAt: zod_1.z.number().int(),
});
/**
 * AuthViewZod 스키마 (access + optional refresh)
 */
exports.AuthViewZ = zod_1.z.object({
    access: exports.TokenViewZ,
    refresh: exports.TokenViewZ.omit({ issuedAt: true }).optional(),
});
exports.MeViewZ = zod_1.z.object({
    username: zod_1.z.string(),
    pns: zod_1.z.string(),
    role: zod_1.z.string(),
});
