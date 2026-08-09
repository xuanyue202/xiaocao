#!/usr/bin/env node

/*
 * Read-only Codex peer gate.
 *
 * The desktop codex_app__list_threads wrapper can stall before its request
 * reaches app-server.  This helper uses the documented local app-server JSONL
 * protocol directly.  It deliberately has no lock, lease, heartbeat, or
 * takeover behavior: it only discovers and reads persisted task state.
 */

const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");

const AUTOMATION_ID = process.env.CODEX_AUTOMATION_ID || "";
const CURRENT_THREAD_ID = process.env.CODEX_THREAD_ID || "";
const EXPECTED_CWD = "/Users/xuanyue202/Documents/project/xiaocao";
const CWD = process.cwd();
const EXPECTED_HOST = process.env.CODEX_REMOTE_HOST || "MacBook-Pro-6.local";
const LIMIT = 20;
const REQUEST_TIMEOUT_MS = 12_000;
const MAX_ATTEMPTS = 2;
const SOURCE_KINDS = [
  "cli",
  "vscode",
  "exec",
  "appServer",
  "subAgent",
  "subAgentReview",
  "subAgentCompact",
  "subAgentThreadSpawn",
  "subAgentOther",
  "unknown",
];

const GATE_STARTED_AT = Date.now();

function fail(code, stage, detail = {}) {
  return {
    schema_version: 1,
    gate_result: "repair_required",
    ownership: "agent",
    retryability: "retryable",
    failure: { category: "control_plane", code, stage },
    detail,
  };
}

function safeJson(value) {
  return JSON.stringify(value, null, 2);
}

function recordAudit(result, attemptCount) {
  const payload = {
    gate_result: result.gate_result,
    attempt_count: attemptCount,
    elapsed_ms: Math.max(0, Date.now() - GATE_STARTED_AT),
  };
  const recorded = spawnSync(
    ".venv/bin/python",
    ["scripts/kol_daily.py", "record-peer-gate"],
    {
      cwd: CWD,
      env: { ...process.env, PYTHONPATH: "src" },
      input: `${JSON.stringify(payload)}\n`,
      encoding: "utf8",
      timeout: REQUEST_TIMEOUT_MS,
    },
  );
  if (recorded.status !== 0) {
    return fail("peer_gate_audit_persist_failed", "peer_gate_audit", {
      recorder_status: recorded.status,
    });
  }
  return { ...result, ...payload };
}

function request(server, method, params, id) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`${method} timeout`));
    }, REQUEST_TIMEOUT_MS);
    server.pending.set(id, { resolve, reject, timer });
    server.child.stdin.write(`${JSON.stringify({ method, id, params })}\n`);
  });
}

function startServer() {
  const child = spawn("codex", ["app-server", "--stdio"], {
    cwd: CWD,
    stdio: ["pipe", "pipe", "pipe"],
    env: process.env,
  });
  const server = { child, pending: new Map(), host: "", buffer: "", stderr: "" };
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => {
    server.stderr = `${server.stderr}${chunk}`.slice(-4000);
  });
  child.stdout.on("data", (chunk) => {
    server.buffer += chunk;
    const lines = server.buffer.split("\n");
    server.buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      let message;
      try {
        message = JSON.parse(line);
      } catch {
        continue;
      }
      if (message.method === "remoteControl/status/changed") {
        const candidate = String(message.params?.serverName || "").trim();
        if (candidate) server.host = candidate;
      }
      if (!Object.prototype.hasOwnProperty.call(message, "id")) continue;
      const slot = server.pending.get(message.id);
      if (!slot) continue;
      server.pending.delete(message.id);
      clearTimeout(slot.timer);
      if (message.error) {
        slot.reject(new Error(`${message.error.code}: ${message.error.message}`));
      } else {
        slot.resolve(message.result);
      }
    }
  });
  child.on("error", (error) => {
    for (const slot of server.pending.values()) {
      clearTimeout(slot.timer);
      slot.reject(error);
    }
    server.pending.clear();
  });
  return server;
}

function stopServer(server) {
  for (const slot of server.pending.values()) {
    clearTimeout(slot.timer);
    slot.reject(new Error("app-server stopped"));
  }
  server.pending.clear();
  try {
    server.child.kill("SIGTERM");
  } catch {
    // The process may already have exited.
  }
}

function userText(turn) {
  return (turn?.items || [])
    .filter((item) => item?.type === "userMessage")
    .map((item) =>
      (item.content || [])
        .filter((part) => part?.type === "text")
        .map((part) => String(part.text || ""))
        .join("\n"),
    )
    .join("\n");
}

function hasTaskComplete(rolloutPath) {
  if (!rolloutPath || !fs.existsSync(rolloutPath)) return null;
  let terminal = false;
  for (const line of fs.readFileSync(rolloutPath, "utf8").split("\n")) {
    if (!line.trim()) continue;
    try {
      const record = JSON.parse(line);
      if (record.type === "event_msg" && record.payload?.type === "task_complete") {
        terminal = true;
      }
      if (
        terminal &&
        ((record.type === "event_msg" &&
          ["task_started", "user_message"].includes(record.payload?.type)) ||
          (record.type === "response_item" &&
            record.payload?.type === "message" &&
            record.payload?.role === "user"))
      ) {
        terminal = false;
      }
    } catch {
      return null;
    }
  }
  return terminal;
}

async function oneAttempt() {
  const server = startServer();
  try {
    const init = await request(
      server,
      "initialize",
      {
        clientInfo: {
          name: "xiaocao-codex-peer-gate",
          title: "Xiaocao read-only peer gate",
          version: "1.0.0",
        },
      },
      1,
    );
    server.child.stdin.write('{"method":"initialized"}\n');
    const listing = await request(
      server,
      "thread/list",
      {
        cursor: null,
        limit: LIMIT,
        sortKey: "updated_at",
        sortDirection: "desc",
        cwd: CWD,
        sourceKinds: SOURCE_KINDS,
        useStateDbOnly: true,
      },
      2,
    );
    const rows = Array.isArray(listing?.data) ? listing.data : null;
    if (!rows) return fail("thread_list_response_invalid", "peer_discovery");
    if (!server.host) {
      return fail("host_identity_unavailable", "peer_discovery", {
        expected_host: EXPECTED_HOST,
        stderr: server.stderr.trim(),
      });
    }
    if (server.host !== EXPECTED_HOST) {
      return fail("host_identity_mismatch", "peer_discovery", {
        expected_host: EXPECTED_HOST,
        observed_host: server.host,
      });
    }

    const candidateRows = rows.filter(
      (row) => row.id && row.id !== CURRENT_THREAD_ID && row.cwd === CWD,
    );
    const candidates = [];
    const readback = [];
    for (const candidate of candidateRows) {
      const result = await request(
        server,
        "thread/read",
        { threadId: candidate.id, includeTurns: true },
        100 + readback.length,
      );
      const thread = result?.thread;
      const turns = Array.isArray(thread?.turns) ? thread.turns : [];
      const promptMatches = turns.some((turn) =>
        userText(turn).includes(`Automation ID: ${AUTOMATION_ID}`),
      );
      if (!thread || thread.id !== candidate.id || thread.cwd !== CWD) {
        return fail("thread_read_identity_mismatch", "peer_readback", {
          thread_id: candidate.id,
        });
      }
      const previewMatches = String(candidate.preview || "").includes(
        `Automation ID: ${AUTOMATION_ID}`,
      );
      if (!promptMatches) {
        if (previewMatches) {
          return fail("thread_prompt_identity_mismatch", "peer_readback", {
            thread_id: candidate.id,
          });
        }
        continue;
      }
      candidates.push(candidate);
      const complete = hasTaskComplete(thread.path);
      if (complete === null) {
        return fail("thread_rollout_unavailable", "peer_readback", {
          thread_id: candidate.id,
        });
      }
      readback.push({ thread_id: candidate.id, task_complete: complete });
      if (!complete) {
        return {
          schema_version: 1,
          gate_result: "no_op",
          ownership: "peer",
          retryability: "not_retryable",
          authoritative_peer_thread_id: candidate.id,
          host: server.host,
          cwd: CWD,
          readback,
        };
      }
    }
    return {
      schema_version: 1,
      gate_result: "pass",
      ownership: "none",
      retryability: "not_retryable",
      host: server.host,
      cwd: CWD,
      candidate_count: candidates.length,
      readback,
      initialize_user_agent: init?.userAgent || "",
    };
  } catch (error) {
    const stderr = server.stderr.trim();
    if (stderr) error.message = `${error.message}; stderr=${stderr}`;
    throw error;
  } finally {
    stopServer(server);
  }
}

async function main() {
  if (!AUTOMATION_ID || !CURRENT_THREAD_ID || !CWD || CWD !== EXPECTED_CWD) {
    console.log(
      safeJson(
        recordAudit(
          fail("gate_identity_incomplete", "peer_discovery"),
          1,
        ),
      ),
    );
    process.exitCode = 2;
    return;
  }
  let last;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    try {
      const result = await oneAttempt();
      const recorded = recordAudit(result, attempt);
      console.log(safeJson(recorded));
      process.exitCode = recorded.gate_result === "repair_required" ? 2 : 0;
      return;
    } catch (error) {
      last = error;
      if (attempt < MAX_ATTEMPTS) await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
  const message = String(last?.message || last || "unknown");
  const code = message.includes("sqlite state runtime")
    ? "app_server_state_runtime_unavailable"
    : message.includes("timeout")
      ? "app_server_request_timeout"
      : "app_server_handler_error";
  const result = recordAudit(
    fail(code, "peer_discovery", { message, attempts: MAX_ATTEMPTS }),
    MAX_ATTEMPTS,
  );
  console.log(safeJson(result));
  process.exitCode = 2;
}

main().catch((error) => {
  const result = recordAudit(
    fail("peer_gate_unhandled_error", "peer_discovery", { message: String(error) }),
    MAX_ATTEMPTS,
  );
  console.log(safeJson(result));
  process.exitCode = 2;
});
