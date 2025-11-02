"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ChatMessageZ = exports.ChatSessionZ = void 0;
var zod_1 = require("zod");
exports.ChatSessionZ = zod_1.z.object({
    id: zod_1.z.uuid(),
    title: zod_1.z.string().optional().nullable(),
    createdAt: zod_1.z.union([zod_1.z.string(), zod_1.z.date()]).optional().nullable(),
    updatedAt: zod_1.z.union([zod_1.z.string(), zod_1.z.date()]).optional().nullable(),
    lastMessagePreview: zod_1.z.union([zod_1.z.string(), zod_1.z.date()]).optional().nullable(),
    lastMessageAt: zod_1.z.union([zod_1.z.string(), zod_1.z.date()]).optional().nullable(),
});
exports.ChatMessageZ = zod_1.z.object({
    id: zod_1.z.string(),
    role: zod_1.z.string(), // or z.enum(['user','assistant','system']) if you want to constrain
    content: zod_1.z.string(),
    messageIndex: zod_1.z.number().int(),
    turn: zod_1.z.number().int(),
    sourcesJson: zod_1.z.unknown().nullable().optional(),
});
