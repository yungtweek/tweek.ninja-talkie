// apps/gateway/src/graphql/types/chat/chat.type.ts
import { Field, ID, Int, ObjectType } from '@nestjs/graphql';
import { PageInfo } from '@/modules/infra/graphql/types/page-info.type';

@ObjectType()
export class Message {
  @Field(() => ID) id!: string;
  @Field() role!: 'user' | 'assistant' | 'system';
  @Field() content!: string;
  @Field(() => Int) turn!: number;
  @Field(() => Int) messageIndex!: number;
  @Field({ nullable: true }) sourcesJson?: string;
}

@ObjectType()
export class MessageEdge {
  @Field(() => Message) node!: Message;
  @Field() cursor!: string;
}

@ObjectType()
export class MessageConnection {
  @Field(() => [MessageEdge]) edges!: MessageEdge[];
  @Field(() => PageInfo) pageInfo!: PageInfo;
}

@ObjectType()
export class ChatSession {
  @Field(() => ID) id!: string;
  @Field(() => MessageConnection) messages!: MessageConnection;
}

@ObjectType()
export class ChatHistory {
  @Field(() => ChatSession)
  session!: ChatSession;

  @Field(() => MessageConnection)
  messages!: MessageConnection;
}
