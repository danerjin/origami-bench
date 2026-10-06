/**
 * Headless driver for Box Pleating Studio's core (MIT, Mu-Tsun Tsai).
 * Bundled by build.mjs into ../bp_core.bundle.mjs.
 *
 * stdin : {"tree": [[n1,n2,len],...], "flaps": [{id,x,y,width,height}], "sheet": {width,height},
 *          "pattern_choice"?: number | {stretchId: index}, "config_choice"?: {stretchId: index}}
 * stdout: JSON result (see README.md)
 */
import "shared/polyfill/toReversed";
import "shared/polyfill/flatMap";

import { Tree } from "core/design/context/tree";
import { heightTask } from "core/design/tasks/height";
import { Processor } from "core/service/processor";
import { State } from "core/service/state";
import { UpdateResult } from "core/service/updateResult";
import { LayoutController } from "core/controller/layoutController";
import { CreaseType } from "shared/types/cp";
import { rank } from "core/math/gops";

import type { JEdge, JFlap } from "shared/json";

interface Input {
	tree: [number, number, number][];
	flaps: { id: number; x: number; y: number; width?: number; height?: number }[];
	sheet: { width: number; height?: number };
	pattern_choice?: number | Record<string, number>;
	config_choice?: Record<string, number>;
}

const KIND: Record<number, string> = {
	[CreaseType.Border]: "border",
	[CreaseType.Mountain]: "ridge",
	[CreaseType.Valley]: "axis-parallel",
	[CreaseType.Auxiliary]: "hinge",
	[CreaseType.None]: "other",
};
const LABEL: Record<number, string> = {
	[CreaseType.Border]: "B",
	[CreaseType.Mountain]: "M",
	[CreaseType.Valley]: "V",
	[CreaseType.Auxiliary]: "A",
	[CreaseType.None]: "U",
};

function fix(x: number): number {
	const n = Math.round(x * 1e9) / 1e9;
	return Math.abs(x - n) < 1e-9 ? n : x;
}

function classifyGadget(g: any, strategy: string | undefined, nDevGadgets: number): any {
	const pieces = g.pieces.map((p: any) => ({ ox: p.ox, oy: p.oy, u: p.u, v: p.v, rank: rank(p), detours: !!p.detours }));
	let type: string;
	if(strategy === "HALFINTEGRAL") type = "Kamiya";
	else if(strategy === "UNIVERSAL") type = "universal-GPS";
	else if(strategy === "BASE_JOIN" || strategy === "STANDARD_JOIN" || nDevGadgets > 1) type = "join";
	else if(pieces.length == 1) {
		const p = pieces[0];
		type = p.u == 0 && p.v == 0 ? "simple" : "GOPS";
	} else type = "GOPS";
	return { type, strategy: strategy ?? null, pieces };
}

function run(input: Input): any {
	const warnings: string[] = [];
	const errors: string[] = [];
	const W = input.sheet.width, H = input.sheet.height ?? input.sheet.width;
	const edges: JEdge[] = input.tree.map(([n1, n2, length]) => ({ n1, n2, length }) as JEdge);
	const flaps: JFlap[] = input.flaps.map(f => ({ id: f.id, x: f.x, y: f.y, width: f.width ?? 0, height: f.height ?? 0 }) as JFlap);

	for(const f of flaps) {
		if(f.x < 0 || f.y < 0 || f.x + f.width > W || f.y + f.height > H) {
			errors.push(`flap ${f.id} outside sheet`);
		}
	}

	// One design per process: state is fresh (fullReset() relies on DEBUG-only methods).
	State.m.$tree = new Tree(edges, flaps);
	State.m.$treeStructureChanged = true;
	State.m.$rootChanged = true;
	Processor.$run(heightTask);
	const update = UpdateResult.$flush();

	const leafIds = new Set(State.m.$tree.$nodes.filter(n => n && n.$isLeaf).map(n => n!.id as number));
	const flapIds = new Set(flaps.map(f => f.id));
	for(const id of leafIds) if(!flapIds.has(id)) errors.push(`leaf ${id} has no flap position`);
	for(const id of flapIds) if(!leafIds.has(id)) warnings.push(`flap ${id} is not a leaf of the tree`);

	const invalidJunctions = Object.keys(update.add.junctions);

	// Explore all configurations/patterns, then choose.
	const stretchInfo: any[] = [];
	for(const [id, stretch] of State.$stretches) {
		const repo = stretch.$repo;
		repo.$complete();
		let cfgIdx = input.config_choice?.[id];
		if(cfgIdx !== undefined && cfgIdx < repo.$configurations.length) LayoutController.switchConfig(id, cfgIdx);
		let pIdx = typeof input.pattern_choice == "number" ? input.pattern_choice : input.pattern_choice?.[id];
		const config = repo.$configuration;
		if(pIdx !== undefined && config && config.$length) {
			if(pIdx >= config.$length) {
				warnings.push(`stretch ${id}: pattern_choice ${pIdx} >= ${config.$length}, using ${pIdx % config.$length}`);
				pIdx %= config.$length;
			}
			LayoutController.switchPattern(id, pIdx);
		}
	}
	UpdateResult.$flush();

	for(const [id, stretch] of State.$stretches) {
		const repo = stretch.$repo;
		const config = repo.$configuration;
		const pattern = repo.$pattern;
		const devices = pattern ? pattern.$devices.map(d => {
			const partition = d.$partition.toJSON() as any;
			return {
				location: d.$location,
				gadgets: d.$gadgets.map(g => classifyGadget(g.toJSON(), partition.strategy, d.$gadgets.length)),
				addOns: d.$addOns.length,
			};
		}) : [];
		stretchInfo.push({
			id,
			active: stretch.$isActive,
			valid: repo.$isValid,
			configurations: repo.$configurations.length,
			config_index: config ? config.$index : null,
			patterns_in_config: config ? config.$length ?? null : null,
			pattern_found: !!pattern,
			devices,
		});
	}

	const borders = [{ x: 0, y: 0 }, { x: W, y: 0 }, { x: W, y: H }, { x: 0, y: H }];
	const cp = LayoutController.getCP(borders, true);
	const lines: any[] = [];
	const bpAssign: string[] = [];
	for(const l of cp) {
		lines.push([fix(l.p1.x), fix(l.p1.y), fix(l.p2.x), fix(l.p2.y), KIND[l.type] ?? "other"]);
		bpAssign.push(LABEL[l.type] ?? "U");
	}

	const gadgetTypes = [...new Set(stretchInfo.flatMap(s => s.devices.flatMap((d: any) => d.gadgets.map((g: any) => g.type))))];
	const missing = stretchInfo.filter(s => s.active && !s.pattern_found);
	if(invalidJunctions.length) errors.push(`invalid (overlapping) flap pairs: ${invalidJunctions.join(" ")}`);
	for(const s of missing) errors.push(`stretch ${s.id} has no pattern`);

	return {
		status: errors.length ? "error" : "ok",
		errors,
		grid: W,
		sheet: { width: W, height: H },
		lines,
		assignment: lines.map(l => (l[4] == "border" ? "B" : "U")),
		bp_assignment: bpAssign,
		stretches: stretchInfo.length,
		patterns_found: stretchInfo.map(s => s.pattern_found),
		gadget_types: gadgetTypes,
		stretch_details: stretchInfo,
		invalid_junctions: invalidJunctions,
		warnings,
	};
}

async function main(): Promise<void> {
	const chunks: Buffer[] = [];
	for await (const c of process.stdin) chunks.push(c as Buffer);
	let out: any;
	// The core may log in debug paths; keep stdout clean.
	const realLog = console.log;
	console.log = (...a: unknown[]) => console.error(...a);
	console.time = () => {}; console.timeEnd = () => {};
	try {
		out = run(JSON.parse(Buffer.concat(chunks).toString("utf8")));
	} catch(e: any) {
		out = { status: "error", errors: [String(e?.message ?? e)], trace: e?.stack ?? "", lines: [], warnings: [] };
	}
	process.stdout.write(JSON.stringify(out) + "\n");
	console.log = realLog;
}

main();
