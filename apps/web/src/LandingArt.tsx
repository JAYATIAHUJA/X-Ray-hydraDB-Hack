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
    octx.font = `700 ${fontPx}px Inter, system-ui, sans-serif`;
    const w = Math.ceil(octx.measureText(text).width) + 20;
    const h = fontPx + 24;
    off.width = w; off.height = h;
    octx.font = `700 ${fontPx}px Inter, system-ui, sans-serif`;
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
