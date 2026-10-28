#!/usr/bin/env node
// Adds a module from the Copier module templates and registers it with the
// app and the uv workspace.
//
// Usage:
//   pnpm run add:module <folder>     # backend-modules/<folder> + frontend-modules/<folder>
//   pnpm run add:backend <folder>    # backend-modules/<folder>
//   pnpm run add:frontend <folder>   # frontend-modules/<folder>
//
// Extra arguments are passed to `copier copy` (e.g. --defaults, --data key=value).
// Set OCELESCOPE_BACKEND_TEMPLATE / OCELESCOPE_FRONTEND_TEMPLATE to use another
// template (e.g. a local checkout).
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline/promises";
import { fileURLToPath } from "node:url";

process.chdir(fileURLToPath(new URL("..", import.meta.url)));

const TEMPLATES = {
	backend:
		process.env.OCELESCOPE_BACKEND_TEMPLATE ?? "gh:promi4s/create-ocelescope-backend-module",
	frontend:
		process.env.OCELESCOPE_FRONTEND_TEMPLATE ?? "gh:promi4s/create-ocelescope-frontend-module",
};
const APP_PACKAGE = "app/package.json";
const APP_CONFIG = "app/ocelescope.config.ts";
const APP_TSCONFIG = "app/tsconfig.json";

const run = (command, args) => {
	const { status, error } = spawnSync(command, args, { stdio: "inherit" });
	if (error) throw error;
	if (status !== 0) process.exit(status ?? 1);
};

const copier = (part, dir, extraArgs) =>
	run("uvx", ["copier", "copy", ...extraArgs, TEMPLATES[part], dir]);

const [kind, ...rest] = process.argv.slice(2);
const parts = { module: ["backend", "frontend"], backend: ["backend"], frontend: ["frontend"] }[kind];
if (!parts) {
	console.error("Usage: add-module.mjs <module|backend|frontend> <folder> [copier args]");
	process.exit(1);
}

let folder = rest[0] && !rest[0].startsWith("-") ? rest.shift() : undefined;
if (!folder) {
	const rl = createInterface({ input: process.stdin, output: process.stdout });
	folder = (await rl.question("Module folder name (e.g. ocel-stats): ")).trim();
	rl.close();
}
if (!/^[a-z0-9][a-z0-9-]*$/.test(folder)) {
	console.error(`"${folder}" is not a valid folder name (lowercase letters, digits and dashes)`);
	process.exit(1);
}

const backendDir = `backend-modules/${folder}`;
const frontendDir = `frontend-modules/${folder}`;
for (const dir of parts.map((part) => (part === "backend" ? backendDir : frontendDir))) {
	if (existsSync(dir)) {
		console.error(`${dir} already exists`);
		process.exit(1);
	}
}

const added = [];
const manualSteps = [];

if (parts.includes("backend")) {
	copier("backend", backendDir, rest);
	const name = readFileSync(`${backendDir}/pyproject.toml`, "utf8").match(/^name = "(.+)"$/m)[1];
	// Adds the member to the root pyproject.toml with `{ workspace = true }`.
	run("uv", ["add", "--no-sync", name]);
	added.push(`backend:  ${backendDir} (${name})`);
}

if (parts.includes("frontend")) {
	const extraArgs = [...rest];
	let tmp;
	if (parts.includes("backend")) {
		// Reuse the backend's answers so both halves share name, description and
		// author, and the API client targets that backend module by default.
		tmp = mkdtempSync(join(tmpdir(), "add-module-"));
		const shared = readFileSync(`${backendDir}/.copier-answers.yml`, "utf8")
			.split("\n")
			.filter((line) => /^(module_label|description|author):/.test(line));
		writeFileSync(join(tmp, "answers.yml"), `${shared.join("\n")}\n`);
		extraArgs.unshift("--data-file", join(tmp, "answers.yml"));
	}
	try {
		copier("frontend", frontendDir, extraArgs);
	} finally {
		if (tmp) rmSync(tmp, { recursive: true, force: true });
	}

	const name = JSON.parse(readFileSync(`${frontendDir}/package.json`, "utf8")).name;
	added.push(`frontend: ${frontendDir} (${name})`);

	const pkg = JSON.parse(readFileSync(APP_PACKAGE, "utf8"));
	pkg.dependencies = Object.fromEntries(
		Object.entries({ ...pkg.dependencies, [name]: "workspace:*" }).sort(([a], [b]) =>
			a.localeCompare(b),
		),
	);
	writeFileSync(APP_PACKAGE, `${JSON.stringify(pkg, null, "\t")}\n`);

	// Resolve the module to its sources, so `next dev` picks up changes without a rebuild.
	const tsconfig = JSON.parse(readFileSync(APP_TSCONFIG, "utf8"));
	tsconfig.compilerOptions.paths = {
		...tsconfig.compilerOptions.paths,
		[name]: [`../${frontendDir}/src/index.ts`],
	};
	writeFileSync(APP_TSCONFIG, `${JSON.stringify(tsconfig, null, 2)}\n`);

	// e.g. @instance/ocel-stats -> ocelStatsModule
	const identifier = `${name
		.replace(/^@[^/]+\//, "")
		.replace(/[^A-Za-z0-9]+(.)/g, (_, c) => c.toUpperCase())
		.replace(/^[^A-Za-z]/, (c) => `m${c}`)}Module`;
	let config = readFileSync(APP_CONFIG, "utf8");
	const lastImport = [...config.matchAll(/^import .*;$/gm)].at(-1);
	// The `modules: [...]` list (up to its closing bracket).
	const modulesList = /(modules:\s*\[)([^\]]*?)(,?\s*)\]/;
	if (lastImport && modulesList.test(config)) {
		config = config.replace(modulesList, (_, open, items, trailing) => {
			if (!items.trim()) return `${open}${identifier}${trailing}]`;
			// Multi-line lists get the new entry on its own line.
			const indent = items.match(/\n([ \t]*)[^\n]*$/)?.[1];
			const separator = indent === undefined ? ", " : `,\n${indent}`;
			return `${open}${items}${separator}${identifier}${trailing}]`;
		});
		const at = lastImport.index + lastImport[0].length;
		config = `${config.slice(0, at)}\nimport ${identifier} from "${name}";${config.slice(at)}`;
		writeFileSync(APP_CONFIG, config);
	} else {
		manualSteps.push(
			`register it in ${APP_CONFIG}: import ${identifier} from "${name}" and add it to \`modules\``,
		);
	}
}

console.log(`\nAdded:\n${added.map((line) => `  ${line}`).join("\n")}`);
for (const step of manualSteps) console.log(`\nManual step needed: ${step}`);
console.log("\nNext: pnpm run sync && pnpm run dev");
