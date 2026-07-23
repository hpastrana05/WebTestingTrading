/** @type {import('next').NextConfig} */
const apiOrigin = (
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig = {
  output: "standalone",
  async rewrites() {
    // Browser calls same-origin /api/* ; Next proxies to the FastAPI backend.
    // In Docker Compose use API_INTERNAL_URL=http://backend:8000
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
