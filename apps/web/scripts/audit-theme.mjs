import fs from "node:fs/promises";
import path from "node:path";

const port = Number(process.env.EDGE_CDP_PORT || 9223);
const baseUrl = process.env.RESORA_URL || "http://127.0.0.1:5173";
const outDir = path.resolve("test-shots", "themes");
const themes = [
  ["dark", 0],
  ["light", 1],
  ["contrast", 2],
];

function requestJson(targetPath, init = {}) {
  return fetch(`http://127.0.0.1:${port}${targetPath}`, init).then((response) => {
    if (!response.ok) throw new Error(`${targetPath} ${response.status}`);
    return response.json();
  });
}

async function createTarget() {
  try {
    return await requestJson(`/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" });
  } catch {
    return requestJson(`/json/new?${encodeURIComponent("about:blank")}`);
  }
}

async function connect(wsUrl) {
  const socket = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  let id = 0;
  const pending = new Map();
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
    }
  });

  return {
    send(method, params = {}) {
      const messageId = ++id;
      socket.send(JSON.stringify({ id: messageId, method, params }));
      return new Promise((resolve, reject) => pending.set(messageId, { resolve, reject }));
    },
    close() {
      socket.close();
    },
  };
}

await fs.mkdir(outDir, { recursive: true });
const target = await createTarget();
const client = await connect(target.webSocketDebuggerUrl);
await client.send("Page.enable");
await client.send("Runtime.enable");
await client.send("Emulation.setDeviceMetricsOverride", {
  width: 1440,
  height: 1000,
  deviceScaleFactor: 1,
  mobile: false,
});

await client.send("Page.navigate", { url: `${baseUrl}/?fresh=theme-audit` });
await new Promise((resolve) => setTimeout(resolve, 1800));
await client.send("Runtime.evaluate", { expression: "localStorage.removeItem('resora-language-source'); localStorage.removeItem('resora-language');" });

const report = [];
for (const [theme, index] of themes) {
  await client.send("Runtime.evaluate", { expression: "document.querySelector('.sidebar-footer button')?.click();" });
  await new Promise((resolve) => setTimeout(resolve, 500));
  await client.send("Runtime.evaluate", {
    expression: `(() => {
      const themeSection = document.querySelectorAll('.settings-section')[0];
      const buttons = [...(themeSection?.querySelectorAll('button') || [])];
      buttons[${index}]?.click();
    })()`,
  });
  await new Promise((resolve) => setTimeout(resolve, 600));
  const result = await client.send("Runtime.evaluate", {
    returnByValue: true,
    expression: `(() => ({
      theme: document.body.dataset.theme,
      saved: localStorage.getItem('resora-theme'),
      background: getComputedStyle(document.body).backgroundColor,
      text: getComputedStyle(document.body).color
    }))()`,
  });
  report.push(result.result.value);
  const screenshot = await client.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await fs.writeFile(path.join(outDir, `${theme}.png`), Buffer.from(screenshot.data, "base64"));
  await client.send("Runtime.evaluate", { expression: "document.querySelector('.settings-overlay')?.click();" });
}

await fs.writeFile(path.join(outDir, "report.json"), JSON.stringify(report, null, 2));
client.close();
console.log(JSON.stringify(report, null, 2));
