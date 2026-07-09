/*
 * Auphere web chat widget — self-contained loader.
 *
 * Install (one line in the site's <head> or footer):
 *   <script src="https://api.auphere.com/widget.js"
 *           data-public-key="wgt_pub_xxx" async></script>
 *
 * The loader is served by the Auphere API and defaults its API calls to the
 * same origin it was loaded from. Optional override:
 *   data-api-base="https://api.auphere.com"
 *
 * The widget mounts a floating bubble + chat panel inside a Shadow DOM so
 * the host site's CSS can't leak in and ours can't leak out. It talks to
 * the public /v1/widget/* endpoints: mint a session, POST the visitor's
 * messages, and poll for the agent's replies (~1.2s). The anonymous
 * session id is stored in localStorage for cart/history continuity.
 */
(function () {
  "use strict";

  var script =
    document.currentScript ||
    (function () {
      var s = document.getElementsByTagName("script");
      return s[s.length - 1];
    })();

  var PUBLIC_KEY = script && script.getAttribute("data-public-key");
  if (!PUBLIC_KEY) {
    console.error("[auphere] widget.js: missing data-public-key");
    return;
  }
  // API origin: explicit data-api-base wins; otherwise use the origin the
  // loader was served from (the API serves widget.js itself), falling back
  // to the production API host.
  function scriptOrigin() {
    try {
      return script && script.src ? new URL(script.src).origin : "";
    } catch (e) {
      return "";
    }
  }
  var API_BASE = (
    (script && script.getAttribute("data-api-base")) ||
    scriptOrigin() ||
    "https://api.auphere.com"
  ).replace(/\/+$/, "");

  var STORAGE_KEY = "auphere_widget_session:" + PUBLIC_KEY;
  var POLL_MS = 1200;

  // ── session state ────────────────────────────────────────────────────
  var token = null; // in-memory session JWT (never persisted)
  var sessionId = null;
  var config = { greeting: null, appearance: {} };
  var lastTs = null; // ISO of the newest message we've rendered
  var seen = {}; // message id -> true (dedupe)
  var pollTimer = null;
  var open = false;
  var minting = null; // in-flight session promise (coalesce)

  try {
    sessionId = window.localStorage.getItem(STORAGE_KEY) || null;
  } catch (e) {
    sessionId = null;
  }

  // ── DOM (Shadow root) ────────────────────────────────────────────────
  var host = document.createElement("div");
  host.setAttribute("data-auphere-widget", "");
  var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
  document.body.appendChild(host);

  var accent = "#111827";
  var els = {};

  function css() {
    return (
      "" +
      ":host{all:initial}" +
      "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}" +
      ".bubble{position:fixed;bottom:20px;right:20px;width:60px;height:60px;border-radius:50%;background:" +
      accent +
      ";color:#fff;border:none;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.25);display:flex;align-items:center;justify-content:center;z-index:2147483000}" +
      ".bubble svg{width:28px;height:28px;fill:#fff}" +
      ".panel{position:fixed;bottom:92px;right:20px;width:370px;max-width:calc(100vw - 32px);height:560px;max-height:calc(100vh - 120px);background:#fff;border-radius:16px;box-shadow:0 12px 48px rgba(0,0,0,.28);display:none;flex-direction:column;overflow:hidden;z-index:2147483000}" +
      ".panel.open{display:flex}" +
      ".hdr{background:" +
      accent +
      ";color:#fff;padding:14px 16px;font-weight:600;font-size:15px;display:flex;align-items:center;justify-content:space-between}" +
      ".hdr button{background:transparent;border:none;color:#fff;font-size:20px;cursor:pointer;line-height:1}" +
      ".log{flex:1;overflow-y:auto;padding:14px;background:#f6f7f9;display:flex;flex-direction:column;gap:8px}" +
      ".msg{max-width:82%;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.4;white-space:pre-wrap;word-wrap:break-word}" +
      ".msg.in{align-self:flex-start;background:#fff;color:#111;border:1px solid #e5e7eb;border-bottom-left-radius:4px}" +
      ".msg.out{align-self:flex-end;background:" +
      accent +
      ";color:#fff;border-bottom-right-radius:4px}" +
      ".btns{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}" +
      ".btns button{background:#fff;border:1px solid " +
      accent +
      ";color:" +
      accent +
      ";border-radius:16px;padding:6px 12px;font-size:13px;cursor:pointer}" +
      ".foot{display:flex;gap:8px;padding:10px;border-top:1px solid #eee;background:#fff}" +
      ".foot input{flex:1;border:1px solid #d1d5db;border-radius:20px;padding:9px 14px;font-size:14px;outline:none}" +
      ".foot button{background:" +
      accent +
      ";border:none;color:#fff;border-radius:20px;padding:0 16px;cursor:pointer;font-size:14px}" +
      ".typing{align-self:flex-start;color:#888;font-size:13px;padding:4px 6px}"
    );
  }

  function h(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }

  function render() {
    accent = (config.appearance && config.appearance.accent_color) || accent;
    var style = document.createElement("style");
    style.textContent = css();

    var bubble = h("button", "bubble");
    bubble.setAttribute("aria-label", "Chat");
    bubble.innerHTML =
      '<svg viewBox="0 0 24 24"><path d="M12 3C6.5 3 2 6.8 2 11.5c0 2.2 1 4.2 2.7 5.7L4 21l4.3-1.6c1.1.3 2.4.5 3.7.5 5.5 0 10-3.8 10-8.4S17.5 3 12 3z"/></svg>';
    bubble.addEventListener("click", toggle);

    var panel = h("div", "panel");
    var hdr = h("div", "hdr");
    hdr.appendChild(
      h("span", null, (config.appearance && config.appearance.title) || "Chat")
    );
    var close = h("button", null, "×");
    close.setAttribute("aria-label", "Cerrar");
    close.addEventListener("click", toggle);
    hdr.appendChild(close);

    var logEl = h("div", "log");
    var foot = h("div", "foot");
    var input = h("input");
    input.type = "text";
    input.placeholder = "Escribe tu mensaje…";
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") submit();
    });
    var send = h("button", null, "Enviar");
    send.addEventListener("click", submit);
    foot.appendChild(input);
    foot.appendChild(send);

    panel.appendChild(hdr);
    panel.appendChild(logEl);
    panel.appendChild(foot);

    root.appendChild(style);
    root.appendChild(bubble);
    root.appendChild(panel);

    els = { bubble: bubble, panel: panel, log: logEl, input: input };
  }

  function scrollDown() {
    els.log.scrollTop = els.log.scrollHeight;
  }

  function addMsg(direction, content, interactive) {
    var m = h("div", "msg " + (direction === "inbound" ? "out" : "in"), content);
    els.log.appendChild(m);
    if (interactive) renderInteractive(interactive);
    scrollDown();
  }

  function renderInteractive(payload) {
    // Best-effort quick-reply buttons from a UCM-ish interactive payload.
    var options = [];
    if (payload.quick_replies) options = payload.quick_replies;
    else if (payload.buttons) options = payload.buttons;
    else if (payload.action && payload.action.buttons)
      options = payload.action.buttons;
    if (!options || !options.length) return;
    var wrap = h("div", "btns");
    options.forEach(function (o) {
      var label = o.title || o.text || o.label || (o.reply && o.reply.title) || "";
      if (!label) return;
      var b = h("button", null, label);
      b.addEventListener("click", function () {
        sendMessage(label);
      });
      wrap.appendChild(b);
    });
    els.log.appendChild(wrap);
  }

  // ── networking ───────────────────────────────────────────────────────
  function mintSession() {
    if (minting) return minting;
    minting = fetch(API_BASE + "/v1/widget/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ public_key: PUBLIC_KEY, session_id: sessionId }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("session " + r.status);
        return r.json();
      })
      .then(function (data) {
        token = data.session_token;
        sessionId = data.session_id;
        config = data.config || config;
        try {
          window.localStorage.setItem(STORAGE_KEY, sessionId);
        } catch (e) {}
        minting = null;
        return token;
      })
      .catch(function (err) {
        minting = null;
        throw err;
      });
    return minting;
  }

  function ensureToken() {
    return token ? Promise.resolve(token) : mintSession();
  }

  function authFetch(path, opts, retried) {
    return ensureToken().then(function (tk) {
      opts = opts || {};
      opts.headers = opts.headers || {};
      opts.headers["Authorization"] = "Bearer " + tk;
      return fetch(API_BASE + path, opts).then(function (r) {
        if (r.status === 401 && !retried) {
          // Token expired — re-mint once and retry.
          token = null;
          return authFetch(path, opts, true);
        }
        return r;
      });
    });
  }

  function sendMessage(text) {
    addMsg("inbound", text, null);
    authFetch("/v1/widget/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text }),
    }).catch(function () {
      addMsg("outbound", "⚠️ No se pudo enviar. Reintenta.", null);
    });
  }

  function submit() {
    var text = (els.input.value || "").trim();
    if (!text) return;
    els.input.value = "";
    sendMessage(text);
  }

  function poll() {
    var q = lastTs ? "?since=" + encodeURIComponent(lastTs) : "";
    authFetch("/v1/widget/messages" + q, { method: "GET" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        if (data && data.messages) {
          data.messages.forEach(function (m) {
            if (seen[m.id]) return;
            seen[m.id] = true;
            lastTs = m.created_at;
            // Echoed inbound rows are already shown optimistically; only
            // render the agent's/operator's outbound replies from polling.
            if (m.direction === "outbound") {
              addMsg("outbound", m.content, m.interactive_payload);
            }
          });
        }
      })
      .catch(function () {})
      .then(function () {
        if (open) pollTimer = setTimeout(poll, POLL_MS);
      });
  }

  // ── open/close ───────────────────────────────────────────────────────
  function toggle() {
    open = !open;
    els.panel.classList.toggle("open", open);
    if (open) {
      ensureToken()
        .then(function () {
          if (config.greeting && !els.log.childElementCount) {
            addMsg("outbound", config.greeting, null);
          }
          els.input.focus();
          if (pollTimer) clearTimeout(pollTimer);
          poll();
        })
        .catch(function () {
          addMsg("outbound", "⚠️ Chat no disponible ahora.", null);
        });
    } else if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  render();
})();
