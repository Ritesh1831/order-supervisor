/** @type {import('next').NextConfig} */
// The Next server proxies /api to the FastAPI backend so the browser stays same-origin.
const nextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: "http://localhost:8000/api/:path*" }];
  },
};
module.exports = nextConfig;
