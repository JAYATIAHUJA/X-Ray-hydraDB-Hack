import { useQuery } from "@tanstack/react-query";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useEffect, useMemo, useRef, useState } from "react";
import { getCurrentSnapshot, getHealth } from "./api";
import heroNight from "./assets/xray-hero-night.png";
import { Graph3D } from "./Graph3D";
import type { Graph3DEdge, Graph3DNode } from "./Graph3D";
import { ParticleGraph, SourceTile } from "./LandingArt";

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

const demoSteps = [
  { key: "p0", label: "Hidden connector", title: "Priya holds the work together", body: "She sits on the most collaboration paths, even though the org chart ranks her #23.", sideLabel: "Selected person", sideValue: "Priya", sideDetail: "#1 structural · #23 formal" },
  { key: "p5", label: "Coordination gap", title: "Two dependent teams rarely talk", body: "X-Ray highlights the code dependency and the missing communication path between its owners.", sideLabel: "Selected faultline", sideValue: "Kofi ↔ Jonas", sideDetail: "shared code · no communication path" },
  { key: "p9", label: "Evidence trace", title: "Every finding opens to its source", body: "Follow the people, messages, and code changes behind the risk before taking action.", sideLabel: "Evidence opened", sideValue: "12 records", sideDetail: "messages · commits · ownership links" }
] as const;

export function Landing() {
  const snapshot = useQuery({ queryKey: ["landing-snapshot"], queryFn: getCurrentSnapshot });
  const health = useQuery({ queryKey: ["landing-health"], queryFn: getHealth });
  const data = snapshot.data;
  const root = useRef<HTMLElement | null>(null);
  const demoWindow = useRef<HTMLElement | null>(null);
  const grainRef = useRef<HTMLDivElement | null>(null);
  const [selected, setSelected] = useState<string | undefined>("p0");
  const [demoStep, setDemoStep] = useState(0);
  const [demoPlaying, setDemoPlaying] = useState(true);
  const [demoVisible, setDemoVisible] = useState(false);
  const demo = useMemo(demoGraph, []);
  const activeDemo = demoSteps[demoStep]!;

  useEffect(() => {
    const el = grainRef.current;
    if (!el) return;
    const c = document.createElement("canvas");
    c.width = 150; c.height = 150;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(150, 150);
    for (let i = 0; i < img.data.length; i += 4) {
      const v = Math.random() * 255;
      img.data[i] = v; img.data[i + 1] = v; img.data[i + 2] = v; img.data[i + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    el.style.backgroundImage = `url(${c.toDataURL()})`;
  }, []);

  useEffect(() => {
    const reduce = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    if (reduce || root.current === null) return;

    const ctx = gsap.context(() => {
      gsap.from(".hero-photo", { scale: 1.035, opacity: 0, duration: 1.6, ease: "expo.out" });

      // hero parallax — copy drifts up faster than the scan scene
      gsap.to(".hero-inner", { yPercent: -10, opacity: 0.28, ease: "none", scrollTrigger: { trigger: ".lp-hero", start: "top top", end: "bottom 35%", scrub: true } });
      gsap.to(".hero-photo", { yPercent: 12, scale: 1.07, ease: "none", scrollTrigger: { trigger: ".lp-hero", start: "top top", end: "bottom top", scrub: true } });
      gsap.to(".hero-scan", { xPercent: 55, opacity: 0.52, ease: "none", scrollTrigger: { trigger: ".lp-hero", start: "top top", end: "bottom 25%", scrub: true } });

      gsap.fromTo(".window",
        { rotateX: 18, y: 80, opacity: 0.2, scale: 0.93 },
        { rotateX: 0, y: 0, opacity: 1, scale: 1, ease: "none",
          scrollTrigger: { trigger: ".window-wrap", start: "top 92%", end: "top 22%", scrub: 0.8 } }
      );

      gsap.utils.toArray<HTMLElement>(".rv").forEach((el) => {
        gsap.from(el, { y: 60, opacity: 0, duration: 1.3, ease: "expo.out",
          scrollTrigger: { trigger: el, start: "top 87%" } });
      });

      gsap.utils.toArray<HTMLElement>("[data-speed]").forEach((el) => {
        const speed = parseFloat(el.dataset.speed || "0.5");
        gsap.to(el, { yPercent: speed * -25, ease: "none",
          scrollTrigger: { trigger: el.closest("section") || el.parentElement, start: "top bottom", end: "bottom top", scrub: true } });
      });

      gsap.utils.toArray<SVGPathElement>(".conn path").forEach((p) => {
        const len = p.getTotalLength();
        gsap.set(p, { strokeDasharray: len, strokeDashoffset: len });
        gsap.to(p, { strokeDashoffset: 0, ease: "none",
          scrollTrigger: { trigger: p, start: "top 85%", end: "bottom 40%", scrub: true } });
      });

      gsap.utils.toArray<HTMLElement>("[data-count]").forEach((el) => {
        const end = Number(el.dataset.count || 0); const o = { v: 0 };
        gsap.to(o, { v: end, duration: 2.2, ease: "power2.out",
          scrollTrigger: { trigger: el, start: "top 86%", once: true },
          onUpdate: () => { el.textContent = Math.round(o.v).toLocaleString(); } });
      });

      const codeEl = document.querySelector<HTMLElement>(".q-code code");
      if (codeEl) {
        const full = codeEl.textContent || ""; codeEl.textContent = "";
        gsap.to({ n: 0 }, { n: full.length, duration: 2.5, ease: "none",
          scrollTrigger: { trigger: ".q-code", start: "top 75%", once: true },
          onUpdate() { codeEl.textContent = full.slice(0, Math.round(this.targets()[0].n)); } });
      }

      gsap.to(".dark-art", { yPercent: -14, ease: "none",
        scrollTrigger: { trigger: ".dark", start: "top bottom", end: "bottom top", scrub: true } });

    }, root);

    const magnets = Array.from(document.querySelectorAll<HTMLElement>(".magnet"));
    const hs = magnets.map((el) => {
      const move = (e: PointerEvent) => { const r = el.getBoundingClientRect(); gsap.to(el, { x: (e.clientX - r.left - r.width / 2) * 0.28, y: (e.clientY - r.top - r.height / 2) * 0.28, duration: 0.4, ease: "power3.out" }); };
      const leave = () => gsap.to(el, { x: 0, y: 0, duration: 0.8, ease: "elastic.out(1, 0.4)" });
      el.addEventListener("pointermove", move); el.addEventListener("pointerleave", leave);
      return { el, move, leave };
    });

    const hero = root.current.querySelector<HTMLElement>(".lp-hero");
    const heroPhoto = root.current.querySelector<HTMLElement>(".hero-photo");
    const photoX = heroPhoto ? gsap.quickTo(heroPhoto, "x", { duration: 0.9, ease: "power3.out" }) : null;
    const photoY = heroPhoto ? gsap.quickTo(heroPhoto, "y", { duration: 0.9, ease: "power3.out" }) : null;
    const moveHero = (e: PointerEvent) => {
      if (!hero || !photoX || !photoY) return;
      const rect = hero.getBoundingClientRect();
      const nx = (e.clientX - rect.left) / rect.width - 0.5;
      const ny = (e.clientY - rect.top) / rect.height - 0.5;
      photoX(nx * 34);
      photoY(ny * 22);
    };
    const leaveHero = () => {
      photoX?.(0);
      photoY?.(0);
    };
    hero?.addEventListener("pointermove", moveHero);
    hero?.addEventListener("pointerleave", leaveHero);

    return () => {
      ctx.revert();
      hs.forEach(({ el, move, leave }) => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerleave", leave); });
      hero?.removeEventListener("pointermove", moveHero);
      hero?.removeEventListener("pointerleave", leaveHero);
    };
  }, []);

  useEffect(() => {
    const element = demoWindow.current;
    if (element === null) return;
    const observer = new IntersectionObserver(([entry]) => setDemoVisible(entry?.isIntersecting === true), { threshold: 0.45 });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const reduceMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    if (!demoVisible || !demoPlaying || reduceMotion) return;
    const timer = globalThis.setInterval(() => {
      setDemoStep((current) => {
        const next = (current + 1) % demoSteps.length;
        setSelected(demoSteps[next]!.key);
        return next;
      });
    }, 3200);
    return () => globalThis.clearInterval(timer);
  }, [demoPlaying, demoVisible]);

  const chooseDemoStep = (index: number) => { setDemoStep(index); setSelected(demoSteps[index]!.key); setDemoPlaying(false); };
  const selectGraphNode = (key: string) => { setSelected(key); const step = demoSteps.findIndex((item) => item.key === key); if (step >= 0) setDemoStep(step); setDemoPlaying(false); };

  return (
    <main className="lp" ref={root}>
      <div className="grain" ref={grainRef} />

      <header className="lp-nav">
        <a className="lp-brand" href="/"><i />X-Ray</a>
        <nav>
          <a href="#lenses">Lenses</a>
          <a href="#engine">Engine</a>
          <a href="#data">Data</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className="lp-nav-r">
          <a className="btn-pill sm magnet" href="/app">Open X-Ray</a>
        </div>
      </header>

      <section className="lp-hero">
        <div className="hero-photo" style={{ backgroundImage: `url(${heroNight})` }} aria-hidden="true" />
        <div className="hero-scan" aria-hidden="true">
          <span>01 10 11 00 01 10 11 00 10 01 00 11 10 01 10 00 11 01</span>
          <span>EDGE NODE PATH TRACE SOURCE COMMIT MESSAGE OWNER</span>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
        </div>
        <div className="hero-inner">
          <h1 className="h-hero">
            X-Ray
          </h1>
          <div className="hero-copy">
            <p className="h-kicker">Your org chart is <em>fiction.</em> See who <span>actually</span> holds it together.</p>
            <p className="h-sub">
              Two graphs from your own exports: the human one and the work one, with the exact places they disagree.
            </p>
            <div className="h-cta">
              <a className="btn-pill magnet" href="/app">Open X-Ray</a>
              <a className="btn-text-light" href="#lenses">See how it works <span className="arrow">-&gt;</span></a>
            </div>
          </div>
        </div>
      </section>

      <section className="window-wrap" ref={demoWindow}>
        <div className="window">
          <div className="window-bar"><span /><span /><span /><em>x-ray · demo-org · Actual</em><b>live</b></div>
          <div className="window-body real-app-preview">
            <aside className="product-sidebar preview-sidebar">
              <a className="product-brand" href="/app"><i aria-hidden="true">X</i><span>X-Ray</span></a>
              <nav aria-label="Preview navigation">
                {["Overview", "Risks", "Ask X-Ray", "Identity review", "Explore graph", "Imports", "Actions", "Settings"].map((label) => (
                  <button aria-current={label === "Risks" ? "page" : undefined} key={label} type="button"><span>{label}</span></button>
                ))}
              </nav>
              <div className="sidebar-foot"><span>Evidence platform</span><small>demo-org</small></div>
            </aside>
            <div className="preview-main product-main">
              <header className="product-topbar preview-topbar">
                <div className="workspace-switcher"><span>Workspace</span><strong>demo-org</strong></div>
                <div className="runtime-state">
                  <div><span>Engine status</span><strong><i className="state-dot state-live" />HydraDB live</strong></div>
                  <div><span>Data status</span><strong><i className="state-dot state-live" />Ready</strong></div>
                </div>
              </header>
              <div className="preview-risks-layout">
                <section className="risk-inbox preview-inbox">
                  <header className="workspace-heading">
                    <div><h1>Risk inbox</h1><p>Prioritized coordination risks from the active evidence snapshot.</p></div>
                    <button className="filter-button" type="button" onClick={() => setDemoPlaying((p) => !p)}>{demoPlaying ? "Pause demo" : "Play demo"}</button>
                  </header>
                  <div className="risk-filters" aria-label="Preview filters">
                    <label><span>Risk type</span><select defaultValue="all"><option value="all">All types</option></select></label>
                    <label><span>Team</span><select defaultValue="all"><option value="all">All teams</option></select></label>
                    <label><span>Confidence</span><select defaultValue="all"><option value="all">All confidence</option></select></label>
                  </div>
                  <div className="risk-count"><strong>12 risks</strong><span>Sorted by priority and confidence</span></div>
                  <div className="risk-table-wrap">
                    <table className="risk-table preview-risk-table">
                      <thead><tr><th>Priority</th><th>Risk</th><th>Risk type</th><th>Affected area</th><th>Team</th><th>Confidence</th><th>Last observed</th></tr></thead>
                      <tbody>
                        {demoSteps.map((step, index) => (
                          <tr aria-selected={index === demoStep} key={step.key} onClick={() => chooseDemoStep(index)}>
                            <td><button className={`priority priority-p${index + 1}`} type="button">{index === 0 ? "P1" : index === 1 ? "P2" : "P3"}</button></td>
                            <td><button className="risk-title-button" type="button">{step.title}</button></td>
                            <td><span className={`risk-type ${index === 1 ? "risk-type-coordination" : ""}`}><i />{step.label}</span></td>
                            <td>{index === 0 ? "Platform graph" : index === 1 ? "Payments API" : "Decision chain"}</td>
                            <td>{index === 0 ? "Platform" : index === 1 ? "Payments" : "Infra"}</td>
                            <td><strong>{index === 0 ? "High" : "Medium"}</strong><small>{index === 0 ? "91%" : index === 1 ? "84%" : "76%"}</small></td>
                            <td>Today</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
                <aside className="risk-detail preview-detail">
                  <div className="detail-header">
                    <div className="detail-kicker"><span>{activeDemo.label}</span><small>{activeDemo.sideValue}</small></div>
                    <h2>{activeDemo.title}</h2>
                    <div className="detail-tags"><span>demo-org</span><span>source backed</span><span>live graph</span></div>
                  </div>
                  <div className="detail-tabs"><button aria-selected="true" type="button">Evidence</button><button type="button">Impact</button><button type="button">Query</button></div>
                  <div className="preview-graph-strip">
                    <Graph3D nodes={demo.nodes} edges={demo.edges} onSelect={selectGraphNode} selectedKey={selected} spin />
                  </div>
                  <div className="detail-body">
                    <section><h3>Why this matters</h3><p>{activeDemo.body}</p></section>
                    <section className="evidence-section">
                      <h3>Opened evidence</h3>
                      <ul className="evidence-list">
                        <li><div><strong>{activeDemo.sideLabel}</strong><span>{activeDemo.sideDetail}</span><code>source://demo/{activeDemo.key}</code></div></li>
                        <li><div><strong>12 source records</strong><span>messages, commits, and ownership links</span><code>snapshot://demo-org/current</code></div></li>
                      </ul>
                    </section>
                  </div>
                </aside>
              </div>
            </div>
          </div>
        </div>
      </section>

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

      <section className="proof">
        <div className="proof-card rv">
          <span className="eyebrow">Single-point risk</span>
          <strong className="dot"><span data-count="516">0</span></strong>
          <p>collaboration paths depend on one person staying available</p>
        </div>
        <div className="proof-card rv">
          <span className="eyebrow">Hidden coordination gap</span>
          <strong className="dot"><span data-count="49">0</span></strong>
          <p>code dependencies connect teams whose owners never communicate</p>
        </div>
        <div className="proof-card rv proof-cta">
          <p>Runs entirely on your machine, against your own exports. <em>Nothing leaves.</em></p>
          <a className="btn-dark magnet" href="/app">Load your exports</a>
        </div>
      </section>

      <section className="dark" id="lenses">
        <ParticleGraph className="dark-art" ink="#F4F2ED" />
        <div className="dark-copy">
          <span className="eyebrow light rv">Three lenses</span>
          <h2 className="rv">See what the org chart <em>leaves out.</em></h2>
          <p className="rv">X-Ray compares how work is supposed to flow with how it actually moves. It shows the people carrying hidden load, the teams that depend on each other without talking, and the missing handoffs that create risk.</p>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
        </div>
      </section>

      <section className="lenses">
        <article className="lens rv">
          <svg className="conn" viewBox="0 0 400 220" preserveAspectRatio="none"><path d="M6 6 V 150 Q 6 190 46 190 H 394" /></svg>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
          <h3>Who <em>quietly</em> holds it together?</h3>
          <p>Rank people by how many bounded shortest paths route through them, then compare with their title. The person at #1 is rarely the one on top of the chart.</p>
          <div className="lens-fig fig-ghost"><i /><i /><i /><i /><i /><i /><i /><b /></div>
        </article>
        <article className="lens rv">
          <svg className="conn" viewBox="0 0 400 220" preserveAspectRatio="none"><path d="M6 6 V 150 Q 6 190 46 190 H 394" /></svg>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
          <h3>Where does code depend but <em>people don&apos;t talk?</em></h3>
          <p>Modules that co-change constantly whose owners have no communication path within four hops. Each ships with the shortest introduction that would fix it.</p>
          <div className="lens-fig fig-fault"><i /><s /><i /></div>
        </article>
        <article className="lens rv">
          <svg className="conn" viewBox="0 0 400 220" preserveAspectRatio="none"><path d="M6 6 V 150 Q 6 190 46 190 H 394" /></svg>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
          <h3>Where is a record the chain <em>requires</em> — but isn&apos;t there?</h3>
          <p>A reply whose parent is missing. X-Ray marks a Phantom node and traces the chain through it. Absence isn&apos;t proof of deletion; it&apos;s a precise question.</p>
          <div className="lens-fig fig-gap"><i /><i /><u /><i /><i /></div>
        </article>
      </section>

      <section className="engine" id="engine">
        <div className="engine-l">
          <span className="eyebrow rv">Why a graph engine</span>
          <h2 className="rv">The signal is an edge that exists in one graph <em>and not the other.</em></h2>
          <p className="rv">A vector index has one embedding space and no notion of &ldquo;present here, absent there.&rdquo; X-Ray asks HydraDB for bounded pairwise traversal in one server-side call, and compares client-side.</p>
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

      <section className="datasets" id="data">
        <div className="ds-head rv">
          <h2>Runs on <em>your</em> exports.<br />Ships with four corpora.</h2>
          <p>Every adapter is deterministic — explicit IDs only, no NLP guessing. What you load is what you get.</p>
        </div>
        <div className="ds-grid">
          <div className="ds rv"><span>demo</span><strong>xray-demo</strong><p>10-person synthetic org, planted findings, no external service.</p></div>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
        </div>
        <div className="ds-live rv">
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
        </div>
      </section>

      <section className="faq" id="faq">
        <h2 className="rv">Questions people <em>actually</em> ask.</h2>
        <div className="faq-grid">
          {[
            ["Where is my data processed?", "Imports are disabled on the hosted demo. In an explicitly enabled self-hosted deployment, exports are sent only to the API you operate and the resulting graph stays in that deployment."],
            ["Is “absence” proof someone deleted something?", "No, and we never say that. A Phantom node means the graph structurally requires a record the corpus doesn’t contain. It’s a precise question, not an accusation."],
            ["Why not a vector database?", "The finding is an edge present in one graph and absent in another. Embedding similarity has no notion of that. Bounded typed traversal does."],
            ["How is structural rank computed?", "Exact NetworkX betweenness below 2,000 people; larger graphs disclose bounded Brandes or HydraDB MSpaths. The metric is standard—the evidence-backed comparison with formal rank and removal impact is the product."]
          ].map(([q, a]) => (
            <details className="rv" key={q}><summary>{q}</summary><p>{a}</p></details>
          ))}
        </div>
      </section>

      <section className="lp-cta">
        <div className="orb orb-cta-1" />
        <div className="orb orb-cta-2" />
        <h2 className="rv">See who actually holds<br /><em>your</em> org together.</h2>
        <div className="rv cta-row">
          <a className="btn-pill magnet" href="/app">Open X-Ray</a>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
        </div>
      </section>

      <footer className="lp-foot">
        <div className="foot-grid">
          <div className="foot-brand">
            <a className="lp-brand" href="/"><i />X-Ray</a>
            <p>Coordination-risk intelligence for engineering organizations. Self-hosted on HydraDB.</p>
          </div>
          <div><h4>Product</h4><a href="#lenses">Ghost</a><a href="#lenses">Faultlines</a><a href="#lenses">Gaps</a><a href="/app">Open X-Ray</a></div>
          <div><h4>Engine</h4><a href="#engine">Why HydraDB</a><a href="#engine">algo.MSpaths</a><a href="#data">Corpora</a><a href="#faq">FAQ</a></div>
          <div><h4>Sources</h4><a href="/app">Slack</a><a href="/app">Email · mbox</a><a href="/app">JIRA · Confluence</a><a href="/app">GitHub · git</a></div>
        </div>
        <div className="foot-bottom">
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
          <span>SCAN TRACE NODE PATH SOURCE COMMIT OWNER EVIDENCE EXPORT</span>
        </div>
      </footer>
    </main>
  );
}
