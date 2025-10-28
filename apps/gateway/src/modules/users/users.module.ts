// src/modules/users/users.module.ts
import { Module } from '@nestjs/common';
import { UsersRepository } from './users.repository';

@Module({
  providers: [UsersRepository],
  exports: [UsersRepository],
})
export class UsersModule {}
