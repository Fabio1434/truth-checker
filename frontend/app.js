(() => {
  "use strict";

  // ✅ BLOC CORRIGÉ POUR RENDER :
const API_BASE = (() => {
  if (location.protocol === "file:") return "http://localhost:8000";
  const configured = window.TRUTHCHECKER_API || localStorage.getItem("truthchecker_api");
  if (configured) return configured.replace(/\/$/, "");
  return ""; // Utilise l'origine courante (https://truth-checker-jsio.onrender.com)
})();
  const HISTORY_KEY = "truthchecker_history_v1";
  const MAX_HISTORY = 8;

  const state = {
    token: sessionStorage.getItem("truthchecker_token") || "",
    user: null,
    type: "text",
    lang: "fr",
    imageBase64: null,
    imageMediaType: null,
    sessionChecks: 0,
    sessionSources: 0,
    sessionVerified: 0,
    sessionFalse: 0,
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  // ================================================================ Authentication
  const authModal = $("#auth-modal");
  const authError = $("#auth-error");
  const accountEmail = $("#account-email");
  const accountBox = $("#account-box");

  function authHeaders(extra = {}) {
    return { ...extra, ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}) };
  }
  function showAuthError(message) { authError.textContent = message; authError.hidden = false; }
  function clearAuthError() { authError.hidden = true; authError.textContent = ""; }
  function openAuth() {
    clearAuthError();
    if (!authModal.open) authModal.showModal();
  }
  function setToken(token) {
    state.token = token || "";
    if (state.token) sessionStorage.setItem("truthchecker_token", state.token);
    else sessionStorage.removeItem("truthchecker_token");
  }
  function updateAccountUI() {
    accountEmail.textContent = state.user?.email || "";
    accountBox.hidden = !state.user;
  }
  async function loadCurrentUser() {
    if (!state.token) return false;
    try {
      const res = await fetch(`${API_BASE}/api/auth/me`, { headers: authHeaders() });
      if (!res.ok) throw new Error();
      state.user = await res.json();
      updateAccountUI();
      return true;
    } catch {
      setToken(""); state.user = null; updateAccountUI(); return false;
    }
  }

  $("#login-tab").addEventListener("click", () => { $("#login-tab").classList.add("is-active"); $("#register-tab").classList.remove("is-active"); $("#login-form").hidden=false; $("#register-form").hidden=true; clearAuthError(); });
  $("#register-tab").addEventListener("click", () => { $("#register-tab").classList.add("is-active"); $("#login-tab").classList.remove("is-active"); $("#login-form").hidden=true; $("#register-form").hidden=false; clearAuthError(); });

  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault(); clearAuthError();
    const btn=e.currentTarget.querySelector("button"); btn.disabled=true;
    try {
      const res=await fetch(`${API_BASE}/api/auth/login`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("#login-email").value,password:$("#login-password").value})});
      const data=await res.json(); if(!res.ok) throw new Error(data.detail||"Connexion impossible.");
      setToken(data.token); state.user=data.user; updateAccountUI(); authModal.close(); showToast("Connexion réussie.");
    } catch(err){ showAuthError(err.message); } finally { btn.disabled=false; }
  });

  $("#register-form").addEventListener("submit", async (e) => {
    e.preventDefault(); clearAuthError();
    const btn=e.currentTarget.querySelector("button"); btn.disabled=true;
    try {
      const res=await fetch(`${API_BASE}/api/auth/register`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("#register-email").value,password:$("#register-password").value})});
      const data=await res.json(); if(!res.ok) throw new Error(data.detail||"Création du compte impossible.");
      setToken(data.token); state.user=data.user; updateAccountUI(); authModal.close(); showToast("Compte créé avec succès.");
    } catch(err){ showAuthError(err.message); } finally { btn.disabled=false; }
  });

  $("#logout-btn").addEventListener("click", () => { setToken(""); state.user=null; updateAccountUI(); openAuth(); showToast("Vous êtes déconnecté."); });

  async function requireAuth() {
    const ok = await loadCurrentUser();
    if (!ok) openAuth();
    return ok;
  }

  // ================================================================ Theme Management
  function initTheme() {
    const savedTheme = localStorage.getItem("truthchecker_theme") || "dark";
    document.documentElement.setAttribute("data-theme", savedTheme);
    if (savedTheme === "light") {
      document.documentElement.classList.add("light-mode");
      $("#theme-toggle").textContent = "☀️";
    } else {
      document.documentElement.classList.remove("light-mode");
      $("#theme-toggle").textContent = "🌙";
    }
  }

  $("#theme-toggle").addEventListener("click", () => {
    const isDark = document.documentElement.classList.contains("light-mode");
    const newTheme = isDark ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", newTheme);
    document.documentElement.classList.toggle("light-mode");
    localStorage.setItem("truthchecker_theme", newTheme);
    $("#theme-toggle").textContent = newTheme === "light" ? "☀️" : "🌙";
    showToast(state.lang === "fr" 
      ? `Mode ${newTheme === "light" ? "clair" : "sombre"} activé` 
      : `${newTheme === "light" ? "Light" : "Dark"} mode enabled`);
  });

  initTheme();
  updateAccountUI();
  requireAuth();

  const VERDICT_LABELS = {
    fr: { vrai: "VÉRIFIÉ", faux: "FAUX", partiellement_vrai: "À NUANCER", non_verifiable: "NON VÉRIFIABLE", trompeur: "TROMPEUR", "obsolète": "OBSOLET" },
    en: { vrai: "VERIFIED", faux: "FALSE", partiellement_vrai: "MIXED", non_verifiable: "UNVERIFIABLE", trompeur: "MISLEADING", "obsolète": "OUTDATED" },
    mg: { vrai: "MARINA", faux: "DISO", partiellement_vrai: "AMPAHANY", non_verifiable: "TSY VOAMARINA", trompeur: "MAMITAKA", "obsolète": "FA TALOHA" },
  };
  const STANCE_ICON = { confirme: "✓", contredit: "✕", contexte: "•" };
  const STEP_ORDER = ["read", "search", "compare", "score"];

  function scoreColor(score) {
    if (score >= 70) return "var(--verified)";
    if (score >= 40) return "var(--mixed)";
    return "var(--false)";
  }
  function verdictColor(verdict) {
    return { vrai: "var(--verified)", faux: "var(--false)", partiellement_vrai: "var(--mixed)", non_verifiable: "var(--unknown)" }[verdict] || "var(--unknown)";
  }

  // ---------------------------------------------------------------- date
  $("#today-date").textContent = new Date().toLocaleDateString(
    state.lang === "fr" ? "fr-FR" : "en-US",
    { day: "2-digit", month: "long", year: "numeric" }
  );

  // ---------------------------------------------------------------- tabs
  function setType(type) {
    state.type = type;
    $$(".tab").forEach((t) => {
      const active = t.dataset.type === type;
      t.classList.toggle("is-active", active);
      t.setAttribute("aria-selected", String(active));
    });
    $$(".panel").forEach((p) => p.classList.toggle("is-active", p.dataset.panel === type));
    hideError();
  }
  $$(".tab").forEach((tab) => tab.addEventListener("click", () => setType(tab.dataset.type)));

  // ---------------------------------------------------------------- lang
  $$(".lang-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".lang-btn").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      state.lang = btn.dataset.lang;
      const locale = state.lang === "fr" ? "fr-FR" : state.lang === "mg" ? "mg-MG" : "en-US";
      $("#today-date").textContent = new Date().toLocaleDateString(locale, { day: "2-digit", month: "long", year: "numeric" });
    });
  });

  // ---------------------------------------------------------------- text counter
  const textInput = $("#input-text");
  textInput.addEventListener("input", () => { $("#text-count").textContent = String(textInput.value.length); });

  // ---------------------------------------------------------------- paste buttons
  async function pasteInto(input) {
    try {
      const text = await navigator.clipboard.readText();
      input.value = text;
      input.dispatchEvent(new Event("input"));
      input.focus();
    } catch {
      showToast(state.lang === "fr" ? "Impossible de lire le presse-papier." : "Couldn't read clipboard.");
    }
  }
  $("#paste-text").addEventListener("click", () => pasteInto(textInput));
  $("#paste-url").addEventListener("click", () => pasteInto($("#input-url")));

  // ---------------------------------------------------------------- example chips
  $$("#example-chips .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const [type, content] = chip.dataset.example.split("|");
      setType(type);
      if (type === "text") { textInput.value = content; textInput.dispatchEvent(new Event("input")); textInput.focus(); }
      else if (type === "url") { $("#input-url").value = content; $("#input-url").focus(); }
    });
  });

  // ---------------------------------------------------------------- image dropzone
  const dropzone = $("#dropzone");
  const fileInput = $("#input-image");
  const previewImg = $("#dropzone-preview");
  const emptyState = $("#dropzone-empty");
  const removeBtn = $("#dropzone-remove");

  dropzone.addEventListener("click", (e) => { if (e.target !== removeBtn) fileInput.click(); });
  dropzone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
  ["dragover", "dragenter"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("is-drag"); }));
  ["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("is-drag"); }));
  dropzone.addEventListener("drop", (e) => { const f = e.dataTransfer.files?.[0]; if (f) handleFile(f); });
  fileInput.addEventListener("change", () => { if (fileInput.files?.[0]) handleFile(fileInput.files[0]); });
  removeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    state.imageBase64 = null; state.imageMediaType = null;
    fileInput.value = "";
    previewImg.hidden = true; removeBtn.hidden = true; emptyState.hidden = false;
  });

  function handleFile(file) {
    if (!file.type.startsWith("image/")) { showError("Merci de choisir un fichier image."); return; }
    if (file.size > 8 * 1024 * 1024) { showError("Image trop lourde (8 Mo maximum)."); return; }
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      const [meta, b64] = result.split(",");
      state.imageBase64 = b64;
      state.imageMediaType = meta.match(/data:(.*);base64/)?.[1] || file.type;
      previewImg.src = result; previewImg.hidden = false;
      emptyState.hidden = true; removeBtn.hidden = false;
    };
    reader.readAsDataURL(file);
  }

  // ---------------------------------------------------------------- errors / toast
  function showError(msg) { const el = $("#error-msg"); el.textContent = msg; el.hidden = false; }
  function hideError() { $("#error-msg").hidden = true; }

  let toastTimer = null;
  function showToast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("is-visible"), 2400);
  }

  // ---------------------------------------------------------------- stats (session)
  function refreshStats() {
    $("#stat-checks").textContent = String(state.sessionChecks);
    $("#stat-sources").textContent = String(state.sessionSources);
    $("#stat-verified").textContent = String(state.sessionVerified);
    $("#stat-false").textContent = String(state.sessionFalse);
  }
  try {
    const saved = JSON.parse(sessionStorage.getItem("truthchecker_stats") || "{}");
    state.sessionChecks = saved.checks || 0;
    state.sessionSources = saved.sources || 0;
    state.sessionVerified = saved.verified || 0;
    state.sessionFalse = saved.false || 0;
  } catch { /* ignore */ }
  refreshStats();

  function bumpStats(sourcesCount, verdict) {
    state.sessionChecks += 1;
    state.sessionSources += sourcesCount;
    if (verdict === "vrai") state.sessionVerified += 1;
    if (verdict === "faux") state.sessionFalse += 1;
    sessionStorage.setItem("truthchecker_stats", JSON.stringify({ 
      checks: state.sessionChecks, 
      sources: state.sessionSources,
      verified: state.sessionVerified,
      false: state.sessionFalse
    }));
    refreshStats();
  }

  // ---------------------------------------------------------------- history (persisted)
  function loadHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); } catch { return []; }
  }
  function saveHistoryEntry(data) {
    const list = loadHistory();
    list.unshift({ id: Date.now(), data });
    localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, MAX_HISTORY)));
    renderHistory();
  }
  function renderHistory() {
    const list = loadHistory();
    const container = $("#history-list");
    const clearBtn = $("#clear-history");
    clearBtn.hidden = list.length === 0;
    if (list.length === 0) {
      container.innerHTML = `<li class="history-empty">Vos dossiers récents apparaîtront ici — rien stocké ailleurs que sur cet appareil.</li>`;
      return;
    }
    container.innerHTML = "";
    list.forEach((entry) => {
      const li = document.createElement("li");
      li.className = "history-item";
      li.innerHTML = `
        <span class="history-item__dot" data-verdict="${entry.data.verdict}"></span>
        <span class="history-item__text">${escapeHtml(entry.data.headline_claim || "—")}</span>
        <span class="history-item__score">${entry.data.score ?? entry.data.evidence_score ?? 0}</span>
      `;
      li.addEventListener("click", () => {
        dossier.hidden = false;
        traceSection.hidden = true;
        renderDossier(entry.data, { fromHistory: true });
        window.scrollTo({ top: dossier.offsetTop - 20, behavior: "smooth" });
      });
      container.appendChild(li);
    });
  }
  $("#clear-history").addEventListener("click", () => {
    localStorage.removeItem(HISTORY_KEY);
    renderHistory();
  });
  renderHistory();

  // ---------------------------------------------------------------- loading trace
  const traceSection = $("#trace");
  const traceSteps = $$("#trace-steps li");
  const traceBar = $("#trace-bar");
  const traceQueries = $("#trace-queries");
  const investigationBoard = $("#investigation-board");
  const investigationFeed = $("#investigation-feed");
  const investigationStatus = $("#investigation-status");
  const investigationCore = $("#investigation-core");
  const investigationCoreLabel = $("#investigation-core-label");
  const investigationCoreDetail = $("#investigation-core-detail");
  let fallbackTimer = null;
  let investigationStartedAt = 0;
  let investigationSearchCount = 0;

  function resetInvestigation() {
    investigationStartedAt = performance.now();
    investigationSearchCount = 0;
    if (investigationBoard) investigationBoard.classList.remove("is-complete", "is-error");
    if (investigationFeed) investigationFeed.innerHTML = "";
    if (investigationStatus) investigationStatus.textContent = state.lang === "fr" ? "Connexion au moteur de preuves…" : "Connecting to evidence engine…";
    if (investigationCoreLabel) investigationCoreLabel.textContent = "CLAIM";
    if (investigationCoreDetail) investigationCoreDetail.textContent = state.lang === "fr" ? "Analyse en préparation" : "Preparing analysis";
    $$(".investigation-node").forEach(n => { n.classList.remove("is-active", "is-done", "is-error"); const sm = n.querySelector("small"); if (sm) sm.textContent = n.dataset.node === "search" ? "0 requête" : n.dataset.node === "compare" ? "0 source" : "—"; });
  }

  function activateInvestigationNode(key, detail = "") {
    const node = document.querySelector(`.investigation-node[data-node="${key}"]`);
    if (!node) return;
    const order = ["read", "search", "compare", "score"];
    const idx = order.indexOf(key);
    $$(".investigation-node").forEach(n => {
      const ni = order.indexOf(n.dataset.node);
      n.classList.toggle("is-done", ni >= 0 && ni < idx);
      n.classList.toggle("is-active", n === node);
    });
    if (detail) { const sm = node.querySelector("small"); if (sm) sm.textContent = detail; }
    if (investigationCoreLabel) investigationCoreLabel.textContent = key === "read" ? "CLAIM" : key === "search" ? "SEARCH" : key === "compare" ? "EVIDENCE" : "VERDICT";
    if (investigationCoreDetail) investigationCoreDetail.textContent = detail || "Enquête en cours";
    if (investigationStatus) investigationStatus.textContent = key === "search" ? "Recherche de preuves en direct…" : key === "compare" ? "Confrontation des sources…" : key === "score" ? "Construction du verdict…" : "Lecture et extraction du claim…";
  }

  function pushInvestigationFeed(kind, text) {
    if (!investigationFeed || !text) return;
    const item = document.createElement("div");
    item.className = "investigation-feed__item";
    item.innerHTML = `<span class="investigation-feed__dot"></span><span>${escapeHtml(text)}</span><time>${new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"})}</time>`;
    investigationFeed.prepend(item);
    while (investigationFeed.children.length > 4) investigationFeed.lastElementChild.remove();
  }

  function completeInvestigation(data) {
    if (!investigationBoard) return;
    const sources = data?.sources || [];
    const searches = Number(data?.searches_performed ?? data?.metadata?.search_count ?? investigationSearchCount);
    investigationBoard.classList.add("is-complete");
    $$(".investigation-node").forEach(n => n.classList.add("is-done"));
    const searchNode = document.querySelector('.investigation-node[data-node="search"] small');
    const compareNode = document.querySelector('.investigation-node[data-node="compare"] small');
    const scoreNode = document.querySelector('.investigation-node[data-node="score"] small');
    if (searchNode) searchNode.textContent = `${searches} requête${searches > 1 ? "s" : ""}`;
    if (compareNode) compareNode.textContent = `${sources.length} source${sources.length > 1 ? "s" : ""}`;
    if (scoreNode) scoreNode.textContent = `${Math.round(Number(data?.score ?? 0))}/100`;
    if (investigationStatus) investigationStatus.textContent = state.lang === "fr" ? `Enquête terminée · ${(performance.now() - investigationStartedAt) / 1000 < 60 ? ((performance.now() - investigationStartedAt) / 1000).toFixed(1) + " s" : "terminée"}` : "Investigation complete";
    if (investigationCoreLabel) investigationCoreLabel.textContent = "VERDICT";
    if (investigationCoreDetail) investigationCoreDetail.textContent = VERDICT_LABELS[state.lang]?.[data?.verdict] || data?.verdict || "Terminé";
  }

  function resetTrace() {
    traceSteps.forEach((li) => li.classList.remove("is-active", "is-done"));
    traceQueries.innerHTML = "";
    traceBar.style.width = "4%";
    resetInvestigation();
  }
  function setStepByKey(key) {
    const idx = STEP_ORDER.indexOf(key);
    if (idx === -1) return;
    traceSteps.forEach((li, i) => {
      li.classList.toggle("is-done", i < idx);
      li.classList.toggle("is-active", i === idx);
    });
    traceBar.style.width = `${Math.min(96, ((idx + 1) / STEP_ORDER.length) * 100)}%`;
  }
  function markStepDoneAll() {
    traceSteps.forEach((li) => { li.classList.remove("is-active"); li.classList.add("is-done"); });
    traceBar.style.width = "100%";
  }
  function addQuery(text) {
    const li = document.createElement("li");
    li.textContent = text;
    traceQueries.appendChild(li);
    investigationSearchCount += 1;
    activateInvestigationNode("search", `${investigationSearchCount} requête${investigationSearchCount > 1 ? "s" : ""}`);
    pushInvestigationFeed("search", text);
  }

  // simulated fallback progression, used only if the live SSE stream is unavailable
  function startFallbackProgress() {
    let i = 0;
    const advance = () => {
      setStepByKey(STEP_ORDER[i]);
      i++;
      if (i < STEP_ORDER.length) fallbackTimer = setTimeout(advance, 1400 + Math.random() * 900);
    };
    advance();
  }
  function stopFallbackProgress() { clearTimeout(fallbackTimer); }

  // ---------------------------------------------------------------- submit
  const form = $("#analyze-form");
  const submitBtn = $("#submit-btn");
  const dossier = $("#dossier");

  function buildPayload() {
    const payload = { type: state.type, language: state.lang, content: "" };
    if (state.type === "text") {
      const v = textInput.value.trim();
      if (!v) return { error: "Merci de coller un texte à vérifier." };
      payload.content = v;
    } else if (state.type === "url") {
      const v = $("#input-url").value.trim();
      if (!v) return { error: "Merci de renseigner une URL." };
      try { new URL(v); } catch { return { error: "Cette URL ne semble pas valide." }; }
      payload.content = v;
    } else if (state.type === "image") {
      if (!state.imageBase64) return { error: "Merci d'importer une image." };
      payload.image_base64 = state.imageBase64;
      payload.image_media_type = state.imageMediaType;
      payload.content = $("#input-image-caption").value.trim();
    }
    return { payload };
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideError();
    if (!(await requireAuth())) return;

    const { payload, error } = buildPayload();
    if (error) return showError(error);

    dossier.hidden = true;
    submitBtn.disabled = true;
    traceSection.hidden = false;
    traceSection.classList.add("is-streaming");
    resetTrace();

    let handled = false;
    try {
      handled = await runStreaming(payload);
    } catch {
      handled = false;
    }

    if (!handled) {
      startFallbackProgress();
      try {
        const res = await fetch(`${API_BASE}/api/analyze`, {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (res.status === 401) { setToken(""); state.user=null; updateAccountUI(); openAuth(); throw new Error("Votre session a expiré."); }
        if (!res.ok) throw new Error(data.detail || "Une erreur est survenue.");
        markStepDoneAll();
        setTimeout(() => finishAnalysis(data), 250);
      } catch (err) {
        traceSection.hidden = true;
        traceSection.classList.remove("is-streaming");
        showError(err.message || "Impossible de joindre le serveur d'analyse. Vérifiez que le backend tourne.");
        submitBtn.disabled = false;
      } finally {
        stopFallbackProgress();
      }
    }
  });

  // Live progress via Server-Sent Events (POST + manual stream read, since
  // EventSource doesn't support POST bodies). Falls back to /api/analyze on
  // any failure so the app still works if streaming isn't reachable.
  async function runStreaming(payload) {
    const res = await fetch(`${API_BASE}/api/analyze/stream`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });
    if (res.status === 401) { setToken(""); state.user=null; updateAccountUI(); openAuth(); return false; }
    if (!res.ok || !res.body) return false;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let gotResult = false;
    let gotError = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const eventMatch = chunk.match(/^event:\s*(.+)$/m);
        const dataMatch = chunk.match(/^data:\s*(.+)$/m);
        if (!eventMatch || !dataMatch) continue;
        const eventName = eventMatch[1].trim();
        let data;
        try { data = JSON.parse(dataMatch[1]); } catch { continue; }

        if (eventName === "step") {
          if (/lecture/i.test(data.label)) { setStepByKey("read"); activateInvestigationNode("read", "Claim extrait"); pushInvestigationFeed("read", data.label); }
          else if (/comparaison/i.test(data.label)) { setStepByKey("compare"); activateInvestigationNode("compare", "Sources confrontées"); pushInvestigationFeed("compare", data.label); }
          else if (/rédaction|verdict/i.test(data.label)) { setStepByKey("score"); activateInvestigationNode("score", "Calcul déterministe"); pushInvestigationFeed("score", data.label); }
        } else if (eventName === "search") {
          setStepByKey("search");
          addQuery(data.query);
        } else if (eventName === "fetch") {
          setStepByKey("read");
          activateInvestigationNode("read", "Source ouverte");
          pushInvestigationFeed("fetch", data.url || data.title || "Source consultée");
        } else if (eventName === "result") {
          markStepDoneAll();
          gotResult = true;
          completeInvestigation(data);
          setTimeout(() => finishAnalysis(data), 650);
        } else if (eventName === "error") {
          gotError = true;
        }
      }
    }

    if (gotResult) return true;
    if (gotError) { submitBtn.disabled = false; traceSection.hidden = true; showError(state.lang === "fr" ? "La vérification en direct a échoué. Nouvelle tentative..." : "Live verification failed. Retrying..."); return false; }
    return false;
  }

  function finishAnalysis(data) {
    traceSection.hidden = true;
    traceSection.classList.remove("is-streaming");
    submitBtn.disabled = false;
    renderDossier(data);
    completeInvestigation(data);
    bumpStats((data.sources || []).length, data.verdict);
    saveHistoryEntry(data);
  }

  $("#btn-again").addEventListener("click", () => {
    dossier.hidden = true;
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  // keyboard shortcut: Ctrl/Cmd+Enter submits from anywhere in the form
  form.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  // ---------------------------------------------------------------- copy dossier
  let currentDossierData = null;

  $("#btn-copy").addEventListener("click", async () => {
    const text = $("#dossier").dataset.shareText || "";
    try {
      await navigator.clipboard.writeText(text);
      showToast(state.lang === "fr" ? "Dossier copié dans le presse-papier !" : "Dossier copied to clipboard!");
    } catch {
      showToast(state.lang === "fr" ? "Impossible de copier." : "Couldn't copy.");
    }
  });

  // ---------------------------------------------------------------- export dossier
  $("#btn-export-json").addEventListener("click", () => {
    if (!currentDossierData) {
      showToast(state.lang === "fr" ? "Aucun dossier à exporter." : "No dossier to export.");
      return;
    }
    const json = JSON.stringify(currentDossierData, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `truthchecker-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast(state.lang === "fr" ? "Dossier exporté en JSON ✓" : "Dossier exported as JSON ✓");
  });

  $("#btn-export-pdf").addEventListener("click", () => {
    if (!currentDossierData) {
      showToast(state.lang === "fr" ? "Aucun dossier à exporter." : "No dossier to export.");
      return;
    }
    const html = generateDossierHTML(currentDossierData);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `truthchecker-${Date.now()}.html`;
    a.click();
    URL.revokeObjectURL(url);
    showToast(state.lang === "fr" ? "Dossier exporté en HTML ✓" : "Dossier exported as HTML ✓");
  });

  $("#btn-share").addEventListener("click", async () => {
    if (!currentDossierData) {
      showToast(state.lang === "fr" ? "Aucun dossier à partager." : "No dossier to share.");
      return;
    }
    const text = $("#dossier").dataset.shareText || "";
    if (navigator.share) {
      try {
        await navigator.share({
          title: "Truth Checker",
          text: text.split("\n")[0],
          url: window.location.href,
        });
      } catch (err) {
        if (err.name !== "AbortError") {
          showToast(state.lang === "fr" ? "Erreur lors du partage." : "Share failed.");
        }
      }
    } else {
      await navigator.clipboard.writeText(text);
      showToast(state.lang === "fr" ? "Dossier copié (partage non disponible)" : "Copied (sharing unavailable)");
    }
  });

  function generateDossierHTML(data) {
    const labels = VERDICT_LABELS[state.lang] || VERDICT_LABELS.fr;
    const sources = (data.sources || []).map(s => 
      `<li data-stance="${s.stance || 'contexte'}">
        <strong>${escapeHtml(s.title)}</strong><br>
        <a href="${escapeAttr(s.url)}" target="_blank">${escapeHtml(s.domain || s.url)}</a><br>
        <em>${escapeHtml(s.excerpt || '')}</em>
      </li>`
    ).join("");

    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Truth Checker - Dossier #${data.__ref || Date.now()}</title>
  <style>
    body { font-family: system-ui; max-width: 900px; margin: 20px auto; color: #333; }
    .header { border-bottom: 3px solid #c9a567; padding-bottom: 20px; }
    .verdict { font-size: 2em; font-weight: bold; margin: 20px 0; }
    .verdict.true { color: #3fb88a; }
    .verdict.false { color: #e15252; }
    .verdict.mixed { color: #e0a93e; }
    .score { font-size: 3em; font-weight: bold; }
    .section { margin: 30px 0; }
    .section h2 { color: #c9a567; border-bottom: 1px solid #ddd; padding-bottom: 10px; }
    .sources { list-style: none; padding: 0; }
    .sources li { padding: 15px; margin: 10px 0; border-left: 3px solid #ddd; }
    .sources li[data-stance="confirme"] { border-left-color: #3fb88a; }
    .sources li[data-stance="contredit"] { border-left-color: #e15252; }
    .sources li[data-stance="contexte"] { border-left-color: #8891a3; }
    a { color: #c9a567; }
    .footer { color: #999; font-size: 0.9em; margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; }
  </style>
</head>
<body>
  <div class="header">
    <h1>Truth Checker — Dossier de vérification</h1>
    <p>Généré le ${new Date().toLocaleString()}</p>
  </div>

  <div class="section">
    <h2>Affirmation analysée</h2>
    <blockquote>${escapeHtml(data.headline_claim || '—')}</blockquote>
  </div>

  <div class="section">
    <h2>Verdict</h2>
    <div class="score verdict ${data.verdict === 'vrai' ? 'true' : data.verdict === 'faux' ? 'false' : 'mixed'}">${data.score}/100</div>
    <p><strong>${labels[data.verdict] || data.verdict}</strong></p>
    <p>${escapeHtml(data.summary || '')}</p>
  </div>

  <div class="section">
    <h2>Explication</h2>
    <p>${escapeHtml(data.explanation || '')}</p>
  </div>

  ${data.correction ? `<div class="section">
    <h2>Ce que disent réellement les faits</h2>
    <p>${escapeHtml(data.correction)}</p>
  </div>` : ''}

  <div class="section">
    <h2>Sources consultées</h2>
    ${sources ? `<ul class="sources">${sources}</ul>` : '<p>Aucune source trouvée.</p>'}
  </div>

  <div class="footer">
    <p>Truth Checker • Projet UNESCO Hackathon Jeunesse 2026</p>
    <p>Cet outil est une aide à la vérification, pas un arbitre absolu de la vérité.</p>
  </div>
</body>
</html>`;
  }

  // ---------------------------------------------------------------- evidence filters
  let currentSources = [];

  // ================================================================ Truth Lab
  const PASSPORT_KEY = "truthchecker_passport_v1";
  const DEMO_KEY = "truthchecker_demo_mode";

  function passportStats() {
    const history = loadHistory();
    const checks = history.length;
    const sources = history.reduce((n, x) => n + ((x.data?.sources || []).length), 0);
    const verified = history.filter(x => x.data?.verdict === "vrai").length;
    const challenged = Number(localStorage.getItem("truthchecker_challenges") || 0);
    const high = history.filter(x => Number(x.data?.score || 0) >= 70).length;
    const badges = [];
    if (checks >= 1) badges.push(["🔎", "Premier contrôle"]);
    if (checks >= 5) badges.push(["🧭", "Vérificateur régulier"]);
    if (sources >= 20) badges.push(["📚", "Chercheur de preuves"]);
    if (challenged >= 3) badges.push(["⚔️", "Esprit critique"]);
    if (high >= 5) badges.push(["🏅", "5 dossiers solides"]);
    return { checks, sources, verified, challenged, high, badges };
  }

  function openModal(id) {
    const el = document.getElementById(id);
    if (el?.showModal) el.showModal(); else el?.classList.add("is-open");
  }
  function closeModal(id) {
    const el = document.getElementById(id);
    if (el?.close) el.close(); else el?.classList.remove("is-open");
  }
  $$("[data-close]").forEach(btn => btn.addEventListener("click", () => closeModal(btn.dataset.close)));

  function renderPassport() {
    const s = passportStats();
    const percent = s.checks ? Math.round((s.verified / s.checks) * 100) : 0;
    $("#passport-content").innerHTML = `
      <div class="passport-hero"><div class="passport-orbit">🛡️</div><div><strong>Explorateur de vérité</strong><p>Votre activité reste locale sur cet appareil.</p></div></div>
      <div class="passport-grid">
        <div><span>Vérifications</span><strong>${s.checks}</strong></div>
        <div><span>Sources consultées</span><strong>${s.sources}</strong></div>
        <div><span>Verdicts vérifiés</span><strong>${s.verified}</strong></div>
        <div><span>Challenges</span><strong>${s.challenged}</strong></div>
      </div>
      <div class="passport-progress"><div><span>Progression EMI</span><strong>${percent}%</strong></div><div class="progress-track"><i style="width:${percent}%"></i></div></div>
      <div class="badge-list">${s.badges.length ? s.badges.map(b => `<span>${b[0]} ${escapeHtml(b[1])}</span>`).join("") : `<span class="muted">Vérifiez votre première information pour débloquer un badge.</span>`}</div>`;
    openModal("passport-modal");
  }

  function renderChallenge(data = currentDossierData) {
    if (!data) { showToast(state.lang === "fr" ? "Faites d'abord une vérification." : "Run a verification first."); return; }
    const labels = VERDICT_LABELS[state.lang] || VERDICT_LABELS.fr;
    const challenge = {
      id: crypto?.randomUUID ? crypto.randomUUID() : String(Date.now()),
      claim: data.headline_claim || "Affirmation",
      verdict: data.verdict,
      score: Number(data.score || 0),
      createdAt: Date.now(),
    };
    const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(challenge))));
    const shareUrl = `${location.origin}${location.pathname}#challenge=${encoded}`;
    $("#challenge-content").innerHTML = `
      <div class="challenge-card">
        <span class="eyebrow">DÉFI #${challenge.id.slice(-6)}</span>
        <h3>${escapeHtml(challenge.claim)}</h3>
        <p>Choisis ton verdict avant de montrer les preuves à ton ami.</p>
        <div class="challenge-choices">
          <button data-choice="vrai">🟢 VRAI</button><button data-choice="faux">🔴 FAUX</button><button data-choice="partiellement_vrai">🟡 À NUANCER</button>
        </div>
        <div class="challenge-reveal" hidden><strong>Verdict TruthChecker : ${escapeHtml(labels[challenge.verdict] || challenge.verdict)}</strong><span>Evidence Score : ${challenge.score}/100</span><p>Le but est de comparer votre démarche avec les preuves, pas seulement de deviner.</p></div>
        <div class="challenge-share"><input readonly value="${escapeAttr(shareUrl)}"/><button id="copy-challenge">Copier le défi</button></div>
      </div>`;
    $("#challenge-content").querySelectorAll("[data-choice]").forEach(btn => btn.addEventListener("click", () => {
      $("#challenge-content .challenge-reveal").hidden = false;
      const correct = btn.dataset.choice === challenge.verdict;
      localStorage.setItem("truthchecker_challenges", String(Number(localStorage.getItem("truthchecker_challenges") || 0) + 1));
      showToast(correct ? "Bonne lecture des preuves ✓" : "Compare maintenant avec les preuves.");
    }));
    $("#copy-challenge").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(shareUrl); showToast("Défi copié ✓"); } catch { showToast("Copiez le lien manuellement."); }
    });
    openModal("challenge-modal");
  }

  $("#btn-passport")?.addEventListener("click", renderPassport);
  $("#btn-result-passport")?.addEventListener("click", renderPassport);
  $("#btn-challenge")?.addEventListener("click", () => renderChallenge());
  $("#btn-result-challenge")?.addEventListener("click", () => renderChallenge());
  $("#btn-demo")?.addEventListener("click", () => {
    document.body.classList.toggle("jury-mode");
    const active = document.body.classList.contains("jury-mode");
    localStorage.setItem(DEMO_KEY, active ? "1" : "0");
    showToast(active ? "Mode Jury activé — interface épurée." : "Mode Jury désactivé.");
  });
  if (localStorage.getItem(DEMO_KEY) === "1") document.body.classList.add("jury-mode");

  $$("#evidence-filters .filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("#evidence-filters .filter-btn").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      applyFilter(btn.dataset.filter);
    });
  });
  function applyFilter(filter) {
    $$("#evidence-list .evidence__item").forEach((li) => {
      li.classList.toggle("is-hidden", filter !== "all" && li.dataset.stance !== filter);
    });
  }

  // ---------------------------------------------------------------- render
  function renderDossier(data, opts = {}) {
    const lang = state.lang;
    const labels = VERDICT_LABELS[lang] || VERDICT_LABELS.fr;

    currentDossierData = data;
    data.__ref = data.__ref || Date.now();

    $("#dossier-ref").textContent = `DOSSIER #${String(opts.fromHistory ? data.__ref : Date.now()).slice(-6)}`;

    const stamp = $("#stamp");
    stamp.textContent = labels[data.verdict] || data.verdict;
    stamp.dataset.verdict = data.verdict;
    stamp.style.animation = "none"; void stamp.offsetWidth; stamp.style.animation = "";

    document.documentElement.style.setProperty("--verdict-glow", hexGlow(data.verdict));

    const score = Math.max(0, Math.min(100, Number(data.score) || 0));
    const circumference = 251;
    const gaugeValue = $("#gauge-value");
    const color = scoreColor(score);
    gaugeValue.style.stroke = color;
    gaugeValue.style.transition = "none";
    gaugeValue.style.strokeDashoffset = String(circumference);
    void gaugeValue.offsetWidth;
    gaugeValue.style.transition = "";
    gaugeValue.style.strokeDashoffset = String(circumference * (1 - score / 100));

    $("#gauge-score").textContent = score;
    $("#gauge-score").style.color = color;

    $("#headline-claim").textContent = data.headline_claim || "—";
    $("#summary-text").textContent = data.summary || "";
    $("#explanation-text").textContent = data.explanation || "";

    renderMetaCards(data);
    renderEvidenceSignal(data);
    renderAuditTimeline(data);
    renderClaims(data.claims || []);
    renderEvidenceGraph(data);

    const bd = data.confidence_breakdown || {};
    setBreakdown("bd-source", bd.source_reliability);
    setBreakdown("bd-corr", bd.corroboration);
    setBreakdown("bd-cons", bd.consensus);

    const correctionBlock = $("#correction-block");
    if (data.correction) {
      const correctionText = typeof data.correction === "string" ? data.correction : (data.correction.text || "");
      const corrSources = (data.sources || []).filter(s => s.stance === "contredit").slice(0, 3);
      $("#correction-text").innerHTML = `${escapeHtml(correctionText)}${corrSources.length ? `<div class="correction-sources"><strong>Sources de la correction</strong>${corrSources.map(s => `<a href="${escapeAttr(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title || s.domain)}</a>`).join("")}</div>` : ""}`;
      correctionBlock.hidden = !correctionText;
    } else { correctionBlock.hidden = true; }

    currentSources = data.sources || [];
    const list = $("#evidence-list");
    list.innerHTML = "";
    if (currentSources.length === 0) {
      list.innerHTML = `<li class="evidence__empty">${lang === "fr" ? "Aucune source exploitable n'a été trouvée pour cette recherche." : "No usable source was found for this search."}</li>`;
    } else {
      currentSources.forEach((s) => {
        const li = document.createElement("li");
        li.className = "evidence__item";
        li.id = `evidence-source-${currentSources.indexOf(s)}`;
        li.dataset.stance = s.stance || "contexte";
        const quality = Math.max(0, Math.min(100, Number(s.authority_score ?? 0)));
        const freshness = s.freshness || "inconnu";
        li.innerHTML = `
          <span class="evidence__marker">${STANCE_ICON[s.stance] || "•"}</span>
          <p class="evidence__title"><a href="${escapeAttr(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title || s.url)}</a></p>
          <span class="evidence__domain">${escapeHtml(s.domain || "")} · qualité ${quality}/100 · ${escapeHtml(freshness)}</span>
          <p class="evidence__excerpt">${escapeHtml(s.excerpt || "")}</p>
        `;
        list.appendChild(li);
      });
    }
    $$("#evidence-filters .filter-btn").forEach((b) => b.classList.toggle("is-active", b.dataset.filter === "all"));
    applyFilter("all");

    const footer = $("#dossier-footer");
    const n = data.searches_performed ?? 0;
    const ms = data.elapsed_ms ?? 0;
    footer.textContent = lang === "fr"
      ? `${n} recherche${n > 1 ? "s" : ""} effectuée${n > 1 ? "s" : ""} sur le web · analyse en ${(ms / 1000).toFixed(1)}s`
      : `${n} web search${n > 1 ? "es" : ""} performed · analyzed in ${(ms / 1000).toFixed(1)}s`;

    $("#dossier").dataset.shareText = buildShareText(data, labels);

    dossier.hidden = false;
    if (!opts.fromHistory) dossier.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderMetaCards(data) {
    const meta = data.metadata || {};
    const sourceCount = (data.sources || []).length;
    const supportCount = (data.sources || []).filter(s => s.stance === "confirme").length;
    const contradictionCount = (data.sources || []).filter(s => s.stance === "contredit").length;
    const el = $("#result-meta");
    if (!el) return;
    const cards = [
      ["Sources", sourceCount, "preuves trouvées"],
      ["Confirment", supportCount, "sources favorables"],
      ["Contredisent", contradictionCount, "sources opposées"],
      ["Recherches", data.searches_performed ?? meta.search_count ?? 0, "requêtes web"],
    ];
    el.innerHTML = cards.map(([label, value, note]) => `<div class="meta-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></div>`).join("");
  }

  function renderClaims(claims) {
    const wrap = $("#claims-list");
    if (!wrap) return;
    if (!claims.length) {
      wrap.innerHTML = `<div class="claims-empty">La vérification porte sur l'affirmation principale.</div>`;
      return;
    }
    const labels = VERDICT_LABELS[state.lang] || VERDICT_LABELS.fr;
    wrap.innerHTML = claims.map((c, i) => {
      const verdict = c.verdict || "non_verifiable";
      const score = Number(c.evidence_score ?? 0);
      return `<article class="claim-card" data-verdict="${escapeAttr(verdict)}">
        <div class="claim-card__head"><span class="claim-card__index">0${i + 1}</span><span class="claim-card__badge">${escapeHtml(labels[verdict] || verdict)}</span><strong>${Math.max(0, Math.min(100, score))}/100</strong></div>
        <p>${escapeHtml(c.text || "")}</p>
        ${c.explanation ? `<small>${escapeHtml(c.explanation)}</small>` : ""}
      </article>`;
    }).join("");
  }

  function renderEvidenceSignal(data) {
    const score = Math.max(0, Math.min(100, Number(data.score ?? data.evidence_score ?? 0) || 0));
    const fill = $("#signal-fill");
    const marker = $("#signal-marker");
    const status = $("#evidence-signal-status");
    const title = $("#evidence-signal-title");
    if (!fill || !marker) return;
    fill.style.width = `${score}%`;
    marker.style.left = `calc(${score}% - 5px)`;
    fill.style.background = `linear-gradient(90deg, ${scoreColor(Math.max(0, score - 35))}, ${scoreColor(score)})`;
    status.textContent = score >= 70 ? "EVIDENCE FORTE" : score >= 40 ? "EVIDENCE MIXTE" : "EVIDENCE FAIBLE";
    status.dataset.level = score >= 70 ? "strong" : score >= 40 ? "mixed" : "weak";
    title.textContent = score >= 70
      ? "Les preuves disponibles soutiennent fortement le verdict."
      : score >= 40
        ? "Les preuves sont partagées ou nécessitent une lecture contextuelle."
        : "Les preuves disponibles sont faibles, contradictoires ou insuffisantes.";
  }

  function renderAuditTimeline(data) {
    const wrap = $("#audit-timeline");
    if (!wrap) return;
    const sources = data.sources || [];
    const searches = Number(data.searches_performed ?? data.metadata?.search_count ?? 0);
    const claims = (data.claims || []).length || 1;
    const supports = sources.filter(s => s.stance === "confirme").length;
    const contradictions = sources.filter(s => s.stance === "contredit").length;
    const steps = [
      ["01", "Affirmation", `${claims} élément${claims > 1 ? "s" : ""} vérifié${claims > 1 ? "s" : ""}`, "claim"],
      ["02", "Recherche Web", `${searches} requête${searches > 1 ? "s" : ""} exécutée${searches > 1 ? "s" : ""}`, "search"],
      ["03", "Confrontation", `${supports} soutien · ${contradictions} contradiction${contradictions > 1 ? "s" : ""}`, "compare"],
      ["04", "Evidence Score", `${Math.round(Number(data.score ?? data.evidence_score ?? 0))}/100 · verdict déterministe`, "score"],
    ];
    wrap.innerHTML = steps.map(([num, label, detail, kind]) => `
      <article class="audit-step" data-kind="${kind}">
        <span class="audit-step__num">${num}</span>
        <div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(detail)}</small></div>
      </article>`).join("");
  }

  function renderEvidenceGraph(data) {
    const graph = $("#evidence-graph");
    if (!graph) return;
    const sources = (data.sources || []).slice(0, 12);
    const verdict = data.verdict || "non_verifiable";
    const score = Number(data.score ?? data.evidence_score ?? 0);
    if (!sources.length) {
      graph.innerHTML = `<div class="graph-empty">Aucune preuve exploitable — verdict limité par l'absence de sources.</div>`;
      return;
    }
    const nodes = sources.map((s, i) => {
      const stance = s.stance || "contexte";
      const icon = STANCE_ICON[stance] || "•";
      const quality = Number(s.authority_score ?? 50);
      return `<button type="button" class="graph-source" data-stance="${escapeAttr(stance)}" data-source-index="${i}" aria-label="Voir la source ${i + 1}">
        <span class="graph-source__line"></span><span class="graph-source__icon">${icon}</span>
        <div><a href="${escapeAttr(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title || s.domain || `Source ${i + 1}`)}</a>
        <small>${escapeHtml(s.domain || "source")} · qualité ${Math.round(quality)}/100</small></div>
      </button>`;
    }).join("");
    graph.innerHTML = `<div class="graph-core" data-verdict="${escapeAttr(verdict)}"><span class="graph-core__pulse"></span><strong>${escapeHtml(VERDICT_LABELS[state.lang]?.[verdict] || verdict)}</strong><span>${score}/100</span><small>Evidence score</small></div><div class="graph-links">${nodes}</div>`;
    $$("#evidence-graph .graph-source").forEach(btn => {
      btn.addEventListener("click", (e) => {
        if (e.target.closest("a")) return;
        const idx = Number(btn.dataset.sourceIndex);
        const item = $("#evidence-list")?.children[idx];
        if (!item) return;
        $$("#evidence-list .evidence__item").forEach(x => x.classList.remove("is-focused"));
        item.classList.add("is-focused");
        item.scrollIntoView({ behavior: "smooth", block: "center" });
        setTimeout(() => item.classList.remove("is-focused"), 1800);
      });
    });
  }

  function setBreakdown(prefix, value) {
    const v = Math.max(0, Math.min(100, Number(value) || 0));
    const fill = $(`#${prefix}`);
    fill.style.width = `${v}%`;
    fill.style.background = scoreColor(v);
    $(`#${prefix}-val`).textContent = String(v);
  }

  function hexGlow(verdict) {
    return {
      vrai: "rgba(63,184,138,0.09)",
      faux: "rgba(225,82,82,0.08)",
      partiellement_vrai: "rgba(224,169,62,0.08)",
      non_verifiable: "rgba(136,145,163,0.07)",
    }[verdict] || "rgba(201,165,103,0.07)";
  }

  function buildShareText(data, labels) {
    const lines = [
      `TRUTH CHECKER — ${labels[data.verdict] || data.verdict} (${data.score}/100)`,
      `« ${data.headline_claim || ""} »`,
      "",
      data.summary || "",
      "",
      data.explanation || "",
    ];
    if (data.correction) lines.push("", "Ce que disent les faits :", data.correction);
    if (data.sources?.length) {
      lines.push("", "Sources :");
      data.sources.forEach((s) => lines.push(`- ${s.title} — ${s.url}`));
    }
    return lines.join("\n");
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function escapeAttr(str) { return escapeHtml(str).replace(/"/g, "&quot;"); }
})();

// Landing page navigation: keep the verification workflow in the same SPA.
document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener('click', (event) => {
    const target = document.querySelector(link.getAttribute('href'));
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});
