// apps/gateway/src/modules/chat/chat.service.spec.ts
import { Test } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '@/app.module';
import type { Server } from 'http';
import { AuthModule } from '@/modules/auth/auth.module';
import { ConfigModule } from '@nestjs/config';
import { ChatModule } from '@/modules/chat/chat.module';
import { DatabaseModule } from '@/modules/infra/database/database.module';

type ChatSsePayload = {
  event?: string;
  jobId?: string;
  index?: number;
  content?: string;
  code?: string;
  message?: string;
  retryable?: boolean;
};

const isChatSsePayload = (u: unknown): u is ChatSsePayload => {
  if (typeof u !== 'object' || u === null) return false;
  const o = u as Record<string, unknown>;
  if ('event' in o && o.event !== undefined && typeof o.event !== 'string') return false;
  if ('index' in o && o.index !== undefined && typeof o.index !== 'number') return false;
  if ('content' in o && o.content !== undefined && typeof o.content !== 'string') return false;

  return !('jobId' in o && o.jobId !== undefined && typeof o.jobId !== 'string');
};

describe('SSE /v1/chat/stream/:jobId (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const m = await Test.createTestingModule({
      imports: [
        await ConfigModule.forRoot({
          isGlobal: true,
          envFilePath: '.env.local', // ✅ .env.local 파일 로드
        }),
        AppModule,
        DatabaseModule,
        AuthModule,
        ChatModule,
      ],
    })
      // 필요 시 KafkaService를 더미로 교체,
      // ChatService.stream 내부에서 Redis만 실제로 쓰도록
      .overrideProvider('KafkaService')
      .useValue({ produce: async () => {} })
      .compile();

    app = m.createNestApplication();
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  it('SSE는 text/event-stream과 함께 token/done을 흘려보낸다', async () => {
    // Narrow the `any` return type from Nest's getHttpServer() to a concrete http.Server
    const server: Server = app.getHttpServer() as unknown as Server;

    const login = await request(app.getHttpServer())
      .post('/v1/auth/login')
      .send({ username: 'tweek', password: 'Naruto1234567890' })
      .expect(201);

    const accessToken = login.body.access.token;
    console.log(accessToken);

    // 0) 먼저 enqueue를 호출하여 jobId를 발급받는다
    const enqueueRes = await request(server)
      .post('/v1/chat')
      .set('Authorization', `Bearer ${accessToken}`)
      .send({
        message: '나루토 vs 사스케',
        mode: 'gen',
      })
      .expect(201);

    const { jobId } = enqueueRes.body as { jobId: string };
    const res = await request(server)
      .get(`/v1/chat/stream/${encodeURIComponent(jobId)}`)
      .set('Authorization', `Bearer ${accessToken}`)
      .set('Accept', 'text/event-stream')
      .buffer(true)
      .parse((res, cb) => {
        // supertest용 SSE 간단 파서 (res.text에 누적 결과를 저장)
        let data = '';
        res.setEncoding('utf8');
        res.on('data', chunk => (data += chunk));
        res.on('end', () => {
          // supertest는 커스텀 파서 사용 시 res.text를 자동 설정하지 않음 → 수동 주입
          // (expect에서 res.text로 바로 검증할 수 있게 통일)

          // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
          (res as any).text = data;

          cb(null, data);
        });
      })
      .expect(200)
      .expect('Content-Type', /text\/event-stream/);

    // SSE 프레임 파싱: 공백 줄(\n\n)로 이벤트 구분 → 각 이벤트에서 data: 라인만 추출해 JSON 파싱
    const frames = res.text
      .split(/\r?\n\r?\n/) // 이벤트 구분
      .map(f => f.trim())
      .filter(Boolean);

    const payloads = frames
      .map(f => {
        const line = f.split(/\r?\n/).find(l => l.startsWith('data: '));
        if (!line) return null;
        const json = line.slice('data: '.length);
        try {
          const raw: unknown = JSON.parse(json);
          return isChatSsePayload(raw) ? raw : null;
        } catch {
          return null;
        }
      })
      .filter((p): p is { event?: string } => !!p);

    // token 과 done 이벤트가 최소 1개 이상 존재해야 함
    expect(payloads.some(p => p.event === 'token')).toBe(true);
    expect(payloads.some(p => p.event === 'done')).toBe(true);
  });
});
