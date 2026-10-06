#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build the optional TreeMaker-based crease-pattern generator `tm_generate`.
#
# TreeMaker 5 (c) Robert J. Lang, GPL v2+, is NOT vendored in this repository.
# This script fetches it (pinned commit of the GitHub mirror) into a user cache
# directory, compiles only the GUI-free model library (Source/tmModel, incl.
# the bundled, unrestricted wnlib subset) and links it with our own driver
# tm_driver.cpp.  No wxWidgets needed.
#
# Usage:
#   creasebench/gen/treemaker/build.sh            # fetch + build
#   TM_SRC=/path/to/TreeMaker build.sh            # use an existing checkout
#   CREASEBENCH_CACHE=/somewhere build.sh         # override cache root
#
# Result: $CACHE/bin/tm_generate  (CACHE defaults to ~/.cache/creasebench/treemaker)
#
# Exact compiler flags (g++ >= 9 / gcc, tested with GCC 13.3):
#   C++:  -std=gnu++98 -O2 -w -fpermissive -include cstddef -include cstring
#         -include cstdlib -DtmUSE_WNLIB  + -I for every tmModel subdirectory
#     * gnu++98: TreeMaker 5 is 2005-era C++.
#     * -fpermissive: tmArray<T> calls inherited std::vector members without
#       `this->` (two-phase lookup errors on modern GCC); this downgrades them
#       to warnings without patching third-party source.
#     * -include cstddef/cstring/cstdlib: headers missing includes for
#       ptrdiff_t, strcpy, etc.
#     * -DtmUSE_WNLIB: enable the wnlib NLCO engine (tmNLCO.h already enables
#       ALM; CFSQP/RFSQP are proprietary and excluded).
#   C (wnlib): -O2 -w + same -I flags.
#   Link: g++ ... -lm
set -euo pipefail

TM_REPO_URL="${TM_REPO_URL:-https://github.com/StOriJimmy/TreeMaker}"
TM_COMMIT="${TM_COMMIT:-3cf34524c99323dbf06b816a5c8cd72b129e187f}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_ROOT="${CREASEBENCH_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/creasebench}"
CACHE="$CACHE_ROOT/treemaker"
CXX="${CXX:-g++}"
CC="${CC:-gcc}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"

mkdir -p "$CACHE"
SRC="$CACHE/TreeMaker"

# 1. Obtain TreeMaker source at the pinned commit
if [[ -n "${TM_SRC:-}" ]]; then
  echo "[tm] copying TreeMaker source from $TM_SRC"
  rm -rf "$SRC"
  mkdir -p "$SRC"
  cp -r "$TM_SRC/Source" "$SRC/Source"
  cp "$TM_SRC/LICENSE.txt" "$SRC/" 2>/dev/null || true
  if git -C "$TM_SRC" rev-parse HEAD >/dev/null 2>&1; then
    git -C "$TM_SRC" rev-parse HEAD > "$SRC/COMMIT"
  fi
elif [[ ! -f "$SRC/COMMIT" || "$(cat "$SRC/COMMIT")" != "$TM_COMMIT" ]]; then
  echo "[tm] cloning $TM_REPO_URL @ $TM_COMMIT"
  rm -rf "$SRC"
  git clone --quiet "$TM_REPO_URL" "$SRC"
  git -C "$SRC" checkout --quiet "$TM_COMMIT"
  echo "$TM_COMMIT" > "$SRC/COMMIT"
else
  echo "[tm] using cached source $SRC ($(cat "$SRC/COMMIT"))"
fi

S="$SRC/Source"
[[ -d "$S/tmModel" ]] || { echo "error: $S/tmModel not found" >&2; exit 1; }

# 2. Compile the model library (no GUI)
OBJ="$CACHE/obj"
rm -rf "$OBJ"; mkdir -p "$OBJ" "$CACHE/bin"
INC=(-I"$S")
while IFS= read -r d; do INC+=(-I"$d"); done < <(find "$S/tmModel" -type d ! -name '._*' | sort)
CXXFLAGS=(-std=gnu++98 -O2 -w -fpermissive -include cstddef -include cstring
          -include cstdlib -DtmUSE_WNLIB)
CFLAGS=(-O2 -w)

CPP_SRCS=()
while IFS= read -r f; do CPP_SRCS+=("$f"); done < <(
  find "$S/tmModel" -name '*.cpp' ! -name '._*' ! -name '*cfsqp*' ! -name '*rfsqp*' | sort)
CPP_SRCS+=("$S/tmHeader.cpp")
C_SRCS=()
while IFS= read -r f; do C_SRCS+=("$f"); done < <(
  find "$S/tmModel/wnlib" -name '*.c' ! -name '._*' | sort)
C_SRCS+=("$S/tmModel/tmNLCO/tmNLCO_wnlibStub.c")

echo "[tm] compiling ${#CPP_SRCS[@]} C++ and ${#C_SRCS[@]} C files (jobs=$JOBS)"
export CXX CC OBJ
printf '%s\n' "${CPP_SRCS[@]}" | xargs -P "$JOBS" -I{} sh -c \
  '"$CXX" '"${CXXFLAGS[*]} ${INC[*]}"' -c "$1" -o "$OBJ/$(basename "$1" .cpp).o"' _ {}
printf '%s\n' "${C_SRCS[@]}" | xargs -P "$JOBS" -I{} sh -c \
  '"$CC" '"${CFLAGS[*]} ${INC[*]}"' -c "$1" -o "$OBJ/$(basename "$1" .c).o"' _ {}
ar rcs "$CACHE/libtmmodel.a" "$OBJ"/*.o

# 3. Compile and link our driver
echo "[tm] linking tm_generate"
"$CXX" "${CXXFLAGS[@]}" "${INC[@]}" "$HERE/tm_driver.cpp" "$CACHE/libtmmodel.a" -lm \
  -o "$CACHE/bin/tm_generate"
cp "$HERE/tm_driver.cpp" "$CACHE/tm_driver.cpp.built"
echo "[tm] built $CACHE/bin/tm_generate"

# 4. Smoke test: 4-flap star
printf 'edge c a 1\nedge c b 1\nedge c d 1\nedge c e 1\n' | "$CACHE/bin/tm_generate" \
  | head -c 200; echo
