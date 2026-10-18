"use client";

import { useRef, useState } from "react";

export type BatchRow = {
  order: number;
  url: string;
};

const MAX_ROWS = 9;

/**
 * Component nhập danh sách video cho batch:
 * - Nhập tay bảng (thêm/xóa dòng, max 9)
 * - Upload file CSV (2 cột: STT, Link)
 */
export default function BatchInputTable({
  rows,
  onChange,
}: {
  rows: BatchRow[];
  onChange: (rows: BatchRow[]) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [csvError, setCsvError] = useState<string | null>(null);

  function addRow() {
    if (rows.length >= MAX_ROWS) return;
    onChange([...rows, { order: rows.length + 1, url: "" }]);
  }

  function removeRow(idx: number) {
    const next = rows
      .filter((_, i) => i !== idx)
      .map((r, i) => ({ ...r, order: i + 1 }));
    onChange(next);
  }

  function updateUrl(idx: number, url: string) {
    const next = [...rows];
    next[idx] = { ...next[idx], url };
    onChange(next);
  }

  function handleCsvUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvError(null);

    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const text = ev.target?.result as string;
        const parsed = parseCsv(text);
        if (parsed.length === 0) {
          setCsvError("File CSV rỗng hoặc không đúng định dạng (cần 2 cột: STT, Link).");
          return;
        }
        if (parsed.length > MAX_ROWS) {
          setCsvError(`File có ${parsed.length} dòng, tối đa ${MAX_ROWS} link.`);
          return;
        }
        onChange(parsed);
      } catch (err) {
        setCsvError(err instanceof Error ? err.message : "Lỗi đọc file CSV.");
      }
    };
    reader.readAsText(file);
    // Reset input để có thể upload lại cùng file
    e.target.value = "";
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Upload CSV */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
        >
          📎 Upload file CSV
        </button>
        <span className="text-xs text-gray-400">
          2 cột: STT, Link — hoặc nhập tay bên dưới
        </span>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.txt"
          className="hidden"
          onChange={handleCsvUpload}
        />
      </div>
      {csvError && <p className="text-xs text-red-500">{csvError}</p>}

      {/* Bảng nhập tay */}
      <div className="rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500 dark:border-gray-700">
              <th className="w-16 px-3 py-2 text-center">STT</th>
              <th className="px-3 py-2">Link video</th>
              <th className="w-12 px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr
                key={idx}
                className="border-b border-gray-100 last:border-b-0 dark:border-gray-800"
              >
                <td className="px-3 py-2 text-center font-mono text-gray-500">
                  {row.order}
                </td>
                <td className="px-3 py-1.5">
                  <input
                    type="text"
                    placeholder="https://youtube.com/watch?v=... hoặc https://douyin.com/..."
                    value={row.url}
                    onChange={(e) => updateUrl(idx, e.target.value)}
                    className="w-full rounded border border-gray-200 px-2 py-1.5 text-sm outline-none focus:border-black dark:border-gray-700 dark:bg-transparent dark:focus:border-white"
                  />
                </td>
                <td className="px-2 py-2 text-center">
                  {rows.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeRow(idx)}
                      title="Xóa dòng"
                      className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20"
                    >
                      🗑️
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Nút thêm dòng */}
      {rows.length < MAX_ROWS && (
        <button
          type="button"
          onClick={addRow}
          className="self-start rounded-lg border border-dashed border-gray-300 px-3 py-1.5 text-sm text-gray-500 hover:border-gray-400 hover:text-gray-700 dark:border-gray-600 dark:hover:border-gray-500 dark:hover:text-gray-300"
        >
          ➕ Thêm video ({rows.length}/{MAX_ROWS})
        </button>
      )}
    </div>
  );
}


/**
 * Parse CSV text thành mảng BatchRow.
 * Hỗ trợ: có/không header, phân cách bằng dấu phẩy hoặc tab.
 */
function parseCsv(text: string): BatchRow[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  if (lines.length === 0) return [];

  const result: BatchRow[] = [];
  let orderCounter = 1;

  for (const line of lines) {
    // Tách bằng comma hoặc tab
    const parts = line.split(/[,\t]+/).map((p) => p.trim().replace(/^["']|["']$/g, ""));

    // Bỏ qua dòng header
    if (parts.length >= 2) {
      const maybeOrder = parseInt(parts[0], 10);
      const maybeUrl = parts[1];

      // Nếu cột 1 là số và cột 2 bắt đầu bằng http → đúng format
      if (!isNaN(maybeOrder) && maybeUrl.startsWith("http")) {
        result.push({ order: orderCounter, url: maybeUrl });
        orderCounter++;
        continue;
      }

      // Nếu cột 1 bắt đầu bằng http (không có cột STT) → coi link nằm ở cột 1
      if (parts[0].startsWith("http")) {
        result.push({ order: orderCounter, url: parts[0] });
        orderCounter++;
        continue;
      }
    } else if (parts.length === 1 && parts[0].startsWith("http")) {
      // File chỉ có 1 cột link
      result.push({ order: orderCounter, url: parts[0] });
      orderCounter++;
    }
    // Bỏ qua dòng không hợp lệ (header, dòng trống...)
  }

  return result;
}
