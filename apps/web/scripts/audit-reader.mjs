import fs from "node:fs/promises";
import path from "node:path";

const port = Number(process.env.EDGE_CDP_PORT || 9223);
const baseUrl = process.env.RESORA_URL || "http://127.0.0.1:5173";
const outDir = path.resolve("test-shots", "reader");

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

async function capture(client, name, scrollY) {
  await client.send("Runtime.evaluate", {
    expression: `(() => {
      const pane = document.querySelector('.main-scroll-pane') || document.scrollingElement;
      pane.scrollTo({ top: ${scrollY}, behavior: "instant" });
    })()`,
  });
  await new Promise((resolve) => setTimeout(resolve, 600));
  const screenshot = await client.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await fs.writeFile(path.join(outDir, `${name}.png`), Buffer.from(screenshot.data, "base64"));
}

await fs.mkdir(outDir, { recursive: true });
const target = await createTarget();
const client = await connect(target.webSocketDebuggerUrl);
await client.send("Page.enable");
await client.send("Runtime.enable");
await client.send("Page.addScriptToEvaluateOnNewDocument", {
  source: `
    window.localStorage.setItem('resora-language-source', 'settings');
    window.localStorage.setItem('resora-language', 'en');
    window.localStorage.setItem('resora-theme', 'dark');
  `,
});
await client.send("Emulation.setDeviceMetricsOverride", {
  width: 1440,
  height: 1000,
  deviceScaleFactor: 1,
  mobile: false,
});
await client.send("Page.navigate", { url: `${baseUrl}/summaries?audit=reader` });
await new Promise((resolve) => setTimeout(resolve, 2200));

await capture(client, "top", 0);
await capture(client, "middle", 720);
await capture(client, "lower", 1450);

const layout = await client.send("Runtime.evaluate", {
  returnByValue: true,
  expression: `(() => {
    const broken = [...document.querySelectorAll('button, input, select, textarea, .panel-surface, .glass-surface')]
      .map((el) => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return {
          tag: el.tagName.toLowerCase(),
          className: el.className ? String(el.className).slice(0, 80) : '',
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          overflowX: el.scrollWidth > Math.ceil(rect.width) + 2,
          display: style.display,
        };
      })
      .filter((item) => item.display !== 'none' && item.width > 0 && item.overflowX);
    return { broken };
  })()`,
});

await fs.writeFile(path.join(outDir, "layout.json"), JSON.stringify(layout.result.value, null, 2));
client.close();
console.log(JSON.stringify(layout.result.value, null, 2));
