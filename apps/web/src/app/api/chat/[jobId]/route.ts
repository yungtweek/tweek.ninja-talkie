import { NextRequest } from 'next/server';

export async function GET(
  nextRequest: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params;

  const url = `${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/chat/stream/${jobId}`;

  return await fetch(url, {
    method: 'GET',
    headers: nextRequest.headers,
    cache: 'no-store',
  });
}
