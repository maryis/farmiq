const api = process.env.API_INTERNAL_URL || 'http://localhost:8000';

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${api}/:path*` }];
  },
};

export default nextConfig;
