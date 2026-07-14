const state = {
  apps: [],
  sessions: [],
  recentLaunches: [],
  activeSessionId: null,
  query: "",
  tag: "all",
};

const appGrid = document.querySelector("#appGrid");
const tagRail = document.querySelector("#tagRail");
const searchInput = document.querySelector("#searchInput");
const sessionList = document.querySelector("#sessionList");
const recentList = document.querySelector("#recentList");
const activeApp = document.querySelector("#activeApp");
const statusLine = document.querySelector("#statusLine");
const refreshButton = document.querySelector("#refreshButton");
const resultCount = document.querySelector("#resultCount");
const sessionCount = document.querySelector("#sessionCount");

searchInput.addEventListener("input", () => {
  state.query = searchInput.value.trim().toLowerCase();
  render();
});

refreshButton.addEventListener("click", () => {
  loadState();
});

async function loadState() {
  const response = await fetch("/api/state");
  const payload = await response.json();
  applyPayload(payload);
}

function applyPayload(payload) {
  state.apps = payload.apps || [];
  state.sessions = payload.sessions || [];
  state.recentLaunches = payload.recent_launches || [];
  state.activeSessionId = payload.active_session_id || null;
  statusLine.textContent = payload.message || `${state.apps.length} apps`;
  render();
}

async function postAction(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    statusLine.textContent = result.error || "Action failed";
    return;
  }
  applyPayload(result);
}

function render() {
  renderTags();
  renderApps();
  renderSessions();
  renderRecentLaunches();
}

function renderTags() {
  const tags = [...new Set(state.apps.flatMap((app) => app.tags))].sort();
  const buttons = ["all", ...tags];
  tagRail.replaceChildren(
    ...buttons.map((tag) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `tagButton${state.tag === tag ? " active" : ""}`;
      button.textContent = tag === "all" ? "All" : tag;
      button.setAttribute("aria-pressed", state.tag === tag ? "true" : "false");
      button.addEventListener("click", () => {
        state.tag = tag;
        render();
      });
      return button;
    }),
  );
}

function renderApps() {
  const filtered = state.apps.filter((app) => {
    const matchesTag = state.tag === "all" || app.tags.includes(state.tag);
    const haystack = `${app.title} ${app.summary} ${app.tags.join(" ")}`.toLowerCase();
    return matchesTag && haystack.includes(state.query);
  });
  resultCount.textContent =
    filtered.length === state.apps.length
      ? `${filtered.length} apps`
      : `${filtered.length} of ${state.apps.length} apps`;

  if (filtered.length === 0) {
    const empty = document.createElement("div");
    empty.className = "emptyResults";
    empty.innerHTML = '<strong>No matching apps</strong><span>Adjust the search or selected tag.</span>';
    appGrid.replaceChildren(empty);
    return;
  }

  appGrid.replaceChildren(...filtered.map((app) => appCard(app)));
}

function appCard(app) {
  const card = document.createElement("article");
  card.className = "appCard";
  card.dataset.appId = app.app_id;
  card.style.setProperty("--app-accent", app.metadata.accent || "#1f2933");

  const identity = document.createElement("div");
  identity.className = "appIdentity";
  const glyph = document.createElement("div");
  glyph.className = "appGlyph";
  glyph.textContent = app.metadata.glyph || app.title.slice(0, 2).toUpperCase();
  const copy = document.createElement("div");
  copy.innerHTML = `<div class="appTitle"></div><p class="appSummary"></p>`;
  copy.querySelector(".appTitle").textContent = app.title;
  copy.querySelector(".appSummary").textContent = app.summary;
  identity.append(glyph, copy);

  const tags = document.createElement("div");
  tags.className = "tagList";
  for (const tag of app.tags) {
    const pill = document.createElement("span");
    pill.className = "tag";
    pill.textContent = tag;
    tags.append(pill);
  }

  const surfaces = document.createElement("div");
  surfaces.className = "surfaceRow";
  for (const surface of app.launch_surfaces) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = surface.surface_id === app.recommended_surface ? "primaryButton" : "secondaryButton";
    button.textContent = surface.label;
    button.setAttribute("aria-label", `${surface.label} ${app.title}`);
    button.addEventListener("click", () => {
      postAction("/api/launch", {
        app_id: app.app_id,
        surface_id: surface.surface_id,
        mode: surface.mode === "attach" ? "attach" : "launch",
      });
    });
    surfaces.append(button);
  }

  card.append(identity, tags, surfaces);
  return card;
}

function renderSessions() {
  const active = state.sessions.find((session) => session.session_id === state.activeSessionId);
  sessionCount.textContent = String(state.sessions.length);
  if (!active) {
    activeApp.className = "activeApp empty";
    activeApp.innerHTML =
      '<span class="panelEyebrow">Active now</span><strong>No active managed session</strong>';
  } else {
    const app = appById(active.app_id);
    activeApp.className = "activeApp";
    activeApp.style.setProperty("--app-accent", app?.metadata.accent || "#0b7a75");
    const eyebrow = document.createElement("span");
    eyebrow.className = "panelEyebrow";
    eyebrow.textContent = "Active now";
    activeApp.replaceChildren(eyebrow, sessionContent(active, app, false));
  }

  if (state.sessions.length === 0) {
    sessionList.className = "sessionList empty";
    sessionList.textContent = "No managed sessions";
    return;
  }
  sessionList.className = "sessionList";
  sessionList.replaceChildren(
    ...state.sessions.map((session) => {
      const item = document.createElement("article");
      const app = appById(session.app_id);
      item.className = `sessionItem${session.session_id === state.activeSessionId ? " current" : ""}`;
      item.style.setProperty("--app-accent", app?.metadata.accent || "#0b7a75");
      item.append(sessionContent(session, app, true));
      return item;
    }),
  );
}

function renderRecentLaunches() {
  if (state.recentLaunches.length === 0) {
    recentList.className = "recentList empty";
    recentList.textContent = "No recent launches";
    return;
  }
  recentList.className = "recentList";
  recentList.replaceChildren(
    ...state.recentLaunches.map((handoff) => {
      const item = document.createElement("article");
      item.className = "recentItem";
      const title = document.createElement("div");
      title.className = "appTitle";
      title.textContent = appById(handoff.app_id)?.title || handoff.app_id;
      const meta = document.createElement("div");
      meta.className = "sessionMeta";
      meta.textContent = `Opened ${formatTime(handoff.handed_off_at)}`;
      item.append(title, meta);
      return item;
    }),
  );
}

function formatTime(value) {
  if (!value) return "recently";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "recently";
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function sessionContent(session, app, withActions) {
  const wrapper = document.createElement("div");
  const title = document.createElement("div");
  title.className = "appTitle";
  title.textContent = app ? app.title : session.app_id;
  const meta = document.createElement("div");
  meta.className = "sessionMeta";
  meta.innerHTML = '<span class="sessionStatus"><i aria-hidden="true"></i><span></span></span><span></span>';
  meta.children[0].children[1].textContent = session.status;
  meta.children[1].textContent = session.ownership.replace("_", " ");
  wrapper.append(title, meta);

  if (withActions) {
    const actions = document.createElement("div");
    actions.className = "sessionActions";
    if (session.status === "running") {
      const switchButton = document.createElement("button");
      switchButton.type = "button";
      switchButton.className = "secondaryButton";
      switchButton.textContent = "Switch";
      switchButton.setAttribute("aria-label", `Switch to ${app ? app.title : session.app_id}`);
      switchButton.addEventListener("click", () => {
        postAction("/api/switch", { session_id: session.session_id });
      });
      actions.append(switchButton);
    }
    if (session.status === "running" && session.ownership === "launcher_owned") {
      const closeButton = document.createElement("button");
      closeButton.type = "button";
      closeButton.className = "dangerButton";
      closeButton.textContent = "Stop";
      closeButton.setAttribute("aria-label", `Stop ${app ? app.title : session.app_id}`);
      closeButton.addEventListener("click", () => {
        postAction("/api/close", { session_id: session.session_id, stop_runtime: true });
      });
      actions.append(closeButton);
    }
    if (actions.childElementCount > 0) {
      wrapper.append(actions);
    }
  }
  return wrapper;
}

function appById(appId) {
  return state.apps.find((app) => app.app_id === appId);
}

loadState();
