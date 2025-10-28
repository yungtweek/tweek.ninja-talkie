// src/main.ts
import { Logger } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import cookieParser from 'cookie-parser';
import { Pool } from 'pg';
import { PG_POOL } from '@/modules/infra/database/database.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, {
    logger: ['error', 'warn', 'debug', 'log', 'verbose'],
  });
  app.enableShutdownHooks();

  const pool = app.get<Pool>(PG_POOL);
  process.on('SIGINT', () => {
    void pool
      .end()
      .then(() => app.close())
      .then(() => process.exit(0))
      .catch(() => void 0);
  });

  app.use(cookieParser());
  app.enableCors({ origin: [/localhost:\d+/], credentials: true });

  const port = Number(process.env.PORT) || 4000;
  await app.listen(port, '0.0.0.0');

  new Logger('Bootstrap').debug(`Gateway up on :${port}`);
}
void bootstrap();
