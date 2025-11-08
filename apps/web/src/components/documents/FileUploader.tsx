'use client';
import React, { useRef, useState } from 'react';
import styles from './FileUploader.module.scss';
import { fetchWithAutoRefresh } from '@/lib/fetchWithAutoRefresh.client';
import { presignAction } from '@/actions/ingest/presign.action';
import { completeAction } from '@/actions/ingest/complete.action';

export default function FileUploader() {
  const [pending, setPending] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

  const inputRef = useRef<HTMLInputElement>(null);

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] ?? null);
  };

  const setFileFromList = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const f = files[0];
    setFile(f);
  };

  const handleDragEnter = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current += 1;
    setIsDragging(true);
  };

  const handleDragOver = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDragLeave = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current -= 1;
    if (dragCounter.current === 0) setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current = 0;
    setIsDragging(false);
    const dt = e.dataTransfer;
    setFileFromList(dt?.files ?? null);
    // 드롭 후 포커스가 버튼으로 넘어가도록 약간의 배려
    if (dt && inputRef.current) inputRef.current.focus();
  };

  async function sha256Base64(file: File) {
    const buffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const bytes = new Uint8Array(hashBuffer);
    let binary = '';
    for (const b of bytes) {
      binary += String.fromCharCode(b);
    }
    return btoa(binary);
  }

  async function uploadFileToPresignedUrl(
    url: string,
    file: File,
    contentType: string,
    checksumBase64: string,
  ) {
    const res = await fetchWithAutoRefresh(url, {
      method: 'PUT',
      headers: {
        'Content-Type': contentType,
        'x-amz-checksum-sha256': checksumBase64,
      },
      credentials: 'include',
      body: file,
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Upload failed: ${res.status} ${errText}`);
    }

    return {
      success: true,
      location: url.split('?')[0], // 실제 접근 가능한 S3 object URL
    };
  }

  const fetchData = async () => {
    if (!file || pending) return;
    setPending(true);

    const checksum = await sha256Base64(file);
    try {
      const presign = await presignAction({
        filename: file.name,
        checksum,
        contentType: file.type,
        size: file.size,
      });

      if (!presign.success) {
        return Promise.reject(new Error(`${presign.error.message}`));
      }
      const { url, bucket, key, contentType } = presign.data;

      const upload = await uploadFileToPresignedUrl(url, file, contentType, checksum);

      if (!upload.success) {
        return Promise.reject(new Error('Uploading FileType failed'));
      }

      const complete = await completeAction({ bucket, key, filename: file.name });

      if (!complete.success) {
        return Promise.reject(new Error(`${complete.error.message}`));
      }
    } catch (e) {
      console.error(e);
    } finally {
      setPending(false);
      setFile(null);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const handleSubmit: React.FormEventHandler<HTMLFormElement> = e => {
    e.preventDefault();
    if (pending || !file) return;
    void fetchData();
  };

  return (
    <div className={styles.container}>
      <form className={styles.form} onSubmit={handleSubmit} aria-busy={pending}>
        <div className={styles.fieldRow}>
          <label
            htmlFor="file-input"
            className={`${styles.dropArea} ${isDragging ? styles.dragActive : ''}`}
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            aria-label="Drag & drop a file or click to select"
          >
            <span className={styles.fileLabel}>
              {isDragging ? 'Drop here' : file ? file.name : 'Select a file or drag & drop'}
            </span>
            <input
              id="file-input"
              ref={inputRef}
              type="file"
              onChange={e => setFileFromList(e.target.files)}
              className={styles.fileInput}
              aria-describedby="file-help"
            />
          </label>

          <button type="submit" className={styles.submitBtn} disabled={pending || !file}>
            {pending ? '…' : 'Upload'}
          </button>
        </div>
        <p id="file-help" className={styles.help}>
          Please upload a document file. (PDF, Markdown, etc.)
        </p>
      </form>
    </div>
  );
}
