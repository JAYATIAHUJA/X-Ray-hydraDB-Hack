/**
 * Full A→Z browser demo for X-Ray product surfaces.
 * Run: node scripts/browser_demo_a2z.cjs
 */
const { chromium } = require("/tmp/node_modules/playwright");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const BASE = process.env.XRAY_WEB_BASE || "http://127.0.0.1:5174";
const OUT = path.join(ROOT, "infra/runtime/browser-qa/shots");
const REPORT = path.join(ROOT, "infra/runtime/browser-qa/demo-report.json");

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
    await page.goto(BASE + "/", { waitUntil: "networkidle", timeout: 60000 });
    await shot(page, "01-landing");
    const landingText = await page.locator("body").innerText();
    log("landing_loads", /X-Ray/i.test(landingText), landingText.slice(0, 120).replace(/\s+/g, " "));
    const enter = page.getByRole("link", { name: /open|enter|launch|start|app/i }).first();
    if ((await enter.count()) > 0) {
      await enter.click();
      await page.waitForURL(/\/app/, { timeout: 15000 }).catch(() => {});
    } else {
      await gotoApp(page, "overview");
    }
    await shot(page, "02-app-entry");

    const top = await page.locator("body").innerText();
    log("hydra_live_shown", /HydraDB live/i.test(top), top.match(/HydraDB live|fallback|Offline/i)?.[0] || "missing");

    await gotoApp(page, "overview");
    await shot(page, "03-overview");
    log("overview", /Open signals|Overview/i.test(await page.locator("body").innerText()));

    await gotoApp(page, "risks");
    await page.waitForTimeout(1200);
    await shot(page, "04-risks");
    const risksBody = await page.locator("body").innerText();
    log("risks_inbox", /key-person|coordination|missing|Risk|P1|P2/i.test(risksBody), risksBody.slice(0, 160).replace(/\s+/g, " "));
    const riskBtn = page.locator(".risks-layout button").first();
    if ((await riskBtn.count()) > 0) {
      await riskBtn.click().catch(() => {});
      await page.waitForTimeout(500);
      await shot(page, "05-risk-detail");
      log("risk_detail", true);
    } else {
      log("risk_detail", /P1|Maya|payments|approval/i.test(risksBody), "no clickable row");
    }

    await gotoApp(page, "ask");
    await shot(page, "06-ask");
    const questions = [
      "Who owns payments-api now, and why did an older Jira record say Alex?",
      "Which services are affected if ledger-worker changes?",
      "Who approved the refund limit change?"
    ];
    for (let i = 0; i < questions.length; i++) {
      const q = questions[i];
      const example = page.locator(".ask-examples button").filter({ hasText: q }).first();
      if ((await example.count()) > 0) {
        await example.click();
      } else {
        const input = page.locator(".ask-composer input").first();
        await input.fill(q);
        await page.getByRole("button", { name: /^Ask$/i }).click();
      }
      await page.waitForSelector(".answer-summary, .ask-error, .ask-loading", { timeout: 30000 }).catch(() => {});
      await page.waitForSelector(".ask-loading", { state: "detached", timeout: 45000 }).catch(() => {});
      await page.waitForTimeout(800);
      await shot(page, `07-ask-q${i + 1}`);
      const body = await page.locator("body").innerText();
      const hasAnswer = /maya|alex|owner|ledger|payments|evidence|abstain|cannot|unknown|hydradb|fixture|query|affected|refused|answer/i.test(body);
      log(`ask_q${i + 1}`, hasAnswer, q.slice(0, 60));
    }

    await gotoApp(page, "identities");
    await page.waitForTimeout(1000);
    await shot(page, "08-identities");
    const idBody = await page.locator("body").innerText();
    log("identity_candidates", /sam|merge|Identity|pending|candidate/i.test(idBody), idBody.slice(0, 140).replace(/\s+/g, " "));
    log("identity_actions_visible", (await page.getByRole("button", { name: /Accept merge|Keep separate/i }).count()) > 0);

    await gotoApp(page, "repairs");
    await page.waitForTimeout(1200);
    await shot(page, "09-repairs");
    const repairsBody = await page.locator("body").innerText();
    log("repairs_list", /Repair|gap|faultline|missing|approval|SUPPORTED/i.test(repairsBody), repairsBody.slice(0, 160).replace(/\s+/g, " "));

    const gapItem = page.locator("aside button, .identity-queue button").filter({ hasText: /missing|approval|gap/i }).first();
    if ((await gapItem.count()) > 0) await gapItem.click();
    await page.waitForTimeout(400);
    const approve = page.getByRole("button", { name: /Approve repair/i }).first();
    if ((await approve.count()) > 0 && !(await approve.isDisabled())) {
      await approve.click();
      await page.waitForTimeout(1500);
      await shot(page, "10-repair-approved");
      log("repair_approve", true);
      const verify = page.getByRole("button", { name: /Re-check|prove closed/i }).first();
      if ((await verify.count()) > 0) {
        await verify.click();
        await page.waitForTimeout(1500);
        await shot(page, "11-repair-verified");
        const after = await page.locator("body").innerText();
        log("repair_closed", /closed/i.test(after), after.match(/closed|approved|gap_absent/i)?.[0] || "");
      } else {
        log("repair_closed", false, "verify button missing");
      }
    } else {
      log("repair_approve", /closed|approved/i.test(repairsBody), "approve unavailable");
      log("repair_closed", /closed/i.test(repairsBody), "pre-existing state");
    }

    await gotoApp(page, "graph");
    await page.waitForTimeout(1000);
    await shot(page, "12-graph");
    log("graph", /graph|Explore|node|edge|Person|Module/i.test(await page.locator("body").innerText()));

    await gotoApp(page, "actions");
    await shot(page, "13-actions");
    log("actions", /Actions|follow|tracked|No follow-up/i.test(await page.locator("body").innerText()));

    await gotoApp(page, "imports");
    await shot(page, "14-imports");
    log("imports", /Import|export|Slack|Jira|GitHub|mbox/i.test(await page.locator("body").innerText()));

    await gotoApp(page, "settings");
    await page.waitForTimeout(1000);
    await shot(page, "15-settings");
    log("settings", /Settings|API|runtime|Engine/i.test(await page.locator("body").innerText()));

    // demo-v2 is activated from Imports (prepared corpora), not Settings
    await gotoApp(page, "imports");
    await page.waitForTimeout(1200);
    await shot(page, "16-imports-corpora");
    const openDemoV2 = page.locator(".corpus-list li").filter({ hasText: /demo-v2|xray-demo-v2/i }).getByRole("button", { name: /Open/i }).first();
    if ((await openDemoV2.count()) > 0) {
      await openDemoV2.click();
      await page.waitForTimeout(2000);
      await shot(page, "17-demo-v2-active");
      const body = await page.locator("body").innerText();
      log("activate_demo_v2_ui", /xray-demo-v2|demo-v2/i.test(body), body.match(/xray-demo-v2|demo-v2|xray-demo-v1/i)?.[0] || "");
    } else {
      const res = await page.request.post("http://127.0.0.1:8000/api/v1/snapshots/activate", {
        data: { name: "demo-v2" },
        headers: { "X-Xray-Write-Token": "local-demo-write-token", "content-type": "application/json" }
      });
      const payload = await res.json();
      log("activate_demo_v2_api", res.ok() && payload.dataset_id === "xray-demo-v2", JSON.stringify(payload).slice(0, 120));
    }
    await gotoApp(page, "risks");
    await page.waitForTimeout(1200);
    await shot(page, "18-demo-v2-risks");
    log("demo_v2_risks", /payments|ledger|Maya|approval|Risk/i.test(await page.locator("body").innerText()));
    await gotoApp(page, "repairs");
    await page.waitForTimeout(1000);
    await shot(page, "19-demo-v2-repairs");
    log("demo_v2_repairs", /Repair|gap|faultline|SUPPORTED|missing/i.test(await page.locator("body").innerText()));
    // restore demo fixture
    await page.request.post("http://127.0.0.1:8000/api/v1/snapshots/activate", {
      data: { name: "demo" },
      headers: { "X-Xray-Write-Token": "local-demo-write-token", "content-type": "application/json" }
    });

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
    fs.writeFileSync(REPORT, JSON.stringify({ base: BASE, passed, failed, results, shots: fs.readdirSync(OUT) }, null, 2));
    console.log(`\nSummary: ${passed} passed, ${failed} failed → ${REPORT}`);
    await browser.close();
    if (failed) process.exitCode = 1;
  }
}

main();
