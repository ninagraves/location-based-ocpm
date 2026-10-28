import { readFileSync } from "node:fs";
import type { NextConfig } from "next";

const apiBase = process.env.EXTERNAL_API_BASE_URL ?? "http://localhost:8002";

// Local frontend modules (`workspace:` dependencies) are compiled from source.
const { dependencies } = JSON.parse(readFileSync("package.json", "utf8"));
const localModules = Object.entries<string>(dependencies)
	.filter(([, version]) => version.startsWith("workspace:"))
	.map(([name]) => name);

const nextConfig: NextConfig = {
	reactStrictMode: true,
	experimental: {
		proxyClientMaxBodySize: "1000gb",
		proxyTimeout: 30 * 60 * 1000,
	},
	transpilePackages: ["@mantine/charts", "recharts", ...localModules],
	rewrites: async () => [
		{ source: "/api/external/:path*", destination: `${apiBase}/:path*` },
	],
};

export default nextConfig;
