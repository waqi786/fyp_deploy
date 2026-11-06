self.addEventListener("message", (event) => {
  if (event.data?.type === "CACHE_READING_ITEM" && event.data.payload?.key) {
    event.waitUntil(
      caches.open("resora-reading-v1").then((cache) =>
        cache.put(
          `/offline/${event.data.payload.key}`,
          new Response(JSON.stringify(event.data.payload), {
            headers: { "Content-Type": "application/json" },
          })
        )
      )
    );
  }
});

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open("resora-static-v1").then((cache) => cache.addAll(["/", "/manifest.webmanifest", "/icon.svg"]))
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(event.request)
        .then((response) => {
          const isReadingAsset = event.request.url.includes("/api/v1/summaries") || event.request.url.includes("/api/v1/documents");
          if (isReadingAsset) {
            const copy = response.clone();
            event.waitUntil(caches.open("resora-reading-v1").then((cache) => cache.put(event.request, copy)));
          }
          return response;
        })
        .catch(() => caches.match("/"));
    })
  );
});

self.addEventListener("sync", (event) => {
  if (event.tag === "resora-offline-sync") {
    event.waitUntil(Promise.resolve());
  }
});
