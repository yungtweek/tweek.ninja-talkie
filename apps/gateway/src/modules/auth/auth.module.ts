// src/modules/auth/auth.module.ts
import { Module } from '@nestjs/common';
import { JwtModule, JwtService } from '@nestjs/jwt';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { PassportModule } from '@nestjs/passport';
import { AuthService } from './auth.service';
import { JwtStrategy } from './jwt.strategy';
import { AuthController } from './auth.controller';
import { RefreshJwtStrategy } from '@/modules/auth/jwt-refresh.strategy';
import { UsersModule } from '@/modules/users/users.module';

@Module({
  imports: [
    ConfigModule,
    PassportModule,
    UsersModule,
    JwtModule.registerAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (cfg: ConfigService) => ({
        secret: cfg.get<string>('JWT_SECRET') as string,
        signOptions: {
          expiresIn: cfg.get<number>('JWT_EXPIRES_IN') ?? 3600,
          issuer: cfg.get<string>('JWT_ISSUER') ?? 'tweek.ninja',
          audience: cfg.get<string>('JWT_AUDIENCE') ?? 'talkie.users',
        },
      }),
    }),
  ],
  providers: [
    AuthService,
    JwtStrategy,
    RefreshJwtStrategy,
    {
      provide: 'REFRESH_JWT',
      inject: [ConfigService],
      useFactory: (cfg: ConfigService) =>
        new JwtService({
          secret: cfg.get<string>('REFRESH_JWT_SECRET'),
          signOptions: {
            expiresIn: cfg.get<number>('REFRESH_JWT_EXPIRES_IN') ?? '7d',
            issuer: cfg.get<string>('JWT_ISSUER') ?? 'tweek.ninja',
            audience: cfg.get<string>('JWT_AUDIENCE') ?? 'talkie.users',
          },
        }),
    },
  ],
  controllers: [AuthController],
  exports: [AuthService, PassportModule, JwtModule],
})
export class AuthModule {}
