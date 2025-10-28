"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ChatMessageZ = exports.ChatSessionsConnectionZ = exports.PageInfoZ = exports.ChatSessionsEdgeZ = exports.ChatSessionsZ = void 0;
var zod_1 = require("zod");
exports.ChatSessionsZ = zod_1.z.object({
    id: zod_1.z.uuid(),
    title: zod_1.z.string().optional().nullable(),
    createdAt: zod_1.z.union([zod_1.z.string(), zod_1.z.date()]),
    updatedAt: zod_1.z.union([zod_1.z.string(), zod_1.z.date()]),
    lastMessagePreview: zod_1.z.union([zod_1.z.string(), zod_1.z.date()]).optional().nullable(),
    lastMessageAt: zod_1.z.union([zod_1.z.string(), zod_1.z.date()]).optional().nullable(),
});
// Connection 형태가 필요할 때를 위한 보조 스키마 (선택)
exports.ChatSessionsEdgeZ = zod_1.z.object({
    cursor: zod_1.z.string(),
    node: exports.ChatSessionsZ,
});
exports.PageInfoZ = zod_1.z.object({
    endCursor: zod_1.z.string().optional(),
    hasNextPage: zod_1.z.boolean(),
});
exports.ChatSessionsConnectionZ = zod_1.z.object({
    edges: zod_1.z.array(exports.ChatSessionsEdgeZ),
    pageInfo: exports.PageInfoZ,
});
exports.ChatMessageZ = zod_1.z.object({
    id: zod_1.z.string(),
    role: zod_1.z.string(), // or z.enum(['user','assistant','system']) if you want to constrain
    content: zod_1.z.string(),
    messageIndex: zod_1.z.number().int(),
    turn: zod_1.z.number().int(),
    sourcesJson: zod_1.z.unknown().nullable().optional(),
});
