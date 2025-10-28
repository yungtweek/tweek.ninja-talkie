// apps/gateway/src/modules/graphql/types/page-info.type.ts
import { Field, ObjectType } from '@nestjs/graphql';

/**
 * Relay-style PageInfo shared across the schema.
 * Both chat and ingest can use this single type.
 */
@ObjectType()
export class PageInfo {
  @Field(() => Boolean)
  hasPreviousPage!: boolean;

  @Field(() => Boolean)
  hasNextPage!: boolean;

  @Field(() => String, { nullable: true })
  startCursor?: string | null;

  @Field(() => String, { nullable: true })
  endCursor?: string | null;
}
