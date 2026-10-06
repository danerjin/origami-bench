// Headless driver for the vendored flat-folder solver.
// stdin: FOLD JSON (vertices_coords, edges_vertices, edges_assignment, faces_vertices)
// argv[2]: solution limit per component (default 1)
// stdout: JSON {status, ...}
import { M } from "./vendor/math.js";
import { NOTE } from "./vendor/note.js";
import { CON } from "./vendor/constraints.js";
import { X } from "./vendor/conversion.js";
import { SOLVER } from "./vendor/solver.js";

NOTE.show = false;
NOTE.log = () => {};
const out = (o) => process.stdout.write(JSON.stringify(o));

let data = "";
process.stdin.on("data", (c) => data += c);
process.stdin.on("end", () => {
    const lim = +(process.argv[2] ?? 1);
    const fold = JSON.parse(data);
    const t0 = performance.now();
    try {
        CON.build();
        const V = fold.vertices_coords, EV = fold.edges_vertices;
        const EA = fold.edges_assignment, FV = fold.faces_vertices;
        const [EF, FE] = X.EV_FV_2_EF_FE(EV, FV);
        const [Vf, Ff] = X.V_FV_EV_EA_2_Vf_Ff(V, FV, EV, EA);
        const L = EV.map((P) => M.expand(P, Vf));
        const [P, SP, SE, eps_i] = X.L_2_V_EV_EL(L);
        if (P.length == 0) { return out({status: "error", error: "precision: no stable graph"}); }
        const [, CP] = X.V_EV_2_VV_FV(P, SP);
        const [SC, CS] = X.EV_FV_2_EF_FE(SP, CP);
        const [CF, FC] = X.EF_FV_P_SP_SE_CP_SC_2_CF_FC(EF, FV, P, SP, SE, CP, SC);
        const BF = X.EF_SP_SE_CP_CF_2_BF(EF, SP, SE, CP, CF);
        const BI = new Map();
        for (const [i, F] of BF.entries()) { BI.set(F, i); }
        const BT = X.BF_BI_EF_SE_CF_SC_2_BT(BF, BI, EF, SE, CF, SC);
        const CC = X.FC_BF_BI_BT_2_CC(FC, BF, BI, BT);
        const BA0 = SOLVER.EF_EA_Ff_BF_BI_2_BA0(EF, EA, Ff, BF, BI);
        const stats = {faces: FV.length, cells: CP.length, variables: BF.length};
        const init = SOLVER.initial_assignment(BA0, BF, BT, BI, FC, CF, CC);
        if ((init.length == 3) && (init[0].length == undefined)) {
            const [type, F] = init;
            return out({status: "none", reason: `unable to resolve ${CON.names[type]}`,
                        faces: F, stats, Ff, seconds: (performance.now() - t0) / 1000});
        }
        const BA = init;
        const GB = SOLVER.get_components(BI, BF, BT, BA, FC, CF, CC);
        const GA = SOLVER.solve(BI, BF, BT, BA, GB, FC, CF, CC, lim);
        if (GA.length == undefined) {
            return out({status: "none", reason: `unable to resolve component ${GA}`, stats, Ff,
                        seconds: (performance.now() - t0) / 1000});
        }
        const states = GA.reduce((s, A) => s * BigInt(A.length), 1n);
        const edges = X.BF_GB_GA_GI_2_edges(BF, GB, GA, GA.map(() => 0));
        // edge [f1, f2] means order value 1, i.e. f2 is above f1 in flat-folder's frame
        const above = edges.map((k) => { const [f1, f2] = M.decode(k); return [f2, f1]; });
        stats.components = GB.length;
        out({status: "found", above, Ff, states: states.toString(), limited: GA.some(A => A.length == lim),
             stats, seconds: (performance.now() - t0) / 1000});
    } catch (e) {
        out({status: "error", error: String(e && e.message || e)});
    }
});
