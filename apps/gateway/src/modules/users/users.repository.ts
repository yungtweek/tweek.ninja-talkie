// src/modules/users/users.repository.ts
import { Inject, Injectable } from '@nestjs/common';
// import * as pg from 'pg';
import { UserRow } from '@/modules/users/user.zod';
import { Pool } from 'pg';
import { PG_POOL } from '@/modules/infra/database/database.module';

@Injectable()
export class UsersRepository {
  constructor(@Inject(PG_POOL) private readonly pool: Pool) {}

  async findByIdentifierAndPwd(
    identifier: string,
    password: string,
  ): Promise<UserRow | null> {
    const sql = `
      SELECT id, username, email, pwd_shadow, public_ns, created_at, updated_at
      FROM users
      WHERE (username = $1 OR (email IS NOT NULL AND email = $1))
        AND pwd_shadow = $2
      LIMIT 1
    `;

    const result = await this.pool.query<UserRow>(sql, [identifier, password]);
    const rows: UserRow[] = result.rows;

    return rows.length > 0 ? rows[0] : null;
  }
}
