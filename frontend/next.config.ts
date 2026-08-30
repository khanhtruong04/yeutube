import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next chặn request cross-origin tới dev server theo mặc định (chỉ cho
  // localhost). Mở cho dải IP nội bộ để máy khác cùng mạng vào được.
  allowedDevOrigins: [
    "192.168.*.*",
    "10.*.*.*",
    "172.*.*.*",
    "26.*.*.*", // Radmin VPN
  ],
};

export default nextConfig;
