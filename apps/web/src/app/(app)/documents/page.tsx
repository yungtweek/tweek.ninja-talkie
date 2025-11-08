'use client';
import styles from '@/app/(app)/documents/page.module.scss';
import type { ApolloCache } from '@apollo/client';
import React, { useEffect, useCallback } from 'react';
import FileUploader from '@/components/documents/FileUploader';
import { chatStore } from '@/features/chat/chat.store';
import { useSessionsActions } from '@/features/chat/chat.sessions.store';
import {
  DeleteFileDocument,
  DeleteFileMutation,
  DeleteFileMutationVariables,
  FilesDocument,
  FilesQuery,
  FilesQueryVariables,
  UpdateVisibilityDocument,
  UpdateVisibilityMutation,
  UpdateVisibilityMutationVariables,
} from '@/gql/graphql';
import type { FileVisibility as FileVisibilityT } from '@/gql/graphql';
import { FileVisibility } from '@talkie/types-zod';
import { useMutation, useQuery } from '@apollo/client/react';
import { removeFromConnection } from '@/lib/apollo/connection';
import FileItem from '@/components/documents/FileItem';
import { useIngestSSE } from '@/features/ingest/useIngestSSE';
import { toGqlVisibility, writeFileVisibility } from '@/features/ingest/ingest.utils';

export default function DocumentsPage() {
  const { reset } = chatStore();
  const { setSelectedSessionId, setActiveSessionId } = useSessionsActions();
  useIngestSSE();

  const { data } = useQuery<FilesQuery, FilesQueryVariables>(FilesDocument, {
    variables: { first: 20 },
    notifyOnNetworkStatusChange: true,
  });

  const [mutateDeleteFile, { loading: deleting }] = useMutation<
    DeleteFileMutation,
    DeleteFileMutationVariables
  >(DeleteFileDocument);

  const [mutateUpdateVisibility, { loading: updatingVisibility }] = useMutation<
    UpdateVisibilityMutation,
    UpdateVisibilityMutationVariables
  >(UpdateVisibilityDocument);

  useEffect(() => {
    setSelectedSessionId(null);
    setActiveSessionId(null);
    reset();
  }, [setActiveSessionId, reset]);

  const deleteFile = useCallback(
    async (fileId: string) => {
      try {
        await mutateDeleteFile({
          variables: { fileId },
          optimisticResponse: {
            deleteFile: {
              __typename: 'DeleteFilePayload',
              ok: true,
              fileId,
              message: 'optimistic',
              deletedCount: null,
            },
          },
          update: (cache: ApolloCache) => {
            const cacheId = cache.identify({ __typename: 'FileListType', id: fileId });
            cache.evict({ id: cacheId });
            removeFromConnection(cache, { fieldName: 'files', id: fileId });
            cache.gc();
          },
        });
      } catch (e) {
        console.error('deleteFile mutation failed', e);
        alert('파일 삭제 요청에 실패했습니다.');
      }
    },
    [mutateDeleteFile],
  );

  const toggleVisibility = useCallback(
    async (fileId: string, currentVisibility: FileVisibilityT) => {
      const next =
        currentVisibility === FileVisibility.Public
          ? FileVisibility.Private
          : FileVisibility.Public;
      try {
        await mutateUpdateVisibility({
          variables: { fileId, visibility: toGqlVisibility(next) },
          optimisticResponse: { updateVisibility: true },
          update: (cache: ApolloCache) => {
            writeFileVisibility(cache, fileId, toGqlVisibility(next));
          },
        });
      } catch (e) {
        console.error('updateVisibility mutation failed', e);
        alert('가시성 변경에 실패했습니다.');
      }
    },
    [mutateUpdateVisibility],
  );

  return (
    <>
      <div style={{ padding: '0 1.7rem' }}>
        <h1 style={{ padding: '8px 0' }}>Documents</h1>
        <div>
          <FileUploader />
        </div>
        <div>
          <ul>
            <div className={styles.tableCard}>
              <div className={styles.tableHeader}>
                <h3>{data?.files.edges.length ?? 0} files</h3>
                <div className={styles.headerActions}>
                  {/*<button type="button" className={styles.btnGhost} onClick={() => null}>*/}
                  {/*  refresh*/}
                  {/*</button>*/}
                </div>
              </div>

              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Filename</th>
                    <th>Size</th>
                    <th>Status</th>
                    <th>Visibility</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {data?.files.edges.map(e => (
                    <FileItem
                      key={e.cursor}
                      node={e.node}
                      deleting={deleting}
                      updatingVisibility={updatingVisibility}
                      onToggle={toggleVisibility}
                      onDelete={deleteFile}
                    />
                  ))}
                  {!data?.files.edges.length && (
                    <tr>
                      <td colSpan={5} className={styles.emptyCell}>
                        업로드된 파일이 없습니다.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </ul>
        </div>
      </div>
    </>
  );
}
