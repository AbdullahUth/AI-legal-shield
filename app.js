// ============ Legal Shield AI — Vanilla JS (live courtroom) ============

// Backend base URL. When the page is served by FastAPI we use same-origin
// (empty string). When index.html is opened directly as a file, we fall back
// to the local backend address (CORS is enabled on the backend).
const API_BASE = location.protocol === "file:" ? "http://127.0.0.1:8000" : "";
const API_URL = API_BASE + "/ask";
const UPLOAD_URL = API_BASE + "/upload";
const HISTORY_URL = API_BASE + "/history";

const SAMPLE_QUESTIONS = [
  "Can my employer fire me for refusing weekend work?",
  "What should I do if I receive a cease and desist letter?",
  "How do I protect my startup's intellectual property?",
];

const state = {
  clientName: "",
  userId: "",
  mode: "normal", // "quick" | "normal" | "thinking"
  messages: [],
  thinking: false,
};

const $ = (id) => document.getElementById(id);

// ---------- THEME ----------
const initTheme = () => {
  const themeBtns = document.querySelectorAll(".theme-toggle");
  const applyTheme = (isLight) => {
    document.body.classList.toggle("light-mode", isLight);
    document.querySelectorAll(".sun-icon").forEach(el => el.classList.toggle("hidden", !isLight));
    document.querySelectorAll(".moon-icon").forEach(el => el.classList.toggle("hidden", isLight));
  };
  applyTheme(localStorage.getItem("theme") === "light");
  themeBtns.forEach(btn => btn.addEventListener("click", () => {
    const next = !document.body.classList.contains("light-mode");
    localStorage.setItem("theme", next ? "light" : "dark");
    applyTheme(next);
  }));
};
initTheme();

const landing = $("landing");
const consult = $("consult");
const nameInput = $("name-input");
const beginBtn = $("begin-btn");
const loginForm = $("login-form");
const exitBtn = $("exit-btn");
const messagesEl = $("messages");
const chatForm = $("chat-form");
const chatInput = $("chat-input");
const sendBtn = $("send-btn");
const clientNameEl = $("client-name");
const clientAvatarEl = $("client-avatar");
const pdfInput = $("pdf-input");
const pdfBtn = $("pdf-btn");
const uploadStatus = $("upload-status");
const historyBtn = $("history-btn");

// ---------- Mode switch ----------
document.querySelectorAll(".mode-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".mode-btn").forEach(b => {
      b.classList.remove("active");
      b.setAttribute("aria-selected", "false");
    });
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");
    state.mode = btn.dataset.mode;
  });
});

// ---------- Landing ----------
nameInput.addEventListener("input", () => {
  beginBtn.disabled = !nameInput.value.trim();
});
loginForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const name = nameInput.value.trim();
  if (!name) return;
  state.clientName = name;
  state.userId = "user-" + name.toLowerCase().replace(/\s+/g, "-") + "-" + Math.random().toString(36).slice(2, 7);
  clientNameEl.textContent = name;
  clientAvatarEl.textContent = name.charAt(0).toUpperCase();
  landing.classList.add("hidden");
  consult.classList.remove("hidden");
  state.messages = [{
    id: "welcome",
    role: "lawyer",
    content: `Good day, ${name}. I am your AI counsel. Describe your matter and I will provide guidance — vetted in chambers before it reaches you.`,
  }];
  render();
});
exitBtn.addEventListener("click", () => {
  consult.classList.add("hidden");
  landing.classList.remove("hidden");
  state.messages = [];
});

// ---------- Chat ----------
chatInput.addEventListener("input", () => {
  sendBtn.disabled = !chatInput.value.trim() || state.thinking;
});
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});
chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  handleSend();
});

// ---------- PDF upload (RAG) ----------
pdfBtn.addEventListener("click", () => pdfInput.click());
pdfInput.addEventListener("change", async () => {
  const file = pdfInput.files && pdfInput.files[0];
  if (!file) return;

  uploadStatus.textContent = `Uploading "${file.name}"…`;
  uploadStatus.className = "upload-status uploading";

  const form = new FormData();
  form.append("user_id", state.userId || "anon");
  form.append("file", file);

  try {
    const res = await fetch(UPLOAD_URL, { method: "POST", body: form });
    const data = await res.json();
    if (res.ok && data.success) {
      uploadStatus.textContent = `✓ ${data.filename} — ${data.chunks_created} chunk(s) ready`;
      uploadStatus.className = "upload-status success";
    } else {
      uploadStatus.textContent = `✕ ${data.message || "Upload failed."}`;
      uploadStatus.className = "upload-status error";
    }
  } catch (err) {
    uploadStatus.textContent = "✕ Upload failed — is the backend running?";
    uploadStatus.className = "upload-status error";
  }
  pdfInput.value = "";
});

// ---------- History ----------
historyBtn.addEventListener("click", async () => {
  if (state.thinking) return;
  try {
    const res = await fetch(HISTORY_URL + "?user_id=" + encodeURIComponent(state.userId || "anon"));
    const data = await res.json();
    const items = (data.history || []).filter((h) => h.final_answer);
    state.messages.push({ id: uid(), role: "history", items });
    render();
  } catch (err) {
    state.messages.push({
      id: uid(),
      role: "history",
      items: [],
      error: "Could not load history — is the backend running?",
    });
    render();
  }
});

async function handleSend(text) {
  const q = (text ?? chatInput.value).trim();
  if (!q || state.thinking) return;

  state.messages.push({ id: uid(), role: "user", content: q });
  chatInput.value = "";
  state.thinking = true;
  sendBtn.disabled = true;

  // Insert a live courtroom placeholder right away
  const liveMsg = {
    id: uid(),
    role: "live",
    mode: state.mode,
    lines: [],         // {speaker, text}
    revealed: 0,
    typingSpeaker: "Lawyer",
    done: false,
  };
  state.messages.push(liveMsg);
  render();

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: state.userId || "anon",
        question: q,
        mode: state.mode,
      }),
    });

    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();

    // Parse trial_chat ["Lawyer: ...", "Judge: ..."]
    const lines = (data.trial_chat || []).map(parseChatLine);

    liveMsg.lines = lines;
    await playLiveCourtroom(liveMsg);

    // After live debate, append the final lawyer reply.
    // "thinking" feeds the "Show Agent Trace" panel — built from agent_trace.
    state.messages.push({
      id: uid(),
      role: "lawyer",
      content: data.final_answer || "Counsel could not produce an answer.",
      brief: buildBrief(data),
      thinking: buildAgentTrace(data),
      warnings: data.warnings || data.emergency_notes || [],
    });
  } catch (err) {
    liveMsg.done = true;
    liveMsg.error = "Server is offline or unreachable. Make sure the backend is running on " + API_URL;
  } finally {
    state.thinking = false;
    sendBtn.disabled = !chatInput.value.trim();
    render();
  }
}

function parseChatLine(raw) {
  const m = /^\s*([A-Za-z]+)\s*:\s*([\s\S]*)$/.exec(raw || "");
  if (!m) return { speaker: "Lawyer", text: String(raw || "") };
  return { speaker: m[1], text: m[2] };
}

function buildBrief(data) {
  const bullets = [];
  if (Array.isArray(data.used_facts) && data.used_facts.length) {
    data.used_facts.slice(0, 3).forEach((f) => bullets.push("Fact considered: " + f));
  }
  if (Array.isArray(data.warnings)) {
    data.warnings.slice(0, 3).forEach((w) => bullets.push(w));
  }
  if (data.lawyer_thinking) bullets.push("Reasoning: " + data.lawyer_thinking);
  if (!bullets.length) return null;
  return { title: "Counsel — Notes & Disclosures", bullets };
}

// ---------- Agent trace ----------
// Turns the backend's structured agent_trace array into clean, readable cards.
// We only ever show visible workflow items (drafts, checklist, feedback,
// approvals, rejections, emergency notes) — never hidden chain-of-thought.
const PHASE_LABELS = {
  draft: "Lawyer Draft",
  checklist: "Risk Checklist",
  risk_review: "Risk Review",
  lawyer_revision: "Lawyer Revision",
  risk_recheck: "Risk Re-check",
  judge_review: "Judge Review",
  emergency: "Emergency Step",
};

function buildAgentTrace(data) {
  const trace = Array.isArray(data.agent_trace) ? data.agent_trace : [];
  return trace.map((item) => {
    const label = PHASE_LABELS[item.phase] || item.phase || "Step";
    let status = (item.status || "").replace(/-/g, " ");
    if (item.approved === true) status += " · approved";
    else if (item.approved === false) status += " · rejected";
    if (item.emergency_used) status += " · emergency";
    return {
      title: `Step ${item.step_number} — ${label} (iteration ${item.iteration})`,
      speaker: item.agent + (status ? " · " + status.trim() : ""),
      rawSpeaker: item.agent,
      text: item.message || "",
    };
  });
}

// ---------- Live courtroom playback ----------
function playLiveCourtroom(liveMsg) {
  return new Promise((resolve) => {
    const step = (i) => {
      if (i >= liveMsg.lines.length) {
        liveMsg.done = true;
        liveMsg.typingSpeaker = null;
        render();
        return resolve();
      }
      // show "typing…" for next speaker
      liveMsg.typingSpeaker = liveMsg.lines[i].speaker;
      render();

      setTimeout(() => {
        liveMsg.revealed = i + 1;
        liveMsg.typingSpeaker = i + 1 < liveMsg.lines.length ? liveMsg.lines[i + 1].speaker : null;
        render();
        setTimeout(() => step(i + 1), 350);
      }, 900 + Math.min(1400, (liveMsg.lines[i].text || "").length * 18));
    };
    step(0);
  });
}

// ---------- Render ----------
function render() {
  messagesEl.innerHTML = "";
  state.messages.forEach((m) => {
    if (m.role === "user") messagesEl.appendChild(renderUser(m));
    else if (m.role === "live") messagesEl.appendChild(renderLive(m));
    else if (m.role === "history") messagesEl.appendChild(renderHistory(m));
    else messagesEl.appendChild(renderLawyer(m));
  });

  if (!state.thinking && state.messages.length === 1) {
    const wrap = document.createElement("div");
    wrap.className = "samples fade-up";
    wrap.innerHTML = `<div class="samples-label">Try a matter</div><div class="samples-grid"></div>`;
    const grid = wrap.querySelector(".samples-grid");
    SAMPLE_QUESTIONS.forEach((q) => {
      const btn = document.createElement("button");
      btn.className = "sample-btn";
      btn.textContent = q;
      btn.addEventListener("click", () => handleSend(q));
      grid.appendChild(btn);
    });
    messagesEl.appendChild(wrap);
  }
  messagesEl.scrollTo({ top: messagesEl.scrollHeight, behavior: "smooth" });
}

function renderUser(m) {
  const row = document.createElement("div");
  row.className = "row-user fade-up";
  const b = document.createElement("div");
  b.className = "bubble-user";
  b.textContent = m.content;
  row.appendChild(b);
  return row;
}

function renderHistory(m) {
  const wrap = document.createElement("div");
  wrap.className = "history-block fade-up";

  const head = document.createElement("div");
  head.className = "history-head";
  head.textContent = "Your Previous Questions";
  wrap.appendChild(head);

  if (m.error) {
    const e = document.createElement("div");
    e.className = "live-error";
    e.textContent = m.error;
    wrap.appendChild(e);
    return wrap;
  }
  if (!m.items.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "No previous questions yet.";
    wrap.appendChild(empty);
    return wrap;
  }

  m.items.forEach((h) => {
    const card = document.createElement("div");
    card.className = "history-card";
    const q = document.createElement("div");
    q.className = "history-q";
    q.textContent = `[${h.mode || "normal"}] ${h.question}`;
    const a = document.createElement("div");
    a.className = "history-a";
    a.textContent = h.final_answer || "";
    card.appendChild(q);
    card.appendChild(a);
    wrap.appendChild(card);
  });
  return wrap;
}

function renderLive(m) {
  const wrap = document.createElement("div");
  wrap.className = "live-courtroom fade-up";

  const head = document.createElement("div");
  head.className = "live-head";
  head.innerHTML = `
    <div class="live-title">
      <span class="live-dot"></span>
      <span>Live Courtroom</span>
      <span class="live-mode">${m.mode === "defense" ? "Defense — Judge engaged" : "Consultation"}</span>
    </div>
    <div class="live-status">${m.done ? "Session closed" : "In session…"}</div>`;
  wrap.appendChild(head);

  const grid = document.createElement("div");
  grid.className = "live-grid";

  const lawyerCol = column("Lawyer", "Advocate", "lawyer-col");
  const judgeCol = column("Judge", "Critic", "judge-col");
  grid.appendChild(lawyerCol.el);
  grid.appendChild(judgeCol.el);

  if (m.error) {
    const err = document.createElement("div");
    err.className = "live-error";
    err.textContent = m.error;
    wrap.appendChild(err);
  } else {
    for (let i = 0; i < m.revealed; i++) {
      const line = m.lines[i];
      const target = line.speaker.toLowerCase().includes("judge") ? judgeCol : lawyerCol;
      const node = document.createElement("div");
      node.className = "live-bubble fade-up";
      node.textContent = line.text;
      target.body.appendChild(node);
    }

    if (!m.done && m.typingSpeaker) {
      const target = m.typingSpeaker.toLowerCase().includes("judge") ? judgeCol : lawyerCol;
      const t = document.createElement("div");
      t.className = "live-bubble typing";
      t.innerHTML = `<span class="typing-dots"><i></i><i></i><i></i></span>`;
      target.body.appendChild(t);
    }

    wrap.appendChild(grid);
  }

  return wrap;
}

function column(title, subtitle, cls) {
  const el = document.createElement("div");
  el.className = "live-col " + cls;
  const h = document.createElement("div");
  h.className = "live-col-head";
  h.innerHTML = `<div class="live-col-title">${title}</div><div class="live-col-sub">${subtitle}</div>`;
  const body = document.createElement("div");
  body.className = "live-col-body";
  el.appendChild(h);
  el.appendChild(body);
  return { el, body };
}

function renderLawyer(m) {
  const block = document.createElement("div");
  block.className = "lawyer-block fade-up";

  if (m.thinking && m.thinking.length) {
    const toggle = document.createElement("button");
    toggle.className = "strategy-toggle";
    toggle.innerHTML = `<span>🔍 Show Agent Trace</span><span class="strategy-arrow">▾</span>`;
    const panel = document.createElement("div");
    panel.className = "phases";
    panel.style.display = "none";
    m.thinking.forEach((p) => {
      const ph = document.createElement("div");
      ph.className = "phase";
      const who = String(p.rawSpeaker || p.speaker).toLowerCase();
      const speakerCls = who.includes("judge") ? "judge"
        : who.includes("risk") ? "risk" : "lawyer";
      ph.innerHTML = `
        <div class="phase-head">
          <div class="phase-title"></div>
          <span class="speaker ${speakerCls}">${p.speaker}</span>
        </div><p></p>`;
      ph.querySelector(".phase-title").textContent = p.title;
      ph.querySelector("p").textContent = p.text;
      panel.appendChild(ph);
    });
    toggle.addEventListener("click", () => {
      const open = panel.style.display !== "none";
      panel.style.display = open ? "none" : "flex";
      toggle.classList.toggle("open", !open);
    });
    block.appendChild(toggle);
    block.appendChild(panel);
  }

  const row = document.createElement("div");
  row.className = "lawyer-row";
  row.innerHTML = `
    <div class="lawyer-avatar">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 3v18"/><path d="M5 21h14"/><path d="M5 6h14"/>
        <path d="M5 6l-3 6a4 4 0 0 0 6 0L5 6z"/><path d="M19 6l-3 6a4 4 0 0 0 6 0l-3-6z"/>
      </svg>
    </div>
    <div class="bubble-lawyer"></div>`;
  row.querySelector(".bubble-lawyer").textContent = m.content;
  block.appendChild(row);

  if (m.brief) {
    const brief = document.createElement("div");
    brief.className = "legal-brief brief-card";
    brief.innerHTML = `
      <div class="brief-head">
        <div class="brief-title"></div>
        <div class="brief-tag">Counsel · Sealed</div>
      </div>
      <ul class="brief-list"></ul>`;
    brief.querySelector(".brief-title").textContent = m.brief.title;
    const ul = brief.querySelector(".brief-list");
    m.brief.bullets.forEach((b) => {
      const li = document.createElement("li");
      const span = document.createElement("span");
      span.textContent = b;
      li.appendChild(span);
      ul.appendChild(li);
    });
    block.appendChild(brief);
  }
  return block;
}

function uid() {
  return (crypto.randomUUID && crypto.randomUUID()) || Math.random().toString(36).slice(2);
}

document.addEventListener('DOMContentLoaded', () => {
    // Modal Elements
    const methodTrigger = document.getElementById('method-trigger');
    const methodModal = document.getElementById('method-modal');
    const closeBtn = document.querySelector('.close-btn');

    // Open Modal
    if (methodTrigger && methodModal) {
        methodTrigger.addEventListener('click', (e) => {
            e.preventDefault(); // Prevents the page from jumping to the top
            methodModal.classList.remove('hidden');
        });
    }

    // Close Modal when clicking the X
    if (closeBtn && methodModal) {
        closeBtn.addEventListener('click', () => {
            methodModal.classList.add('hidden');
        });
    }

    // Close Modal when clicking the dark background outside the box
    window.addEventListener('click', (e) => {
        if (e.target === methodModal) {
            methodModal.classList.add('hidden');
        }
    });
});