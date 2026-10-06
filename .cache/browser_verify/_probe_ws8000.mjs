// 装置自检：只测「8000 的 /ws 能不能握手、能吐出什么帧」。不预设它能通。
const url = process.argv[2] || 'ws://127.0.0.1:8000/ws';
console.log('probe target:', url);
let ws;
try { ws = new WebSocket(url); } catch (e) { console.log('CONSTRUCT_FAIL', e.message); process.exit(2); }
const t = setTimeout(() => { console.log('TIMEOUT_NO_OPEN'); try{ws.close()}catch{}; process.exit(3); }, 6000);
let n = 0;
ws.onopen = () => console.log('OPEN');
ws.onmessage = (ev) => {
  n++;
  const s = typeof ev.data === 'string' ? ev.data : `<binary ${ev.data?.byteLength ?? '?'}B>`;
  console.log(`MSG#${n} len=${s.length} head=${s.slice(0, 240)}`);
  if (n >= 3) { clearTimeout(t); try{ws.close()}catch{}; process.exit(0); }
};
ws.onerror = (e) => { console.log('ERROR', e.message || '(no detail)'); };
ws.onclose = (e) => { console.log(`CLOSE code=${e.code} wasClean=${e.wasClean} msgs=${n}`); clearTimeout(t); process.exit(n > 0 ? 0 : 4); };
