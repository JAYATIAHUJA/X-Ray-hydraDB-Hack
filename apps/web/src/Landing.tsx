import { useQuery } from "@tanstack/react-query";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useEffect, useMemo, useRef, useState } from "react";
import { getCurrentSnapshot, getHealth } from "./api";
import { Graph3D } from "./Graph3D";
import type { Graph3DEdge, Graph3DNode } from "./Graph3D";
import { HexPattern, Mosaic, ParticleGraph, PixelText, SourceTile } from "./LandingArt";

gsap.registerPlugin(ScrollTrigger);

function demoGraph(): { nodes: Graph3DNode[]; edges: Graph3DEdge[] } {
  const names = ["Priya","Marcus","Aditi","Tomás","Lena","Kofi","Sara","Ravi","Ines","Jonas","Mei","Omar","Nadia","Felix","Yara","Dev","Hana","Ilya","Zoe","Arjun","Noor","Luca","Emi","Theo","Aya","Ben","Kai","Mila","Sam","Uma"];
  const nodes: Graph3DNode[] = names.map((n, i) => ({
    key: `p${i}`, label: n,
    size: i === 0 ? 62 : i < 4 ? 30 : 16 + ((i * 7) % 9),
    focus: i === 0 || i === 5 || i === 9,
    role: i === 0 ? "ghost" : i === 5 || i === 9 ? "faultline" : "none"
  }));
  const edges: Graph3DEdge[] = [];
  for (let i = 1; i < names.length; i += 1) {
    edges.push({ source: "p0", target: `p${i}`, kind: i % 3 === 0 ? "strong" : "medium" });
    if (i % 4 === 0) edges.push({ source: `p${i}`, target: `p${(i * 3) % names.length || 1}`, kind: "weak" });
  }
  edges.push({ source: "p5", target: "p9", kind: "faultline" });
  return { nodes, edges };
}

export function Landing() {
  const snapshot = useQuery({ queryKey: ["landing-snapshot"], queryFn: getCurrentSnapshot });
  const health = useQuery({ queryKey: ["landing-health"], queryFn: getHealth });
  const data = snapshot.data;
  const root = useRef<HTMLElement | null>(null);
  const [selected, setSelected] = useState<string | undefined>("p0");
  const demo = useMemo(demoGraph, []);

  useEffect(() => {
    const reduce = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    if (reduce || root.current === null) return;

    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: "power4.out" } });
      tl.from(".h-pill", { y: 12, opacity: 0, duration: 0.7 }, 0.05)
        .from(".pixel-word", { y: 24, opacity: 0, duration: 1.1, stagger: 0.12 }, 0.2)
        .from(".h-line", { y: 18, opacity: 0, duration: 0.9, stagger: 0.08 }, 0.7)
        .from(".float", { scale: 0.6, opacity: 0, duration: 0.9, stagger: 0.06, ease: "back.out(1.7)" }, 0.5)
        .from(".h-cta > *", { y: 14, opacity: 0, duration: 0.7, stagger: 0.08 }, 1.1);

      // floating tiles bob independently
      gsap.utils.toArray<HTMLElement>(".float").forEach((el, i) => {
        gsap.to(el, { y: `+=${10 + (i % 3) * 5}`, rotation: (i % 2 ? 1 : -1) * (3 + (i % 4)), duration: 3.2 + (i % 5) * 0.4, ease: "sine.inOut", yoyo: true, repeat: -1, delay: i * 0.2 });
      });
      // hero parallax
      gsap.to(".hero-art", { yPercent: 8, ease: "none", scrollTrigger: { trigger: ".lp-hero", start: "top top", end: "bottom top", scrub: true } });

      // product window: tilt → flat
      gsap.fromTo(".window", { rotateX: 16, y: 70, opacity: 0.5 }, { rotateX: 0, y: 0, opacity: 1, ease: "none", scrollTrigger: { trigger: ".window-wrap", start: "top 92%", end: "top 30%", scrub: 0.6 } });

      // reveals
      gsap.utils.toArray<HTMLElement>(".rv").forEach((el) => {
        gsap.from(el, { y: 26, opacity: 0, duration: 0.95, ease: "power3.out", scrollTrigger: { trigger: el, start: "top 88%" } });
      });
      // connector lines
      gsap.utils.toArray<SVGPathElement>(".conn path").forEach((p) => {
        const len = p.getTotalLength();
        gsap.set(p, { strokeDasharray: len, strokeDashoffset: len });
        gsap.to(p, { strokeDashoffset: 0, ease: "none", scrollTrigger: { trigger: p, start: "top 85%", end: "bottom 40%", scrub: true } });
      });
      // counters
      gsap.utils.toArray<HTMLElement>("[data-count]").forEach((el) => {
        const end = Number(el.dataset.count ?? 0); const o = { v: 0 };
        gsap.to(o, { v: end, duration: 1.5, ease: "power2.out", scrollTrigger: { trigger: el, start: "top 88%", once: true }, onUpdate: () => { el.textContent = Math.round(o.v).toLocaleString(); } });
      });
      // typewriter
      const code = document.querySelector<HTMLElement>(".q-code code");
      if (code) {
        const full = code.textContent ?? ""; code.textContent = "";
        gsap.to({ n: 0 }, { n: full.length, duration: 2, ease: "none", scrollTrigger: { trigger: ".q-code", start: "top 75%", once: true }, onUpdate() { code.textContent = full.slice(0, Math.round(this.targets()[0].n)); } });
      }
      // dark section: dots drift
      gsap.to(".dark-art", { yPercent: -10, ease: "none", scrollTrigger: { trigger: ".dark", start: "top bottom", end: "bottom top", scrub: true } });
    }, root);

    const magnets = Array.from(document.querySelectorAll<HTMLElement>(".magnet"));
    const hs = magnets.map((el) => {
      const move = (e: PointerEvent) => { const r = el.getBoundingClientRect(); gsap.to(el, { x: (e.clientX - r.left - r.width / 2) * 0.2, y: (e.clientY - r.top - r.height / 2) * 0.2, duration: 0.4, ease: "power3.out" }); };
      const leave = () => gsap.to(el, { x: 0, y: 0, duration: 0.7, ease: "elastic.out(1, 0.45)" });
      el.addEventListener("pointermove", move); el.addEventListener("pointerleave", leave);
      return { el, move, leave };
    });
    return () => { ctx.revert(); hs.forEach(({ el, move, leave }) => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerleave", leave); }); };
  }, []);

  return (
    <main className="lp" ref={root}>
      {/* ── NAV ── */}
      <header className="lp-nav">
        <a className="lp-brand" href="/"><i />X-Ray</a>
        <nav>
          <a href="#lenses">Lenses</a>
          <a href="#engine">Engine</a>
          <a href="#data">Data</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className="lp-nav-r">
          <a href="/app">Log in</a>
          <a className="btn-dark magnet" href="/app">Open X-Ray</a>
        </div>
      </header>

      {/* ── HERO ── */}
      <section className="lp-hero">
        <HexPattern className="hex hex-tr" />
        <div className="hero-art" aria-hidden="true">
          <span className="float f1"><SourceTile kind="slack" /></span>
          <span className="float f2"><SourceTile kind="mail" /></span>
          <span className="float f3"><SourceTile kind="jira" /></span>
          <span className="float f4"><SourceTile kind="git" /></span>
          <span className="float f5"><SourceTile kind="confluence" /></span>
          <span className="float f6"><SourceTile kind="github" /></span>
        </div>

        <span className="h-pill">✦ &nbsp;HackHydra 2026 · Track 01 · built on HydraDB</span>

        <div className="pixel-title" aria-label="See. Trace. Prevent.">
          <PixelText className="pixel-word" text="SEE." dot={5} gap={3} />
          <PixelText className="pixel-word" text="TRACE." dot={5} gap={3} />
          <PixelText className="pixel-word" text="PREVENT." dot={5} gap={3} />
        </div>

        <h1 className="h-headline">
          <span className="h-line"><em>Your org chart</em> is fiction.</span>
          <span className="h-line">X-Ray shows who <mark>actually</mark> holds it together.</span>
        </h1>
        <p className="h-lede h-line">
          Two graphs from your own exports — the human one and the work one — and the exact places they disagree.
          Self-hosted. Evidence-backed. One HydraDB call, not forty thousand.
        </p>
        <div className="h-cta">
          <a className="btn-dark lg magnet" href="/app">Open X-Ray</a>
          <a className="btn-plain lg" href="#lenses">See how it works ↓</a>
        </div>
      </section>

      {/* ── PRODUCT WINDOW ── */}
      <section className="window-wrap">
        <div className="window">
          <div className="window-bar">
            <span /><span /><span />
            <em>x-ray · demo-org · Actual</em>
            <b>live</b>
          </div>
          <div className="window-body">
            <div className="window-graph">
              <Graph3D nodes={demo.nodes} edges={demo.edges} onSelect={setSelected} selectedKey={selected} spin />
            </div>
            <aside className="window-side">
              <div className="ws-kpi"><span>Load-bearing</span><strong>Priya</strong><small>#1 structural · #23 formal</small></div>
              <div className="ws-kpi"><span>Faultlines</span><strong>7</strong><small>uncoordinated dependencies</small></div>
              <div className="ws-kpi"><span>Gaps</span><strong>12</strong><small>missing records</small></div>
              <ol className="ws-rank">
                {[["Priya", 100, "+22"], ["Kofi", 62, "+9"], ["Jonas", 55, "+4"], ["Marcus", 41, "-2"]].map(([n, w, g]) => (
                  <li key={n as string}><span>{n}</span><i><b style={{ width: `${w}%` }} /></i><em className={String(g).startsWith("+") ? "pos" : ""}>{g}</em></li>
                ))}
              </ol>
            </aside>
          </div>
        </div>
      </section>

      {/* ── LOGO / TRUST STRIP ── */}
      <div className="trust rv">
        <span>Reads exports from</span>
        <ul>
          <li><SourceTile kind="slack" /> Slack</li>
          <li><SourceTile kind="mail" /> Email</li>
          <li><SourceTile kind="jira" /> JIRA</li>
          <li><SourceTile kind="confluence" /> Confluence</li>
          <li><SourceTile kind="github" /> GitHub</li>
          <li><SourceTile kind="git" /> git</li>
        </ul>
      </div>

      {/* ── PROOF CARDS ── */}
      <section className="proof">
        <div className="proof-card rv">
          <span className="eyebrow">Apache Kafka · Mar–Jun 2025</span>
          <strong className="dot"><span data-count="516">0</span></strong>
          <p>coordination paths disappear if the #1 person leaves</p>
        </div>
        <div className="proof-card rv">
          <span className="eyebrow">Same corpus</span>
          <strong className="dot"><span data-count="49">0</span></strong>
          <p>module pairs that co-change with owners who never talk</p>
        </div>
        <div className="proof-card rv proof-cta">
          <p>Runs entirely on your machine, against your own exports. <em>Nothing leaves.</em></p>
          <a className="btn-dark magnet" href="/app">Load your exports</a>
        </div>
      </section>

      {/* ── DARK: INTRODUCING THREE LENSES ── */}
      <section className="dark" id="lenses">
        <ParticleGraph className="dark-art" ink="#F4F2ED" />
        <div className="dark-copy">
          <span className="eyebrow light">Introducing</span>
          <h2>Three lenses.<br /><em>Three questions</em> an org chart can&apos;t answer.</h2>
          <p>Every finding carries its evidence IDs, a confidence score, the exact HydraDB query that produced it, and one recommended action. Nothing is a vibe.</p>
          <a className="btn-light magnet" href="/app">Explore in the app →</a>
        </div>
      </section>

      {/* ── LENSES DETAIL ── */}
      <section className="lenses">
        <article className="lens rv">
          <svg className="conn" viewBox="0 0 400 220" preserveAspectRatio="none"><path d="M6 6 V 150 Q 6 190 46 190 H 394" /></svg>
          <span className="eyebrow">01 · Structural rank</span>
          <h3>Who <em>quietly</em> holds it together?</h3>
          <p>Rank people by how many bounded shortest paths route through them, then compare with their title. The person at #1 is rarely the one on top of the chart.</p>
          <div className="lens-fig fig-ghost"><i /><i /><i /><i /><i /><i /><i /><b /></div>
        </article>
        <article className="lens rv">
          <svg className="conn" viewBox="0 0 400 220" preserveAspectRatio="none"><path d="M6 6 V 150 Q 6 190 46 190 H 394" /></svg>
          <span className="eyebrow">02 · Faultlines</span>
          <h3>Where does code depend but <em>people don&apos;t talk?</em></h3>
          <p>Modules that co-change constantly whose owners have no communication path within four hops. Each ships with the shortest introduction that would fix it.</p>
          <div className="lens-fig fig-fault"><i /><s /><i /></div>
        </article>
        <article className="lens rv">
          <svg className="conn" viewBox="0 0 400 220" preserveAspectRatio="none"><path d="M6 6 V 150 Q 6 190 46 190 H 394" /></svg>
          <span className="eyebrow">03 · Gaps</span>
          <h3>Where is a record the chain <em>requires</em> — but isn&apos;t there?</h3>
          <p>A reply whose parent is missing. A step absent from a sequence. X-Ray marks a Phantom node and traces the chain through it. Absence isn&apos;t proof of deletion; it&apos;s a precise question.</p>
          <div className="lens-fig fig-gap"><i /><i /><u /><i /><i /></div>
        </article>
      </section>

      {/* ── ENGINE ── */}
      <section className="engine" id="engine">
        <HexPattern className="hex hex-bl" accent="#7C6CF6" accent2="#1FB8B1" />
        <div className="engine-l">
          <span className="eyebrow rv">Why a graph engine</span>
          <h2 className="rv">The signal is an edge that exists in one graph <em>and not the other.</em></h2>
          <p className="rv">A vector index has one embedding space and no notion of “present here, absent there.” X-Ray asks HydraDB for bounded pairwise traversal — every person against every person — in one server-side call, and compares client-side.</p>
          <div className="engine-stat rv">
            <div><strong data-count="42486">0</strong><span>per-pair queries</span></div>
            <i>→</i>
            <div><strong>1</strong><span>round trip</span></div>
          </div>
        </div>
        <pre className="q-code rv"><code>{`CALL algo.MSpaths({
  sourceLabel: 'Person', sourceValues: $people,
  targetLabel: 'Person', targetValues: $people,
  relTypes: ['COMMUNICATES'], relDirection: 'BOTH',
  maxLen: 4, pairwise: true
}) YIELD path
RETURN collect(path)`}</code></pre>
      </section>

      {/* ── DATA ── */}
      <section className="datasets" id="data">
        <div className="ds-head rv">
          <h2>Runs on <em>your</em> exports.<br />Ships with four corpora.</h2>
          <p>Every adapter is deterministic — explicit IDs only, no NLP guessing. What you load is what you get.</p>
        </div>
        <div className="ds-grid">
          <div className="ds rv"><span>demo</span><strong>xray-demo</strong><p>10-person synthetic org, planted findings, no external service.</p></div>
          <div className="ds rv"><span>synthetic · labelled</span><strong>synth-500</strong><p>Faultline & gap precision/recall 1.0 · ghost top-10 overlap 0.93 vs exact betweenness.</p></div>
          <div className="ds rv"><span>real · public</span><strong>kafka-2025q2</strong><p>Apache Kafka git log + dev list, through the same adapters you&apos;d use on your own data.</p></div>
          <div className="ds rv"><span>official · track 01</span><strong>herb-2026</strong><p>Salesforce HERB, all 30 products — 5,126 people, 92k edges. Ghost #1 is a Software Engineer ranked #282 on paper.</p></div>
        </div>
        <div className="ds-live rv">
          <div><strong>{data ? data.node_count.toLocaleString() : "—"}</strong><span>nodes live</span></div>
          <div><strong>{data ? data.edge_count.toLocaleString() : "—"}</strong><span>typed edges</span></div>
          <div><strong>{data ? data.evidence_count.toLocaleString() : "—"}</strong><span>evidence records</span></div>
          <div><strong className="mono">{health.data?.hydra.status ?? "—"}</strong><span>HydraDB</span></div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className="faq" id="faq">
        <h2 className="rv">Questions people <em>actually</em> ask.</h2>
        <div className="faq-grid">
          {[
            ["Where is my data processed?", "Imports are disabled on the hosted demo. In an explicitly enabled self-hosted deployment, exports are sent only to the API you operate and the resulting graph stays in that deployment."],
            ["Is “absence” proof someone deleted something?", "No, and we never say that. A Phantom node means the graph structurally requires a record the corpus doesn't contain. It's a precise question, not an accusation."],
            ["Why not a vector database?", "The finding is an edge present in one graph and absent in another. Embedding similarity has no notion of that. Bounded typed traversal does."],
            ["How is structural rank computed?", "Exact NetworkX betweenness below 2,000 people; larger graphs disclose bounded Brandes or HydraDB MSpaths. The metric is standard—the evidence-backed comparison with formal rank and removal impact is the product."]
          ].map(([q, a]) => (
            <details className="rv" key={q}><summary>{q}</summary><p>{a}</p></details>
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="lp-cta">
        <Mosaic className="mosaic" />
        <h2 className="rv">See who actually holds<br /><em>your</em> org together.</h2>
        <div className="rv cta-row">
          <a className="btn-dark lg magnet" href="/app">Open X-Ray</a>
          <a className="btn-plain lg" href="/app">Load your exports</a>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="lp-foot">
        <div className="foot-grid">
          <div className="foot-brand">
            <a className="lp-brand" href="/"><i />X-Ray</a>
            <p>Coordination-risk intelligence for engineering organizations. Self-hosted on HydraDB.</p>
            <span className="foot-badge">HackHydra 2026 · Track 01</span>
          </div>
          <div><h4>Product</h4><a href="#lenses">Ghost</a><a href="#lenses">Faultlines</a><a href="#lenses">Gaps</a><a href="/app">Open X-Ray</a></div>
          <div><h4>Engine</h4><a href="#engine">Why HydraDB</a><a href="#engine">algo.MSpaths</a><a href="#data">Corpora</a><a href="#faq">FAQ</a></div>
          <div><h4>Sources</h4><a href="/app">Slack</a><a href="/app">Email · mbox</a><a href="/app">JIRA · Confluence</a><a href="/app">GitHub · git</a></div>
        </div>
        <div className="foot-bottom">
          <span>© 2026 X-Ray · Apache-2.0 · Absence in a corpus is not proof of deletion.</span>
          <span className="foot-status">HydraDB {health.data?.hydra.status ?? "—"}</span>
        </div>
      </footer>
    </main>
  );
}
