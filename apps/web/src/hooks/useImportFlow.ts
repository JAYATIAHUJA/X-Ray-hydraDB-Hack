import { useEffect, useState } from "react";
import {
  activateSnapshot,
  getAvailableSnapshots,
  importSnapshot
} from "../api";
import type { AvailableSnapshot, ImportPayload } from "../api";

async function readJson(file: File | null | undefined, fallback: unknown) {
  return file ? JSON.parse(await file.text()) as unknown : fallback;
}

async function readText(file: File | null | undefined) {
  return file ? await file.text() : undefined;
}

export function useImportFlow(onDone: () => void) {
  const [datasetId, setDatasetId] = useState("imported-snapshot");
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [slackFiles, setSlackFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [available, setAvailable] = useState<AvailableSnapshot[]>([]);
  const [switching, setSwitching] = useState<string | null>(null);

  useEffect(() => {
    getAvailableSnapshots().then(setAvailable).catch(() => setAvailable([]));
  }, []);

  const pick = (key: string) => (file: File | null) => {
    setFiles((current) => ({ ...current, [key]: file }));
  };

  async function run() {
    if (!files.directory) {
      setStatus("A directory.json is required — it lists the people.");
      return;
    }
    setBusy(true);
    setStatus("Building the graph…");
    try {
      const slackExports: Record<string, Record<string, unknown>[]> = {};
      for (const file of slackFiles) {
        slackExports[file.name.replace(/\.json$/i, "")] =
          (await readJson(file, [])) as Record<string, unknown>[];
      }
      const payload: ImportPayload = {
        dataset_id: datasetId.trim() || "imported-snapshot",
        directory: (await readJson(files.directory, [])) as Record<string, unknown>[],
        identity_map: (await readJson(files.identity, {})) as Record<string, string>,
        mbox: files.mbox ? [await files.mbox.text()] : [],
        jira_csv: await readText(files.jira),
        git_log: await readText(files.git),
        module_prefixes: (await readJson(files.modules, {})) as Record<string, string>,
        slack_exports: slackExports,
        channel_modules: (await readJson(files.channels, {})) as Record<string, string[]>,
        message_modules: (await readJson(files.messages, {})) as Record<string, string[]>,
        confluence_xml: await readText(files.confluence),
        github_csv: await readText(files.github),
        sequence_contracts: (await readJson(
          files.contracts,
          { contracts: [], limitations: [] }
        )) as Record<string, unknown>
      };
      const snapshot = await importSnapshot(payload);
      setStatus(
        `Imported ${snapshot.node_count.toLocaleString()} nodes and ${snapshot.edge_count.toLocaleString()} edges. Opening dashboard…`
      );
      globalThis.setTimeout(() => window.location.reload(), 600);
      onDone();
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "Import failed");
      setBusy(false);
    }
  }

  async function open(name: string) {
    setSwitching(name);
    try {
      await activateSnapshot(name);
      window.location.reload();
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "Could not switch corpus");
      setSwitching(null);
    }
  }

  return {
    available,
    busy,
    datasetId,
    open,
    pick,
    run,
    setDatasetId,
    setSlackFiles,
    status,
    switching
  };
}
