const assert = require("node:assert/strict");
const test = require("node:test");

const { discoverPeers } = require("../scripts/codex_peer_gate.js");

const AUTOMATION_ID = "xiaocao-kol-hourly-low-bandwidth-operation";
const CWD = "/Users/xuanyue202/Documents/project/xiaocao";
const HOST = "MacBook-Pro-6.local";
const NOW_SECONDS = 2_000_000_000;
const LOOKBACK_SECONDS = 12 * 60 * 60;

function candidate(id, { updatedAt = NOW_SECONDS - 60 } = {}) {
  return {
    id,
    cwd: CWD,
    preview: `Automation ID: ${AUTOMATION_ID}`,
    source: "vscode",
    updatedAt,
  };
}

function automationTurn(id, status = "completed") {
  return {
    id,
    status,
    items: [
      {
        type: "userMessage",
        content: [{ type: "text", text: `Automation ID: ${AUTOMATION_ID}` }],
      },
    ],
  };
}

function unrelatedTurn(id, status = "inProgress") {
  return {
    id,
    status,
    items: [
      {
        type: "userMessage",
        content: [{ type: "text", text: "Design Book T selection logic" }],
      },
    ],
  };
}

function thread(
  id,
  {
    source = "vscode",
    parentThreadId = null,
    preview = `Automation ID: ${AUTOMATION_ID}`,
    turns = [automationTurn(`${id}-completed`)],
  } = {},
) {
  return {
    thread: {
      id,
      cwd: CWD,
      path: id,
      source,
      parentThreadId,
      preview,
      turns,
    },
  };
}

function fixture(pages, threadOverrides = new Map()) {
  const cursors = [];
  const reads = [];
  return {
    cursors,
    reads,
    requestFn: async (_server, method, params) => {
      if (method === "thread/list") {
        cursors.push(params.cursor);
        return pages.get(params.cursor);
      }
      if (method === "thread/read") {
        reads.push(params.threadId);
        return threadOverrides.get(params.threadId) || thread(params.threadId);
      }
      throw new Error(`unexpected method ${method}`);
    },
  };
}

test("discovers an active peer beyond the first thread page", async () => {
  const firstPage = Array.from({ length: 20 }, (_, index) =>
    candidate(`terminal-${index}`),
  );
  const active = candidate("active-page-two");
  const pages = new Map([
    [null, { data: firstPage, nextCursor: "page-two" }],
    ["page-two", { data: [active], nextCursor: null }],
  ]);
  const { cursors, requestFn } = fixture(
    pages,
    new Map([
      [
        active.id,
        thread(active.id, {
          turns: [automationTurn(`${active.id}-automation`, "inProgress")],
        }),
      ],
    ]),
  );

  const result = await discoverPeers({
    server: { host: HOST, stderr: "" },
    requestFn,
    automationId: AUTOMATION_ID,
    currentThreadId: "current",
    cwd: CWD,
    expectedHost: HOST,
    readTaskComplete: (path) => path !== active.id,
  });

  assert.equal(result.gate_result, "no_op");
  assert.equal(result.authoritative_peer_thread_id, active.id);
  assert.equal(result.page_count, 2);
  assert.deepEqual(cursors, [null, "page-two"]);
});

test("does not treat an interrupted automation turn as an active peer", async () => {
  const interrupted = candidate("interrupted-without-task-complete");
  const pages = new Map([
    [null, { data: [interrupted], nextCursor: null }],
  ]);
  const { requestFn } = fixture(
    pages,
    new Map([
      [
        interrupted.id,
        thread(interrupted.id, {
          turns: [automationTurn(`${interrupted.id}-automation`, "interrupted")],
        }),
      ],
    ]),
  );

  const result = await discoverPeers({
    server: { host: HOST, stderr: "" },
    requestFn,
    automationId: AUTOMATION_ID,
    currentThreadId: "current",
    cwd: CWD,
    expectedHost: HOST,
    readTaskComplete: () => false,
  });

  assert.equal(result.gate_result, "pass");
  assert.equal(result.candidate_count, 1);
  assert.equal(result.readback[0].latest_turn_status, "interrupted");
});

test("stops peer discovery at the twelve-hour update boundary", async () => {
  const recent = candidate("recent-terminal");
  const old = candidate("old-in-progress", {
    updatedAt: NOW_SECONDS - LOOKBACK_SECONDS - 1,
  });
  const pages = new Map([
    [null, { data: [recent, old], nextCursor: "older-page" }],
    [
      "older-page",
      {
        data: [
          candidate("older-in-progress", {
            updatedAt: NOW_SECONDS - LOOKBACK_SECONDS - 2,
          }),
        ],
        nextCursor: null,
      },
    ],
  ]);
  const { cursors, reads, requestFn } = fixture(
    pages,
    new Map([
      [
        old.id,
        thread(old.id, {
          turns: [automationTurn(`${old.id}-automation`, "inProgress")],
        }),
      ],
    ]),
  );

  const result = await discoverPeers({
    server: { host: HOST, stderr: "" },
    requestFn,
    automationId: AUTOMATION_ID,
    currentThreadId: "current",
    cwd: CWD,
    expectedHost: HOST,
    readTaskComplete: () => false,
    nowSeconds: NOW_SECONDS,
  });

  assert.equal(result.gate_result, "pass");
  assert.equal(result.candidate_count, 1);
  assert.deepEqual(cursors, [null]);
  assert.deepEqual(reads, [recent.id]);
});

test("ignores a subagent that inherited the automation prompt", async () => {
  const inherited = candidate("inherited-subagent");
  const pages = new Map([
    [null, { data: [inherited], nextCursor: null }],
  ]);
  const { requestFn } = fixture(
    pages,
    new Map([
      [
        inherited.id,
        thread(inherited.id, {
          source: {
            subAgent: {
              threadSpawn: {
                parentThreadId: "parent",
              },
            },
          },
          parentThreadId: "parent",
          turns: [
            automationTurn(`${inherited.id}-inherited`, "completed"),
            unrelatedTurn(`${inherited.id}-book-t`, "interrupted"),
          ],
        }),
      ],
    ]),
  );

  const result = await discoverPeers({
    server: { host: HOST, stderr: "" },
    requestFn,
    automationId: AUTOMATION_ID,
    currentThreadId: "current",
    cwd: CWD,
    expectedHost: HOST,
    readTaskComplete: () => false,
  });

  assert.equal(result.gate_result, "pass");
  assert.equal(result.candidate_count, 0);
});

test("ignores automation wording that appears only in a later turn", async () => {
  const unrelated = candidate("unrelated-top-level");
  const pages = new Map([
    [null, { data: [unrelated], nextCursor: null }],
  ]);
  const { requestFn } = fixture(
    pages,
    new Map([
      [
        unrelated.id,
        thread(unrelated.id, {
          preview: "Design Book T selection logic",
          turns: [
            unrelatedTurn(`${unrelated.id}-book-t`, "completed"),
            automationTurn(`${unrelated.id}-quoted`, "inProgress"),
          ],
        }),
      ],
    ]),
  );

  const result = await discoverPeers({
    server: { host: HOST, stderr: "" },
    requestFn,
    automationId: AUTOMATION_ID,
    currentThreadId: "current",
    cwd: CWD,
    expectedHost: HOST,
    readTaskComplete: () => false,
  });

  assert.equal(result.gate_result, "pass");
  assert.equal(result.candidate_count, 0);
});

test("passes only after every thread page has no incomplete top-level peer", async () => {
  const firstPage = Array.from({ length: 20 }, (_, index) =>
    candidate(`terminal-${index}`),
  );
  const pages = new Map([
    [null, { data: firstPage, nextCursor: "page-two" }],
    ["page-two", { data: [candidate("terminal-20")], nextCursor: null }],
  ]);
  const { requestFn } = fixture(pages);

  const result = await discoverPeers({
    server: { host: HOST, stderr: "" },
    requestFn,
    automationId: AUTOMATION_ID,
    currentThreadId: "current",
    cwd: CWD,
    expectedHost: HOST,
    readTaskComplete: () => true,
  });

  assert.equal(result.gate_result, "pass");
  assert.equal(result.candidate_count, 21);
  assert.equal(result.page_count, 2);
});

test("fails closed when preview and first-turn identity disagree", async () => {
  const inconsistent = candidate("inconsistent-identity");
  const pages = new Map([
    [null, { data: [inconsistent], nextCursor: null }],
  ]);
  const { requestFn } = fixture(
    pages,
    new Map([
      [
        inconsistent.id,
        thread(inconsistent.id, {
          turns: [unrelatedTurn(`${inconsistent.id}-unrelated`, "inProgress")],
        }),
      ],
    ]),
  );

  const result = await discoverPeers({
    server: { host: HOST, stderr: "" },
    requestFn,
    automationId: AUTOMATION_ID,
    currentThreadId: "current",
    cwd: CWD,
    expectedHost: HOST,
    readTaskComplete: () => false,
  });

  assert.equal(result.gate_result, "repair_required");
  assert.equal(result.failure.code, "thread_prompt_identity_mismatch");
});

test("fails closed when thread pagination is incomplete", async () => {
  const pages = new Map([[null, { data: [] }]]);
  const { requestFn } = fixture(pages);

  const result = await discoverPeers({
    server: { host: HOST, stderr: "" },
    requestFn,
    automationId: AUTOMATION_ID,
    currentThreadId: "current",
    cwd: CWD,
    expectedHost: HOST,
    readTaskComplete: () => true,
  });

  assert.equal(result.gate_result, "repair_required");
  assert.equal(result.failure.code, "thread_list_response_invalid");
});

test("fails closed when the app-server repeats a cursor", async () => {
  const pages = new Map([
    [null, { data: [], nextCursor: "repeat" }],
    ["repeat", { data: [], nextCursor: "repeat" }],
  ]);
  const { requestFn } = fixture(pages);

  const result = await discoverPeers({
    server: { host: HOST, stderr: "" },
    requestFn,
    automationId: AUTOMATION_ID,
    currentThreadId: "current",
    cwd: CWD,
    expectedHost: HOST,
    readTaskComplete: () => true,
  });

  assert.equal(result.gate_result, "repair_required");
  assert.equal(result.failure.code, "thread_list_cursor_invalid");
});
