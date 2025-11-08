import { NextRequest } from 'next/server';

export function authChecker(nextRequest: NextRequest) {
  const auth = nextRequest.headers.get('authorization');
  const hasAccess = nextRequest.cookies.has('access_token');
  const hasRefresh = nextRequest.cookies.has('refresh_token');
  return auth || hasAccess || hasRefresh;
}
