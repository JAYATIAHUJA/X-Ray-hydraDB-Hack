import { useQuery } from "@tanstack/react-query";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useEffect, useMemo, useRef, useState } from "react";
import { getCurrentSnapshot, getHealth } from "./api";
import heroNight from "./assets/xray-hero-night.png";
import { XRayLogo } from "./Brand";
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
  const [navCompact, setNavCompact] = useState(false);
  const [selected, setSelected] = useState<string | undefined>("p0");
  const [demoStep, setDemoStep] = useState(0);
  const [demoPlaying, setDemoPlaying] = useState(true);
  const [demoVisible, setDemoVisible] = useState(false);
  const demo = useMemo(demoGraph, []);
  const activeDemo = demoSteps[demoStep]!;

  useEffect(() => {
    const updateNav = () => setNavCompact(globalThis.scrollY > 72);
    updateNav();
    globalThis.addEventListener("scroll", updateNav, { passive: true });
    return () => globalThis.removeEventListener("scroll", updateNav);
  }, []);

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

      ScrollTrigger.create({
        trigger: ".engine-visual",
        start: "top 88%",
        end: "bottom 12%",
        toggleClass: { targets: ".engine-visual", className: "is-active" }
      });

      const lensCards = gsap.utils.toArray<HTMLElement>(".lens");
      if (lensCards.length >= 3) {
        gsap.set(".lenses-head", { opacity: 1, y: 0 });
        gsap.set(lensCards, { transformOrigin: "50% 88%", willChange: "transform, opacity" });
        gsap.timeline({
          scrollTrigger: {
            trigger: ".lenses",
            start: "top top",
            end: "+=900",
            scrub: 0.85,
            pin: true,
            anticipatePin: 1
          }
        })
          .fromTo(lensCards[0]!, { xPercent: 101, y: 42, rotate: -8, scale: 0.92, opacity: 0.72, zIndex: 1 }, { xPercent: 0, y: 0, rotate: 0, scale: 1, opacity: 1, zIndex: 1, ease: "none" }, 0)
          .fromTo(lensCards[1]!, { xPercent: 0, y: 0, rotate: 0, scale: 1, opacity: 1, zIndex: 3 }, { xPercent: 0, y: 0, rotate: 0, scale: 1, opacity: 1, zIndex: 2, ease: "none" }, 0)
          .fromTo(lensCards[2]!, { xPercent: -101, y: 50, rotate: 8, scale: 0.92, opacity: 0.78, zIndex: 2 }, { xPercent: 0, y: 0, rotate: 0, scale: 1, opacity: 1, zIndex: 3, ease: "none" }, 0);
      }

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
      hero.style.setProperty("--mx", `${((nx + 0.5) * 100).toFixed(2)}%`);
      hero.style.setProperty("--my", `${((ny + 0.5) * 100).toFixed(2)}%`);
      photoX(nx * 34);
      photoY(ny * 22);
    };
    const leaveHero = () => {
      hero?.style.setProperty("--mx", "50%");
      hero?.style.setProperty("--my", "50%");
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

      <header className={`lp-nav${navCompact ? " is-compact" : ""}`}>
        <a className="lp-brand" href="/"><XRayLogo />X-Ray</a>
        <nav>
          <a href="#proof">Proof</a>
          <a href="#lenses">Lenses</a>
          <a href="#engine">Engine</a>
          <a href="#data">Sources</a>
        </nav>
        <div className="lp-nav-r">
          <a className="github-link magnet" href="https://github.com/JAYATIAHUJA/X-Ray-hydraDB-Hack" rel="noreferrer" target="_blank">GitHub</a>
        </div>
      </header>

      <section className="lp-hero">
        <div className="hero-photo" style={{ backgroundImage: `url(${heroNight})` }} aria-hidden="true" />
        <div className="hero-scan" aria-hidden="true">
          <span>01 10 11 00 01 10 11 00 10 01 00 11 10 01 10 00 11 01</span>
          <span>EDGE NODE PATH TRACE SOURCE COMMIT MESSAGE OWNER</span>
          <span>Missing evidence</span>
        </div>
        <div className="hero-inner">
          <h1 className="h-hero">
            X-Ray
          </h1>
          <div className="hero-copy">
            <p className="h-kicker">Your org chart is <em>fiction.</em> See who <span>actually</span> holds it together.</p>
            <p className="h-sub">
              Import Slack, mail, Jira, Confluence, GitHub, and git exports. X-Ray turns them into a risk inbox for hidden key people, silent dependencies, and missing evidence.
            </p>
            <div className="h-cta">
              <a className="btn-pill magnet" href="/app">Open X-Ray</a>
              <a className="btn-text-light" href="#lenses">See how it works <span className="arrow" aria-hidden="true">→</span></a>
            </div>
          </div>
        </div>
      </section>

      <section className="window-wrap" ref={demoWindow}>
        <div className="window">
          <div className="window-bar"><span /><span /><span /><em>x-ray · demo-org · Actual</em><b>live</b></div>
          <div className="window-body real-app-preview">
            <aside className="product-sidebar preview-sidebar">
              <a className="product-brand" href="/app"><XRayLogo /><span>X-Ray</span></a>
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
                  <div><span>Engine status</span><strong><i className="state-dot state-live" />Demo preview</strong></div>
                  <div><span>Data status</span><strong><i className="state-dot state-live" />Fixture UI</strong></div>
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
                    <Graph3D nodes={demo.nodes} edges={demo.edges} initialZoom={2.35} onSelect={selectGraphNode} selectedKey={selected} spin />
                  </div>
                  <div className="detail-body">
                    <section><h3>Why this matters</h3><p>{activeDemo.body}</p></section>
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

      <section className="proof" id="proof">
        <div className="proof-card rv">
          <span className="eyebrow">Open-corpus validation</span>
          <strong className="dot"><span data-count="5126">0</span></strong>
          <h3>People in one evidence graph</h3>
          <p>Validated on all 30 Salesforce HERB products while keeping unresolved identities out of the score.</p>
        </div>
        <div className="proof-card rv">
          <span className="eyebrow">Apache Kafka corpus</span>
          <strong className="dot"><span data-count="49">0</span></strong>
          <h3>Source-backed faultlines</h3>
          <p>Found across 292 people, with missing in-window records kept separate from export-boundary cases.</p>
        </div>
        <div className="proof-card rv proof-cta">
          <span className="eyebrow">What you get</span>
          <p>A prioritized risk inbox. Each finding opens the exact people, artifacts, paths, and source records behind the claim. <em>Runs in the self-hosted deployment you control.</em></p>
          <a className="btn-dark magnet" href="/app">Load your exports</a>
        </div>
      </section>

      <section className="dark" id="lenses">
        <ParticleGraph className="dark-art" ink="#F4F2ED" />
        <div className="dark-copy">
          <span className="eyebrow light rv">What X-Ray checks</span>
          <h2 className="rv">Find coordination risk before it becomes delivery risk.</h2>
          <p className="rv">X-Ray turns Slack, email, Jira, Confluence, GitHub, and git exports into an evidence graph. It highlights hidden key people, teams that depend on each other without talking, and missing records in important decision chains.</p>
          <span>Source-backed findings from your own work exports</span>
        </div>
      </section>

      <section className="lenses">
        <header className="lenses-head">
          <span className="eyebrow">Evidence lenses</span>
          <h2>Three checks your normal dashboards miss.</h2>
          <p>Each lens produces a source-backed finding, not a vague score. Open a risk and X-Ray shows the people, artifacts, and records behind it.</p>
        </header>
        <article className="lens">
          <span>Key-person dependency</span>
          <h3>Find the people carrying invisible load.</h3>
          <p>X-Ray compares observed collaboration paths with formal roles, then flags people whose absence would break too many handoffs.</p>
          <div className="lens-fig finding-person" aria-label="Priya has 22 observed collaboration paths but only 4 assigned handoffs">
            <div className="finding-top"><span>Collaboration load</span><b>High risk</b></div>
            <div className="person-summary">
              <i aria-hidden="true">P</i>
              <div><strong>Priya N.</strong><small>Platform engineering</small></div>
              <em>+22</em>
            </div>
            <div className="signal-row"><span>Observed paths</span><i><b /></i><strong>22</strong></div>
            <div className="signal-row assigned"><span>Assigned handoffs</span><i><b /></i><strong>4</strong></div>
            <p className="finding-note"><i />18 handoffs exist outside the org chart</p>
          </div>
        </article>
        <article className="lens">
          <span>Uncoordinated dependency</span>
          <h3>Catch teams that share code but not context.</h3>
          <p>When modules depend on each other but owners have no short communication path, X-Ray shows the affected areas and source evidence.</p>
          <div className="lens-fig finding-dependency" aria-label="Billing API depends on Ledger Core but their owners have no communication path">
            <div className="finding-top"><span>Dependency check</span><b>Needs attention</b></div>
            <div className="module-pair">
              <div><small>Service</small><strong>Billing API</strong><span>Maya</span></div>
              <i aria-hidden="true"><span>code edge</span><b /></i>
              <div><small>Service</small><strong>Ledger Core</strong><span>Owen</span></div>
            </div>
            <div className="path-result"><span>Owner communication</span><strong><i />No path found</strong></div>
          </div>
        </article>
        <article className="lens">
          <span>Missing evidence</span>
          <h3>Spot gaps in the decision trail.</h3>
          <p>If a workflow requires a message, ticket, approval, or parent record that is not in the export, X-Ray marks the gap clearly instead of guessing.</p>
          <div className="lens-fig finding-evidence" aria-label="The decision trail is missing an approval record between the issue and deployment">
            <div className="finding-top"><span>Evidence trace</span><b>Incomplete</b></div>
            <div className="trace-line">
              <div className="is-found"><i>1</i><strong>Issue</strong><small>Jira</small></div>
              <span />
              <div className="is-found"><i>2</i><strong>Decision</strong><small>Slack</small></div>
              <span className="is-gap" />
              <div className="is-missing"><i>?</i><strong>Approval</strong><small>Missing</small></div>
              <span className="is-gap" />
              <div className="is-found"><i>4</i><strong>Deploy</strong><small>GitHub</small></div>
            </div>
            <p className="finding-note"><i />Required approval record was not found</p>
          </div>
        </article>
      </section>

      <section className="engine" id="engine">
        <div className="engine-l">
          <span className="eyebrow rv">Why a graph engine</span>
          <h2 className="rv">Graph risk starts with a <em>mismatch</em> between work and communication.</h2>
          <p className="rv">A vector index cannot tell whether a typed edge exists in one graph and is absent in another. X-Ray sends HydraDB one bounded multi-source traversal and returns the paths, weights, and costs behind the finding.</p>
          <div className="engine-stat rv">
            <div><strong data-count="42486">0</strong><span>naive pair checks for 292 people</span></div>
            <div><strong>1</strong><span>bounded multi-source query</span></div>
          </div>
        </div>
        <div className="engine-visual rv">
          <div className="hydra-run">
            <header className="hydra-run-top">
              <div><i />HydraDB query path</div>
              <code>algo.MSpaths</code>
              <span>1 round trip</span>
            </header>
            <div className="hydra-run-body">
              <section className="run-input">
                <span>Person set</span>
                <strong>292 people</strong>
                <small>COMMUNICATES · max 4 hops</small>
                <div className="run-people" aria-hidden="true"><i>P</i><i>K</i><i>J</i><i>M</i><b>+288</b></div>
              </section>
              <div className="run-core" aria-hidden="true"><i>H</i><span /></div>
              <section className="run-output">
                <span>Bounded paths</span>
                <strong>Evidence returned</strong>
                <small>path · weight · cost</small>
                <ul>
                  <li><i /><span>Priya → Jonas</span><b>3 hops</b></li>
                  <li><i /><span>Kofi → Marcus</span><b>2 hops</b></li>
                  <li><i /><span>Aditi → Lena</span><b>4 hops</b></li>
                </ul>
              </section>
            </div>
            <footer className="hydra-run-foot"><span>Typed relationships</span><span>Bounded traversal</span><span>Query proof attached</span></footer>
          </div>
        </div>
      </section>

      <section className="hydra-tribute" id="hydradb">
        <div className="hydra-tribute-inner">
          <div className="hydra-tribute-copy">
            <span className="eyebrow rv">Built on HydraDB</span>
            <h2 className="rv">The graph engine behind X-Ray’s live path queries.</h2>
            <p className="rv">HydraDB gives X-Ray graph-native traversal over typed relationships. That is what lets a finding carry its exact route, execution bounds, engine timing, and source evidence instead of a similarity score.</p>
          </div>
          <dl className="hydra-capabilities rv">
            <div><dt>algo.MSpaths</dt><dd>Multi-source ownership and communication paths</dd></div>
            <div><dt>algo.SPpaths</dt><dd>Shortest evidence chains and missing-link context</dd></div>
            <div><dt>Fail-closed proof</dt><dd>X-Ray only says “HydraDB live” when the query actually ran</dd></div>
          </dl>
        </div>
        <strong className="hydra-wordmark" aria-hidden="true">HydraDB</strong>
      </section>

      <section className="datasets" id="data">
        <div className="ds-head rv">
          <h2>Runs on your work exports.<br />Includes safe demo corpora.</h2>
          <p>Every adapter is deterministic — explicit IDs only, no NLP guessing. What you load is what you get.</p>
        </div>
        <div className="ds-grid">
          <div className="ds rv"><span>demo</span><strong>xray-demo</strong><p>10-person synthetic org, planted findings, no external service.</p></div>
          <div className="ds rv"><span>synthetic</span><strong>xray-synth-500</strong><p>Larger generated org for stress-testing graph traversal and ranking.</p></div>
          <div className="ds rv"><span>benchmark</span><strong>Kafka export</strong><p>Open-source collaboration data used to validate parser and evidence behavior.</p></div>
          <div className="ds rv"><span>custom</span><strong>Your exports</strong><p>Slack, email, Jira, Confluence, GitHub, and git loaded into one evidence graph.</p></div>
        </div>
        <div className="ds-live rv">
          <div><strong>{data?.node_count ?? "500+"}</strong><span>people, artifacts, and records</span></div>
          <div><strong>{data?.edge_count ?? "2k+"}</strong><span>observed relationships</span></div>
          <div><strong>{data?.evidence_count ?? "12k+"}</strong><span>source-backed evidence records</span></div>
          <div><strong>{health.data?.hydra.status === "live" ? "Live" : "Local"}</strong><span>graph engine status</span></div>
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

      <footer className="lp-foot">
        <p className="foot-script">Run it locally.</p>
        <div className="foot-card">
          <div className="foot-brand">
            <a className="lp-brand" href="/"><XRayLogo />X-Ray</a>
            <h2>Source-backed coordination findings inside the deployment you control.</h2>
            <a className="foot-input" href="/app">
              <span>Open X-Ray</span>
              <i aria-hidden="true">→</i>
            </a>
            <p>Load Slack, mail, Jira, Confluence, GitHub, and git exports. X-Ray compares the work graph with the human graph in your self-hosted runtime.</p>
            <div className="foot-legal">
              <span>© 2026 X-Ray</span>
              <a href="#faq">FAQ</a>
              <a href="#engine">Evidence model</a>
            </div>
          </div>
          <nav className="foot-links" aria-label="Footer">
            <div><h4>Explore</h4><a href="#proof">Proof</a><a href="#lenses">Lenses</a><a href="#engine">Engine</a><a href="#hydradb">HydraDB</a></div>
            <div><h4>Use</h4><a href="#data">Sources</a><a href="#faq">FAQ</a><a href="/app">Open X-Ray</a></div>
          </nav>
          <strong className="foot-wordmark">X-Ray</strong>
        </div>
      </footer>
    </main>
  );
}
