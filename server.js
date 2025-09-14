// server.js (webhook version)
const express = require("express");
const fetch = (...args) => import("node-fetch").then(({default: f}) => f(...args));
const app = express();

app.use(express.text({ type: ["text/*", "text/plain"], limit: "1mb" }));
app.use(express.json({ limit: "1mb" }));

const WEBHOOK = process.env.DISCORD_WEBHOOK_URL; // set this in your env
let latestPost = { text: null, updatedAt: null };

app.post("/", async (req, res) => {
  const text = typeof req.body === "string"
    ? req.body
    : (req.body && req.body.text) || "";

  if (!text.trim()) return res.status(400).json({ error: "empty text" });

  latestPost = { text, updatedAt: new Date().toISOString() };

  // Push to Discord via webhook
  try {
    const r = await fetch(WEBHOOK, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text })
    });
    if (!r.ok) {
      const body = await r.text();
      return res.status(502).json({ error: "discord webhook failed", status: r.status, body });
    }
  } catch (e) {
    return res.status(502).json({ error: "discord webhook error", detail: e.message });
  }

  res.status(201).json({ ok: true, ...latestPost });
});

app.get("/latest", (req, res) => {
  if (!latestPost.text) return res.status(204).end();
  res.json(latestPost);
});

app.listen(process.env.PORT || 3000, () =>
  console.log("http://localhost:3000 ready"));
