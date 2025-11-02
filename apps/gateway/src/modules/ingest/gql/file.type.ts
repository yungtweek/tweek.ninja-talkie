import { Field, ObjectType, registerEnumType, ID, PickType } from '@nestjs/graphql';
import { FileMetadataZDto } from '@/modules/ingest/ingest.zod';
import { PageInfo } from '@/modules/infra/graphql/types/page-info.type';
import {
  FileStatusZ,
  FileVisibilityZ,
  type FileStatus as FileStatusValue,
  type FileVisibility as FileVisibilityValue,
} from '@talkie/types-zod';

export const GqlFileStatus = FileStatusZ.enum;
export const GqlFileVisibility = FileVisibilityZ.enum;
registerEnumType(GqlFileStatus, { name: 'FileStatus' });
registerEnumType(GqlFileVisibility, { name: 'FileVisibility' });

@ObjectType()
export class FileType implements FileMetadataZDto {
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

  @Field(() => GqlFileStatus)
  status!: FileStatusValue;

  @Field(() => GqlFileVisibility)
  visibility!: FileVisibilityValue;

  @Field(() => String)
  ownerId!: string;

  @Field(() => Date, { nullable: true })
  uploadedAt?: Date | null;

  @Field(() => Date)
  createdAt!: Date;

  @Field(() => Date, { nullable: true })
  modifiedAt?: Date | null;
}

@ObjectType()
export class FileListType extends PickType(FileType, [
  'id',
  'filename',
  'contentType',
  'size',
  'status',
  'visibility',
  'uploadedAt',
  'createdAt',
] as const) {
  // Tighten nullability for list view where values are guaranteed
  @Field(() => String)
  override contentType!: string;

  @Field(() => Number)
  override size!: number;

  @Field(() => Date)
  override uploadedAt!: Date;
}

@ObjectType()
export class FileEdge {
  @Field(() => FileListType)
  node!: FileListType;
  @Field(() => String, { nullable: true })
  cursor?: string | null;
}

@ObjectType()
export class FileConnection {
  @Field(() => [FileEdge])
  edges!: FileEdge[];

  @Field(() => PageInfo)
  pageInfo!: PageInfo;
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
