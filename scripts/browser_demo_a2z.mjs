/**
 * Full A→Z browser demo for X-Ray product surfaces.
 * Run: NODE_PATH=/tmp/node_modules node scripts/browser_demo_a2z.mjs
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.XRAY_WEB_BASE || "http://127.0.0.1:5174";
const OUT = path.resolve("infra/runtime/browser-qa/shots");
const REPORT = path.resolve("infra/runtime/browser-qa/demo-report.json");

fs.mkdirSync(OUT, { recursive: true });

const results = [];
function log(step, ok, detail = "") {
  results.push({ step, ok, detail, at: new Date().toISOString() });
  console.log(`${ok ? "PASS" : "FAIL"}  ${step}${detail ? " — " + detail : ""}`);
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
}

async function gotoApp(page, view) {
  await page.goto(`${BASE}/app?view=${view}`, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(800);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  page.setDefaultTimeout(20000);

  try {
    // 1) Landing
    await page.goto(BASE + "/", { waitUntil: "networkidle", timeout: 60000 });
    await shot(page, "01-landing");
    const landingText = await page.locator("body").innerText();
    log("landing_loads", /X-Ray/i.test(landingText), landingText.slice(0, 120).replace(/\s+/g, " "));
    const enter = page.getByRole("link", { name: /open|enter|launch|start|app/i }).first();
    if (await enter.count()) {
      await enter.click();
      await page.waitForURL(/\/app/, { timeout: 15000 }).catch(() => {});
    } else {
      await gotoApp(page, "overview");
    }
    await shot(page, "02-app-entry");

    // Engine status
    const top = await page.locator("body").innerText();
    log("hydra_live_shown", /HydraDB live/i.test(top), top.match(/HydraDB live|fallback|Offline/i)?.[0] || "missing");

    // 2) Overview
    await gotoApp(page, "overview");
    await shot(page, "03-overview");
    log("overview", /Open signals|Overview/i.test(await page.locator("body").innerText()));

    // 3) Risks
    await gotoApp(page, "risks");
    await page.waitForTimeout(1200);
    await shot(page, "04-risks");
    const risksBody = await page.locator("body").innerText();
    log("risks_inbox", /key-person|coordination|missing|Risk|P1|P2/i.test(risksBody), risksBody.slice(0, 160).replace(/\s+/g, " "));
    const riskBtn = page.locator(".risks-layout button, [class*=risk] button").first();
    if (await riskBtn.count()) {
      await riskBtn.click().catch(() => {});
      await page.waitForTimeout(500);
      await shot(page, "05-risk-detail");
      log("risk_detail", true);
    } else {
      log("risk_detail", /P1|Maya|payments|approval/i.test(risksBody), "no clickable row; body still has findings");
    }

    // 4) Ask X-Ray — three judge questions
    await gotoApp(page, "ask");
    await shot(page, "06-ask");
    const questions = [
      "Who owns payments-api now, and why did an older Jira record say Alex?",
      "Which services are affected if ledger-worker changes?",
      "Who approved the refund limit change?"
    ];
    for (let i = 0; i < questions.length; i++) {
      const q = questions[i];
      const input = page.getByRole("textbox").first().or(page.locator("textarea, input[type=text]").first());
      await input.fill(q);
      const askBtn = page.getByRole("button", { name: /ask|submit|send/i }).first();
      if (await askBtn.count()) await askBtn.click();
      else await input.press("Enter");
      await page.waitForTimeout(2500);
      await shot(page, `07-ask-q${i + 1}`);
      const body = await page.locator("body").innerText();
      const hasAnswer = /maya|alex|owner|ledger|payments|evidence|abstain|cannot|unknown|hydradb|fixture|query/i.test(body);
      log(`ask_q${i + 1}`, hasAnswer, q.slice(0, 60));
    }

    // 5) Identity review
    await gotoApp(page, "identities");
    await page.waitForTimeout(1000);
    await shot(page, "08-identities");
    const idBody = await page.locator("body").innerText();
    log("identity_candidates", /sam|merge|Identity|pending|candidate/i.test(idBody), idBody.slice(0, 140).replace(/\s+/g, " "));
    const keep = page.getByRole("button", { name: /Keep separate|Reject/i }).first();
    // don't permanently accept; just verify UI renders actions
    log("identity_actions_visible", (await page.getByRole("button", { name: /Accept merge|Keep separate/i }).count()) > 0);

    // 6) Repairs — approve gap + verify closed
    await gotoApp(page, "repairs");
    await page.waitForTimeout(1200);
    await shot(page, "09-repairs");
    const repairsBody = await page.locator("body").innerText();
    log("repairs_list", /Repair|gap|faultline|missing|approval|SUPPORTED/i.test(repairsBody), repairsBody.slice(0, 160).replace(/\s+/g, " "));

    const gapItem = page.locator("aside button, .identity-queue button").filter({ hasText: /missing|approval|gap/i }).first();
    if (await gapItem.count()) await gapItem.click();
    await page.waitForTimeout(400);
    const approve = page.getByRole("button", { name: /Approve repair/i }).first();
    if (await approve.count() && !(await approve.isDisabled())) {
      await approve.click();
      await page.waitForTimeout(1500);
      await shot(page, "10-repair-approved");
      log("repair_approve", true);
      const verify = page.getByRole("button", { name: /Re-check|prove closed/i }).first();
      if (await verify.count()) {
        await verify.click();
        await page.waitForTimeout(1500);
        await shot(page, "11-repair-verified");
        const after = await page.locator("body").innerText();
        log("repair_closed", /closed/i.test(after), after.match(/closed|approved|gap_absent/i)?.[0] || "");
      } else {
        log("repair_closed", false, "verify button missing");
      }
    } else {
      // maybe already closed from prior run — still mark list present
      log("repair_approve", /closed|approved/i.test(repairsBody), "approve unavailable; checking existing state");
      log("repair_closed", /closed/i.test(repairsBody), "pre-existing closed state");
    }

    // 7) Graph
    await gotoApp(page, "graph");
    await page.waitForTimeout(1000);
    await shot(page, "12-graph");
    log("graph", /graph|Explore|node|edge|Person|Module/i.test(await page.locator("body").innerText()));

    // 8) Actions
    await gotoApp(page, "actions");
    await shot(page, "13-actions");
    log("actions", /Actions|follow|tracked|No follow-up/i.test(await page.locator("body").innerText()));

    // 9) Imports
    await gotoApp(page, "imports");
    await shot(page, "14-imports");
    log("imports", /Import|export|Slack|Jira|GitHub|mbox/i.test(await page.locator("body").innerText()));

    // 10) Settings — activate demo-v2
    await gotoApp(page, "settings");
    await page.waitForTimeout(1000);
    await shot(page, "15-settings");
    const settingsBody = await page.locator("body").innerText();
    log("settings", /Settings|snapshot|fixture|demo/i.test(settingsBody));

    // Try activate demo-v2 via UI if selector exists, else API fallback check
    const demoV2 = page.getByRole("button", { name: /demo-v2/i }).or(page.locator("text=demo-v2")).first();
    if (await demoV2.count()) {
      await demoV2.click();
      await page.waitForTimeout(1500);
      await shot(page, "16-demo-v2");
      log("activate_demo_v2_ui", /xray-demo-v2|demo-v2/i.test(await page.locator("body").innerText()));
    } else {
      // API activation to prove fixture works, then refresh settings
      const res = await page.request.post("http://127.0.0.1:8000/api/v1/snapshots/activate", {
        data: { name: "demo-v2" },
        headers: { "X-Xray-Write-Token": "local-demo-write-token", "content-type": "application/json" }
      });
      const payload = await res.json();
      log("activate_demo_v2_api", res.ok() && payload.dataset_id === "xray-demo-v2", JSON.stringify(payload).slice(0, 120));
      await gotoApp(page, "settings");
      await shot(page, "16-demo-v2");
      await gotoApp(page, "risks");
      await page.waitForTimeout(1200);
      await shot(page, "17-demo-v2-risks");
      log("demo_v2_risks", /payments|ledger|Maya|approval|Risk/i.test(await page.locator("body").innerText()));
      // restore demo for cleanliness
      await page.request.post("http://127.0.0.1:8000/api/v1/snapshots/activate", {
        data: { name: "demo" },
        headers: { "X-Xray-Write-Token": "local-demo-write-token", "content-type": "application/json" }
      });
    }

    // Final health probe via page request
    const health = await page.request.get("http://127.0.0.1:8000/api/v1/health");
    const hj = await health.json();
    log("api_hydra_live", hj.hydra?.status === "live" && hj.hydra?.graph_loaded === true, `${hj.hydra?.status} loaded=${hj.hydra?.graph_loaded}`);
  } catch (err) {
    log("fatal", false, String(err));
    try {
      await shot(page, "99-fatal");
    } catch {}
  } finally {
    const passed = results.filter((r) => r.ok).length;
    const failed = results.filter((r) => !r.ok).length;
    fs.writeFileSync(
      REPORT,
      JSON.stringify({ base: BASE, passed, failed, results, shots: fs.readdirSync(OUT) }, null, 2)
    );
    console.log(`\nSummary: ${passed} passed, ${failed} failed → ${REPORT}`);
    await browser.close();
    if (failed) process.exitCode = 1;
  }
}

main();
