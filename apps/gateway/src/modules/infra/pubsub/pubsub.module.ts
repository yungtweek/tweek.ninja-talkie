// apps/gateway/src/modules/pubsub/pubsub.module.ts
import { Global, Module } from '@nestjs/common';
import { RedisPubSub } from 'graphql-redis-subscriptions';
import type { PubSubEngine } from 'graphql-subscriptions';
import type { RedisOptions } from 'ioredis';

export const SESSION_PUBSUB = Symbol('SESSION_PUBSUB');

@Global()
@Module({
  providers: [
    {
      provide: SESSION_PUBSUB,
      useFactory: (): PubSubEngine => {
        // Prefer REDIS_URL if provided; otherwise use host/port/password
        const url = process.env.REDIS_URL;
        let connection: RedisOptions;
        if (url) {
          const u = new URL(url);
          // Force DB to 0 for managed Redis providers that may not support SELECT
          const base: RedisOptions = {
            host: u.hostname,
            port: Number(u.port || 6379),
            password: u.password || undefined,
            db: 0,
            retryStrategy: (times: number) => Math.min(times * 50, 2000),
          };
          // ioredis enables TLS automatically when using rediss://
          // No explicit tls options needed unless you customize certificates
          if (u.protocol === 'rediss:') {
            // leave as-is
          }
          connection = base;
        } else {
          connection = {
            host: process.env.REDIS_HOST ?? '127.0.0.1',
            port: Number(process.env.REDIS_PORT ?? 6379),
            password: process.env.REDIS_PASSWORD || undefined,
            db: 0,
            retryStrategy: (times: number) => Math.min(times * 50, 2000),
          } satisfies RedisOptions;
        }
        const options: ConstructorParameters<typeof RedisPubSub>[0] = {
          connection,
        };
        return new RedisPubSub(options);
      },
    },
  ],
  exports: [SESSION_PUBSUB],
})
export class PubSubModule {}
