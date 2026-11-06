async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

document.getElementById("send").addEventListener("click", async () => {
  const status = document.getElementById("status");
  const selection = document.getElementById("selection").value;
  const tab = await getActiveTab();
  const response = await fetch("http://localhost:8000/api/v1/developer/extension/intake", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: tab.title || "Untitled tab",
      url: tab.url || "",
      selection,
    }),
  });
  const data = await response.json();
  status.textContent = `${data.status}: ${data.saved_item_id}`;
});

