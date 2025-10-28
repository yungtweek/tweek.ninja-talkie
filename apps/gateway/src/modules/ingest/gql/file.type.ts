import { Field, ObjectType, registerEnumType, ID, InputType } from '@nestjs/graphql';
import { FileMetadataZDto } from '@/modules/ingest/ingest.zod';

export enum FileStatus {
  PENDING = 'pending',
  READY = 'ready',
  FAILED = 'failed',
  DELETED = 'deleted',
  INDEXED = 'indexed',
  VECTORIZED = 'vectorized',
}

export enum FileVisibility {
  PRIVATE = 'private',
  FOLLOWERS = 'followers',
  DEPARTMENT = 'department',
  PUBLIC = 'public',
}

registerEnumType(FileStatus, { name: 'FileStatus' });
registerEnumType(FileVisibility, { name: 'FileVisibility' });

@ObjectType()
export class FileType {
  @Field(() => ID)
  id!: string;

  @Field()
  bucket!: string;

  @Field()
  key!: string;

  @Field()
  filename!: string;

  @Field(() => String, { nullable: true })
  extension?: string | null;

  @Field(() => String, { nullable: true })
  contentType?: string | null;

  @Field(() => Number, { nullable: true })
  sizeExpected?: number | null;

  @Field(() => String, { nullable: true })
  checksumSha256Expected?: string | null;

  @Field(() => Number, { nullable: true })
  size?: number | null;

  @Field(() => String, { nullable: true })
  etag?: string | null;

  @Field(() => FileStatus)
  status!: FileStatus;

  @Field(() => FileVisibility)
  visibility!: FileVisibility;

  @Field(() => String)
  ownerId!: string;

  @Field(() => Date, { nullable: true })
  uploadedAt?: Date | null;

  @Field(() => Date, { nullable: true })
  modifiedAt?: Date | null;
}

@ObjectType()
export class FileListType {
  @Field(() => ID)
  id!: string;

  @Field()
  filename!: string;

  @Field(() => String, { nullable: true })
  contentType?: string | null;

  @Field(() => Number, { nullable: true })
  size?: number | null;

  @Field(() => FileStatus)
  status!: FileStatus;

  @Field(() => FileVisibility)
  visibility!: FileVisibility;

  @Field(() => Date, { nullable: true })
  uploadedAt?: Date | null;

  @Field(() => Date)
  createdAt!: Date;
}

@ObjectType()
export class DeleteFilePayload {
  @Field(() => Boolean)
  ok!: boolean;

  @Field(() => ID, { nullable: true })
  fileId?: string;

  @Field(() => Number, { nullable: true })
  deletedCount?: number;

  @Field(() => String, { nullable: true })
  message?: string | null;
}

@InputType()
export class FileMetadataInput implements FileMetadataZDto {
  @Field()
  bucket!: string;

  @Field()
  key!: string;

  @Field()
  filename!: string;

  @Field({ nullable: true })
  extension?: string;

  @Field({ nullable: true })
  contentType?: string;

  @Field(() => Number, { nullable: true })
  sizeExpected?: number | null;

  @Field(() => String, { nullable: true })
  checksumSha256Expected?: string | null;

  @Field(() => Number, { nullable: true })
  size?: number;

  @Field(() => String, { nullable: true })
  etag?: string;

  @Field(() => FileVisibility, {
    nullable: true,
    defaultValue: FileVisibility.PRIVATE,
  })
  visibility?: FileVisibility;

  @Field(() => String)
  ownerId!: string;

  // 최초 등록 시 항상 'pending'
  @Field(() => FileStatus, { nullable: true, defaultValue: FileStatus.PENDING })
  status?: FileStatus;

  @Field(() => Date, { nullable: true })
  uploadedAt?: Date | null;

  @Field(() => Date, { nullable: true })
  modifiedAt?: Date | null;
}
