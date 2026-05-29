/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  basePath: process.env.NODE_ENV === "production" ? "/wc-2026-predictor" : "",
};

module.exports = nextConfig;