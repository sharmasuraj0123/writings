#!/usr/bin/env bash
# Time four scenarios x 5 reps for each tool. Parallelism pinned to 2 (= nproc) for both.
set -uo pipefail
export TURBO_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1 NX_NO_CLOUD=true NX_TUI=false
T=/tmp/ws-turbo; N=${NXWS:-/tmp/ws-nx}; REPS=${REPS:-5}
ms(){ local s=$(date +%s%N); "$@" >/dev/null 2>&1 || echo "FAIL: $*" >&2; echo $(( ($(date +%s%N)-s)/1000000 )); }
turbo_run(){ (cd $T && ./node_modules/.bin/turbo run build --concurrency=2 --output-logs=none --ui=stream); }
nx_run(){ (cd $N && ./node_modules/.bin/nx run-many -t build --parallel=2 --outputStyle=static); }
clean(){ rm -rf $1/packages/*/dist $1/.turbo $1/node_modules/.cache/turbo $1/.nx/cache $1/.nx/workspace-data; }
bump(){ sed -i "s/v[0-9]*'/v$RANDOM'/" $1/packages/$2/src/index.js; }
emit(){ echo "{\"tool\":\"$1\",\"mode\":\"$2\",\"scenario\":\"$3\",\"ms\":$4}"; }
for mode in default nodaemon; do
 for r in $(seq $REPS); do
  for tool in turbo nx; do
   [ $tool = turbo ] && [ $mode = nodaemon ] && continue
   W=$T; f=turbo_run; [ $tool = nx ] && { W=$N; f=nx_run; }
   [ $mode = nodaemon ] && export NX_DAEMON=false || export NX_DAEMON=true
   [ $tool = nx ] && (cd $N && ./node_modules/.bin/nx reset >/dev/null 2>&1)
   clean $W;                 emit $tool $mode cold  $(ms $f)
                             emit $tool $mode warm  $(ms $f)
   bump $W p01;              emit $tool $mode leaf  $(ms $f)
   bump $W p12;              emit $tool $mode app   $(ms $f)
  done
 done
done
