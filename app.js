// ============ Legal Shield AI — Vanilla JS (live courtroom) ============

// Backend base URL. When the page is served by FastAPI we use same-origin
// (empty string). When index.html is opened directly as a file, we fall back
// to the local backend address (CORS is enabled on the backend).
const API_BASE = location.protocol === "file:" ? "http://127.0.0.1:8000" : "";
const API_URL = API_BASE + "/ask";
const UPLOAD_URL = API_BASE + "/upload";
const HISTORY_URL = API_BASE + "/history";
const SIGNUP_URL = API_BASE + "/signup";
const LOGIN_URL = API_BASE + "/login";
const ME_URL = API_BASE + "/me";

// Public, friendly loading phrases. NOTE: never mention internal "agents" here —
// these are announced to screen readers, so they must stay user-friendly.
const THINKING_PHRASES = [
  "I received your question and I’m working on it.",
  "I’m reviewing the important details.",
  "I’m checking for risks and missing information.",
  "I’m comparing this with relevant past cases.",
  "I’m preparing a clearer answer.",
  "Almost ready.",
];

const SAMPLE_QUESTIONS = [
  "Can my employer fire me for refusing weekend work?",
  "What should I do if I receive a cease and desist letter?",
  "How do I protect my startup's intellectual property?",
];

const state = {
  clientName: "",
  userId: "",
  token: "",          // session token from login/signup ("" for guests)
  authMode: "login",  // "login" | "signup"
  mode: "normal",     // "quick" | "normal" | "thinking"
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
const emailInput = $("email-input");
const passwordInput = $("password-input");
const nameField = $("name-field");
const authMsg = $("auth-msg");
const guestBtn = $("guest-btn");
const beginBtn = $("begin-btn");
const loginForm = $("login-form");
const exitBtn = $("exit-btn");
const logoutBtn = $("logout-btn");
const messagesEl = $("messages");
const chatForm = $("chat-form");
const chatInput = $("chat-input");
const sendBtn = $("send-btn");
const micBtn = $("mic-btn");
const clientNameEl = $("client-name");
const clientAvatarEl = $("client-avatar");
const pdfInput = $("pdf-input");
const pdfBtn = $("pdf-btn");
const docTypeSelect = $("doc-type");
const uploadStatus = $("upload-status");
const historyBtn = $("history-btn");
const srStatus = $("sr-status");
const voiceSelect = $("voice-select");
const adminPass = $("admin-pass");
const adminDocType = $("admin-doc-type");
const adminFile = $("admin-file");
const adminUploadBtn = $("admin-upload-btn");
const adminStatus = $("admin-status");

// Announce a message to screen readers via the aria-live region.
function announce(text) {
  if (srStatus) srStatus.textContent = text;
}

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

// ---------- Auth (login / signup / guest) ----------
function setAuthMode(mode) {
  state.authMode = mode;
  document.querySelectorAll(".auth-tab").forEach((t) => {
    const active = t.dataset.auth === mode;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", active ? "true" : "false");
  });
  nameField.classList.toggle("hidden", mode !== "signup");
  beginBtn.textContent = mode === "signup" ? "Create Account" : "Log In";
  authMsg.textContent = "";
  validateAuth();
}
document.querySelectorAll(".auth-tab").forEach((tab) => {
  tab.addEventListener("click", () => setAuthMode(tab.dataset.auth));
});

function validateAuth() {
  const emailOk = emailInput.value.trim().length > 3;
  const passOk = passwordInput.value.length >= 4;
  const nameOk = state.authMode === "login" || nameInput.value.trim().length > 0;
  beginBtn.disabled = !(emailOk && passOk && nameOk);
}
[nameInput, emailInput, passwordInput].forEach((el) =>
  el.addEventListener("input", validateAuth));

function enterConsult(name) {
  state.clientName = name;
  clientNameEl.textContent = name;
  clientAvatarEl.textContent = (name || "G").charAt(0).toUpperCase();
  landing.classList.add("hidden");
  consult.classList.remove("hidden");
  state.messages = [{
    id: "welcome",
    role: "lawyer",
    content: `Good day, ${name}. I am your AI counsel. Describe your matter and I will provide guidance — vetted in chambers before it reaches you.`,
  }];
  render();
  chatInput.focus();
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = emailInput.value.trim();
  const password = passwordInput.value;
  const name = nameInput.value.trim();
  if (!email || !password) return;

  authMsg.textContent = state.authMode === "signup" ? "Creating account…" : "Logging in…";
  authMsg.className = "auth-msg";
  beginBtn.disabled = true;

  const url = state.authMode === "signup" ? SIGNUP_URL : LOGIN_URL;
  const body = state.authMode === "signup"
    ? { name, email, password }
    : { email, password };

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (res.ok && data.success) {
      state.token = data.token;
      state.userId = data.user_id;
      localStorage.setItem("auth_token", data.token);
      localStorage.setItem("auth_user_id", data.user_id);
      localStorage.setItem("auth_name", data.name);
      enterConsult(data.name);
    } else {
      authMsg.textContent = data.message || "Authentication failed.";
      authMsg.className = "auth-msg error";
    }
  } catch (err) {
    authMsg.textContent = "Could not reach the server. Is the backend running?";
    authMsg.className = "auth-msg error";
  } finally {
    validateAuth();
  }
});

guestBtn.addEventListener("click", () => {
  const name = nameInput.value.trim() || "Guest";
  state.token = "";
  state.userId = "guest-" + Math.random().toString(36).slice(2, 9);
  enterConsult(name);
});

function logout() {
  state.token = "";
  state.userId = "";
  state.clientName = "";
  state.messages = [];
  localStorage.removeItem("auth_token");
  localStorage.removeItem("auth_user_id");
  localStorage.removeItem("auth_name");
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  consult.classList.add("hidden");
  landing.classList.remove("hidden");
  emailInput.value = "";
  passwordInput.value = "";
  validateAuth();
}
exitBtn.addEventListener("click", logout);
logoutBtn.addEventListener("click", logout);

// Restore an existing session on page load (token kept in localStorage).
(async function restoreSession() {
  const token = localStorage.getItem("auth_token");
  if (!token) return;
  try {
    const res = await fetch(ME_URL, { headers: { Authorization: "Bearer " + token } });
    const data = await res.json();
    if (res.ok && data.success) {
      state.token = token;
      state.userId = data.user_id;
      enterConsult(data.name);
    } else {
      localStorage.removeItem("auth_token");
    }
  } catch (err) {
    /* backend offline — just stay on the landing screen */
  }
})();

setAuthMode("login");

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
  form.append("token", state.token || "");
  form.append("document_type", docTypeSelect ? docTypeSelect.value : "general_document");
  form.append("file", file);

  try {
    const res = await fetch(UPLOAD_URL, { method: "POST", body: form });
    const data = await res.json();
    if (res.ok && data.success) {
      const typeLabel = (data.document_type || "document").replace(/_/g, " ");
      uploadStatus.textContent = `✓ ${data.filename} (${typeLabel}) — ${data.chunks_created} chunk(s) ready`;
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

// ---------- Admin Knowledge Upload ----------
// Lets us load law files / past case PDFs into the shared RAG knowledge base
// before the demo. Uses the same backend RAG extraction + chunking.
if (adminUploadBtn) {
  adminUploadBtn.addEventListener("click", () => adminFile.click());
  adminFile.addEventListener("change", async () => {
    const file = adminFile.files && adminFile.files[0];
    if (!file) return;

    adminStatus.textContent = `Uploading "${file.name}"…`;
    adminStatus.className = "admin-status uploading";

    const form = new FormData();
    form.append("file", file);
    form.append("document_type", adminDocType ? adminDocType.value : "law_reference");
    form.append("admin_password", adminPass ? adminPass.value : "");

    try {
      const res = await fetch(API_BASE + "/admin/upload-knowledge", {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      if (res.ok && data.success) {
        const typeLabel = (data.document_type || "document").replace(/_/g, " ");
        adminStatus.textContent =
          `✓ ${data.filename} (${typeLabel}) — ${data.chunks_created} chunk(s) added to knowledge base`;
        adminStatus.className = "admin-status success";
      } else {
        adminStatus.textContent = `✕ ${data.message || "Upload failed."}`;
        adminStatus.className = "admin-status error";
      }
    } catch (err) {
      adminStatus.textContent = "✕ Upload failed — is the backend running?";
      adminStatus.className = "admin-status error";
    }
    adminFile.value = "";
  });
}

// ---------- History ----------
historyBtn.addEventListener("click", async () => {
  if (state.thinking) return;
  let url = HISTORY_URL + "?user_id=" + encodeURIComponent(state.userId || "anon");
  if (state.token) url += "&token=" + encodeURIComponent(state.token);
  try {
    const res = await fetch(url);
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

// ---------- Voice input (Web Speech API) ----------
const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let listening = false;

if (SpeechRec) {
  recognition = new SpeechRec();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.addEventListener("result", (e) => {
    const transcript = e.results[0][0].transcript;
    chatInput.value = (chatInput.value ? chatInput.value + " " : "") + transcript;
    chatInput.dispatchEvent(new Event("input"));
    announce("Voice input added. You can edit it before sending.");
  });
  recognition.addEventListener("end", () => {
    listening = false;
    micBtn.classList.remove("listening");
  });
  recognition.addEventListener("error", () => {
    listening = false;
    micBtn.classList.remove("listening");
    announce("Voice input stopped.");
  });
}

micBtn.addEventListener("click", () => {
  if (!recognition) {
    announce("Voice input is not supported in this browser.");
    alert("Voice input is not supported in this browser.");
    return;
  }
  if (listening) {
    recognition.stop();
    return;
  }
  try {
    recognition.start();
    listening = true;
    micBtn.classList.add("listening");
    announce("Listening. Please speak your legal question.");
  } catch (err) {
    listening = false;
    micBtn.classList.remove("listening");
  }
});

// ---------- Voice output (Speech Synthesis) with good English voice ----------
// Voices load asynchronously, so we listen for `onvoiceschanged` and pick the
// best available English voice (the user can override it with the selector).
const PREFERRED_VOICE_NAMES = [
  "Google US English", "Microsoft Aria", "Microsoft Jenny", "Microsoft Guy",
  "Microsoft David", "Microsoft Zira", "Samantha", "Alex", "Daniel", "Karen",
];
let availableVoices = [];
let selectedVoiceName = localStorage.getItem("voice_name") || "";
let speaking = false;

function getEnglishVoices() {
  return availableVoices.filter((v) => /^en(-|_|$)/i.test(v.lang || ""));
}

function getBestVoice() {
  const english = getEnglishVoices();
  // 1. An explicit user choice always wins (if still available).
  if (selectedVoiceName) {
    const chosen = availableVoices.find((v) => v.name === selectedVoiceName);
    if (chosen) return chosen;
  }
  // 2. Prefer known natural-sounding voices by name.
  for (const name of PREFERRED_VOICE_NAMES) {
    const match = english.find((v) => (v.name || "").includes(name));
    if (match) return match;
  }
  // 3. Prefer en-US, then en-GB.
  const us = english.find((v) => /^en-US/i.test(v.lang || ""));
  if (us) return us;
  const gb = english.find((v) => /^en-GB/i.test(v.lang || ""));
  if (gb) return gb;
  // 4. Any English voice, otherwise none.
  return english[0] || null;
}

function populateVoiceSelect() {
  if (!voiceSelect) return;
  const english = getEnglishVoices();
  voiceSelect.innerHTML = "";
  if (!english.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No English voice found";
    voiceSelect.appendChild(opt);
    return;
  }
  const best = getBestVoice();
  english.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v.name;
    opt.textContent = `${v.name} (${v.lang})`;
    if (best && v.name === best.name) opt.selected = true;
    voiceSelect.appendChild(opt);
  });
}

function loadVoices() {
  if (!window.speechSynthesis) return;
  availableVoices = window.speechSynthesis.getVoices() || [];
  populateVoiceSelect();
}

if (window.speechSynthesis) {
  loadVoices();
  // Some browsers populate voices asynchronously.
  window.speechSynthesis.onvoiceschanged = loadVoices;
}
if (voiceSelect) {
  voiceSelect.addEventListener("change", () => {
    selectedVoiceName = voiceSelect.value;
    localStorage.setItem("voice_name", selectedVoiceName);
  });
}

function speakAnswer(text, btn, stopBtn) {
  if (!window.speechSynthesis) {
    alert("Voice output is not supported in this browser.");
    return;
  }
  const voice = getBestVoice();
  if (!voice) {
    announce("No English voice was found on this browser or device.");
    alert("No English voice was found on this browser/device.");
    return;
  }
  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  utter.voice = voice;
  utter.lang = voice.lang || "en-US";
  utter.rate = 0.95;
  utter.pitch = 1.0;
  utter.volume = 1.0;
  utter.addEventListener("end", () => {
    speaking = false;
    if (btn) btn.classList.remove("speaking");
    if (stopBtn) stopBtn.disabled = true;
  });
  speaking = true;
  if (btn) btn.classList.add("speaking");
  if (stopBtn) stopBtn.disabled = false;
  announce("Reading the answer aloud.");
  window.speechSynthesis.speak(utter);
}

function stopSpeaking() {
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  speaking = false;
  document.querySelectorAll(".voice-btn.speaking").forEach((b) => b.classList.remove("speaking"));
  document.querySelectorAll(".voice-stop-btn").forEach((b) => (b.disabled = true));
  announce("Stopped reading.");
}

// ---------- Thinking animation ----------
// While loading we show a clean, friendly "Thinking..." state with fading
// phrases. The detailed agent dialogue stays hidden until the user asks for it.
let thinkingTimer = null;

function startThinking(liveMsg) {
  liveMsg.phraseIndex = 0;
  announce(THINKING_PHRASES[0]);
  thinkingTimer = setInterval(() => {
    if (liveMsg.phraseIndex < THINKING_PHRASES.length - 1) {
      liveMsg.phraseIndex += 1;
      announce(THINKING_PHRASES[liveMsg.phraseIndex]);
      render();
    }
  }, 2200);
}

function stopThinking() {
  if (thinkingTimer) {
    clearInterval(thinkingTimer);
    thinkingTimer = null;
  }
}

async function handleSend(text) {
  const q = (text ?? chatInput.value).trim();
  if (!q || state.thinking) return;

  stopSpeaking();
  state.messages.push({ id: uid(), role: "user", content: q });
  chatInput.value = "";
  chatInput.dispatchEvent(new Event("input"));
  state.thinking = true;
  sendBtn.disabled = true;

  // Clean "Thinking..." placeholder — the detailed dialogue stays hidden.
  const liveMsg = { id: uid(), role: "live", phraseIndex: 0, done: false, error: null };
  state.messages.push(liveMsg);
  render();
  startThinking(liveMsg);

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: state.userId || "anon",
        token: state.token || "",
        question: q,
        mode: state.mode,
      }),
    });

    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();

    stopThinking();
    // Remove the thinking placeholder; the agent dialogue now lives behind the
    // "Show Agent Dialogue" button on the answer itself (hidden by default).
    state.messages = state.messages.filter((m) => m.id !== liveMsg.id);
    state.messages.push({
      id: uid(),
      role: "lawyer",
      content: data.plain_text_answer || data.final_answer || "Counsel could not produce an answer.",
      plainText: data.plain_text_answer || data.final_answer || "",
      brief: buildBrief(data),
      thinking: buildAgentTrace(data),   // feeds the "Show Agent Dialogue" panel
      warnings: data.warnings || data.emergency_notes || [],
    });
    announce("Your answer is ready.");
  } catch (err) {
    stopThinking();
    liveMsg.done = true;
    liveMsg.error = "Server is offline or unreachable. Make sure the backend is running on "
      + (API_BASE || location.origin);
    announce("Something went wrong reaching the server.");
  } finally {
    state.thinking = false;
    sendBtn.disabled = !chatInput.value.trim();
    render();
  }
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
  memory: "Shared Legal Memory",
  draft: "Lawyer Draft",
  checklist: "Risk Checklist",
  judge_prep: "Judge Preparation Notes",
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

// Clean "Thinking..." loading state — friendly phrases, no agent jargon.
function renderLive(m) {
  const wrap = document.createElement("div");
  wrap.className = "thinking-card fade-up";

  if (m.error) {
    const head = document.createElement("div");
    head.className = "thinking-head";
    head.innerHTML = `<span class="pulse"></span><span class="thinking-title">Connection problem</span>`;
    wrap.appendChild(head);
    const err = document.createElement("div");
    err.className = "live-error";
    err.textContent = m.error;
    wrap.appendChild(err);
    return wrap;
  }

  const head = document.createElement("div");
  head.className = "thinking-head";
  head.innerHTML = `<span class="pulse"></span><span class="thinking-title">Thinking…</span>`;
  wrap.appendChild(head);

  const phrase = document.createElement("div");
  phrase.className = "thinking-phrase fade-up";
  phrase.textContent = THINKING_PHRASES[m.phraseIndex || 0];
  wrap.appendChild(phrase);

  const dots = document.createElement("div");
  dots.className = "thinking-dots";
  dots.innerHTML = "<i></i><i></i><i></i>";
  wrap.appendChild(dots);

  return wrap;
}

function renderLawyer(m) {
  const block = document.createElement("div");
  block.className = "lawyer-block fade-up";

  if (m.thinking && m.thinking.length) {
    const toggle = document.createElement("button");
    toggle.className = "strategy-toggle";
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    toggle.innerHTML = `<span>🔍 Show Agent Dialogue</span><span class="strategy-arrow">▾</span>`;
    const panel = document.createElement("div");
    panel.className = "phases";
    panel.style.display = "none";
    m.thinking.forEach((p) => {
      const ph = document.createElement("div");
      ph.className = "phase";
      const who = String(p.rawSpeaker || p.speaker).toLowerCase();
      const speakerCls = who.includes("judge") ? "judge"
        : who.includes("risk") ? "risk"
        : who.includes("system") ? "system" : "lawyer";
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
      toggle.setAttribute("aria-expanded", open ? "false" : "true");
      const label = toggle.querySelector("span");
      if (label) label.textContent = open ? "🔍 Show Agent Dialogue" : "🔍 Hide Agent Dialogue";
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

  // Voice output: read the final user-facing answer aloud (not the dialogue).
  if (m.plainText) {
    const voiceBar = document.createElement("div");
    voiceBar.className = "voice-bar";

    const readBtn = document.createElement("button");
    readBtn.type = "button";
    readBtn.className = "voice-btn";
    readBtn.setAttribute("aria-label", "Read the legal answer aloud");
    readBtn.innerHTML = `<span aria-hidden="true">🔊</span><span>Read Answer Aloud</span>`;

    const stopBtn = document.createElement("button");
    stopBtn.type = "button";
    stopBtn.className = "voice-btn voice-stop-btn";
    stopBtn.setAttribute("aria-label", "Stop reading the answer aloud");
    stopBtn.disabled = true;
    stopBtn.innerHTML = `<span aria-hidden="true">⏹</span><span>Stop Reading</span>`;

    readBtn.addEventListener("click", () => speakAnswer(m.plainText, readBtn, stopBtn));
    stopBtn.addEventListener("click", stopSpeaking);

    voiceBar.appendChild(readBtn);
    voiceBar.appendChild(stopBtn);
    block.appendChild(voiceBar);
  }

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