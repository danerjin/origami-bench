// Build bp_core.bundle.mjs from a Box Pleating Studio checkout.
// Usage: node build.mjs /path/to/box-pleating-studio   (needs `esbuild` resolvable, e.g. NODE_PATH or local install)
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const bps = path.resolve(process.argv[2] ?? "");
const require = createRequire(path.join(process.cwd(), "noop.js"));
const esbuild = require("esbuild");
const src = path.join(bps, "src");

// Strip `/// #if DEBUG ... /// #endif` blocks (BP Studio uses ifdef-loader with DEBUG=false in production).
const stripDebug = {
	name: "strip-debug",
	setup(build) {
		build.onLoad({ filter: /\.ts$/ }, args => {
			let text = readFileSync(args.path, "utf8");
			const out = []; let depth = 0;
			for(const line of text.split("\n")) {
				const t = line.trim();
				if(t.startsWith("/// #if")) { depth++; continue; }
				if(t.startsWith("/// #endif")) { depth = Math.max(0, depth - 1); continue; }
				if(depth == 0) out.push(line);
			}
			return { contents: out.join("\n"), loader: "ts" };
		});
	},
};

// Resolve BP Studio's bare-path aliases ("core/...", "shared/...") to its src folder.
const alias = {
	name: "bps-alias",
	setup(build) {
		build.onResolve({ filter: /^(core|shared)(\/|$)/ }, async args => {
			const r = await build.resolve("./" + args.path, { resolveDir: src, kind: args.kind });
			return r;
		});
	},
};

await esbuild.build({
	entryPoints: [path.join(here, "src", "entry.ts")],
	bundle: true,
	platform: "node",
	format: "esm",
	target: "node18",
	outfile: path.join(here, "bp_core.bundle.mjs"),
	plugins: [alias, stripDebug],
	define: { "process.env.NODE_ENV": '"production"' },
	legalComments: "inline",
	banner: { js: "// Bundled from Box Pleating Studio v0.7.17 core (MIT License, Copyright (c) Mu-Tsun Tsai). See LICENSE-bpstudio.\n" },
	logLevel: "info",
});
