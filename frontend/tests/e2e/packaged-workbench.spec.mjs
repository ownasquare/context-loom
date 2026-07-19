import { expect, test } from "@playwright/test";
import { execFile, spawn } from "node:child_process";
import { mkdir, mkdtemp, readdir, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const execFileAsync = promisify(execFile);
let serverProcess;
let serverUrl;
let temporaryRoot;
let projectRoot;
let serverOutput = "";

test.beforeAll(async () => {
  const port = await availablePort();
  serverUrl = `http://127.0.0.1:${port}`;
  temporaryRoot = await mkdtemp(join(tmpdir(), "context-loom-packaged-e2e-"));
  projectRoot = join(temporaryRoot, "Project with spaces Ω");
  const sourceDirectory = join(projectRoot, "src");
  await mkdir(sourceDirectory, { recursive: true });
  await writeFile(
    join(projectRoot, "README.md"),
    "# Editorial desk\n\nEvery prepared request stays local until a person copies it.\n",
    "utf8",
  );
  await writeFile(
    join(sourceDirectory, "planner.py"),
    "BUDGET = 4000\n\ndef local_plan(message: str) -> str:\n    return message\n",
    "utf8",
  );

  const artifactDirectory = join(temporaryRoot, "artifacts");
  const environmentDirectory = join(temporaryRoot, "venv");
  await mkdir(artifactDirectory);
  await runCommand("uv", ["build", "--wheel", "--out-dir", artifactDirectory], repoRoot);
  const wheels = (await readdir(artifactDirectory)).filter((name) => name.endsWith(".whl"));
  if (wheels.length !== 1) {
    throw new Error(`Expected one wheel for packaged E2E, found ${wheels.length}.`);
  }
  const python = virtualEnvironmentPython(environmentDirectory);
  await runCommand("uv", ["venv", "--python", "3.12", environmentDirectory], temporaryRoot);
  await runCommand(
    "uv",
    ["pip", "install", "--python", python, join(artifactDirectory, wheels[0])],
    temporaryRoot,
  );

  serverProcess = spawn(
    python,
    [
      "-m",
      "context_loom",
      "--home",
      join(temporaryRoot, "state"),
      "serve",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
    ],
    { cwd: temporaryRoot, env: isolatedEnvironment() },
  );
  serverProcess.stdout.on("data", (chunk) => {
    serverOutput = `${serverOutput}${chunk}`.slice(-12_000);
  });
  serverProcess.stderr.on("data", (chunk) => {
    serverOutput = `${serverOutput}${chunk}`.slice(-12_000);
  });

  await waitForServer(`${serverUrl}/healthz`);
});

test.afterAll(async () => {
  if (serverProcess && serverProcess.exitCode === null) {
    serverProcess.kill("SIGTERM");
    await Promise.race([
      new Promise((resolveExit) => serverProcess.once("exit", resolveExit)),
      new Promise((resolveTimeout) => setTimeout(resolveTimeout, 3_000)),
    ]);
    if (serverProcess.exitCode === null) {
      serverProcess.kill("SIGKILL");
    }
  }
  if (temporaryRoot) {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test("onboards a real local project and preserves one conversation across two prepared messages", async ({ page }) => {
  await page.goto(`${serverUrl}/hydrate`);
  await expect(page.getByRole("heading", { name: "Add your first project" })).toBeVisible();

  const projectFolder = page.getByRole("textbox", { name: "Project folder", exact: true });
  await expect(projectFolder).toHaveAttribute("required", "");
  await projectFolder.fill(projectRoot);
  await page.getByText("Change project name (optional)").click();
  await page.getByLabel("Project name").fill("Editorial desk");
  await page.getByRole("button", { name: "Add and scan project" }).click();
  await expect(page.getByRole("heading", { name: "Prepare message" })).toBeVisible();

  await page.locator("details.conversation-selector > summary").click();
  await page.getByLabel("Conversation name").fill("Release notes review");
  const firstMessage = "Review src/planner.py. Preserve BUDGET = 4000 and keep the workflow offline.";
  await page.getByRole("textbox", { name: "What do you want to do?" }).fill(firstMessage);
  await prepareAndWait(page);
  await expect(page.getByRole("heading", { name: "Prepared request" })).toBeVisible();
  await page.getByText("Message integrity and technical details").click();
  await expect(page.getByTestId("exact-message")).toHaveText(firstMessage);

  const secondMessage = "Check README.md and keep the statement that a person copies the request.";
  await page.getByRole("textbox", { name: "What do you want to do?" }).fill(secondMessage);
  await prepareAndWait(page);

  await page.getByRole("link", { name: "Savings" }).first().click();
  await expect(page.getByRole("heading", { name: "Savings" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Release notes review/ })).toContainText("2 messages");
  await expect(page.getByText("2 prepared messages")).toBeVisible();

  await recordUsage(page, "OpenAI", "gpt-5", "1200");
  await expect(page.getByRole("button", { name: "Add provider usage" })).toBeVisible();
  await recordUsage(page, "OpenAI", "gpt-5", "900");
  await expect(
    page.getByRole("button", { name: "Usage complete", exact: true }),
  ).toBeDisabled();
  await expect(page.getByText("2,100").first()).toBeVisible();
});

async function prepareAndWait(page) {
  const completed = page.waitForResponse((response) => (
    response.request().method() === "POST"
      && response.url().endsWith("/api/v1/hydrations")
      && response.status() === 201
  ));
  await page.getByRole("button", { name: "Prepare request" }).click();
  await completed;
  await expect(page.getByRole("button", { name: "Prepare request" })).toBeEnabled();
}

async function recordUsage(page, provider, model, inputTokens) {
  await page.getByRole("button", { name: "Add provider usage" }).click();
  await expect(page.getByLabel("Prepared message")).toHaveValue(/hydration-/);
  await page.getByLabel("Provider").fill(provider);
  await page.getByLabel("Model").fill(model);
  await page.getByLabel("Input tokens", { exact: true }).fill(inputTokens);
  const completed = page.waitForResponse((response) => (
    response.request().method() === "POST"
      && response.url().includes("/api/v1/threads/")
      && response.url().endsWith("/usage")
      && response.status() === 200
  ));
  await page.getByRole("button", { name: "Save usage" }).click();
  await completed;
}

async function availablePort() {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close((error) => {
        if (error) {
          reject(error);
        } else if (port === null) {
          reject(new Error("Could not reserve a packaged-test port"));
        } else {
          resolvePort(port);
        }
      });
    });
  });
}

async function runCommand(command, arguments_, cwd) {
  try {
    await execFileAsync(command, arguments_, {
      cwd,
      env: isolatedEnvironment(),
      maxBuffer: 20 * 1024 * 1024,
    });
  } catch (error) {
    const stdout = typeof error?.stdout === "string" ? error.stdout : "";
    const stderr = typeof error?.stderr === "string" ? error.stderr : "";
    throw new Error(`Command failed: ${command} ${arguments_.join(" ")}\n${stdout}${stderr}`);
  }
}

function isolatedEnvironment() {
  const environment = {
    ...process.env,
    CONTEXT_LOOM_ALLOW_OUTBOUND: "false",
    CONTEXT_LOOM_RETAIN_MESSAGE_CONTENT: "false",
    NO_COLOR: "1",
    PYTHONNOUSERSITE: "1",
  };
  delete environment.CONTEXT_LOOM_PROXY_UPSTREAM_URL;
  delete environment.PYTHONPATH;
  return environment;
}

function virtualEnvironmentPython(environmentDirectory) {
  return process.platform === "win32"
    ? join(environmentDirectory, "Scripts", "python.exe")
    : join(environmentDirectory, "bin", "python");
}

async function waitForServer(healthUrl) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (serverProcess.exitCode !== null) {
      throw new Error(`Packaged server exited before readiness.\n${serverOutput}`);
    }
    try {
      const response = await fetch(healthUrl);
      if (response.ok) {
        return;
      }
    } catch {
      // The server is still starting.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  }
  throw new Error(`Packaged server did not become ready.\n${serverOutput}`);
}
