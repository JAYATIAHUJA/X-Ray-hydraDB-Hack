import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/* ─────────────────────────────────────────────────────────────
   PixelText — renders a word as a dot-matrix (like a flip-dot
   display). Draws the text offscreen, samples it, paints dots.
   ───────────────────────────────────────────────────────────── */
export function PixelText({ text, className, dot = 5, gap = 3, color = "#1C1E21" }: { text: string; className?: string; dot?: number; gap?: number; color?: string }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let t = 0;
    const cell = dot + gap;

    // Offscreen sample of the glyphs.
    const off = document.createElement("canvas");
    const octx = off.getContext("2d")!;
    const fontPx = 120;
    octx.font = `700 ${fontPx}px "Inter Variable", Inter, system-ui, sans-serif`;
    const w = Math.ceil(octx.measureText(text).width) + 20;
    const h = fontPx + 24;
    off.width = w; off.height = h;
    octx.font = `700 ${fontPx}px "Inter Variable", Inter, system-ui, sans-serif`;
    octx.textBaseline = "middle";
    octx.fillStyle = "#000";
    octx.fillText(text, 10, h / 2 + 4);
    const cols = Math.ceil(w / cell);
    const rows = Math.ceil(h / cell);
    const img = octx.getImageData(0, 0, w, h).data;
    const grid: number[] = [];
    for (let r = 0; r < rows; r += 1) {
      for (let q = 0; q < cols; q += 1) {
        const x = Math.min(w - 1, Math.floor(q * cell + cell / 2));
        const y = Math.min(h - 1, Math.floor(r * cell + cell / 2));
        grid.push(img[(y * w + x) * 4 + 3]! > 90 ? 1 : 0);
      }
    }
    const dpr = Math.min(devicePixelRatio || 1, 2);
    c.width = cols * cell * dpr;
    c.height = rows * cell * dpr;
    c.style.width = `${cols * cell}px`;
    c.style.height = `${rows * cell}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const draw = () => {
      ctx.clearRect(0, 0, cols * cell, rows * cell);
      for (let r = 0; r < rows; r += 1) {
        for (let q = 0; q < cols; q += 1) {
          if (!grid[r * cols + q]) continue;
          const wave = Math.sin(q * 0.35 - t * 2.2 + r * 0.15);
          const rr = dot / 2 * (0.86 + 0.14 * wave);
          ctx.beginPath();
          ctx.arc(q * cell + cell / 2, r * cell + cell / 2, rr, 0, Math.PI * 2);
          ctx.fillStyle = color;
          ctx.globalAlpha = 0.82 + 0.18 * wave;
          ctx.fill();
        }
      }
      ctx.globalAlpha = 1;
      t += 0.016;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [text, dot, gap, color]);
  return <canvas className={className} ref={ref} aria-hidden="true" />;
}
/* ─────────────────────────────────────────────────────────────
   HexPattern — geometric hex lattice with a few accent-filled
   cells (Coding-Bio style). Pure SVG.
   ───────────────────────────────────────────────────────────── */
export function HexPattern({ className, accent = "#1FB8B1", accent2 = "#EA5A67" }: { className?: string; accent?: string; accent2?: string }) {
  const R = 22;
  const hexes: Array<{ x: number; y: number; fill?: string; op: number }> = [];
  const cols = 9, rows = 7;
  const seeded = (i: number) => (Math.sin(i * 12.9898) * 43758.5453) % 1;
  for (let r = 0; r < rows; r += 1) {
    for (let q = 0; q < cols; q += 1) {
      const x = q * R * 1.74 + (r % 2) * R * 0.87;
      const y = r * R * 1.5;
      const rnd = Math.abs(seeded(r * cols + q));
      // fade the lattice toward the bottom-left so it dissolves into the page
      const op = Math.max(0, 1 - (r / rows) * 0.9 - ((cols - q) / cols) * 0.35);
      const fill = rnd > 0.9 ? accent : rnd > 0.86 ? accent2 : rnd > 0.8 ? "#1C1E21" : undefined;
      hexes.push({ x, y, fill, op });
    }
  }
  const pts = (cx: number, cy: number) => Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 3) * i + Math.PI / 6;
    return `${(cx + R * Math.cos(a)).toFixed(1)},${(cy + R * Math.sin(a)).toFixed(1)}`;
  }).join(" ");
  return (
    <svg className={className} viewBox={`-30 -30 ${cols * R * 1.74 + 60} ${rows * R * 1.5 + 60}`} aria-hidden="true">
      {hexes.map((h, i) => (
        <polygon key={i} points={pts(h.x, h.y)} fill={h.fill ?? "none"} fillOpacity={h.fill ? 0.85 * h.op : 0} stroke="#1C1E21" strokeOpacity={0.35 * h.op} strokeWidth="1" />
      ))}
    </svg>
  );
}

/* ─────────────────────────────────────────────────────────────
   Mosaic — strip of coloured tiles (Unlearn style), muted palette.
   ───────────────────────────────────────────────────────────── */
export function Mosaic({ className, rows = 4, cols = 40 }: { className?: string; rows?: number; cols?: number }) {
  const palette = ["#1FB8B1", "#0A7C77", "#EA5A67", "#E8962C", "#7C6CF6", "#1C1E21", "#B4C0CD", "#F0EDE6", "#DDE4EB", "#F7D9A0"];
  const seeded = (i: number) => Math.abs((Math.sin(i * 78.233) * 43758.5453) % 1);
  return (
    <div className={className} aria-hidden="true" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
      {Array.from({ length: rows * cols }, (_, i) => {
        const r = seeded(i);
        const empty = r > 0.62;
        return <i key={i} style={{ background: empty ? "transparent" : palette[Math.floor(seeded(i + 999) * palette.length)], opacity: empty ? 0 : 0.5 + seeded(i + 7) * 0.5 }} />;
      })}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   ParticleGraph — dot field that resolves into a small org graph.
   ───────────────────────────────────────────────────────────── */
export function ParticleGraph({ className, ink = "#1C1E21" }: { className?: string; ink?: string }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let t = 0;
    // A few "people" positions; particles cluster around them, one big hub.
    const hubs = [
      { x: 0.5, y: 0.5, r: 0.16, w: 1 },
      { x: 0.2, y: 0.32, r: 0.08, w: 0.6 },
      { x: 0.8, y: 0.3, r: 0.07, w: 0.55 },
      { x: 0.25, y: 0.76, r: 0.07, w: 0.5 },
      { x: 0.78, y: 0.74, r: 0.09, w: 0.65 },
      { x: 0.55, y: 0.14, r: 0.05, w: 0.4 },
      { x: 0.5, y: 0.88, r: 0.05, w: 0.4 }
    ];
    const draw = () => {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      const w = c.clientWidth, h = c.clientHeight;
      if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      // spokes
      ctx.strokeStyle = ink; ctx.globalAlpha = 0.18; ctx.lineWidth = 1;
      for (let i = 1; i < hubs.length; i += 1) {
        ctx.beginPath(); ctx.moveTo(hubs[0]!.x * w, hubs[0]!.y * h); ctx.lineTo(hubs[i]!.x * w, hubs[i]!.y * h); ctx.stroke();
      }
      ctx.globalAlpha = 1;
      const step = 9;
      for (let y = step / 2; y < h; y += step) {
        for (let x = step / 2; x < w; x += step) {
          let d = 0;
          for (const hb of hubs) {
            const dx = x / w - hb.x, dy = y / h - hb.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < hb.r) d = Math.max(d, (1 - dist / hb.r) * hb.w);
          }
          const noise = Math.sin(x * 0.07 + t) * Math.cos(y * 0.06 - t * 0.8) * 0.18;
          d += noise;
          if (d < 0.1) continue;
          ctx.beginPath();
          ctx.arc(x, y, 0.7 + d * 2.4, 0, Math.PI * 2);
          ctx.fillStyle = ink;
          ctx.globalAlpha = Math.min(0.9, 0.12 + d * 0.8);
          ctx.fill();
        }
      }
      ctx.globalAlpha = 1;
      t += 0.01;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [ink]);
  return <canvas className={className} ref={ref} aria-hidden="true" />;
}

/* ─────────────────────────────────────────────────────────────
   Stars — twinkling starfield for the hero sky.
   ───────────────────────────────────────────────────────────── */
export function Stars({ className, count = 220 }: { className?: string; count?: number }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let t = 0;
    const seeded = (i: number) => Math.abs((Math.sin(i * 127.1 + 311.7) * 43758.5453) % 1);
    const stars = Array.from({ length: count }, (_, i) => ({
      x: seeded(i), y: seeded(i + 1000) * 0.85, r: 0.4 + seeded(i + 2000) * 1.1,
      p: seeded(i + 3000) * Math.PI * 2, s: 0.4 + seeded(i + 4000) * 1.4
    }));
    const reduce = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    const draw = () => {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      const w = c.clientWidth, h = c.clientHeight;
      if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      for (const st of stars) {
        const tw = reduce ? 0.7 : 0.45 + 0.55 * (0.5 + 0.5 * Math.sin(t * st.s + st.p));
        // fade stars near the horizon so the glow owns the bottom
        const fade = 1 - st.y / 0.9;
        ctx.beginPath();
        ctx.arc(st.x * w, st.y * h, st.r, 0, Math.PI * 2);
        ctx.fillStyle = "#DCE6FF";
        ctx.globalAlpha = tw * fade * 0.9;
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      t += 0.016;
      if (!reduce) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [count]);
  return <canvas className={className} ref={ref} aria-hidden="true" />;
}

/* ─────────────────────────────────────────────────────────────
   Clouds — soft volumetric cloud bank drifting along the bottom
   of the hero, like a night-flight view above the deck.
   ───────────────────────────────────────────────────────────── */
export function Clouds({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let t = 0;
    const seeded = (i: number) => Math.abs((Math.sin(i * 78.233 + 43.17) * 43758.5453) % 1);
    // clusters of puffs; y in [0..1] of canvas height, drifting on x
    const clouds = Array.from({ length: 14 }, (_, i) => ({
      x: seeded(i) * 1.4 - 0.2,
      y: 0.35 + seeded(i + 50) * 0.6,
      s: 90 + seeded(i + 100) * 190,
      v: 0.004 + seeded(i + 150) * 0.010,
      a: 0.05 + seeded(i + 200) * 0.10,
      puffs: Array.from({ length: 5 }, (_, k) => ({
        dx: (seeded(i * 7 + k) - 0.5) * 2.1,
        dy: (seeded(i * 11 + k) - 0.5) * 0.55,
        r: 0.45 + seeded(i * 13 + k) * 0.65
      }))
    }));
    const reduce = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    const draw = () => {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      const w = c.clientWidth, h = c.clientHeight;
      if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      for (const cl of clouds) {
        const cx = ((cl.x + t * cl.v) % 1.4 - 0.2) * w;
        const cy = cl.y * h;
        for (const p of cl.puffs) {
          const px = cx + p.dx * cl.s;
          const py = cy + p.dy * cl.s;
          const pr = p.r * cl.s;
          const g = ctx.createRadialGradient(px, py, 0, px, py, pr);
          g.addColorStop(0, `rgba(168,196,255,${cl.a})`);
          g.addColorStop(0.55, `rgba(150,180,240,${cl.a * 0.55})`);
          g.addColorStop(1, "rgba(140,170,235,0)");
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(px, py, pr, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      t += 1;
      if (!reduce) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);
  return <canvas className={className} ref={ref} aria-hidden="true" />;
}

/* ─────────────────────────────────────────────────────────────
   XRayScan — the hero metaphor. A formal org chart sits on the
   film; a radiograph scan band sweeps across it (and follows the
   pointer), revealing the REAL collaboration network underneath:
   the hidden hub, a red faultline, a phantom node.
   ───────────────────────────────────────────────────────────── */
export function XRayScan({ className }: { className?: string }) {
  const ref = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    const clip = svg.querySelector<SVGRectElement>(".scan-clip-rect");
    const bandG = svg.querySelector<SVGGElement>(".scan-g");
    if (!clip || !bandG) return;
    const W = 1200, BW = 320;
    let raf = 0, t = 0, x = (W - BW) / 2;
    let target: number | null = null;
    const reduce = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    const onMove = (e: PointerEvent) => {
      const r = svg.getBoundingClientRect();
      target = ((e.clientX - r.left) / r.width) * W - BW / 2;
    };
    const onLeave = () => { target = null; };
    svg.addEventListener("pointermove", onMove);
    svg.addEventListener("pointerleave", onLeave);
    const apply = (cx: number) => {
      clip.setAttribute("x", String(cx));
      bandG.setAttribute("transform", `translate(${cx} 0)`);
    };
    const step = () => {
      t += 0.016;
      const auto = (W - BW) / 2 + Math.sin(t * 0.45) * ((W - BW) / 2) * 0.94;
      x += ((target ?? auto) - x) * 0.07;
      apply(Math.max(0, Math.min(W - BW, x)));
      raf = requestAnimationFrame(step);
    };
    if (reduce) apply((W - BW) / 2);
    else raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      svg.removeEventListener("pointermove", onMove);
      svg.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  const CEO: [number, number] = [600, 64];
  const L1: Array<[number, number]> = [[240, 206], [480, 206], [720, 206], [960, 206]];
  const L2: Array<[number, number]> = [[120, 380], [250, 380], [380, 380], [510, 380], [640, 380], [770, 380], [900, 380], [1030, 380]];
  const L1_NAMES = ["VP Eng", "VP Product", "VP Sales", "VP Ops"];
  const L2_NAMES = ["Omar", "Kofi", "Lena", "Priya", "Jonas", "Sara", "Mei", "Dev"];
  const KIDS: Array<[number, number]> = [[0, 1], [2, 3], [4, 5], [6, 7]];
  const HUB = L2[3]!; // Priya — formal #23, structural #1
  const elbow = (p: [number, number], c: [number, number]) => {
    const my = (p[1] + c[1]) / 2 + 8;
    return `M ${p[0]} ${p[1] + 23} L ${p[0]} ${my} L ${c[0]} ${my} L ${c[0]} ${c[1] - 23}`;
  };
  const curve = (a: [number, number], b: [number, number], lift = 70) =>
    `M ${a[0]} ${a[1]} Q ${(a[0] + b[0]) / 2} ${Math.min(a[1], b[1]) - lift} ${b[0]} ${b[1]}`;
  const boxes: Array<{ p: [number, number]; name: string; sub?: string }> = [
    { p: CEO, name: "CEO" },
    ...L1.map((p, i) => ({ p, name: L1_NAMES[i]! })),
    ...L2.map((p, i) => ({ p, name: L2_NAMES[i]!, sub: i === 3 ? "#23" : undefined }))
  ];
  const hubTargets: Array<[number, number]> = [CEO, L1[0]!, L1[1]!, L1[2]!, L1[3]!, L2[0]!, L2[1]!, L2[4]!, L2[5]!, L2[6]!, L2[7]!];

  return (
    <svg ref={ref} className={className} viewBox="0 0 1200 520" role="img" aria-label="An X-ray scan sweeping across a formal org chart, revealing the real collaboration network underneath">
      <defs>
        <filter id="xr-glow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="4.5" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <clipPath id="xr-clip"><rect className="scan-clip-rect" x="440" y="0" width="320" height="520" rx="10" /></clipPath>
        <linearGradient id="xr-edge" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#67E8E0" stopOpacity="0" />
          <stop offset="0.5" stopColor="#67E8E0" stopOpacity="0.9" />
          <stop offset="1" stopColor="#67E8E0" stopOpacity="0" />
        </linearGradient>
        <radialGradient id="xr-film" cx="0.5" cy="0.45" r="0.75">
          <stop offset="0" stopColor="#07131F" />
          <stop offset="1" stopColor="#020A12" />
        </radialGradient>
      </defs>

      {/* ── formal org chart (the fiction) ── */}
      <g className="xr-formal">
        {[...L1.map((c) => elbow(CEO, c)), ...KIDS.flatMap(([a, b], i) => [elbow(L1[i]!, L2[a]!), elbow(L1[i]!, L2[b]!)])].map((d, i) => (
          <path key={i} d={d} fill="none" stroke="rgba(226,236,255,0.22)" strokeWidth="1.2" />
        ))}
        {boxes.map(({ p, name, sub }) => (
          <g key={name}>
            <rect x={p[0] - 54} y={p[1] - 23} width="108" height="46" rx="11" fill="rgba(13,22,40,0.72)" stroke="rgba(226,236,255,0.28)" strokeWidth="1" />
            <text x={p[0]} y={p[1] + (sub ? -2 : 4)} textAnchor="middle" className="xr-box-txt">{name}</text>
            {sub && <text x={p[0]} y={p[1] + 14} textAnchor="middle" className="xr-box-sub">rank {sub}</text>}
          </g>
        ))}
      </g>

      {/* ── the truth, revealed only inside the scan band ── */}
      <g clipPath="url(#xr-clip)">
        <rect x="0" y="0" width="1200" height="520" fill="url(#xr-film)" />
        {Array.from({ length: 13 }, (_, i) => (
          <line key={`v${i}`} x1={i * 100} y1="0" x2={i * 100} y2="520" stroke="rgba(103,232,224,0.05)" strokeWidth="1" />
        ))}
        {Array.from({ length: 6 }, (_, i) => (
          <line key={`h${i}`} x1="0" y1={i * 100} x2="1200" y2={i * 100} stroke="rgba(103,232,224,0.05)" strokeWidth="1" />
        ))}
        <g filter="url(#xr-glow)">
          {hubTargets.map((p, i) => (
            <path key={i} d={curve(HUB, p, 60 + (i % 3) * 26)} fill="none" stroke="#35E0D6" strokeOpacity={i < 5 ? 0.65 : 0.4} strokeWidth={i < 5 ? 2 : 1.3} />
          ))}
          {/* faultline: Kofi ↔ Mei share code, never talk */}
          <path d={curve(L2[1]!, L2[6]!, 140)} fill="none" stroke="#FF5D6C" strokeWidth="2" strokeDasharray="7 6" strokeOpacity="0.85" />
          {/* phantom: a record the chain requires but the corpus lacks */}
          <circle cx="640" cy="286" r="13" fill="none" stroke="#F5B14C" strokeWidth="2" strokeDasharray="5 5" />
          <path d={`M 640 299 L 640 357`} stroke="#F5B14C" strokeWidth="1.4" strokeDasharray="4 5" strokeOpacity="0.7" />
          {[...L1, ...L2].map((p, i) => (
            <circle key={i} cx={p[0]} cy={p[1]} r={5.5} fill="#9BF0EA" fillOpacity="0.9" />
          ))}
          <circle cx={CEO[0]} cy={CEO[1]} r="6.5" fill="#9BF0EA" fillOpacity="0.85" />
          <circle cx={HUB[0]} cy={HUB[1]} r="17" fill="#35E0D6" />
          <circle cx={HUB[0]} cy={HUB[1]} r="27" fill="none" stroke="#35E0D6" strokeOpacity="0.45" strokeWidth="1.4" />
        </g>
        <text x={HUB[0]} y={HUB[1] + 56} textAnchor="middle" className="xr-tag">PRIYA — #1 STRUCTURAL</text>
        <text x={HUB[0]} y={HUB[1] + 74} textAnchor="middle" className="xr-tag-dim">org chart says #23</text>
        <text x="640" y="264" textAnchor="middle" className="xr-tag-amber">PHANTOM</text>
        <text x={(L2[1]![0] + L2[6]![0]) / 2} y="216" textAnchor="middle" className="xr-tag-red">FAULTLINE · NO COMMS PATH</text>
      </g>

      {/* ── scan band chrome (moves with the clip) ── */}
      <g className="scan-g">
        <rect x="0" y="0" width="320" height="520" rx="10" fill="rgba(53,224,214,0.03)" />
        <rect x="0" y="0" width="2.5" height="520" fill="url(#xr-edge)" />
        <rect x="317.5" y="0" width="2.5" height="520" fill="url(#xr-edge)" />
        <text x="14" y="28" className="xr-scan-txt">● SCANNING — ACTUAL GRAPH</text>
      </g>
    </svg>
  );
}

/* Small brand-ish tiles for the floating icons around the hero. */
export function SourceTile({ kind }: { kind: "slack" | "mail" | "jira" | "git" | "confluence" | "github" }) {
  const glyph: Record<typeof kind, ReactElement> = {
    slack: <svg viewBox="0 0 24 24"><path fill="#E01E5A" d="M6 15a2 2 0 1 1-2-2h2v2Zm1 0a2 2 0 0 1 4 0v5a2 2 0 0 1-4 0v-5Z"/><path fill="#36C5F0" d="M9 6a2 2 0 1 1 2-2v2H9Zm0 1a2 2 0 0 1 0 4H4a2 2 0 0 1 0-4h5Z"/><path fill="#2EB67D" d="M18 9a2 2 0 1 1 2 2h-2V9Zm-1 0a2 2 0 0 1-4 0V4a2 2 0 0 1 4 0v5Z"/><path fill="#ECB22E" d="M15 18a2 2 0 1 1-2 2v-2h2Zm0-1a2 2 0 0 1 0-4h5a2 2 0 0 1 0 4h-5Z"/></svg>,
    mail: <svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2" fill="#fff" stroke="#1C1E21" strokeOpacity=".2"/><path d="M4 7l8 6 8-6" fill="none" stroke="#EA4335" strokeWidth="1.8"/><path d="M4 7v10M20 7v10" stroke="#4285F4" strokeWidth="1.8"/></svg>,
    jira: <svg viewBox="0 0 24 24"><path fill="#2684FF" d="M12 3 5 10a3 3 0 0 0 0 4l7 7 7-7a3 3 0 0 0 0-4l-7-7Z"/><path fill="#fff" d="m12 8-3 3 3 3 3-3-3-3Z"/></svg>,
    git: <svg viewBox="0 0 24 24"><path fill="#F05033" d="M21.6 11.1 12.9 2.4a1.3 1.3 0 0 0-1.8 0L9.3 4.2l2.3 2.3a1.5 1.5 0 0 1 1.9 1.9l2.2 2.2a1.5 1.5 0 1 1-.9.9l-2-2v5.4a1.5 1.5 0 1 1-1.3 0V9.4a1.5 1.5 0 0 1-.8-2L8.4 5.1l-6 6a1.3 1.3 0 0 0 0 1.8l8.7 8.7a1.3 1.3 0 0 0 1.8 0l8.7-8.7a1.3 1.3 0 0 0 0-1.8Z"/></svg>,
    confluence: <svg viewBox="0 0 24 24"><path fill="#1868DB" d="M3 17c3-5 6-6 10-4l4 2 3-5c-4-2-9-4-13 1-1 1-3 4-4 6Z"/><path fill="#1868DB" opacity=".55" d="M21 7c-3 5-6 6-10 4L7 9l-3 5c4 2 9 4 13-1 1-1 3-4 4-6Z"/></svg>,
    github: <svg viewBox="0 0 24 24"><path fill="#1C1E21" d="M12 2a10 10 0 0 0-3.2 19.5c.5.1.7-.2.7-.5v-1.8c-2.8.6-3.4-1.2-3.4-1.2-.4-1.1-1.1-1.4-1.1-1.4-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.6 2.4 1.1 3 .9.1-.7.4-1.1.6-1.4-2.2-.2-4.6-1.1-4.6-5a3.9 3.9 0 0 1 1-2.7c-.1-.3-.4-1.3.1-2.7 0 0 .9-.3 2.8 1a9.5 9.5 0 0 1 5 0c1.9-1.3 2.8-1 2.8-1 .5 1.4.2 2.4.1 2.7a3.9 3.9 0 0 1 1 2.7c0 3.9-2.4 4.8-4.6 5 .4.3.7.9.7 1.9v2.8c0 .3.2.6.7.5A10 10 0 0 0 12 2Z"/></svg>
  };
  return <span className={`tile tile-${kind}`}>{glyph[kind]}</span>;
}

