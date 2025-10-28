// src/modules/infra/db/database.module.ts (was: database.module.ts)
import {
  Global,
  Inject,
  Logger,
  Module,
  OnModuleDestroy,
} from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { Pool } from 'pg';

/**
 * Neutral DI token so callers don't care about the underlying driver.
 * You can later bind a different adapter (e.g., Prisma, Kysely, etc.)
 * to the same token without touching consumers.
 */
export const DATABASE_POOL = Symbol('DATABASE_POOL');

// Back-compat alias (optional). Remove once all imports use DATABASE_POOL.
export const PG_POOL = DATABASE_POOL;

@Global()
@Module({
  imports: [ConfigModule],
  providers: [
    {
      provide: DATABASE_POOL,
      inject: [ConfigService],
      useFactory: (cfg: ConfigService): Pool => {
        // Prefer a single DATABASE_URL if provided, otherwise compose from PG_* pieces.
        const fromUrl = cfg.get<string>('DATABASE_URL');
        const user = cfg.get<string>('PG_USER')!;
        const pass = cfg.get<string>('PG_PASSWORD')!;
        const host = cfg.get<string>('PG_HOST', 'localhost');
        const port = cfg.get<string>('PG_PORT', '5432');
        const db = cfg.get<string>('PG_DB', 'postgres');

        const connStr =
          fromUrl ??
          `postgresql://${encodeURIComponent(user)}:${encodeURIComponent(
            pass,
          )}@${host}:${port}/${db}`;

        const logger = new Logger('DB');
        logger.debug(connStr.replace(/:(.*?)@/, ':****@'));

        const pool: Pool = new Pool({
          connectionString: connStr,
        });

        pool.on('error', (err: Error) => {
          logger.error('Pool error', err);
        });

        return pool;
      },
    },
  ],
  exports: [DATABASE_POOL],
})
export class DatabaseModule implements OnModuleDestroy {
  constructor(@Inject(DATABASE_POOL) private readonly pool: Pool) {}
  async onModuleDestroy() {
    await this.pool.end();
  }
}
