/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Force webpack to bundle @react-pdf/renderer (ESM-only) instead of
  // treating it as a Node external (which would fail with require()).
  transpilePackages: ['@react-pdf/renderer'],
  webpack: (config) => {
    // @react-pdf/renderer uses canvas internally; exclude from server bundle
    config.resolve.alias = { ...config.resolve.alias, canvas: false };
    return config;
  },
}

module.exports = nextConfig
