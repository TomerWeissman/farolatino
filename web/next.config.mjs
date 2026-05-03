/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export — `npm run build` produces web/out/ which the FastAPI
  // app mounts at / so end-users only need Python at runtime.
  output: "export",

  // Trailing slash makes static-file serving work cleanly behind FastAPI's
  // StaticFiles mount (otherwise /runs would 404; /runs/ resolves to
  // out/runs/index.html).
  trailingSlash: true,

  // No image optimization at runtime — static export can't run the
  // Next.js image server.
  images: { unoptimized: true },

  // In `npm run dev` (port 3000), proxy /api/* to FastAPI on :8000 so
  // the frontend can fetch from a single origin in both dev and prod.
  // (output: 'export' is a build-time setting; rewrites only apply in dev.)
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
