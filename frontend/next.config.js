/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    // 关掉 webpack 的 pack 文件缓存。
    //
    // 症状：dev server 起得来、日志报 "Ready"，但 GET / 一律 404，而且
    // app-paths-manifest.json 里根本没有 `/` 这一条——app/page.tsx 从没被
    // 编译。真正的报错被吞在 unhandledRejection 里：
    //   ENOENT: no such file or directory, stat '.next/cache/webpack/server-development/0.pack.gz'
    //
    // 缓存写坏了会连锁失败：pack 读不到 → 编译产物不落盘 → 路由不注册。
    // 清 .next 只能撑一轮，下次照样坏，所以直接在配置层关掉。
    config.cache = false;
    return config;
  },
};

module.exports = nextConfig;