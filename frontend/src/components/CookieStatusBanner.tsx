"use client";

import { useEffect, useState } from "react";
import { api, type CookieStatus } from "@/lib/api";

const CHECK_INTERVAL_MS = 30_000;

/** Cảnh báo khi cookie đăng nhập Douyin (cookies_playwright.json) hết hạn hoặc
 * bị Douyin âm thầm huỷ phía server — tránh để user tạo job rồi mới biết tải lỗi. */
export default function CookieStatusBanner() {
  const [status, setStatus] = useState<CookieStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function check() {
      try {
        const s = await api.getCookieStatus();
        if (!cancelled) setStatus(s);
      } catch {
        // im lặng: đây chỉ là banner phụ, không phải luồng chính.
      }
      if (!cancelled) timer = setTimeout(check, CHECK_INTERVAL_MS);
    }
    check();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  if (!status || status.ok) return null;

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
      <p className="font-medium">⚠️ Cookie Douyin có vấn đề</p>
      <p className="mt-0.5">{status.message}</p>
      <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
        Mở douyin.com (đã đăng nhập) → export cookie bằng Cookie-Editor → ghi đè{" "}
        <code>cookies_playwright.json</code> ở thư mục gốc project → thử lại.
      </p>
    </div>
  );
}
