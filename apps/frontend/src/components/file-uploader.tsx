import { FileImage, LoaderCircle, Upload } from "lucide-react";
import { ChangeEvent, useEffect, useRef, useState } from "react";

import { api, FileAsset, uploadFile } from "../lib/api";

export function FileUploader({
  entityType,
  entityId,
  purpose = "photo",
  onUploaded,
}: {
  entityType: string;
  entityId: string;
  purpose?: "photo" | "document" | "attachment" | "avatar";
  onUploaded?: (asset: FileAsset) => void;
}) {
  const [files, setFiles] = useState<FileAsset[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const onUploadedRef = useRef(onUploaded);

  useEffect(() => {
    onUploadedRef.current = onUploaded;
  }, [onUploaded]);

  useEffect(() => {
    const query = new URLSearchParams({ entity_type: entityType, entity_id: entityId });
    void api<FileAsset[]>(`/files?${query}`)
      .then((items) => {
        setFiles(items);
        items.forEach((item) => onUploadedRef.current?.(item));
      })
      .catch(() => undefined);
  }, [entityId, entityType]);

  async function selected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!navigator.onLine) {
      setError("Загрузка файлов недоступна без сети");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const asset = await uploadFile(file, entityType, entityId, purpose, files.length === 0);
      setFiles((items) => [...items, asset]);
      onUploaded?.(asset);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить файл");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="file-uploader">
      <div className="file-previews">
        {files.slice(0, 1).map((file) =>
          file.stored_mime.startsWith("image/") ? (
            <img
              key={file.id}
              src={`/api/v1/files/${file.id}?thumbnail=true`}
              alt={file.original_name}
            />
          ) : (
            <a key={file.id} href={`/api/v1/files/${file.id}`} target="_blank" rel="noreferrer">
              <FileImage /> {file.original_name}
            </a>
          ),
        )}
        {files.length > 1 && (
          <details className="additional-files">
            <summary>Ещё файлов: {files.length - 1}</summary>
            <div>
              {files.slice(1).map((file) =>
                file.stored_mime.startsWith("image/") ? (
                  <img
                    key={file.id}
                    src={`/api/v1/files/${file.id}?thumbnail=true`}
                    alt={file.original_name}
                  />
                ) : (
                  <a
                    key={file.id}
                    href={`/api/v1/files/${file.id}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <FileImage /> {file.original_name}
                  </a>
                ),
              )}
            </div>
          </details>
        )}
      </div>
      <label className={`file-upload-button${busy ? " is-busy" : ""}`}>
        {busy ? <LoaderCircle className="spin" /> : <Upload />}
        {busy ? "Обработка…" : "Добавить файл"}
        <input
          type="file"
          accept=".jpg,.jpeg,.png,.webp,.heic,.heif,.pdf"
          disabled={busy}
          onChange={(event) => void selected(event)}
        />
      </label>
      {error && <small className="form-error">{error}</small>}
    </div>
  );
}
