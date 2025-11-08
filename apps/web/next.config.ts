import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  /* config options here */
  serverActions: {
    allowedOrigins: ['localhost:4000'],
  },
};

export default nextConfig;
