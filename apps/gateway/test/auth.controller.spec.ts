import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AuthModule } from '@/modules/auth/auth.module';
import { ConfigModule } from '@nestjs/config';
import { DatabaseModule } from '@/modules/infra/database/database.module';

describe('AuthController', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [
        await ConfigModule.forRoot({
          isGlobal: true,
          envFilePath: '.env.local', // ✅ .env.local 파일 로드
        }),
        DatabaseModule,
        AuthModule,
      ],
    }).compile();

    app = moduleFixture.createNestApplication({});

    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  it('POST /v1/auth/login -> should return 401', async () => {
    await request(app.getHttpServer())
      .post('/v1/auth/login')
      .send({ email: 'demo@tweek.ninja', password: 'test' })
      .expect(401);
  });

  it('POST /v1/auth/login → should issue a JWT token', async () => {
    const response = await request(app.getHttpServer())
      .post('/v1/auth/login')
      .send({ email: 'iam@tweek.ninja', password: 'Naruto1234567890' })
      .expect(201);

    expect(response.body).toHaveProperty('accessToken');
    expect(typeof response.body.accessToken).toBe('string');
    expect(response.body.accessToken.split('.').length).toBe(3);
  });

  it('POST /v1/auth/refresh → should issue new tokens', async () => {
    const login = await request(app.getHttpServer())
      .post('/v1/auth/login')
      .send({ email: 'iam@tweek.ninja', password: 'Naruto1234567890' })
      .expect(201);

    const refreshToken = login.body.refreshToken;
    expect(refreshToken).toBeDefined();

    const refresh = await request(app.getHttpServer())
      .post('/v1/auth/refresh')
      // RefreshJwtStrategy expects token via cookie 'rt' or Authorization: Bearer
      .set('Authorization', `Bearer ${refreshToken}`)
      .expect(201);

    expect(refresh.body).toHaveProperty('accessToken');
    expect(refresh.body).toHaveProperty('refreshToken');
    expect(refresh.body.accessToken.split('.').length).toBe(3);
    expect(refresh.body.refreshToken.split('.').length).toBe(3);
  });
});
