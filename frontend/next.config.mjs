/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Backend runs as a separate service; the browser calls it directly.
  // If a server-side proxy is desired later, add `rewrites` here.
};

export default nextConfig;
