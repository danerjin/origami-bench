// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * tm_driver.cpp -- headless crease-pattern generator built on Robert J. Lang's
 * TreeMaker 5 model library (tmModel).
 *
 * Copyright (C) 2026 creasebench contributors.
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the Free
 * Software Foundation; either version 2 of the License, or (at your option)
 * any later version.  It is distributed WITHOUT ANY WARRANTY; see the GNU
 * General Public License for details.
 *
 * This file is our own code. It is linked against the TreeMaker 5 model
 * sources (GPL v2+, (c) Robert J. Lang), which are fetched and compiled by
 * build.sh into a user cache directory; TreeMaker source is never vendored
 * into this repository. The resulting tm_generate binary is GPL-2.0-or-later.
 * Crease patterns written by the binary are program output, not covered by
 * the GPL.
 *
 * ---------------------------------------------------------------------------
 * Input (stdin), line-oriented, '#' starts a comment:
 *
 *   edge <a> <b> <length>        tree edge between node ids a and b (ints/
 *                                tokens without spaces); required, >= 2
 *   loc <id> <x> <y>             optional initial position in [0,1]^2
 *   corner <id>                  condition: leaf node fixed to a paper corner
 *   border <id>                  condition: leaf node fixed to a paper edge
 *   option <key> <value>         see below
 *
 * Options (defaults in brackets):
 *   solver   auto|alm|wnlib      NLCO engine for scale/edge optimization; auto
 *                                alternates ALM (even attempts) and wnlib
 *                                (odd attempts) [auto]
 *   restarts N                   random-restart attempts [8]
 *   seed     S                   RNG seed for initial layouts [1]
 *   stubs    0|1|2               0 never, 1 only if CP fails, 2 always
 *                                triangulate with tmStubFinder [1]
 *   pin      0|1                 stretch unpinned leaf flaps with the edge
 *                                optimizer until every leaf is pinned [1]
 *   pin_iters N                  max pin rounds [6]
 *   first    0|1                 stop at the first attempt with a full CP
 *                                instead of keeping the largest-scale one [0]
 *   attempt_timeout SEC          per-attempt wall limit (SIGALRM) [30]
 *
 * Output (stdout): a single JSON object (see README.md for the schema).
 * Exit code is 0 whenever JSON was written (check "ok"), 2 on input errors.
 */

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>
#include <algorithm>

#include <signal.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include "tmModel.h"
#include "tmNLCO.h"

using namespace std;

/* ------------------------------------------------------------------------- */
/* Small helpers                                                              */
/* ------------------------------------------------------------------------- */

struct InEdge { string a, b; double len; };

struct Input {
  vector<InEdge> edges;
  map<string, pair<double, double> > locs;
  vector<string> corners, borders;
  string solver;
  int restarts, seed, stubs, pin, pinIters, first, attemptTimeout;
  Input() : solver("auto"), restarts(8), seed(1), stubs(1), pin(1),
            pinIters(6), first(0), attemptTimeout(30) {}
};

static string JStr(const string& s) {
  string o = "\"";
  for (size_t i = 0; i < s.size(); ++i) {
    char c = s[i];
    if (c == '"' || c == '\\') { o += '\\'; o += c; }
    else if (c == '\n') o += "\\n";
    else if ((unsigned char)c < 0x20) o += ' ';
    else o += c;
  }
  return o + "\"";
}

static string JNum(double x) {
  if (!(x == x) || x > 1e300 || x < -1e300) return "null";
  char buf[64];
  snprintf(buf, sizeof(buf), "%.10g", x);
  return buf;
}

static double Urand(unsigned long long& st) {
  st = st * 6364136223846793005ULL + 1442695040888963407ULL;
  return ((st >> 11) & ((1ULL << 53) - 1)) / 9007199254740992.0;
}

static const char* KindName(tmCrease::Kind k) {
  switch (k) {
    case tmCrease::AXIAL: return "axial";
    case tmCrease::GUSSET: return "gusset";
    case tmCrease::RIDGE: return "ridge";
    case tmCrease::UNFOLDED_HINGE: return "unfolded_hinge";
    case tmCrease::FOLDED_HINGE: return "hinge";
    case tmCrease::PSEUDOHINGE: return "pseudohinge";
  }
  return "unknown";
}

static const char* FoldName(tmCrease::Fold f) {
  switch (f) {
    case tmCrease::FLAT: return "F";
    case tmCrease::MOUNTAIN: return "M";
    case tmCrease::VALLEY: return "V";
    case tmCrease::BORDER: return "B";
  }
  return "U";
}

static const char* StatusName(tmTree::CPStatus s) {
  switch (s) {
    case tmTree::HAS_FULL_CP: return "HAS_FULL_CP";
    case tmTree::EDGES_TOO_SHORT: return "EDGES_TOO_SHORT";
    case tmTree::POLYS_NOT_VALID: return "POLYS_NOT_VALID";
    case tmTree::POLYS_NOT_FILLED: return "POLYS_NOT_FILLED";
    case tmTree::POLYS_MULTIPLE_IBPS: return "POLYS_MULTIPLE_IBPS";
    case tmTree::VERTICES_LACK_DEPTH: return "VERTICES_LACK_DEPTH";
    case tmTree::FACETS_NOT_VALID: return "FACETS_NOT_VALID";
    case tmTree::NOT_LOCAL_ROOT_CONNECTABLE: return "NOT_LOCAL_ROOT_CONNECTABLE";
  }
  return "UNKNOWN";
}

/* ------------------------------------------------------------------------- */
/* Optimizer wrappers. tmOptimizer::Optimize() discards the solver result     */
/* whenever the engine returns a nonzero code (wnlib often reports            */
/* WN_SUBOPTIMAL on perfectly usable solutions), so we always copy the state  */
/* back and let the tree's own feasibility check decide.                     */
/* ------------------------------------------------------------------------- */

class ScaleOpt : public tmScaleOptimizer {
public:
  ScaleOpt(tmTree* t, tmNLCO* n) : tmScaleOptimizer(t, n) {}
  int Run() {
    std::vector<double> x = mCurrentStateVec;
    int inform = mNLCO->Minimize(x);
    mCurrentStateVec = x;
    DataToTree();
    return inform;
  }
};

class EdgeOpt : public tmEdgeOptimizer {
public:
  EdgeOpt(tmTree* t, tmNLCO* n) : tmEdgeOptimizer(t, n) {}
  int Run() {
    std::vector<double> x = mCurrentStateVec;
    int inform = mNLCO->Minimize(x);
    mCurrentStateVec = x;
    DataToTree();
    return inform;
  }
};

static tmNLCO* MakeSolver(const string& name) {
#ifdef tmUSE_WNLIB
  if (name == "wnlib") return new tmNLCO_wnlib();
#endif
#ifdef tmUSE_ALM
  if (name == "alm") return new tmNLCO_alm();
#endif
  (void)name;
#ifdef tmUSE_WNLIB
  return new tmNLCO_wnlib();
#else
  return new tmNLCO_alm();
#endif
}

/* ------------------------------------------------------------------------- */
/* Input parsing                                                              */
/* ------------------------------------------------------------------------- */

static bool ParseInput(istream& in, Input& inp, string& err) {
  string line;
  int lineno = 0;
  while (getline(in, line)) {
    ++lineno;
    size_t h = line.find('#');
    if (h != string::npos) line = line.substr(0, h);
    istringstream ss(line);
    string kw;
    if (!(ss >> kw)) continue;
    if (kw == "edge") {
      InEdge e;
      if (!(ss >> e.a >> e.b >> e.len) || e.len <= 0 || e.a == e.b) {
        ostringstream o; o << "bad edge on line " << lineno; err = o.str();
        return false;
      }
      inp.edges.push_back(e);
    } else if (kw == "loc") {
      string id; double x, y;
      if (!(ss >> id >> x >> y)) { err = "bad loc line"; return false; }
      inp.locs[id] = make_pair(x, y);
    } else if (kw == "corner") {
      string id; if (ss >> id) inp.corners.push_back(id);
    } else if (kw == "border") {
      string id; if (ss >> id) inp.borders.push_back(id);
    } else if (kw == "option") {
      string k, v;
      if (!(ss >> k >> v)) { err = "bad option line"; return false; }
      if (k == "solver") inp.solver = v;
      else if (k == "restarts") inp.restarts = atoi(v.c_str());
      else if (k == "seed") inp.seed = atoi(v.c_str());
      else if (k == "stubs") inp.stubs = atoi(v.c_str());
      else if (k == "pin") inp.pin = atoi(v.c_str());
      else if (k == "pin_iters") inp.pinIters = atoi(v.c_str());
      else if (k == "first") inp.first = atoi(v.c_str());
      else if (k == "attempt_timeout") inp.attemptTimeout = atoi(v.c_str());
    } else {
      ostringstream o; o << "unknown keyword '" << kw << "' on line " << lineno;
      err = o.str();
      return false;
    }
  }
  if (inp.edges.empty()) { err = "no edges"; return false; }
  if (inp.restarts < 1) inp.restarts = 1;
  return true;
}

/* ------------------------------------------------------------------------- */
/* Tree construction                                                          */
/* ------------------------------------------------------------------------- */

struct Graph {
  vector<string> ids;                       // node index -> user id
  map<string, int> idx;                     // user id -> node index
  vector<vector<pair<int, double> > > adj;  // adjacency with lengths
};

static bool BuildGraph(const Input& inp, Graph& g, string& err) {
  for (size_t i = 0; i < inp.edges.size(); ++i) {
    const string* ends[2] = { &inp.edges[i].a, &inp.edges[i].b };
    for (int k = 0; k < 2; ++k)
      if (!g.idx.count(*ends[k])) {
        g.idx[*ends[k]] = (int)g.ids.size();
        g.ids.push_back(*ends[k]);
      }
  }
  g.adj.assign(g.ids.size(), vector<pair<int, double> >());
  for (size_t i = 0; i < inp.edges.size(); ++i) {
    int a = g.idx[inp.edges[i].a], b = g.idx[inp.edges[i].b];
    g.adj[a].push_back(make_pair(b, inp.edges[i].len));
    g.adj[b].push_back(make_pair(a, inp.edges[i].len));
  }
  if (inp.edges.size() + 1 != g.ids.size()) {
    err = "input is not a tree (|E| != |V|-1)"; return false;
  }
  // connectivity
  vector<int> seen(g.ids.size(), 0), st(1, 0); seen[0] = 1;
  size_t cnt = 1;
  while (!st.empty()) {
    int u = st.back(); st.pop_back();
    for (size_t k = 0; k < g.adj[u].size(); ++k) {
      int v = g.adj[u][k].first;
      if (!seen[v]) { seen[v] = 1; ++cnt; st.push_back(v); }
    }
  }
  if (cnt != g.ids.size()) { err = "input tree is disconnected"; return false; }
  size_t nleaves = 0;
  for (size_t i = 0; i < g.adj.size(); ++i) if (g.adj[i].size() == 1) ++nleaves;
  if (nleaves < 3) { err = "TreeMaker needs at least 3 leaf nodes"; return false; }
  return true;
}

static tmPoint SnapToEdge(tmPoint p) {
  double d[4] = {p.x, 1 - p.x, p.y, 1 - p.y};
  int k = 0;
  for (int i = 1; i < 4; ++i) if (d[i] < d[k]) k = i;
  if (k == 0) p.x = 0; else if (k == 1) p.x = 1; else if (k == 2) p.y = 0; else p.y = 1;
  return p;
}

static tmPoint SnapToCorner(tmPoint p) {
  return tmPoint(p.x < 0.5 ? 0.0 : 1.0, p.y < 0.5 ? 0.0 : 1.0);
}

/* Initial layout: leaves on a circle in DFS (planar) order, rotated and
   jittered per attempt; internal nodes at the mean of their subtree leaves. */
static void Layout(const Graph& g, const Input& inp, int attempt,
                   unsigned long long& rng, vector<tmPoint>& pos) {
  size_t n = g.ids.size();
  pos.assign(n, tmPoint(0.5, 0.5));
  int root = 0;
  for (size_t i = 0; i < n; ++i) if (g.adj[i].size() > 1) { root = (int)i; break; }
  vector<int> order, parent(n, -1), stack(1, root);
  vector<int> seen(n, 0); seen[root] = 1;
  while (!stack.empty()) {
    int u = stack.back(); stack.pop_back(); order.push_back(u);
    for (size_t k = g.adj[u].size(); k-- > 0;) {
      int v = g.adj[u][k].first;
      if (!seen[v]) { seen[v] = 1; parent[v] = u; stack.push_back(v); }
    }
  }
  vector<int> leaves;
  for (size_t i = 0; i < order.size(); ++i)
    if (g.adj[order[i]].size() == 1) leaves.push_back(order[i]);
  double rot = (attempt == 0) ? 0.25 * M_PI / leaves.size() : 2 * M_PI * Urand(rng);
  double jit = (attempt == 0) ? 0.0 : 0.15;
  for (size_t i = 0; i < leaves.size(); ++i) {
    double th = rot + 2 * M_PI * i / leaves.size() + jit * (Urand(rng) - 0.5);
    double r = 0.45 - jit * Urand(rng);
    pos[leaves[i]] = tmPoint(0.5 + r * cos(th), 0.5 + r * sin(th));
  }
  // internal nodes: mean of leaves in subtree (post-order accumulate)
  vector<double> sx(n, 0), sy(n, 0), sc(n, 0);
  for (size_t i = order.size(); i-- > 0;) {
    int u = order[i];
    if (g.adj[u].size() == 1) { sx[u] = pos[u].x; sy[u] = pos[u].y; sc[u] = 1; }
    else if (sc[u] > 0) pos[u] = tmPoint(sx[u] / sc[u], sy[u] / sc[u]);
    if (parent[u] >= 0) { sx[parent[u]] += sx[u]; sy[parent[u]] += sy[u]; sc[parent[u]] += sc[u]; }
  }
  // user-specified locations override (first attempt exactly, later jittered)
  for (map<string, pair<double, double> >::const_iterator it = inp.locs.begin();
       it != inp.locs.end(); ++it) {
    map<string, int>::const_iterator f = g.idx.find(it->first);
    if (f == g.idx.end()) continue;
    double x = it->second.first, y = it->second.second;
    if (attempt > 0) { x += 0.05 * (Urand(rng) - 0.5); y += 0.05 * (Urand(rng) - 0.5); }
    pos[f->second] = tmPoint(min(1.0, max(0.0, x)), min(1.0, max(0.0, y)));
  }
  // conditioned leaves start on their constraint: corner leaves greedily on
  // distinct nearest corners, border leaves projected to the nearest edge
  const double cx[4] = {0, 1, 1, 0}, cy[4] = {0, 0, 1, 1};
  bool used[4] = {false, false, false, false};
  for (size_t i = 0; i < inp.corners.size(); ++i) {
    map<string, int>::const_iterator f = g.idx.find(inp.corners[i]);
    if (f == g.idx.end()) continue;
    tmPoint p = pos[f->second];
    int best = -1; double bd = 1e9;
    for (int c = 0; c < 4; ++c) {
      double d = Mag(p - tmPoint(cx[c], cy[c])) + (used[c] ? 10.0 : 0.0);
      if (d < bd) { bd = d; best = c; }
    }
    used[best] = true;
    pos[f->second] = tmPoint(cx[best], cy[best]);
  }
  for (size_t i = 0; i < inp.borders.size(); ++i) {
    map<string, int>::const_iterator f = g.idx.find(inp.borders[i]);
    if (f == g.idx.end()) continue;
    pos[f->second] = SnapToEdge(pos[f->second]);
  }
}

static tmTree* MakeTree(const Graph& g, const Input& inp,
                        const vector<tmPoint>& pos) {
  tmTree* t = new tmTree();
  size_t n = g.ids.size();
  vector<tmNode*> nodes(n, (tmNode*)0);
  int root = 0;
  {
    tmNode* nn; tmEdge* ee = 0;
    t->AddNode(NULL, pos[root], nn, ee);
    nodes[root] = nn;
  }
  vector<int> st(1, root);
  while (!st.empty()) {
    int u = st.back(); st.pop_back();
    for (size_t k = 0; k < g.adj[u].size(); ++k) {
      int v = g.adj[u][k].first;
      if (nodes[v]) continue;
      tmNode* nn; tmEdge* ee;
      t->AddNode(nodes[u], pos[v], nn, ee);
      ee->SetLength(g.adj[u][k].second);
      nodes[v] = nn;
      st.push_back(v);
    }
  }
  for (size_t i = 0; i < n; ++i) {
    // internal label "n<index>" survives tmTree::Clone(); mapped back to the
    // user id on output
    ostringstream lab; lab << "n" << i;
    nodes[i]->SetLabel(lab.str().c_str());
  }
  // Initial scale: the largest scale at which the start layout is feasible,
  // times 0.9 (any feasible-ish start works; the optimizer only needs >0).
  double s = 1e9;
  for (size_t i = 0; i < n; ++i) {
    if (g.adj[i].size() != 1) continue;
    for (size_t j = i + 1; j < n; ++j) {
      if (g.adj[j].size() != 1) continue;
      tmPath* p = t->GetLeafPath(nodes[i], nodes[j]);
      if (!p) continue;
      double d = Mag(pos[i] - pos[j]);
      double L = p->GetMinTreeLength();
      if (L > 0) s = min(s, d / L);
    }
  }
  if (!(s > 1e-4) || s > 1.0) s = 0.05;
  t->SetScale(0.9 * s);
  // conditions
  tmArray<tmNode*> cn, bn;
  for (size_t i = 0; i < inp.corners.size(); ++i)
    if (g.idx.count(inp.corners[i])) cn.push_back(nodes[g.idx.find(inp.corners[i])->second]);
  for (size_t i = 0; i < inp.borders.size(); ++i)
    if (g.idx.count(inp.borders[i])) bn.push_back(nodes[g.idx.find(inp.borders[i])->second]);
  if (!cn.empty()) t->SetNodesFixedToPaperCorner(cn);
  if (!bn.empty()) t->SetNodesFixedToPaperEdge(bn);
  return t;
}

/* ------------------------------------------------------------------------- */
/* One attempt of the full pipeline                                           */
/* ------------------------------------------------------------------------- */

struct Attempt {
  tmTree* tree;
  bool feasible, fullCP;
  int scaleInform, pinRounds, numStubs;
  bool allPinned, usedStubs;
  string status, log, solver;
  double scale, maxKawasaki;
  int localBad, localChecked;
  Attempt() : maxKawasaki(0), localBad(-1), localChecked(0), tree(0), feasible(false), fullCP(false), scaleInform(-99),
              pinRounds(0), numStubs(0), allPinned(false), usedStubs(false),
              scale(0) {}
};

static bool AllLeavesPinned(tmTree* t, tmDpptrArray<tmNode>& unpinned,
                            tmDpptrArray<tmEdge>& edges) {
  unpinned.clear(); edges.clear();
  const tmDpptrArray<tmNode>& ns = t->GetOwnedNodes();
  for (size_t i = 0; i < ns.size(); ++i) {
    tmNode* nd = ns[i];
    if (!nd->IsLeafNode() || nd->IsPinnedNode()) continue;
    unpinned.push_back(nd);
    const tmDpptrArray<tmEdge>& es = nd->GetEdges();
    for (size_t k = 0; k < es.size(); ++k)
      if (!es[k]->IsPinnedEdge() && !edges.contains(es[k])) edges.push_back(es[k]);
  }
  return unpinned.empty();
}

static tmTree::CPStatus CPStatusOf(tmTree* t) {
  tmArray<tmEdge*> be; tmArray<tmPoly*> bp; tmArray<tmVertex*> bv;
  tmArray<tmCrease*> bc; tmArray<tmFacet*> bf;
  return t->GetCPStatus(be, bp, bv, bc, bf);
}

static void TryBuildCP(Attempt& a) {
  try {
    a.tree->BuildPolysAndCreasePattern();
  } catch (...) {
    a.log += "exception in BuildPolysAndCreasePattern; ";
  }
  a.fullCP = a.tree->HasFullCP();
  a.status = a.fullCP ? "HAS_FULL_CP" : StatusName(CPStatusOf(a.tree));
}

/* Set the scale to the largest value for which the current node positions
   are feasible (all leaf paths: |p_i - p_j| >= m * L_ij). The NLCO engines
   frequently stop slightly outside the feasible set (beyond TreeMaker's 1e-4
   tolerance); this projects back onto it and makes binding paths exactly
   active. Returns the new scale. */
static tmNode* FindNode(tmTree* t, int idx) {
  ostringstream want; want << "n" << idx;
  const tmDpptrArray<tmNode>& ns = t->GetOwnedNodes();
  for (size_t i = 0; i < ns.size(); ++i)
    if (want.str() == ns[i]->GetLabel()) return ns[i];
  return 0;
}

static double RepairScale(tmTree* t, const Graph& g, const Input& inp) {
  // optimizers leave conditioned nodes within ~1e-4 of their corner/edge;
  // put them exactly on it first
  for (size_t i = 0; i < inp.corners.size(); ++i) {
    map<string, int>::const_iterator f = g.idx.find(inp.corners[i]);
    tmNode* nd = (f == g.idx.end()) ? 0 : FindNode(t, f->second);
    if (nd) nd->SetLoc(SnapToCorner(nd->GetLoc()));
  }
  for (size_t i = 0; i < inp.borders.size(); ++i) {
    map<string, int>::const_iterator f = g.idx.find(inp.borders[i]);
    tmNode* nd = (f == g.idx.end()) ? 0 : FindNode(t, f->second);
    if (nd) nd->SetLoc(SnapToEdge(nd->GetLoc()));
  }
  double s = 1e300;
  const tmDpptrArray<tmPath>& ps = t->GetOwnedPaths();
  for (size_t i = 0; i < ps.size(); ++i) {
    tmPath* p = ps[i];
    if (!p->IsLeafPath()) continue;
    const tmDpptrArray<tmNode>& pn = p->GetNodes();
    double d = Mag(pn.front()->GetLoc() - pn.back()->GetLoc());
    double L = p->GetMinTreeLength();
    if (L > 0) s = min(s, d / L);
  }
  if (s < 1e299 && s > 0) t->SetScale(s * (1 - 1e-12));
  return t->GetScale();
}

static void RunScaleOpt(tmTree* t, const string& solver, int& inform,
                        ostringstream& log) {
  tmNLCO* nlco = MakeSolver(solver);
  try {
    ScaleOpt opt(t, nlco);
    opt.Initialize();
    inform = opt.Run();
  } catch (tmNLCO::EX_BAD_CONVERGENCE& ex) {
    inform = ex.GetReason();
  } catch (tmScaleOptimizer::EX_BAD_SCALE&) {
    log << "scale too small; ";
  } catch (...) {
    log << "exception in scale optimizer; ";
  }
  delete nlco;
}

static int CountLocalViolations(tmTree* t, double& maxKawasaki, int& checked);

static void RunAttempt(const Graph& g, const Input& inp, int attempt,
                       unsigned long long& rng, Attempt& a) {
  vector<tmPoint> pos;
  Layout(g, inp, attempt, rng, pos);
  a.tree = MakeTree(g, inp, pos);
  ostringstream log;
  string solver = inp.solver;
  if (solver == "auto") solver = (attempt % 2 == 0) ? "alm" : "wnlib";
  a.solver = solver;

  // 1. scale optimization, then project onto the feasible set and polish
  //    (re-optimize from the feasible point) until the scale stops improving.
  RunScaleOpt(a.tree, solver, a.scaleInform, log);
  double prev = RepairScale(a.tree, g, inp);
  for (int pass = 0; pass < 3; ++pass) {
    int inf2 = 0;
    tmTree* backup = a.tree->Clone();
    RunScaleOpt(a.tree, solver, inf2, log);
    double now = RepairScale(a.tree, g, inp);
    if (now < prev) {           // polish made it worse: restore
      delete a.tree; a.tree = backup;
      break;
    }
    delete backup;
    if (now - prev < 1e-7 * prev) break;
    prev = now;
  }
  a.feasible = a.tree->IsFeasible();
  log << "scale_inform=" << a.scaleInform << "; ";
  if (!a.feasible) {
    a.status = "INFEASIBLE_AFTER_SCALE_OPT";
    a.scale = a.tree->GetScale();
    a.log = log.str();
    return;
  }

  // 2. pin all leaves by stretching unpinned flaps (edge optimizer)
  tmDpptrArray<tmNode> un; tmDpptrArray<tmEdge> ue;
  a.allPinned = AllLeavesPinned(a.tree, un, ue);
  if (inp.pin) {
    for (int r = 0; r < inp.pinIters && !a.allPinned; ++r) {
      tmTree* backup = a.tree->Clone();
      double s0 = a.tree->GetScale();
      tmNLCO* nlco = MakeSolver(solver);
      try {
        EdgeOpt opt(a.tree, nlco);
        opt.Initialize(un, ue);
        int inf = opt.Run();
        log << "pin" << r << "_inform=" << inf << "; ";
      } catch (tmEdgeOptimizer::EX_NO_MOVING_NODES&) {
        log << "pin: no moving nodes; ";
      } catch (tmEdgeOptimizer::EX_NO_MOVING_EDGES&) {
        log << "pin: no moving edges; ";
      } catch (...) {
        log << "pin: exception; ";
      }
      delete nlco;
      ++a.pinRounds;
      if (!a.tree->IsFeasible()) {
        // engine overshot (strain too large): shrink the scale back onto the
        // feasible set if that costs < 1%, otherwise undo this round
        RepairScale(a.tree, g, inp);
        if (!a.tree->IsFeasible() || a.tree->GetScale() < 0.99 * s0) {
          delete a.tree;
          a.tree = backup;
          backup = 0;
          log << "pin round reverted (infeasible); ";
          a.allPinned = AllLeavesPinned(a.tree, un, ue);
          break;
        }
      }
      delete backup;
      a.allPinned = AllLeavesPinned(a.tree, un, ue);
    }
  }
  a.feasible = a.tree->IsFeasible();

  // 3. polygons + crease pattern (+ facet ordering / MV, done in cleanup)
  size_t nodesBefore = a.tree->GetOwnedNodes().size();
  if (inp.stubs >= 2) {
    try { tmStubFinder sf(a.tree); sf.TriangulateTree(); a.usedStubs = true; }
    catch (...) { log << "stubfinder exception; "; }
  }
  TryBuildCP(a);
  if (!a.fullCP && inp.stubs == 1) {
    log << "first CP status=" << a.status << "; ";
    try {
      a.tree->KillPolysAndCreasePattern();
      tmStubFinder sf(a.tree);
      sf.TriangulateTree();
      a.usedStubs = true;
    } catch (...) { log << "stubfinder exception; "; }
    TryBuildCP(a);
  }
  a.numStubs = (int)(a.tree->GetOwnedNodes().size() - nodesBefore);
  a.scale = a.tree->GetScale();
  if (a.fullCP)
    a.localBad = CountLocalViolations(a.tree, a.maxKawasaki, a.localChecked);
  a.log = log.str();
}

/* ------------------------------------------------------------------------- */
/* JSON output                                                                */
/* ------------------------------------------------------------------------- */

/* Local flat-foldability at TreeMaker-interior vertices (not on the leaf
   convex hull): even degree, Maekawa |M-V| = 2 and Kawasaki (alternating
   sector sum = pi, tolerance 1e-3 rad) over the M/V creases. */
static int CountLocalViolations(tmTree* t, double& maxKawasaki, int& checked) {
  int bad = 0;
  maxKawasaki = 0; checked = 0;
  const tmDpptrArray<tmVertex>& vs = t->GetVertices();
  for (size_t i = 0; i < vs.size(); ++i) {
    tmVertex* v = vs[i];
    if (v->IsBorderVertex()) continue;
    const tmDpptrArray<tmCrease>& cs = v->GetCreases();
    vector<pair<double, int> > rays;
    bool skip = cs.empty();
    for (size_t k = 0; k < cs.size(); ++k) {
      tmCrease* c = cs[k];
      if (c->GetFold() == tmCrease::BORDER) { skip = true; break; }
      if (c->GetFold() == tmCrease::FLAT) continue;
      const tmDpptrArray<tmVertex>& cv = c->GetVertices();
      tmVertex* o = (cv.front() == v) ? cv.back() : cv.front();
      tmPoint d = o->GetLoc() - v->GetLoc();
      rays.push_back(make_pair(atan2(d.y, d.x),
                               c->GetFold() == tmCrease::MOUNTAIN ? 1 : -1));
    }
    if (skip) continue;
    ++checked;
    int n = (int)rays.size(), mv = 0;
    for (int k = 0; k < n; ++k) mv += rays[k].second;
    if (n % 2 || (mv != 2 && mv != -2)) { ++bad; continue; }
    sort(rays.begin(), rays.end());
    double alt = 0;
    for (int k = 0; k < n; ++k) {
      double sec = rays[(k + 1) % n].first - rays[k].first;
      if (sec < 0) sec += 2 * M_PI;
      alt += (k % 2) ? -sec : sec;
    }
    double err = fabs(alt);
    if (err > maxKawasaki) maxKawasaki = err;
    if (err > 1e-3) ++bad;
  }
  return bad;
}

static string ResultJSON(const Graph& g, Attempt& a, int attemptIdx) {
  tmTree* t = a.tree;
  int stubCounter = 0;
  const tmDpptrArray<tmNode>& nodes = t->GetNodes();
  map<tmNode*, string> lab;
  for (size_t i = 0; i < nodes.size(); ++i) {
    const char* l = nodes[i]->GetLabel();
    if (nodes[i]->IsTreeNode() && l[0] == 'n' && l[1]) {
      size_t k = (size_t)atol(l + 1);
      if (k < g.ids.size()) { lab[nodes[i]] = g.ids[k]; continue; }
    }
    {
      ostringstream o;
      o << (nodes[i]->IsSubNode() ? "sub_" : "stub_") << stubCounter++;
      lab[nodes[i]] = o.str();
    }
  }
  double W = t->GetPaperWidth(), H = t->GetPaperHeight();
  ostringstream o;
  o << "{";
  o << "\"ok\":" << (a.fullCP ? "true" : "false");
  o << ",\"status\":" << JStr(a.status);
  o << ",\"feasible\":" << (a.feasible ? "true" : "false");
  o << ",\"all_leaves_pinned\":" << (a.allPinned ? "true" : "false");
  o << ",\"polygon_valid\":" << (t->IsPolygonValid() ? "true" : "false");
  o << ",\"polygon_filled\":" << (t->IsPolygonFilled() ? "true" : "false");
  o << ",\"vertex_depth_valid\":" << (t->IsVertexDepthValid() ? "true" : "false");
  o << ",\"facet_data_valid\":" << (t->IsFacetDataValid() ? "true" : "false");
  o << ",\"local_root_connectable\":" << (t->IsLocalRootConnectable() ? "true" : "false");
  o << ",\"scale\":" << JNum(a.scale);
  o << ",\"paper\":[" << JNum(W) << "," << JNum(H) << "]";
  o << ",\"solver\":" << JStr(a.solver);
  o << ",\"attempt\":" << attemptIdx;
  o << ",\"interior_vertices_checked\":" << a.localChecked;
  o << ",\"interior_violations\":" << a.localBad;
  o << ",\"max_kawasaki_error\":" << JNum(a.maxKawasaki);
  o << ",\"scale_inform\":" << a.scaleInform;
  o << ",\"pin_rounds\":" << a.pinRounds;
  o << ",\"used_stub_finder\":" << (a.usedStubs ? "true" : "false");
  o << ",\"num_stubs_added\":" << a.numStubs;
  o << ",\"log\":" << JStr(a.log);

  // tree nodes
  o << ",\"nodes\":[";
  for (size_t i = 0; i < nodes.size(); ++i) {
    tmNode* nd = nodes[i];
    if (i) o << ",";
    o << "{\"id\":" << JStr(lab[nd]) << ",\"x\":" << JNum(nd->GetLocX())
      << ",\"y\":" << JNum(nd->GetLocY())
      << ",\"leaf\":" << (nd->IsLeafNode() ? "true" : "false")
      << ",\"sub\":" << (nd->IsSubNode() ? "true" : "false")
      << ",\"pinned\":" << (nd->IsPinnedNode() ? "true" : "false")
      << ",\"border\":" << (nd->IsBorderNode() ? "true" : "false")
      << ",\"depth\":" << JNum(nd->GetDepth())
      << ",\"elevation\":" << JNum(nd->GetElevation()) << "}";
  }
  o << "]";

  // tree edges (lengths include strain introduced by pinning)
  const tmDpptrArray<tmEdge>& edges = t->GetEdges();
  o << ",\"edges\":[";
  for (size_t i = 0; i < edges.size(); ++i) {
    tmEdge* e = edges[i];
    if (i) o << ",";
    o << "{\"a\":" << JStr(lab[e->GetNodes().front()])
      << ",\"b\":" << JStr(lab[e->GetNodes().back()])
      << ",\"length\":" << JNum(e->GetLength())
      << ",\"strain\":" << JNum(e->GetStrain())
      << ",\"strained_length\":" << JNum(e->GetStrainedLength()) << "}";
  }
  o << "]";

  // vertices
  const tmDpptrArray<tmVertex>& vs = t->GetVertices();
  map<const tmVertex*, size_t> vidx;
  o << ",\"vertices\":[";
  for (size_t i = 0; i < vs.size(); ++i) {
    tmVertex* v = vs[i];
    vidx[v] = i;
    if (i) o << ",";
    o << "{\"x\":" << JNum(v->GetLoc().x) << ",\"y\":" << JNum(v->GetLoc().y)
      << ",\"elevation\":" << JNum(v->GetElevation())
      << ",\"depth\":" << JNum(v->GetDepth())
      << ",\"border\":" << (v->IsBorderVertex() ? "true" : "false")
      << ",\"tree_node\":";
    if (v->GetTreeNode()) o << JStr(lab[v->GetTreeNode()]); else o << "null";
    o << "}";
  }
  o << "]";

  // creases
  const tmDpptrArray<tmCrease>& cs = t->GetCreases();
  o << ",\"creases\":[";
  for (size_t i = 0; i < cs.size(); ++i) {
    tmCrease* c = cs[i];
    if (i) o << ",";
    const tmDpptrArray<tmVertex>& cv = c->GetVertices();
    o << "{\"v\":[" << vidx[cv.front()] << "," << vidx[cv.back()] << "]"
      << ",\"kind\":" << JStr(KindName(c->GetKind()))
      << ",\"fold\":" << JStr(FoldName(c->GetFold())) << "}";
  }
  o << "]";

  // facets
  const tmDpptrArray<tmFacet>& fs = t->GetFacets();
  o << ",\"facets\":[";
  for (size_t i = 0; i < fs.size(); ++i) {
    tmFacet* f = fs[i];
    if (i) o << ",";
    o << "{\"v\":[";
    const tmArray<tmVertex*>& fv = f->GetVertices();
    for (size_t k = 0; k < fv.size(); ++k) o << (k ? "," : "") << vidx[fv[k]];
    o << "],\"color\":"
      << (f->IsWhiteUpFacet() ? "\"white_up\"" :
          f->IsColorUpFacet() ? "\"color_up\"" : "null")
      << ",\"order\":" << f->GetOrder()
      << ",\"corridor_edge\":";
    tmEdge* ce = f->GetCorridorEdge();
    if (ce) o << "[" << JStr(lab[ce->GetNodes().front()]) << ","
              << JStr(lab[ce->GetNodes().back()]) << "]";
    else o << "null";
    o << "}";
  }
  o << "]";
  o << "}";
  return o.str();
}

static void WriteError(const string& msg) {
  cout << "{\"ok\":false,\"status\":\"INPUT_ERROR\",\"error\":" << JStr(msg)
       << "}\n";
}

/* ------------------------------------------------------------------------- */

/* Each attempt runs in a forked child: TreeMaker's model code has assertions
   compiled out and can crash (SIGSEGV) on degenerate geometry, so isolating
   attempts keeps one bad layout from killing the whole run. The child sends
   "rank scale\n<json>" back through a pipe. */
static double WallTime() {
  struct timeval tv; gettimeofday(&tv, 0);
  return tv.tv_sec + 1e-6 * tv.tv_usec;
}

int main() {
  tmPart::InitTypes();
  Input inp;
  string err;
  if (!ParseInput(cin, inp, err)) { WriteError(err); return 2; }
  Graph g;
  if (!BuildGraph(inp, g, err)) { WriteError(err); return 2; }

  double t0 = WallTime();
  string bestJson;
  double bestScale = -1;
  int bestRank = -1, run = 0;
  ostringstream alog;
  // rank: 3 full CP passing the local check, 2 full CP, 1 feasible, 0 other;
  // ties broken by larger scale
  for (int k = 0; k < inp.restarts; ++k) {
    int fd[2];
    if (pipe(fd) != 0) break;
    fflush(stdout);
    pid_t pid = fork();
    if (pid == 0) {
      close(fd[0]);
      alarm(inp.attemptTimeout);
      unsigned long long rng = 0x9E3779B97F4A7C15ULL * (unsigned long long)(inp.seed + 1)
                               + 0xBF58476D1CE4E5B9ULL * (unsigned long long)(k + 1);
      Attempt a;
      RunAttempt(g, inp, k, rng, a);
      int rank = a.fullCP ? (a.localBad == 0 ? 3 : 2) : (a.feasible ? 1 : 0);
      ostringstream out;
      out << rank << " " << JNum(a.scale) << " " << JStr(a.status) << " "
          << JStr(a.solver) << "\n" << ResultJSON(g, a, k);
      string str = out.str();
      size_t off = 0;
      while (off < str.size()) {
        ssize_t w = write(fd[1], str.data() + off, str.size() - off);
        if (w <= 0) break;
        off += (size_t)w;
      }
      close(fd[1]);
      _exit(0);
    }
    close(fd[1]);
    string buf;
    char tmp[65536];
    ssize_t r;
    while ((r = read(fd[0], tmp, sizeof(tmp))) > 0) buf.append(tmp, (size_t)r);
    close(fd[0]);
    int wstatus = 0;
    waitpid(pid, &wstatus, 0);
    ++run;
    if (k) alog << ",";
    size_t nl = buf.find('\n');
    if (pid < 0 || nl == string::npos || !WIFEXITED(wstatus)) {
      alog << "{\"attempt\":" << k << ",\"status\":\"CRASH\",\"signal\":"
           << (WIFSIGNALED(wstatus) ? WTERMSIG(wstatus) : 0) << "}";
      continue;
    }
    istringstream hs(buf.substr(0, nl));
    int rank = 0; string scaleStr, status, solver;
    hs >> rank >> scaleStr >> status >> solver;
    double sc = atof(scaleStr.c_str());
    alog << "{\"attempt\":" << k << ",\"rank\":" << rank << ",\"scale\":"
         << scaleStr << ",\"status\":" << status << ",\"solver\":" << solver << "}";
    if (rank > bestRank || (rank == bestRank && sc > bestScale)) {
      bestRank = rank; bestScale = sc; bestJson = buf.substr(nl + 1);
    }
    if (bestRank >= 3 && inp.first) break;
  }
  double secs = WallTime() - t0;
  if (bestJson.empty()) {
    cout << "{\"ok\":false,\"status\":\"ALL_ATTEMPTS_CRASHED\",\"seconds\":"
         << JNum(secs) << ",\"attempts_run\":" << run << ",\"attempts\":["
         << alog.str() << "]}\n";
    return 0;
  }
  cout << "{\"seconds\":" << JNum(secs) << ",\"attempts_run\":" << run
       << ",\"attempts\":[" << alog.str() << "]," << bestJson.substr(1) << "\n";
  return 0;
}
