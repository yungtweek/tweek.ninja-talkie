// app/api/ingest/events/route.ts
import { NextRequest } from 'next/server';

const SSE_HEADERS: HeadersInit = {
  'Content-Type': 'text/event-stream; charset=utf-8',
  'Cache-Control': 'no-cache, no-transform',
  Connection: 'keep-alive',
};

export type SSEErrorMeta = {
  code: number;
  reason: string;
  refreshed: string | null;
};

export async function GET(req: NextRequest) {
  const url = `${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/ingest/events`;

  // ❗️쿠키 전부를 막 포워드하지 말고, 필요한 헤더만 추려 보내는 걸 권장
  // 여기서는 일단 그대로 쓰되, 나중엔 Authorization만 보내거나 refresh 미들웨어 우회 권장
  const upstream = await fetch(url, {
    method: 'GET',
    headers: req.headers,
    // 중요: SSE는 캐시/압축 금지
    cache: 'no-store',
  });
  const refreshed = req.headers.get('x-refreshed');

  // ✅ 정상 SSE면 바디를 그대로 파이프(상태/헤더도 맞춰줌)
  if (upstream.ok && upstream.headers.get('content-type')?.includes('text/event-stream')) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        ...SSE_HEADERS,
      },
    });
  }

  // ❌ 401/403 등 에러면, 200 + 이벤트로 클라이언트에 "명시적으로" 알림
  if (upstream.status === 401 || upstream.status === 403) {
    const meta: SSEErrorMeta = {
      code: upstream.status,
      reason: 'Unauthorized',
      refreshed: refreshed ?? null,
    };

    const body = `event: unauthorized\ndata: ${JSON.stringify(meta)}\n\n`;
    // 한 번 이벤트 쏘고 연결 종료
    return new Response(body, {
      status: 200,
      headers: {
        ...SSE_HEADERS,
      },
    });
  }

  // 그 외 에러도 이벤트로 전환해주면 디버깅 쉬움
  const payload = JSON.stringify({ code: upstream.status });
  const body = `event: upstream_error\ndata: ${payload}\n\n`;
  return new Response(body, {
    status: 200,
    headers: {
      ...SSE_HEADERS,
    },
  });
}
