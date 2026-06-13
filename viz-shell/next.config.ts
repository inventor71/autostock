import type { NextConfig } from "next";

// Webpack dev mode (no --turbopack): the generated-view auto-registry relies on
// webpack's require.context; Turbopack does not guarantee it.
const nextConfig: NextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
