/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_INTERNAL_BASE || "http://api:8000"}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
