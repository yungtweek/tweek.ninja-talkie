import React from 'react';
import { FragmentType } from '@/gql';
import { FileMetaFragment, FileMetaFragmentDoc } from '@/gql/graphql';
import type { FileVisibility as FileVisibilityT } from '@/gql/graphql';
import { FileStatus, FileVisibility } from '@talkie/types-zod';
import { useFragment } from '@apollo/client/react';
import styles from '@/app/(app)/documents/page.module.scss';
import { formatBytes } from '@/lib/format';

// ---- UI helpers (module-level to avoid re-creation per render) ----
const renderStatus = (status: FileStatus) => {
  const s = String(status || '').toLowerCase();
  const cls =
    s === FileStatus.Ready
      ? styles.badgeReady
      : s === FileStatus.Indexed
        ? styles.badgeReady
        : s === FileStatus.Vectorized
          ? styles.badgeVectorized
          : styles.badgeMuted;
  return <span className={`${styles.badge} ${cls}`}>{(status ?? '-').toUpperCase()}</span>;
};

const renderVisibility = (v: FileVisibility) => {
  const isPublic = v === FileVisibility.Public;
  const cls = isPublic ? styles.badgePublic : styles.badgePrivate;
  return <span className={`${styles.badge} ${cls}`}>{String(v).toUpperCase()}</span>;
};

const FileItem: React.FC<{
  node: FragmentType<typeof FileMetaFragmentDoc>;
  deleting: boolean;
  updatingVisibility: boolean;
  onToggle: (fileId: string, v: FileVisibilityT) => Promise<void>;
  onDelete: (fileId: string) => Promise<void>;
}> = ({ node, deleting, updatingVisibility, onToggle, onDelete }) => {
  const { data } = useFragment<FileMetaFragment>({
    fragment: FileMetaFragmentDoc,
    from: node,
  });

  if (!data) return null;
  // Narrow possibly null fragment fields (schema may allow nulls)
  if (!data.id || !data.status || !data.visibility) return null;

  const id = data.id;
  const visibility = data.visibility;
  const status = data.status;

  return (
    <tr>
      <td className={styles.filenameCell} title={data.filename}>
        {data.filename}
      </td>
      <td style={{ textAlign: 'center', width: 150 }}>{renderStatus(status)}</td>
      <td style={{ textAlign: 'center', width: 90 }}>{formatBytes(data.size)}</td>
      <td style={{ textAlign: 'center', width: 120 }}>
        <button
          type="button"
          className={styles.visibilityBtn}
          onClick={() => {
            void onToggle(id, visibility);
          }}
          aria-label={`toggle visibility for ${data.filename}`}
        >
          {renderVisibility(data.visibility)}
        </button>
      </td>
      <td className={styles.actionsCell}>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnDanger}`}
          onClick={() => {
            void onDelete(id);
          }}
          disabled={deleting || updatingVisibility}
        >
          DELETE
        </button>
      </td>
    </tr>
  );
};

export default React.memo(FileItem);
