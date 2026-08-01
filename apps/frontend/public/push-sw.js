/* global self */
self.addEventListener("push", (event) => {
  let payload = { title: "Домовой", body: "Новое уведомление" };
  try {
    payload = { ...payload, ...event.data.json() };
  } catch {
    if (event.data) payload.body = event.data.text();
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icon.svg",
      badge: "/icon.svg",
      data: { url: "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      const current = clients.find((client) => "focus" in client);
      if (current) return current.focus();
      return self.clients.openWindow(event.notification.data?.url || "/");
    }),
  );
});
