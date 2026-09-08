#!/usr/bin/env node
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";

const DEFAULT_TIMEOUT_MS = 45_000;
const HOOK_COMMAND_RE = /agent-(?:memory-hook|window-label|codex-hud-launcher)/;

function parseArgs(argv) {
  const options = { hooks: false, timeoutMs: DEFAULT_TIMEOUT_MS };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--hooks") {
      options.hooks = true;
    } else if (arg === "--timeout-ms") {
      const value = Number(argv[i + 1]);
      if (!Number.isFinite(value) || value <= 0) {
        throw new Error("--timeout-ms requires a positive number");
      }
      options.timeoutMs = value;
      i += 1;
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return options;
}

function printHelp() {
  console.log(`Usage: node scripts/check-codex-apps.mjs [--hooks] [--timeout-ms MS]

Read-only Codex Apps health check via "codex app-server --stdio".

Options:
  --hooks          Also report matching user hook commands for memory/window label hooks.
  --timeout-ms MS  Per-request timeout. Default: ${DEFAULT_TIMEOUT_MS}.
`);
}

function redact(value) {
  if (value == null) {
    return value;
  }
  return String(value)
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "<email-redacted>")
    .replace(/sk-[A-Za-z0-9_-]{8,}/g, "<token-redacted>")
    .replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, "<jwt-redacted>")
    .replace(/[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{24,}/g, "<token-redacted>");
}

function summarizeError(value) {
  const text = redact(value);
  const statusMatch = text.match(/Request failed with status \d{3} [^:]+/);
  if (statusMatch) {
    return statusMatch[0];
  }
  return text.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 300);
}

function summarizeServerStatus(server) {
  return {
    name: redact(server.name),
    authStatus: redact(server.authStatus),
    toolsCount: server.tools && typeof server.tools === "object" ? Object.keys(server.tools).length : 0,
    toolsError: server.toolsError ? redact(server.toolsError) : null,
  };
}

function summarizeAppList(response) {
  if (response.error) {
    return { error: summarizeError(response.error) };
  }
  const data = Array.isArray(response.data) ? response.data : [];
  return {
    count: data.length,
    nextCursorPresent: Boolean(response.nextCursor),
    accessibleCount: data.filter((app) => app?.isAccessible === true).length,
    enabledCount: data.filter((app) => app?.isEnabled === true).length,
  };
}

function summarizeHook(hook) {
  return {
    key: redact(hook.key),
    currentHash: redact(hook.currentHash),
    trustStatus: redact(hook.trustStatus),
    enabled: Boolean(hook.enabled),
    eventName: redact(hook.eventName),
    command: redact(hook.command),
  };
}

function matchingUserHookCommands(response) {
  const entries = Array.isArray(response.data) ? response.data : [];
  return entries.flatMap((entry) =>
    (Array.isArray(entry.hooks) ? entry.hooks : [])
      .filter((hook) => hook?.handlerType === "command")
      .filter((hook) => typeof hook.command === "string" && HOOK_COMMAND_RE.test(hook.command))
      .filter((hook) => hook.isManaged !== true)
      .map(summarizeHook),
  );
}

class AppServerProbe {
  constructor(timeoutMs) {
    this.timeoutMs = timeoutMs;
    this.child = spawn("codex", ["app-server", "--stdio"], {
      cwd: process.cwd(),
      env: { ...process.env },
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.nextId = 1;
    this.pending = new Map();
    this.stderr = "";
    this.notifications = 0;
    this.serverRequests = [];
    this.exited = false;

    const stdout = createInterface({ input: this.child.stdout });
    stdout.on("line", (line) => this.onLine(line));
    this.child.stderr.on("data", (chunk) => {
      this.stderr += chunk.toString("utf8");
    });
    this.child.on("exit", (code, signal) => {
      this.exited = true;
      const error = new Error(`app-server exited before response: ${code ?? signal}`);
      for (const waiter of this.pending.values()) {
        waiter.reject(error);
      }
      this.pending.clear();
    });
  }

  onLine(line) {
    let message;
    try {
      message = JSON.parse(line);
    } catch (error) {
      return;
    }

    if (Object.hasOwn(message, "id") && (Object.hasOwn(message, "result") || Object.hasOwn(message, "error"))) {
      const waiter = this.pending.get(String(message.id));
      if (waiter) {
        this.pending.delete(String(message.id));
        waiter.resolve(message);
      }
      return;
    }

    if (message.method && Object.hasOwn(message, "id")) {
      this.serverRequests.push(redact(message.method));
      this.child.stdin.write(
        `${JSON.stringify({
          jsonrpc: "2.0",
          id: message.id,
          error: { code: -32601, message: "check-codex-apps does not service server requests" },
        })}\n`,
      );
      return;
    }

    if (message.method) {
      this.notifications += 1;
    }
  }

  request(method, params) {
    const id = String(this.nextId);
    this.nextId += 1;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} timed out after ${this.timeoutMs}ms`));
      }, this.timeoutMs);

      this.pending.set(id, {
        resolve: (message) => {
          clearTimeout(timer);
          if (message.error) {
            reject(new Error(`${method} failed: ${summarizeError(message.error.message)} (${message.error.code})`));
          } else {
            resolve(message.result ?? {});
          }
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        },
      });

      this.child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
    });
  }

  async close() {
    try {
      this.child.stdin.end();
    } catch {
      // Best-effort cleanup; SIGTERM/SIGKILL below handle a stuck process.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
    if (!this.exited) {
      this.child.kill("SIGTERM");
      await new Promise((resolve) => setTimeout(resolve, 2_000));
    }
    if (!this.exited) {
      this.child.kill("SIGKILL");
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
}

async function run() {
  const options = parseArgs(process.argv.slice(2));
  const probe = new AppServerProbe(options.timeoutMs);
  const startedAt = Date.now();
  try {
    await probe.request("initialize", {
      clientInfo: { name: "check-codex-apps", title: "Codex Apps Check", version: "0.0.0" },
      capabilities: {
        experimentalApi: true,
        requestAttestation: false,
        optOutNotificationMethods: [],
        extensions: null,
      },
    });

    const statuses = await probe.request("mcpServerStatus/list", {
      cursor: null,
      limit: 100,
      detail: "full",
      threadId: null,
    });

    let appList;
    try {
      appList = await probe.request("app/list", {
        cursor: null,
        limit: 100,
        threadId: null,
        forceRefetch: false,
      });
    } catch (error) {
      appList = { error: error.message };
    }

    const mcpServers = (Array.isArray(statuses.data) ? statuses.data : []).map(summarizeServerStatus);
    const codexApps = mcpServers.find((server) => server.name === "codex_apps");
    const appListSummary = summarizeAppList(appList);
    const ok =
      Boolean(codexApps) &&
      codexApps.authStatus !== "notLoggedIn" &&
      codexApps.toolsCount > 0 &&
      codexApps.toolsError == null &&
      appListSummary.error == null;

    const output = {
      ok,
      mcpServers,
      appList: appListSummary,
      durationMs: Date.now() - startedAt,
    };

    if (options.hooks) {
      const hooks = await probe.request("hooks/list", { cwds: [process.cwd()] });
      output.hooks = matchingUserHookCommands(hooks);
    }

    console.log(JSON.stringify(output, null, 2));
    if (!ok) {
      process.exitCode = 1;
    }
  } catch (error) {
    console.log(
      JSON.stringify(
        {
          ok: false,
          error: summarizeError(error.message),
          stderr: probe.stderr ? summarizeError(probe.stderr) : "",
          durationMs: Date.now() - startedAt,
        },
        null,
        2,
      ),
    );
    process.exitCode = 1;
  } finally {
    await probe.close();
  }
}

run().catch((error) => {
  console.error(redact(error.message));
  process.exit(1);
});
