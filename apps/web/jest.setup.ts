// apps/web/jest.setup.ts  (ESM)
import '@testing-library/jest-dom';
/*
import {
  fetch as undiciFetch,
  Headers as UndiciHeaders,
  Request as UndiciRequest,
  Response as UndiciResponse,
  FormData as UndiciFormData,
} from 'undici';

// Node 내장 Web APIs
import { Blob as NodeBlob } from 'node:buffer';
import { ReadableStream as NodeReadableStream } from 'node:stream/web';
import {
  MessageChannel as NodeMessageChannel,
  MessagePort as NodeMessagePort,
} from 'node:worker_threads';
import { TextEncoder as NodeTextEncoder, TextDecoder as NodeTextDecoder } from 'node:util';

// fetch/Headers/Request/Response/FormData
globalThis.fetch ??= undiciFetch as any;
globalThis.Headers ??= UndiciHeaders as any;
globalThis.Request ??= UndiciRequest as any;
globalThis.Response ??= UndiciResponse as any;
globalThis.FormData ??= UndiciFormData as any;

// Ensure Blob exists globally (Node provides it via node:buffer)
globalThis.Blob ??= NodeBlob as any;

// Worker primitives
// @ts-expect-error test env polyfill
globalThis.MessageChannel ??= NodeMessageChannel;
// @ts-expect-error test env polyfill
globalThis.MessagePort ??= NodeMessagePort;

// ReadableStream (Jest 런타임이 비워둘 수 있음)
if (typeof globalThis.ReadableStream === 'undefined') {
  // @ts-expect-error test env polyfill
  globalThis.ReadableStream = NodeReadableStream;
}

// TextEncoder/Decoder (Jest + Node18에서 전역 아님)
if (typeof globalThis.TextEncoder === 'undefined') {
  globalThis.TextEncoder = NodeTextEncoder;
}
if (typeof globalThis.TextDecoder === 'undefined') {
  // @ts-expect-error test env polyfill
  globalThis.TextDecoder = NodeTextDecoder;
}
*/
