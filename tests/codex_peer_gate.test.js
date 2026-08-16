const assert = require("node:assert/strict");
const test = require("node:test");

const { discoverPeers } = require("../scripts/codex_peer_gate.js");

const AUTOMATION_ID = "xiaocao-kol-hourly-low-bandwidth-operation";
const CWD = "/Users/xuanyue202/Documents/project/xiaocao";
const HOST = "MacBook-Pro-6.local";

function candidate(id) {
  return { id, cwd: CWD, preview: `Automation ID: ${AUTOMATION_ID}` };
}

function thread(id) {
  return {
    thread: {
      id,
      cwd: CWD,
      path: id,
      turns: [
        {
          items: [
            {
              type: "userMessage",
              content: [
                { type: "text", text: `Automation ID: ${AUTOMATION_ID}` },
              ],
            },
          ],
        },
      ],
    },
  };
}

function fixture(pages) {
  const cursors = [];
  return {
    cursors,
    requestFn: async (_server, method, params) => {
      if (method === "thread/list") {
        cursors.push(params.cursor);
        return pages.get(params.cursor);
      }
      if (method === "thread/read") return thread(params.threadId);
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
  const { cursors, requestFn } = fixture(pages);

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

test("passes only after every thread page is terminal", async () => {
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
