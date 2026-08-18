import { useEffect, useRef, useState } from "react";

export type Graph3DNode = {
  key: string;
  label: string;
  size: number;
  excluded?: boolean;
  /** true = this node carries a finding; drawn bright and always labelled. Others recede. */
  focus?: boolean;
  /** Which finding this node belongs to — drives its colour. */
  role?: "ghost" | "faultline" | "gap" | "none";
};

// One hue per finding so the eye can separate them at a glance.
const PALETTE = {
  ghost: ["#8FEDE6", "#1FB8B1", "#0A7C77"],
  faultline: ["#FFB3B9", "#EA5A67", "#B72A38"],
  gap: ["#FFD9A6", "#E8962C", "#A85F0A"],
  none: ["#DDE4EB", "#B4C0CD", "#8E9CAB"],
  selected: ["#D9D2FF", "#7C6CF6", "#4B3AC9"]
} as const;

export type Graph3DEdge = {
  source: string;
  target: string;
  kind: "weak" | "medium" | "strong" | "faultline";
};

type Body = {
  key: string;
  label: string;
  r: number;
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  excluded: boolean;
  focus: boolean;
  role: keyof typeof PALETTE;
  // filled per frame
  sx: number;
  sy: number;
  sr: number;
  depth: number;
};

function withAlpha(hex: string, alpha: number) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

const MAX_NODES = 220;
const FOCAL = 900;

/**
 * Dependency-free 3D force graph. Nodes are laid out in 3D with a short
 * force simulation, then perspective-projected onto a 2D canvas and painted
 * back-to-front. Drag rotates, wheel zooms, click selects.
 */
export function Graph3D({
  nodes,
  edges,
  selectedKey,
  onSelect,
  spin = true
}: {
  nodes: Graph3DNode[];
  edges: Graph3DEdge[];
  selectedKey?: string;
  onSelect: (key: string) => void;
  spin?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const bodiesRef = useRef<Body[]>([]);
  const linksRef = useRef<Array<{ a: Body; b: Body; kind: Graph3DEdge["kind"] }>>([]);
  const camRef = useRef({ rotX: -0.22, rotY: 0.4, zoom: 1, autoSpin: spin });
  const dragRef = useRef<{ active: boolean; x: number; y: number; moved: boolean }>({
    active: false,
    x: 0,
    y: 0,
    moved: false
  });
  const hoverRef = useRef<string | undefined>(undefined);
  const selectedRef = useRef<string | undefined>(selectedKey);
  const [hovered, setHovered] = useState<string | undefined>(undefined);

  selectedRef.current = selectedKey;

  // ── Layout: run a short 3D force simulation whenever the graph changes ──
  useEffect(() => {
    const visible = [...nodes].sort((a, b) => b.size - a.size).slice(0, MAX_NODES);
    const n = visible.length;
    if (n === 0) {
      bodiesRef.current = [];
      linksRef.current = [];
      return;
    }

    const spread = 130 + Math.sqrt(n) * 30;
    const golden = Math.PI * (3 - Math.sqrt(5));
    const bodies: Body[] = visible.map((node, i) => {
      // Fibonacci sphere seeding — avoids the clumped start a random seed gives.
      const t = n === 1 ? 0 : i / (n - 1);
      const inclination = Math.acos(1 - 2 * t);
      const azimuth = golden * i;
      const radius = spread * (0.45 + 0.55 * Math.cbrt(t));
      return {
        key: node.key,
        label: node.label,
        r: Math.max(5, node.size * 0.42),
        x: radius * Math.sin(inclination) * Math.cos(azimuth),
        y: radius * Math.sin(inclination) * Math.sin(azimuth),
        z: radius * Math.cos(inclination),
        vx: 0,
        vy: 0,
        vz: 0,
        excluded: node.excluded === true,
        focus: node.focus !== false,
        role: node.role ?? "none",
        sx: 0,
        sy: 0,
        sr: 0,
        depth: 0
      };
    });

    const index = new Map(bodies.map((body) => [body.key, body]));
    const links = edges
      .map((edge) => ({ a: index.get(edge.source), b: index.get(edge.target), kind: edge.kind }))
      .filter((link): link is { a: Body; b: Body; kind: Graph3DEdge["kind"] } => link.a !== undefined && link.b !== undefined);

    const iterations = n > 160 ? 140 : n > 80 ? 220 : 320;
    const repulsion = 900 + n * 18;
    const springLength = spread * 0.34;

    for (let step = 0; step < iterations; step += 1) {
      const cooling = 1 - step / iterations;

      for (let i = 0; i < n; i += 1) {
        const a = bodies[i]!;
        for (let j = i + 1; j < n; j += 1) {
          const b = bodies[j]!;
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          let dz = a.z - b.z;
          let distSq = dx * dx + dy * dy + dz * dz;
          if (distSq < 1) {
            dx = (i % 3) - 1 || 0.7;
            dy = (j % 3) - 1 || 0.7;
            dz = ((i + j) % 3) - 1 || 0.7;
            distSq = 3;
          }
          const dist = Math.sqrt(distSq);
          const force = repulsion / distSq;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          const fz = (dz / dist) * force;
          a.vx += fx;
          a.vy += fy;
          a.vz += fz;
          b.vx -= fx;
          b.vy -= fy;
          b.vz -= fz;
        }
      }

      for (const link of links) {
        const dx = link.b.x - link.a.x;
        const dy = link.b.y - link.a.y;
        const dz = link.b.z - link.a.z;
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
        const force = (dist - springLength) * 0.045;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        const fz = (dz / dist) * force;
        link.a.vx += fx;
        link.a.vy += fy;
        link.a.vz += fz;
        link.b.vx -= fx;
        link.b.vy -= fy;
        link.b.vz -= fz;
      }

      for (const body of bodies) {
        body.vx -= body.x * 0.012;
        body.vy -= body.y * 0.012;
        body.vz -= body.z * 0.012;
        const damping = 0.82 * cooling + 0.1;
        body.vx *= damping;
        body.vy *= damping;
        body.vz *= damping;
        body.x += Math.max(-40, Math.min(40, body.vx));
        body.y += Math.max(-40, Math.min(40, body.vy));
        body.z += Math.max(-40, Math.min(40, body.vz));
      }
    }

    bodiesRef.current = bodies;
    linksRef.current = links;
  }, [nodes, edges]);

  // ── Render loop ──
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    const context = canvas.getContext("2d");
    if (context === null) {
      return;
    }
    const reduceMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    let frame = 0;

    function draw() {
      const cam = camRef.current;
      const bodies = bodiesRef.current;
      const links = linksRef.current;
      const dpr = Math.min(globalThis.devicePixelRatio || 1, 2);
      const width = canvas!.clientWidth;
      const height = canvas!.clientHeight;
      if (canvas!.width !== width * dpr || canvas!.height !== height * dpr) {
        canvas!.width = width * dpr;
        canvas!.height = height * dpr;
      }
      context!.setTransform(dpr, 0, 0, dpr, 0, 0);
      context!.clearRect(0, 0, width, height);

      if (cam.autoSpin && !dragRef.current.active && !reduceMotion) {
        cam.rotY += 0.0016;
      }

      const cx = width / 2;
      const cy = height / 2;
      const cosY = Math.cos(cam.rotY);
      const sinY = Math.sin(cam.rotY);
      const cosX = Math.cos(cam.rotX);
      const sinX = Math.sin(cam.rotX);
      const fit = Math.min(width, height) / 620;
      const zoom = cam.zoom * fit;

      for (const body of bodies) {
        const x1 = body.x * cosY - body.z * sinY;
        const z1 = body.x * sinY + body.z * cosY;
        const y1 = body.y * cosX - z1 * sinX;
        const z2 = body.y * sinX + z1 * cosX;
        const perspective = FOCAL / (FOCAL + z2 + 260);
        body.sx = cx + x1 * perspective * zoom;
        body.sy = cy + y1 * perspective * zoom;
        body.sr = Math.max(2.4, body.r * perspective * zoom);
        body.depth = z2;
      }

      const hover = hoverRef.current;
      const selected = selectedRef.current;

      // Edges, far to near.
      const sortedLinks = [...links].sort((p, q) => (p.a.depth + p.b.depth) / 2 - (q.a.depth + q.b.depth) / 2);
      for (const link of sortedLinks) {
        const near = link.a.key === hover || link.b.key === hover || link.a.key === selected || link.b.key === selected;
        const mid = (link.a.depth + link.b.depth) / 2;
        const quiet = !link.a.focus && !link.b.focus && link.kind !== "faultline";
        const fade = Math.max(0.12, Math.min(1, 1 - (mid + 320) / 900)) * (quiet ? 0.45 : 1);
        context!.beginPath();
        context!.moveTo(link.a.sx, link.a.sy);
        context!.lineTo(link.b.sx, link.b.sy);
        if (link.kind === "faultline") {
          context!.setLineDash([5, 5]);
          context!.strokeStyle = `rgba(224, 64, 79, ${(near ? 0.95 : 0.62) * fade + 0.18})`;
          context!.lineWidth = near ? 2.4 : 1.7;
        } else {
          context!.setLineDash([]);
          const alpha = (link.kind === "strong" ? 0.4 : link.kind === "medium" ? 0.24 : 0.15) * fade;
          const touchesSelected = link.a.key === selected || link.b.key === selected;
          context!.strokeStyle = near
            ? touchesSelected
              ? `rgba(124, 108, 246, ${Math.min(0.9, alpha + 0.55)})`
              : `rgba(21, 32, 46, ${Math.min(0.7, alpha + 0.4)})`
            : `rgba(96, 125, 148, ${alpha})`;
          context!.lineWidth = near ? 1.8 : 1;
        }
        context!.stroke();
      }
      context!.setLineDash([]);

      // Nodes, far to near — painter's algorithm gives the depth cue.
      const sortedBodies = [...bodies].sort((p, q) => q.depth - p.depth);
      for (const body of sortedBodies) {
        const isSelected = body.key === selected;
        const isHovered = body.key === hover;
        const quiet = !body.focus && !isSelected && !isHovered;
        const fade = Math.max(0.32, Math.min(1, 1 - (body.depth + 320) / 1000)) * (quiet ? 0.55 : 1);

        if (isSelected || isHovered) {
          context!.beginPath();
          context!.arc(body.sx, body.sy, body.sr + (isSelected ? 10 : 6), 0, Math.PI * 2);
          context!.fillStyle = isSelected ? "rgba(124, 108, 246, 0.18)" : "rgba(21, 32, 46, 0.08)";
          context!.fill();
          if (isSelected) {
            context!.beginPath();
            context!.arc(body.sx, body.sy, body.sr + 5, 0, Math.PI * 2);
            context!.strokeStyle = "rgba(124, 108, 246, 0.9)";
            context!.lineWidth = 1.5;
            context!.stroke();
          }
        }

        const gradient = context!.createRadialGradient(
          body.sx - body.sr * 0.36,
          body.sy - body.sr * 0.42,
          body.sr * 0.12,
          body.sx,
          body.sy,
          body.sr
        );
        const swatch = body.excluded
          ? PALETTE.none
          : isSelected
            ? PALETTE.selected
            : quiet
              ? PALETTE.none
              : PALETTE[body.role];
        gradient.addColorStop(0, withAlpha(swatch[0], isSelected ? 1 : fade));
        gradient.addColorStop(0.55, withAlpha(swatch[1], isSelected ? 1 : fade));
        gradient.addColorStop(1, withAlpha(swatch[2], isSelected ? 1 : fade));

        context!.beginPath();
        context!.arc(body.sx, body.sy, body.sr, 0, Math.PI * 2);
        context!.fillStyle = gradient;
        context!.fill();
        context!.lineWidth = isSelected ? 2 : 1;
        context!.strokeStyle = body.excluded
          ? `rgba(217, 119, 6, ${fade})`
          : `rgba(255, 255, 255, ${(quiet ? 0.3 : 0.55) * fade + 0.2})`;
        context!.stroke();

        if (!quiet) {
          // Specular highlight sells the sphere — only on nodes that matter.
          context!.beginPath();
          context!.arc(body.sx - body.sr * 0.32, body.sy - body.sr * 0.36, body.sr * 0.26, 0, Math.PI * 2);
          context!.fillStyle = `rgba(255, 255, 255, ${0.35 * fade})`;
          context!.fill();
        }
      }

      // Labels only where they carry meaning — big nodes, hover, selection.
      const labelled = sortedBodies.filter(
        (body) => (body.focus && body.sr > 4) || body.key === hover || body.key === selected
      );
      context!.font = "600 11px Inter, system-ui, sans-serif";
      context!.textAlign = "center";
      context!.textBaseline = "top";
      for (const body of labelled) {
        const emphasised = body.key === hover || body.key === selected;
        const text = body.label;
        const metrics = context!.measureText(text);
        const padX = 6;
        const boxW = metrics.width + padX * 2;
        const top = body.sy + body.sr + 7;
        const labelBg =
          body.key === selected
            ? "rgba(124, 108, 246, 0.96)"
            : body.key === hover
              ? "rgba(21, 32, 46, 0.92)"
              : "rgba(255, 255, 255, 0.88)";
        context!.fillStyle = labelBg;
        context!.beginPath();
        context!.roundRect(body.sx - boxW / 2, top, boxW, 17, 8);
        context!.fill();
        if (!emphasised) {
          context!.strokeStyle = "rgba(203, 213, 224, 0.9)";
          context!.lineWidth = 1;
          context!.stroke();
        }
        context!.fillStyle = emphasised ? "#FFFFFF" : PALETTE[body.role][2];
        context!.fillText(text, body.sx, top + 3);
      }

      frame = globalThis.requestAnimationFrame(draw);
    }

    frame = globalThis.requestAnimationFrame(draw);
    return () => globalThis.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    camRef.current.autoSpin = spin;
  }, [spin]);

  function bodyAt(clientX: number, clientY: number) {
    const canvas = canvasRef.current;
    if (canvas === null) return undefined;
    const rect = canvas.getBoundingClientRect();
    const px = clientX - rect.left;
    const py = clientY - rect.top;
    let best: Body | undefined;
    let bestDepth = Infinity;
    for (const body of bodiesRef.current) {
      const dx = px - body.sx;
      const dy = py - body.sy;
      const hit = Math.max(body.sr, 9);
      if (dx * dx + dy * dy <= hit * hit && body.depth < bestDepth) {
        best = body;
        bestDepth = body.depth;
      }
    }
    return best;
  }

  return (
    <div className="graph3d">
      <canvas
        ref={canvasRef}
        className={hovered === undefined ? "graph3d-canvas" : "graph3d-canvas is-pointing"}
        onPointerDown={(event) => {
          dragRef.current = { active: true, x: event.clientX, y: event.clientY, moved: false };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const drag = dragRef.current;
          if (drag.active) {
            const dx = event.clientX - drag.x;
            const dy = event.clientY - drag.y;
            if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
            camRef.current.rotY += dx * 0.006;
            camRef.current.rotX = Math.max(-1.2, Math.min(1.2, camRef.current.rotX + dy * 0.006));
            drag.x = event.clientX;
            drag.y = event.clientY;
            return;
          }
          const body = bodyAt(event.clientX, event.clientY);
          if (body?.key !== hoverRef.current) {
            hoverRef.current = body?.key;
            setHovered(body?.key);
          }
        }}
        onPointerUp={(event) => {
          const drag = dragRef.current;
          dragRef.current = { active: false, x: 0, y: 0, moved: false };
          if (drag.moved) return;
          const body = bodyAt(event.clientX, event.clientY);
          if (body !== undefined) onSelect(body.key);
        }}
        onPointerLeave={() => {
          dragRef.current = { active: false, x: 0, y: 0, moved: false };
          hoverRef.current = undefined;
          setHovered(undefined);
        }}
        onWheel={(event) => {
          const next = camRef.current.zoom * (event.deltaY > 0 ? 0.92 : 1.08);
          camRef.current.zoom = Math.max(0.45, Math.min(3.2, next));
        }}
      />
      <div className="graph3d-hint">Drag to rotate · scroll to zoom · click a node</div>
    </div>
  );
}
