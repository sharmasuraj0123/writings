#!/usr/bin/env bash
# Build one synthetic npm workspace: 12 packages in a 4-layer DAG.
# Usage: make-ws.sh <dir> turbo|nx|nx-naive
#   nx-naive: build inputs = own src only (no ^ input) - reproduces the stale-dependent footgun
set -euo pipefail
dir=$1; tool=$2
rm -rf "$dir"; mkdir -p "$dir/packages"; cd "$dir"
# layer edges: p01..p04 leaves; p05..p08 depend on two leaves; p09..p11 on two mids; p12 (app) on p09..p11
declare -A deps=( [p05]="p01 p02" [p06]="p02 p03" [p07]="p03 p04" [p08]="p01 p04"
                  [p09]="p05 p06" [p10]="p06 p07" [p11]="p07 p08" [p12]="p09 p10 p11" )
for i in $(seq -w 1 12); do
  p=p$i; mkdir -p packages/$p/src
  d=""; for x in ${deps[$p]:-}; do d="$d\"@ws/$x\": \"*\","; done; d=${d%,}
  cat > packages/$p/package.json <<J
{ "name": "@ws/$p", "version": "0.0.0", "private": true,
  "scripts": { "build": "node ../../build.js $p" },
  "dependencies": { $d } }
J
  echo "export const $p = '$p v1';" > packages/$p/src/index.js
done
# build step: ~400ms of real CPU work, then write dist/
cat > build.js <<'J'
const fs=require('fs'),c=require('crypto');const p=process.argv[2];
let h=fs.readFileSync('src/index.js');const t=Date.now();while(Date.now()-t<400)h=c.createHash('sha256').update(h).digest();
fs.mkdirSync('dist',{recursive:true});fs.writeFileSync('dist/index.js',fs.readFileSync('src/index.js','utf8')+'// '+h.toString('hex')+'\n');
J
if [ $tool = turbo ]; then
  cat > package.json <<'J'
{ "name": "ws", "private": true, "packageManager": "npm@11.19.0", "workspaces": ["packages/*"],
  "devDependencies": { "turbo": "2.11.6" } }
J
  cat > turbo.json <<'J'
{ "$schema": "https://turborepo.dev/schema.json",
  "tasks": { "build": { "dependsOn": ["^build"], "inputs": ["src/**"], "outputs": ["dist/**"] } } }
J
else
  cat > package.json <<'J'
{ "name": "ws", "private": true, "workspaces": ["packages/*"],
  "devDependencies": { "nx": "23.2.1" } }
J
  if [ $tool = nx-naive ]; then inputs='["src"]'; else inputs='["src", "^src"]'; fi
  cat > nx.json <<J
{ "\$schema": "./node_modules/nx/schemas/nx-schema.json",
  "namedInputs": { "src": ["{projectRoot}/src/**/*"] },
  "targetDefaults": { "build": { "dependsOn": ["^build"], "inputs": $inputs,
                                 "outputs": ["{projectRoot}/dist"], "cache": true } } }
J
fi
git init -q && git add -A && git -c user.email=b@b -c user.name=b commit -qm init
npm install --no-audit --no-fund --loglevel=error >/dev/null
