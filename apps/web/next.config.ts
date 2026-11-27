import type { NextConfig } from "next";

const API = process.env.KYM_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return ["api", "bank", "oauth", "adapters"].map((p) => ({
      source: `/${p}/:path*`,
      destination: `${API}/${p}/:path*`,
    }));
  },
};

export default nextConfig;
