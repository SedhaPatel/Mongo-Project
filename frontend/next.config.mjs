/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  webpack(config) {
    // embed .jsonl event fixtures as raw strings
    config.module.rules.push({
      test: /\.jsonl$/i,
      type: "asset/source",
    });
    return config;
  },
};

export default nextConfig;
