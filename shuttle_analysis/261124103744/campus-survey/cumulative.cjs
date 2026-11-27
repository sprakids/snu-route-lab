// One shortest-distance path per ordered pair of sampled vertices. Among tied
// shortest distances, prefer the greatest accumulated climb (same for descent).
const fs = require('node:fs');
const {z, adj} = JSON.parse(fs.readFileSync(0, 'utf8'));
const n = z.length;
const dist = new Float64Array(n), climb = new Float64Array(n), parent = new Int32Array(n);
const heap = new Int32Array(n), position = new Int32Array(n);
let count = 0, pairs = 0;
const best = [{meters:-1}, {meters:-1}];
function before(a, b) { return dist[a] < dist[b] || (dist[a] === dist[b] && a < b); }
function insert(v) {
  let i = position[v];
  if (i === -1) i = count++;
  while (i > 0) {
    const p = (i - 1) >> 1;
    if (!before(v, heap[p])) break;
    heap[i] = heap[p]; position[heap[i]] = i; i = p;
  }
  heap[i] = v; position[v] = i;
}
function remove() {
  const result = heap[0], tail = heap[--count];
  position[result] = -1;
  if (count > 0) {
    let i = 0;
    while (2*i + 1 < count) {
      let child = 2*i+1;
      if (child+1 < count && before(heap[child+1], heap[child])) child++;
      if (!before(heap[child],tail)) break;
      heap[i]=heap[child]; position[heap[i]]=i; i=child;
    }
    heap[i]=tail; position[tail]=i;
  }
  return result;
}
function record(i, meters, s, u) {
  if (meters <= best[i].meters + 1e-8) return;
  const chain = [u];
  while (chain[chain.length - 1] !== s) chain.push(parent[chain[chain.length - 1]]);
  best[i] = {meters, chain:chain.reverse(), length:dist[u]};
}
for (let s=0; s<n; s++) {
  dist.fill(Infinity); position.fill(-1);
  dist[s]=0; climb[s]=0; insert(s);
  while (count) {
    const u=remove();
    if (u !== s) {
      pairs++;
      record(0,climb[u],s,u); record(1,climb[u]+z[s]-z[u],s,u);
    }
    for (const [v,len] of adj[u]) {
      const d=dist[u]+len, c=climb[u]+Math.max(0,z[v]-z[u]);
      if (d < dist[v]-1e-8) {
        dist[v]=d; climb[v]=c; parent[v]=u; insert(v);
      } else if (Math.abs(d-dist[v]) <= 1e-8 && c>climb[v]) {
        climb[v]=c; parent[v]=u;
      }
    }
  }
}
process.stdout.write(JSON.stringify({pairs,best}));
