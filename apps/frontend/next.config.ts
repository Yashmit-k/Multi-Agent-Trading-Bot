import type { NextConfig } from "next";

// Pages of the NIFTY 50 paper system, archived on 4 Nov 2026 when its Zerodha market data ended and its data was
// removed from the server. The code stays in the repo; the pages now send visitors to the Momentum trial.
export const ARCHIVED_PATHS = [
  "/dashboard", "/portfolio", "/positions", "/orders", "/journal", "/risk", "/agents", "/manager",
  "/trace", "/signals", "/news", "/market", "/stocks", "/watchlist", "/strategies",
];

const nextConfig: NextConfig = {
  distDir: ".next",
  async redirects() {
    return ARCHIVED_PATHS.flatMap((path) => [
      { source: path, destination: "/momentum", permanent: false },
      { source: `${path}/:rest*`, destination: "/momentum", permanent: false },
    ]);
  },
};

export default nextConfig;
