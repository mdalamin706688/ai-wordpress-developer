(function () {
  var STEPS = [
    { id: "config", ja: "1 Config" },
    { id: "hearing", ja: "2 Hearing" },
    { id: "planner", ja: "3 Plan structure", role: "ai1" },
    { id: "draft", ja: "4 Write content", role: "ai2" },
    { id: "sections", ja: "5 Review" },
    { id: "export", ja: "6 Download" }
  ];

  var KEY_LABELS = {
    zai_api_key: "Z.AI",
    nvidia_api_key: "NVIDIA",
    deepseek_api_key: "DeepSeek",
    openai_api_key: "OpenAI",
    anthropic_api_key: "Anthropic",
    gemini_api_key: "Gemini (Free)",
    gemini_paid_api_key: "Gemini (Paid)",
    moonshot_api_key: "Moonshot (Kimi)",
    minimax_api_key: "MiniMax",
    qwen_api_key: "Qwen (DashScope)"
  };

  var PROVIDER_LABELS = {
    gemini: "Gemini",
    gemini_paid: "Gemini (Paid)",
    zai: "Z.AI",
    nvidia: "NVIDIA",
    deepseek: "DeepSeek",
    openai: "OpenAI",
    anthropic: "Anthropic",
    moonshot: "Moonshot",
    minimax: "MiniMax",
    qwen: "Qwen"
  };

  var state = {
    step: "config",
    max: 0,
    config: null,
    hearing: null,
    hearingFile: "",
    blueprint: null,
    sections: [],
    sectionsPage: "home",
    pageGroup: "nav",
    planning: false,
    planningProgress: { index: 0, total: 0, page: "", phase: "", label: "", log: [], startedAt: 0 },
    writeProgress: { index: 0, total: 0, page: "", label: "", log: [], startedAt: 0 },
    selected: [],
    /** Model ids picked from Paid menu (Flash can be free-catalog but billed-key path). */
    paidKeyModels: {},
    draftKeys: {},
    acceptedKeys: {},
    committedSelected: null,
    modelFilter: "all",
    promptPage: "home",
    promptSections: null,
    promptPackTab: "type1",
    showAdvanced: false,
    running: false,
    writePartial: false,
    exporting: false,
    sheetsUrl: "",
    sheetTabRef: null,
    sessionRestored: false,
    exportProgress: { index: 0, total: 0, page: "", label: "", active: [], log: [], startedAt: 0, soft_pct: 0, kind: "export" }
  };

  var LAB_SESSION_KEY = "bbs_v2_lab_session_v1";

  function api(path) {
    var base = String(window.DEMO_API_BASE || "").replace(/\/$/, "");
    return base + path;
  }

  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  function msg(text, ok) {
    var el = document.getElementById("msg");
    if (!el) return;
    el.textContent = text || "";
    el.className = "msg" + (ok === true ? " ok" : ok === false ? " err" : "");
  }

  function clearMsg() {
    msg("", null);
  }

  function pruneDraftKeysForSelection() {
    var needed = {};
    neededKeyFields(state.selected || []).forEach(function (k) {
      needed[k.field] = true;
    });
    Object.keys(state.draftKeys || {}).forEach(function (field) {
      if (!needed[field]) delete state.draftKeys[field];
    });
  }

  function go(step, max) {
    state.step = step;
    if (typeof max === "number") state.max = Math.max(state.max, max);
    persistLabSession();
    draw();
  }

  function persistLabSession() {
    try {
      var payload = {
        v: 1,
        savedAt: Date.now(),
        step: state.step,
        max: state.max,
        hearing: state.hearing,
        hearingFile: state.hearingFile || "",
        blueprint: state.blueprint,
        sections: state.sections || [],
        sectionsPage: state.sectionsPage || "home",
        pageGroup: state.pageGroup || "nav",
        promptPage: state.promptPage || "home",
        promptSections: state.promptSections,
        selected: (state.selected || []).slice(0, 2),
        paidKeyModels: state.paidKeyModels || {},
        sheetsUrl: state.sheetsUrl || "",
        showAdvanced: !!state.showAdvanced
      };
      sessionStorage.setItem(LAB_SESSION_KEY, JSON.stringify(payload));
    } catch (e) {
      try {
        // Quota fallback: drop long seeds to shrink payload
        var secs = (state.sections || []).map(function (r) {
          var o = {};
          Object.keys(r || {}).forEach(function (k) {
            o[k] = k === "seeds" ? String(r[k] || "").slice(0, 80) : r[k];
          });
          return o;
        });
        sessionStorage.setItem(LAB_SESSION_KEY, JSON.stringify({
          v: 1,
          savedAt: Date.now(),
          step: state.step,
          max: state.max,
          hearing: state.hearing,
          hearingFile: state.hearingFile || "",
          blueprint: state.blueprint,
          sections: secs,
          sectionsPage: state.sectionsPage,
          pageGroup: state.pageGroup,
          promptPage: state.promptPage,
          promptSections: state.promptSections,
          selected: (state.selected || []).slice(0, 2),
          paidKeyModels: state.paidKeyModels || {},
          sheetsUrl: state.sheetsUrl || "",
          showAdvanced: !!state.showAdvanced,
          slimmed: true
        }));
      } catch (e2) { /* ignore quota */ }
    }
  }

  function restoreLabSession() {
    try {
      var raw = sessionStorage.getItem(LAB_SESSION_KEY);
      if (!raw) return false;
      var data = JSON.parse(raw);
      if (!data || data.v !== 1) return false;
      if (!(data.hearing || data.blueprint || (data.sections && data.sections.length))) return false;
      state.hearing = data.hearing || null;
      state.hearingFile = data.hearingFile || "";
      state.blueprint = data.blueprint || null;
      state.sections = data.sections || [];
      state.sectionsPage = data.sectionsPage || "home";
      state.pageGroup = data.pageGroup || "nav";
      state.promptPage = data.promptPage || "home";
      state.promptSections = data.promptSections || null;
      state.sheetsUrl = data.sheetsUrl || "";
      // Prompts panel always starts closed on refresh / reopen
      state.showAdvanced = false;
      if (Array.isArray(data.selected) && data.selected.length) {
        state.selected = data.selected.slice(0, 2);
        state.committedSelected = state.selected.slice();
      }
      state.paidKeyModels = data.paidKeyModels && typeof data.paidKeyModels === "object"
        ? data.paidKeyModels
        : {};
      syncPaidKeyModelsFromSelection();
      state.step = data.step || "config";
      state.max = typeof data.max === "number" ? data.max : 0;
      // Drop legacy flat TOP (hero_brand_name / business_info_*) — nested catalog only.
      if (blueprintHasLegacyFlatTop(state.blueprint) || sectionsHaveLegacyFlatTop(state.sections)) {
        state.blueprint = null;
        state.sections = [];
        state.promptSections = null;
        if (state.step === "planner" || state.step === "write" || state.step === "review" || state.step === "download") {
          state.step = "hearing";
          state.max = Math.min(state.max || 0, 1);
        }
      }
      // Never resume mid-stream flags after refresh
      state.planning = false;
      state.running = false;
      state.sessionRestored = true;
      return true;
    } catch (e) {
      return false;
    }
  }

  function blueprintHasLegacyFlatTop(bp) {
    if (!bp || !bp.pages) return false;
    for (var i = 0; i < bp.pages.length; i++) {
      var p = bp.pages[i];
      if (!p || (p.slug !== "home" && p.type !== "top_satellite" && p.type !== "top")) continue;
      var secs = p.sections || [];
      for (var j = 0; j < secs.length; j++) {
        var id = String((secs[j] && secs[j].id) || "");
        if (id === "hero_brand_name" || id.indexOf("hero_") === 0 || id.indexOf("business_info_") === 0) {
          return true;
        }
      }
    }
    return false;
  }

  function sectionsHaveLegacyFlatTop(rows) {
    if (!rows || !rows.length) return false;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i] || {};
      var slug = String(r.page_slug || r.slug || "");
      var id = String(r.section_id || r.id || "");
      if (slug && slug !== "home") continue;
      if (id === "hero_brand_name" || id.indexOf("hero_") === 0 || id.indexOf("business_info_") === 0) {
        return true;
      }
    }
    return false;
  }

  function clearLabSession(opts) {
    opts = opts || {};
    try { sessionStorage.removeItem(LAB_SESSION_KEY); } catch (e) { /* ignore */ }
    state.hearing = null;
    state.hearingFile = "";
    state.blueprint = null;
    state.sections = [];
    state.sectionsPage = "home";
    state.pageGroup = "nav";
    state.promptPage = "home";
    state.promptSections = null;
    state.sheetsUrl = "";
    state.sheetTabRef = null;
    state.showAdvanced = false;
    state.planning = false;
    state.running = false;
    state.writePartial = false;
    state.sessionRestored = false;
    state.max = 0;
    state.step = "config";
    if (opts.keepModels === false) {
      state.selected = [];
      state.committedSelected = null;
      state.paidKeyModels = {};
    }
    if (!opts.silent) msg("New generation started — previous lab progress cleared.", true);
  }

  function confirmNewGeneration() {
    if (!window.confirm("Start a new generation?\n\nHearing / section map / content will be cleared. Config models stay.")) {
      return;
    }
    clearLabSession({ keepModels: true });
    // Refresh quota chips (status_for clears expired rate-limits) — stale chips
    // made AI-1 look "Rate limited" until a hard refresh.
    loadConfig().then(function () {
      go("config", 0);
    }).catch(function () {
      go("config", 0);
    });
  }

  function newGenerationBtnHtml() {
    if (!(state.hearing || state.blueprint || (state.sections && state.sections.length))) return "";
    return '<button type="button" class="btn" id="newGeneration" title="Clear progress and start over">New generation</button>';
  }

  function stepper() {
    document.getElementById("stepper").innerHTML = STEPS.map(function (s, i) {
      var disabled = i > state.max ? " disabled" : "";
      var classes = [];
      if (state.step === s.id) classes.push("on");
      if (s.role === "ai1") classes.push("step-ai1");
      if (s.role === "ai2") classes.push("step-ai2");
      var cls = classes.length ? ' class="' + classes.join(" ") + '"' : "";
      var label;
      if (s.role === "ai1") {
        label = '<span class="step-badge">AI-1</span><span class="step-label">Sections Planner</span>';
      } else if (s.role === "ai2") {
        label = '<span class="step-badge">AI-2</span><span class="step-label">Sections Content Creator</span>';
      } else {
        label = '<span class="step-label">' + esc(s.ja) + "</span>";
      }
      return '<button type="button" data-step="' + s.id + '"' + disabled + cls + ">" + label + "</button>";
    }).join("");
    document.querySelectorAll("[data-step]").forEach(function (b) {
      b.onclick = function () {
        if (b.disabled) return;
        if (b.getAttribute("data-step") !== "config") {
          var err = configGateError(state.selected, collectPastedKeys(), "nav");
          if (err) { msg(err, false); go("config", 0); return; }
          if (state.step === "config" && configIsDirty()) {
            msg("Press Save & continue to apply Config changes.", false);
            return;
          }
        }
        state.step = b.getAttribute("data-step");
        persistLabSession();
        draw();
      };
    });
  }
  function mergeV2ConfigMeta(next) {
    next = next || {};
    var prev = state.config || {};
    ["blueprint_version", "type3_nav_pages", "server_nav_probe", "satellite_build", "model_roles"].forEach(function (k) {
      if (next[k] == null && prev[k] != null) next[k] = prev[k];
    });
    return next;
  }

  function normalizeTypePromptsInConfig(cfg) {
    if (!cfg || typeof cfg !== "object") return cfg;
    if (!cfg.type_prompts || typeof cfg.type_prompts !== "object") cfg.type_prompts = {};
    if (!cfg.prompt_pack || typeof cfg.prompt_pack !== "object") {
      cfg.prompt_pack = { mode: "per_type", language: "en", sections: [] };
    }
    var titles = {
      type1: "Type 1 — New site",
      type2: "Type 2 — Renewal",
      type3: "Type 3 — Satellite",
      type4: "Type 4 — Satellite renewal"
    };
    var descriptions = {
      type1: "AI-1 structure + AI-2 content for Type 1 (new site).",
      type2: "AI-1 structure + AI-2 content for Type 2 (renewal).",
      type3: "AI-1 structure + AI-2 content for Type 3 (satellite).",
      type4: "AI-1 structure + AI-2 content for Type 4 (satellite renewal)."
    };
    var sections = cfg.prompt_pack.sections || [];
    var byId = {};
    sections.forEach(function (s) {
      if (s && (s.id || s.type_id)) byId[s.id || s.type_id] = s;
    });
    ["type1", "type2", "type3", "type4"].forEach(function (tid) {
      var slot = cfg.type_prompts[tid] || {};
      var fromPack = byId[tid] || {};
      var planner = resolvePlannerValue(
        tid,
        fromPack.planner_value || slot.planner_system_prompt || ""
      );
      var system = resolvePromptValue(
        tid,
        fromPack.value || slot.system_prompt || ""
      );
      var user = resolveUserTemplate(
        tid,
        fromPack.user_value || slot.user_prompt_template || ""
      );
      if (!byId[tid]) {
        sections.push({
          id: tid,
          type_id: tid,
          title: titles[tid],
          description: descriptions[tid]
        });
        byId[tid] = sections[sections.length - 1];
      } else {
        byId[tid].title = titles[tid];
        byId[tid].description = descriptions[tid];
        // Keep prompt bodies only in type_prompts (avoid duplicating ~30KB in prompt_pack)
        delete byId[tid].planner_value;
        delete byId[tid].value;
        delete byId[tid].user_value;
      }
      cfg.type_prompts[tid] = {
        planner_system_prompt: planner,
        system_prompt: system,
        user_prompt_template: user
      };
    });
    cfg.prompt_pack.sections = ["type1", "type2", "type3", "type4"].map(function (tid) {
      return {
        id: tid,
        type_id: tid,
        title: titles[tid],
        description: descriptions[tid]
      };
    });
    cfg.system_prompt = (cfg.type_prompts.type3 && cfg.type_prompts.type3.system_prompt) || cfg.system_prompt || "";
    cfg.planner_system_prompt = (cfg.type_prompts.type3 && cfg.type_prompts.type3.planner_system_prompt) || cfg.planner_system_prompt || "";
    return cfg;
  }

  async function loadConfig() {
    var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, 15000) : null;
    try {
      var res = await fetch(api("/v2/lab/config"), ctrl ? { signal: ctrl.signal } : undefined);
      if (!res.ok) throw new Error("HTTP " + res.status);
      state.config = mergeV2ConfigMeta(await res.json());
      if (state.config && state.config.prompt_sections) {
        delete state.config.prompt_sections;
      }
      // Always normalize Type 1–4 prompts in memory so UI never shows TYPE FOCUS / AI-1 stubs.
      normalizeTypePromptsInConfig(state.config);
      state.selected = (state.config.selected_models || []).slice(0, V2_MAX_MODELS);
      var san = sanitizeSelectedForKeys(state.selected);
      if (san.swaps.length) {
        state.selected = san.selected;
        state._lastKeySwapHint = san.swaps.map(function (s) {
          return modelLabel(s.from) + " → " + modelLabel(s.to);
        }).join("; ");
      }
      syncPaidKeyModelsFromSelection();
      state.committedSelected = state.selected.slice();
      // Keys already on server (.env / lab) count as accepted.
      state.acceptedKeys = state.acceptedKeys || {};
      Object.keys(state.config.keys || {}).forEach(function (field) {
        if (state.config.keys[field] && state.config.keys[field].set) {
          state.acceptedKeys[field] = true;
        }
      });
      markAcceptedKeys(state.selected, {});
    } finally {
      if (timer) clearTimeout(timer);
    }
  }
  function neededKeyFields(selectedIds) {
    var cfg = state.config || { models: [], keys: {} };
    var byId = {};
    (cfg.models || []).forEach(function (m) { byId[m.id] = m; });
    var fields = [];
    var seen = {};
    (selectedIds || []).forEach(function (id) {
      var m = byId[id];
      if (!m || !m.key_field || seen[m.key_field]) return;
      seen[m.key_field] = true;
      fields.push({
        field: m.key_field,
        label: m.key_label || KEY_LABELS[m.key_field] || m.key_field,
        ready: !!(cfg.keys[m.key_field] && cfg.keys[m.key_field].set),
        meta: cfg.keys[m.key_field] || {},
        paid: false
      });
    });
    // Mark fields used by any paid selected model (catalog paid OR Paid-menu Flash).
    (selectedIds || []).forEach(function (id) {
      var m = byId[id];
      if (!m || !m.key_field) return;
      var paidPath = m.pricing === "paid" || !!(state.paidKeyModels && state.paidKeyModels[id]);
      if (!paidPath) return;
      fields.forEach(function (f) {
        if (f.field === m.key_field) f.paid = true;
      });
    });
    return fields;
  }

  function paidKeyFields(selectedIds) {
    return neededKeyFields(selectedIds).filter(function (k) { return k.paid; });
  }

  /** Merge saved draftKeys with current DOM password inputs. */
  function collectPastedKeys() {
    var keys = {};
    Object.keys(state.draftKeys || {}).forEach(function (f) {
      var v = String(state.draftKeys[f] || "").trim();
      if (v) keys[f] = v;
    });
    document.querySelectorAll("[data-key]").forEach(function (el) {
      var v = String(el.value || "").trim();
      var f = el.getAttribute("data-key");
      if (!f) return;
      if (v) keys[f] = v;
      else delete keys[f];
    });
    return keys;
  }

  /** Keys that still block progress.
   *  Only paid-path models require credentials in the UI.
   *  Free models use the server/.env key — never ask the client to paste.
   */
  function unresolvedKeyFields(selectedIds, pastedKeys, phase) {
    pastedKeys = pastedKeys || {};
    phase = phase || "config";
    return neededKeyFields(selectedIds).filter(function (k) {
      if (!k.paid) return false;
      var pasted = String(pastedKeys[k.field] || "").trim();
      if (pasted) return false;
      if (k.ready) return false;
      if (phase === "config" && state.acceptedKeys && state.acceptedKeys[k.field]) {
        return false;
      }
      return true;
    });
  }

  /** Returns error string if gate fails; otherwise null.
   *  phase: "config" (Save) | "nav" (Hearing→Draft→Run)
   */
  function configGateError(selectedIds, pastedKeys, phase) {
    if (!(selectedIds || []).length) {
      return "Select at least one model to continue.";
    }
    var miss = unresolvedKeyFields(selectedIds, pastedKeys, phase || "config");
    if (miss.length) {
      return "Paid model selected — paste API key for: " +
        miss.map(function (k) { return k.label; }).join(", ");
    }
    return null;
  }

  function markAcceptedKeys(selectedIds, pastedKeys) {
    state.acceptedKeys = state.acceptedKeys || {};
    neededKeyFields(selectedIds).forEach(function (k) {
      var pasted = pastedKeys && String(pastedKeys[k.field] || "").trim();
      if (pasted || k.ready) state.acceptedKeys[k.field] = true;
    });
  }

  function configIsDirty() {
    var cur = (state.selected || []).slice();
    var saved = state.committedSelected;
    if (!saved) return cur.length > 0;
    if (cur.length !== saved.length) return true;
    for (var i = 0; i < cur.length; i++) {
      if (cur[i] !== saved[i]) return true;
    }
    return Object.keys(collectPastedKeys()).length > 0;
  }

  function refreshConfigGateUi() {
    var err = configGateError(state.selected, collectPastedKeys(), "config");
    var btn = document.getElementById("saveConfig");
    var bar = document.getElementById("configGateBar");
    var hint = document.getElementById("configGateHint");
    var title = document.getElementById("configGateTitle");
    if (btn) {
      btn.disabled = !!err;
      btn.title = err || "Save models and continue";
    }
    if (bar) {
      if (err) {
        bar.className = "gate-bar bad";
        bar.removeAttribute("aria-hidden");
      } else {
        bar.className = "gate-bar ok hid";
        bar.setAttribute("aria-hidden", "true");
      }
    }
    if (title) title.textContent = err ? "Cannot continue yet" : "";
    if (hint) hint.textContent = err || "";
    document.querySelectorAll("[data-key]").forEach(function (inp) {
      var field = inp.getAttribute("data-key");
      var meta = neededKeyFields(state.selected).filter(function (k) {
        return k.field === field;
      })[0];
      var has = !!String(inp.value || state.draftKeys[field] || "").trim();
      var accepted = !!(state.acceptedKeys && state.acceptedKeys[field]);
      var must = meta && meta.paid && !accepted && !has;
      if (must) inp.classList.add("invalid");
      else inp.classList.remove("invalid");
    });
  }

  var V2_MAX_MODELS = 2;

  function roleLabel(selected, idx) {
    if (idx === 0) return "AI-1";
    if (idx === 1) return "AI-2";
    return "Unused";
  }

  function roleSubtitle(idx) {
    if (idx === 0) return "Sections Planner";
    if (idx === 1) return "Sections Content Creator";
    return "";
  }

  function roleBadgeClass(role) {
    var r = String(role || "").toLowerCase();
    if (r.indexOf("ai-1") === 0 || r.indexOf("section map") === 0 || r.indexOf("sections planner") >= 0) {
      return "role-ai1";
    }
    if (r.indexOf("ai-2") === 0 || r.indexOf("section content") === 0 || r.indexOf("writer") === 0 || r.indexOf("content") >= 0) {
      return "role-ai2";
    }
    if (r.indexOf("improve") === 0) return "role-improve";
    if (r.indexOf("verifier") === 0) return "role-verifier";
    return "role-unused";
  }

  function roleBadgeHtml(role) {
    return '<span class="badge ' + roleBadgeClass(role) + '">' + esc(role) + "</span>";
  }

  function selectedModelsBoardHtml(selected, byId) {
    selected = selected || [];
    var slots = [0, 1].map(function (idx) {
      var id = selected[idx];
      var role = roleLabel(selected, idx);
      var sub = roleSubtitle(idx);
      if (!id) {
        return '<div class="model-slot empty" data-slot="' + idx + '">' +
          '<div class="ms-role">' +
          '<span class="ms-num">' + (idx + 1) + "</span>" +
          '<div><strong>' + esc(role) + "</strong><small>" + esc(sub) + "</small></div>" +
          "</div>" +
          '<div class="ms-empty">Awaiting model</div>' +
          "</div>";
      }
      var m = byId[id] || { id: id };
      var price = (m.pricing === "paid" || !!(state.paidKeyModels && state.paidKeyModels[id]))
        ? "paid"
        : "free";
      var provider = PROVIDER_LABELS[m.provider] || m.provider || "";
      var q = (price === "free" && m.quota) ? m.quota : null;
      var qHtml = q && q.label
        ? '<span class="qchip ' + esc(q.level || "ok") + '">' + esc(q.label) + "</span>"
        : "";
      return '<div class="model-slot filled" data-slot="' + idx + '">' +
        '<div class="ms-role">' +
        '<span class="ms-num on">' + (idx + 1) + "</span>" +
        '<div><strong>' + esc(role) + "</strong><small>" + esc(sub) + "</small></div>" +
        "</div>" +
        '<div class="ms-model">' +
        '<div class="ms-name">' + esc(m.name || id) + "</div>" +
        '<div class="ms-meta">' +
        (provider ? '<span>' + esc(provider) + "</span>" : "") +
        '<span class="badge ' + price + '">' + price + "</span>" +
        qHtml +
        "</div></div>" +
        '<button type="button" class="ms-remove" data-remove="' + esc(id) +
        '" title="Remove" aria-label="Remove model">×</button>' +
        "</div>";
    }).join("");
    return '<div class="model-board">' +
      '<div class="model-board-head">' +
      "<span>Selected pipeline</span>" +
      '<span class="model-board-count">' + selected.length + " / 2</span>" +
      "</div>" +
      '<div class="model-slots">' + slots + "</div>" +
      "</div>";
  }

  function plannedPipelineBoardHtml(selected) {
    var planned = pipelinePreview(selected || []);
    if (!planned.writer) return "";
    return '<div class="pipeline-board">' +
      '<p class="pb-title">Running pipeline</p>' +
      '<div class="pb-row">' + roleBadgeHtml("AI-2") +
      '<span class="pb-model">' + esc(modelLabel(planned.writer)) + "</span>" +
      '<span class="pb-status">running</span></div></div>';
  }


  function modelById(id) {
    var cfg = state.config || {};
    var found = null;
    (cfg.models || []).forEach(function (m) {
      if (m.id === id) found = m;
    });
    return found;
  }

  /** Display name only (id stays in option value / API). */
  function modelLabel(id) {
    var m = modelById(id) || {};
    return m.name || id || "";
  }

  function pipelinePreview(selected) {
    var s = (selected || []).slice(0, V2_MAX_MODELS);
    if (!s.length) {
      return { sectionsOnly: false, writer: "", planner: "", hint: "Select model #1 for AI-1 section creator." };
    }
    if (s.length === 1) {
      return {
        sectionsOnly: true, writer: "", planner: s[0],
        hint: modelLabel(s[0]) + " (AI-1) builds the section map — add a 2nd model for AI-2 section content."
      };
    }
    return {
      sectionsOnly: false, writer: s[1], planner: s[0],
      hint: modelLabel(s[0]) + " (AI-1 section map) → " + modelLabel(s[1]) + " (AI-2 section content)."
    };
  }

  function v2SectionsOnly(selected) {
    return !!(pipelinePreview(selected || []).sectionsOnly);
  }

  function providerLabel(m) {
    return PROVIDER_LABELS[m.provider] || m.key_label || m.provider || "";
  }

  /** Free = $0 list price, not "no API key". Gemini Flash still needs GEMINI_API_KEY. */
  function modelKeyReady(m) {
    if (!m) return false;
    if (m.key_configured) return true;
    var f = m.key_field;
    if (!f) return true;
    var cfg = state.config || { keys: {} };
    if (cfg.keys && cfg.keys[f] && cfg.keys[f].set) return true;
    if (String((state.draftKeys || {})[f] || "").trim()) return true;
    return false;
  }

  var FREE_KEY_FALLBACKS = [
    "glm-4.5-flash", "glm-4.7-flash", "nvidia-nemotron-super-49b",
    "nvidia-minimax-m3", "nvidia-deepseek-v4-flash", "nvidia-kimi-k3",
    "nvidia-nemotron-3-super-120b"
  ];

  function pickReadyFreeFallback(excludeIds) {
    var cfg = state.config || { models: [] };
    var byId = {};
    (cfg.models || []).forEach(function (m) { byId[m.id] = m; });
    excludeIds = excludeIds || [];
    var i, id, m;
    for (i = 0; i < FREE_KEY_FALLBACKS.length; i++) {
      id = FREE_KEY_FALLBACKS[i];
      if (excludeIds.indexOf(id) >= 0) continue;
      m = byId[id];
      if (m && modelKeyReady(m)) return id;
    }
    for (i = 0; i < (cfg.models || []).length; i++) {
      m = cfg.models[i];
      if (!m || excludeIds.indexOf(m.id) >= 0) continue;
      if (m.pricing === "paid") continue;
      if (modelKeyReady(m)) return m.id;
    }
    return null;
  }

  /** Replace free picks that lack a key with GLM/NIM that already have .env keys. */
  function sanitizeSelectedForKeys(selectedIds) {
    var cfg = state.config || { models: [] };
    var byId = {};
    (cfg.models || []).forEach(function (m) { byId[m.id] = m; });
    var next = [];
    var swaps = [];
    (selectedIds || []).forEach(function (id) {
      var m = byId[id];
      if (!m) return;
      if (modelKeyReady(m)) {
        if (next.indexOf(id) < 0) next.push(id);
        return;
      }
      // Paid / Paid-menu Flash without key: keep so the paste gate asks for the key.
      if (m.pricing === "paid" || !!(state.paidKeyModels && state.paidKeyModels[id])) {
        if (next.indexOf(id) < 0) next.push(id);
        return;
      }
      var fb = pickReadyFreeFallback(next);
      if (fb) {
        if (next.indexOf(fb) < 0) next.push(fb);
        swaps.push({ from: id, to: fb });
      }
    });
    return { selected: next, swaps: swaps };
  }

  /** Free models dual-listed under Paid for customer key paste:
   *  Z.AI GLM-4.5/4.7 Flash only. Free Gemini stays Free-only;
   *  Paid Gemini (3.6+) uses gemini_paid + GEMINI_PAID_API_KEY.
   */
  function isFreeModelForPaidMenu(m) {
    if (!m || m.pricing === "paid") return false;
    if (m.provider === "nvidia" || m.provider === "gemini") return false;
    var id = String(m.id || "").toLowerCase();
    if (m.provider === "zai") {
      return id === "glm-4.5-flash" || id === "glm-4.7-flash";
    }
    return false;
  }

  function filteredModels(cfg) {
    var q = String(state.modelQuery || "").trim().toLowerCase();
    var filter = state.modelFilter || "all";
    return (cfg.models || []).filter(function (m) {
      var price = m.pricing === "free" ? "free" : "paid";
      if (filter === "free" && price !== "free") return false;
      // Paid: catalog-paid (Gemini Paid first company) + optional GLM Flash dual-list.
      // Free Gemini / free NIM stay Free-only.
      if (filter === "paid") {
        if (m.provider === "nvidia" && price !== "paid") return false;
        if (price !== "paid" && !isFreeModelForPaidMenu(m)) return false;
      }
      if (!q) return true;
      var hay = [m.name, m.id, m.provider, providerLabel(m), price].join(" ").toLowerCase();
      return hay.indexOf(q) >= 0;
    }).slice().sort(function (a, b) {
      var ap = a.pricing === "free" ? 0 : 1;
      var bp = b.pricing === "free" ? 0 : 1;
      if (ap !== bp) return ap - bp;
      // Newest official GLMs / Gemini Paid first within groups.
      var ar = modelRank(a.id);
      var br = modelRank(b.id);
      if (ar !== br) return ar - br;
      return String(a.name || a.id).localeCompare(String(b.name || b.id));
    });
  }

  function modelRank(id) {
    var order = [
      "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
      "gemini-3.5-flash-paid", "gemini-3.5-flash-lite-paid", "gemini-3.1-pro-preview",
      "glm-5.3", "glm-5.2", "glm-5.1", "glm-5-turbo", "glm-5",
      "glm-4.7-flash", "glm-4.5-flash", "nemotron-3-super-120b", "nemotron-super-49b",
      "nvidia-nemotron-super-49b", "nvidia-minimax-m3",
      "kimi-k3", "minimax-m3"
    ];
    var i = order.indexOf(id);
    return i >= 0 ? i : 200;
  }

  var COMPANY_ORDER = [
    "gemini_paid", "gemini", "zai", "nvidia", "moonshot", "minimax", "qwen",
    "deepseek", "openai", "anthropic"
  ];

  function companiesFor(list) {
    var seen = {};
    (list || []).forEach(function (m) {
      if (m.provider) seen[m.provider] = true;
    });
    var keys = Object.keys(seen);
    keys.sort(function (a, b) {
      var ai = COMPANY_ORDER.indexOf(a);
      var bi = COMPANY_ORDER.indexOf(b);
      if (ai < 0) ai = 99;
      if (bi < 0) bi = 99;
      if (ai !== bi) return ai - bi;
      return (PROVIDER_LABELS[a] || a).localeCompare(PROVIDER_LABELS[b] || b);
    });
    return keys;
  }

  /** Keep catalog-paid selections marked on the paid path (after load/save). */
  function syncPaidKeyModelsFromSelection() {
    state.paidKeyModels = state.paidKeyModels || {};
    var byId = {};
    ((state.config || {}).models || []).forEach(function (m) {
      if (m && m.id) byId[m.id] = m;
    });
    (state.selected || []).forEach(function (id) {
      var m = byId[id];
      if (m && m.pricing === "paid") state.paidKeyModels[id] = true;
    });
  }

  /** Flash appears in both menus — selection is per path (free server key vs paid paste). */
  function isSelectedInMenu(kind, id, model) {
    if ((state.selected || []).indexOf(id) < 0) return false;
    // Catalog-paid models always belong to the paid menu only.
    if (model && model.pricing === "paid") return kind === "paid";
    var paidPath = !!(state.paidKeyModels && state.paidKeyModels[id]);
    if (kind === "paid") return paidPath;
    return !paidPath;
  }

  /** Premium cascade: providers in panel → models submenu to the right. */
  function hoverMenuHtml(kind, list, selected) {
    var cos = companiesFor(list);
    var badge = kind === "free" ? "free" : "paid";
    var title = kind === "free" ? "Free models" : "Paid models";
    var placeholder = kind === "free" ? "Select a free model" : "Select a paid model";
    var restore = state._megaRestore || {};
    var ddOpen = restore.kind === kind;
    var listIds = {};
    (list || []).forEach(function (m) { listIds[m.id] = m; });
    // Only count IDs that exist in THIS menu's list (paid IDs must not appear on Free).
    var pickedHere = (selected || []).filter(function (id) {
      if (!listIds[id]) return false;
      return isSelectedInMenu(kind, id, listIds[id]);
    });
    var triggerVal = pickedHere.map(function (id) {
      return (listIds[id] && listIds[id].name) || id;
    }).join(", ");
    var triggerSub = pickedHere.length
      ? (pickedHere.length === 1 ? "1 selected" : pickedHere.length + " selected")
      : "Provider → model";
    var checkSvg = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 6.2l2.4 2.4 4.6-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    var chevSvg = '<svg class="mega-chev" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    var arrowSvg = '<svg class="mega-co-arrow" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    var companies = cos.map(function (p) {
      var items = (list || []).filter(function (m) { return m.provider === p; });
      var selectedInCo = items.filter(function (m) {
        return isSelectedInMenu(kind, m.id, m);
      }).length;
      var opts = items.map(function (m) {
        var on = isSelectedInMenu(kind, m.id, m);
        var ready = modelKeyReady(m);
        // Free list: never ask for keys. Show soft hint only if server key missing (fallback path).
        var needs = kind === "free" && !ready;
        var meta = needs ? "Server key missing · GLM/NIM fallback" : "";
        if (kind === "paid" && isFreeModelForPaidMenu(m)) {
          meta = "Paste your key";
        }
        var q = m.quota || null;
        var qChip = "";
        if (kind === "free" && q && q.label) {
          qChip = '<span class="qchip ' + esc(q.level || "ok") + '" title="' +
            esc(
              (q.pct != null ? q.pct + "% of free daily limit · " : "") +
              (q.used != null ? "used " + q.used : "") +
              (q.limit != null ? " / " + q.limit : "") +
              (q.available_in ? " · back " + q.available_in : "")
            ) + '">' + esc(q.label) + "</span>";
        }
        return '<button type="button" role="menuitemcheckbox" class="mega-opt' +
          (on ? " on" : "") + (needs ? " needs-key" : "") +
          (q && q.exceeded ? " quota-exceeded" : "") +
          '" data-pick-model="' + esc(m.id) + '"' +
          ' data-pick-tier="' + esc(kind) + '"' +
          ' aria-checked="' + (on ? "true" : "false") + '"' +
          (needs ? ' title="No server API key — will use GLM/NIM from .env instead"' : "") +
          (q && q.exceeded ? ' title="Free quota exceeded — ' + esc(q.label) + '"' : "") + ">" +
          '<span class="mega-opt-main">' +
          '<span class="mega-opt-name">' + esc(m.name || m.id) + "</span>" +
          (meta ? '<span class="mega-opt-meta">' + esc(meta) + "</span>" : "") +
          (qChip || "") +
          "</span>" +
          '<span class="mega-opt-check">' + checkSvg + "</span>" +
          "</button>";
      }).join("");
      var coOpen = ddOpen && restore.company === p;
      return '<div class="mega-co' + (coOpen ? " open" : "") + '" data-company="' + esc(p) + '">' +
        '<button type="button" class="mega-co-btn" data-company-toggle="' + esc(p) + '"' +
        ' aria-haspopup="menu" aria-expanded="' + (coOpen ? "true" : "false") + '">' +
        '<span class="mega-co-main">' +
        '<span class="mega-co-name">' + esc(PROVIDER_LABELS[p] || p) + "</span>" +
        '<span class="mega-co-meta">' + items.length + " model" + (items.length === 1 ? "" : "s") +
        (selectedInCo ? " · " + selectedInCo + " selected" : "") + "</span>" +
        "</span>" + arrowSvg + "</button>" +
        '<div class="mega-sub" role="menu">' +
        '<div class="mega-sub-head">' + esc(PROVIDER_LABELS[p] || p) + "</div>" +
        (opts || '<div class="mega-empty">No models</div>') +
        "</div></div>";
    }).join("");

    return '<div class="pick-box">' +
      '<h3><span class="badge ' + badge + '">' + badge + "</span> " + title + "</h3>" +
      '<div class="mega-dd' + (ddOpen ? " open" : "") + '" data-kind="' + kind + '" id="' + kind + 'MegaDd">' +
      '<button type="button" class="mega-trigger" data-mega-trigger="' + kind + '"' +
      ' aria-haspopup="menu" aria-expanded="' + (ddOpen ? "true" : "false") + '">' +
      '<span class="mega-trigger-text">' +
      (triggerVal
        ? '<span class="val">' + esc(triggerVal) + '</span><span class="sub">' + esc(triggerSub) + "</span>"
        : '<span class="ph">' + esc(placeholder) + '</span><span class="sub">' + esc(triggerSub) + "</span>") +
      "</span>" + chevSvg + "</button>" +
      '<div class="mega-panel" role="menu">' +
      '<div class="mega-scroll">' +
      (companies || '<div class="mega-empty">No models available</div>') +
      "</div></div></div></div>";
  }

  function promptSectionsCatalog() {
    if (state.promptSections && state.promptSections.source === "blueprint") {
      return state.promptSections;
    }
    return {
      dynamic: true,
      source: "pending",
      tabs: [],
      hint: "Run AI-1 Sections Planner after loading a hearing file. Section blocks are built from that hearing."
    };
  }

  function hasBlueprintPromptSections() {
    var c = promptSectionsCatalog();
    return c.source === "blueprint" && (c.tabs || []).length > 0;
  }

  function tabGroupOf(t) {
    if (!t) return "nav";
    if (t.group === "seo" || t.group === "tag" || t.group === "nav") return t.group;
    if (t.group === "page") return "nav";
    var lab = String(t.label || "");
    if (/\(seo\)/i.test(lab)) return "seo";
    if (/\(tag/i.test(lab)) return "tag";
    return "nav";
  }

  function groupCounts(tabs) {
    var c = { nav: 0, seo: 0, tag: 0 };
    (tabs || []).forEach(function (t) {
      var g = tabGroupOf(t);
      if (c[g] != null) c[g] += 1;
    });
    return c;
  }

  function ensureActiveInGroup(tabs, activeId, group) {
    var inGroup = (tabs || []).filter(function (t) { return tabGroupOf(t) === group; });
    if (!inGroup.length) return activeId;
    for (var i = 0; i < inGroup.length; i++) {
      if (inGroup[i].id === activeId) return activeId;
    }
    return inGroup[0].id;
  }

  function pageBrowserHtml(opts) {
    opts = opts || {};
    var tabs = opts.tabs || [];
    var activeId = opts.activeId || "";
    var group = opts.group || state.pageGroup || "nav";
    var counts = groupCounts(tabs);
    if (!(counts[group] > 0)) {
      group = counts.nav > 0 ? "nav" : (counts.seo > 0 ? "seo" : "tag");
    }
    activeId = ensureActiveInGroup(tabs, activeId, group);
    state.pageGroup = group;
    var groupTabs = tabs.filter(function (t) { return tabGroupOf(t) === group; });
    var active = null;
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].id === activeId) { active = tabs[i]; break; }
    }
    if (!active && groupTabs.length) active = groupTabs[0];
    var groups = [
      { id: "nav", label: "Nav", n: counts.nav },
      { id: "seo", label: "SEO", n: counts.seo },
      { id: "tag", label: "Tag", n: counts.tag }
    ].filter(function (g) { return g.n > 0; });
    var listHtml = groupTabs.length
      ? groupTabs.map(function (t) {
          var n = (t.items && t.items.length)
            ? t.items.length
            : (opts.countFn ? opts.countFn(t.id) : 0);
          var short = String(t.label || t.id).replace(/\s*\((seo|tag\d*)\)\s*$/i, "");
          return '<button type="button" data-page-id="' + esc(t.id) + '"' +
            (active && active.id === t.id ? ' class="on"' : "") +
            ' title="' + esc(t.label || t.id) + '">' +
            '<span class="pl-label">' + esc(short) + "</span>" +
            (n ? '<span class="pl-meta">' + n + "</span>" : "") +
            "</button>";
        }).join("")
      : '<p class="pl-empty">No pages in this group</p>';
    return '<div class="page-browser" id="' + esc(opts.rootId || "pageBrowser") + '">' +
      '<aside class="page-rail">' +
      '<div class="page-groups">' +
      groups.map(function (g) {
        return '<button type="button" data-page-group="' + g.id + '"' +
          (group === g.id ? ' class="on"' : "") + ">" + esc(g.label) +
          '<span class="pg-n">' + g.n + "</span></button>";
      }).join("") +
      "</div>" +
      '<div class="page-list">' + listHtml + "</div>" +
      "</aside>" +
      '<div class="page-panel">' +
      '<div class="page-panel-head">' +
      "<h4>" + esc((active && (active.label || active.id)) || "—") + "</h4>" +
      (active && active.web_path ? '<span class="path">' + esc(active.web_path) + "</span>" : "") +
      "</div>" +
      (opts.panelHtml || "") +
      "</div></div>";
  }

  function bindPageBrowser(rootId, onPick) {
    var root = document.getElementById(rootId);
    if (!root) return;
    root.querySelectorAll("[data-page-group]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.pageGroup = btn.getAttribute("data-page-group") || "nav";
        onPick({ group: state.pageGroup });
      });
    });
    root.querySelectorAll("[data-page-id]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        onPick({ id: btn.getAttribute("data-page-id") || "" });
      });
    });
  }

  /** Client-facing structure review — no rules jargon. */
  function promptSectionPanelHtml() {
    if (!hasBlueprintPromptSections()) {
      return '<p class="prompt-note">' + esc(promptSectionsCatalog().hint) + "</p>";
    }
    var catalog = promptSectionsCatalog();
    var tabs = catalog.tabs || [];
    state.promptPage = ensureActiveInGroup(tabs, state.promptPage, state.pageGroup || "nav");
    return pageBrowserHtml({
      rootId: "promptPageBrowser",
      tabs: tabs,
      activeId: state.promptPage,
      group: state.pageGroup || "nav",
      countFn: function (id) {
        for (var i = 0; i < tabs.length; i++) {
          if (tabs[i].id === id) return (tabs[i].items || []).length;
        }
        return 0;
      },
      panelHtml: promptSectionItemsHtml(state.promptPage)
    });
  }

  function promptSectionItemsHtml(page) {
    var catalog = promptSectionsCatalog();
    var tabs = catalog.tabs || [];
    if (!tabs.length) {
      return '<p class="prompt-note">' + esc(catalog.hint ||
        "Section blocks are built after AI-1 Sections Planner runs on the hearing file.") +
        "</p>";
    }
    var tab = null;
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].id === page) { tab = tabs[i]; break; }
    }
    if (!tab) {
      tab = tabs[0] || null;
    }
    if (!tab) {
      return '<p class="prompt-note">No sections yet — run AI-1.</p>';
    }
    var items = tab.items || [];
    var rows = items.map(function (it, idx) {
      return "<tr>" +
        "<td>" + esc(String(idx + 1)) + "</td>" +
        "<td><strong>" + esc(it.label || it.id) + "</strong>" +
        '<div class="pi-web">' + esc(it.id || "") + "</div></td>" +
        "<td><span class=\"tag\">" + esc(it.mode || "generate") + "</span></td>" +
        "<td>" + esc(it.web || it.label || "") + "</td>" +
        "</tr>";
    }).join("");
    return '<p class="prompt-note" style="margin-top:0">' +
      esc(tab.description || "Section structure for this page") +
      " · " + items.length + " blocks</p>" +
      '<div style="overflow:auto">' +
      '<table class="prompt-table">' +
      "<thead><tr><th>#</th><th>Block</th><th>mode</th><th>On-site role</th></tr></thead>" +
      "<tbody>" + rows + "</tbody></table></div>";
  }

  /** Fallback English prompts — must stay aligned with src/ai_agent/v2/prompt_packs.py.
   * Prefer API type_prompts values; these are only used when the API pack is missing/stale. */
  function defaultPlannerForType(tid) {
    if (tid === "type1") {
      return (
        "TYPE 1 — hearing-driven structure.\n" +
        "Plan section blocks only from THIS hearing sheet. Do not invent facts.\n" +
        "Output JSON sections with id, label, mode, rule only. No page copy.\n\n" +
        "You are AI-1 (Sections Planner) for Type 1 — NEW site (新規).\n" +
        "Your job: design the SECTION MAP for one WordPress page so AI-2 can write Japanese copy later.\n" +
        "You do NOT write website content, headings, paragraphs, or customer-facing text.\n\n" +
        "HEARING SHEET IS THE SOURCE OF TRUTH:\n" +
        "- Use only pages, seeds, directives, flags, and facts from THIS Type 1 hearing.\n" +
        "- Do not invent services, prices, staff, reviews, jobs, pages, or claims.\n" +
        "- Do not use renewal / existing-URL ideas — Type 1 is a new site.\n\n" +
        "PAGE LIST CONTEXT (already decided before you run — do not invent pages):\n" +
        "1) MUST pages always exist: TOP, Access, Blog, Form/Contact, Sitemap, Privacy Policy.\n" +
        "2) CONDITIONAL: Reviews (口コミ slots), Recruit (制作種別=リクルート), AI blog (AIサポート=あり).\n" +
        "3) Other content pages from ページの追加 / SEO / tag.\n" +
        "- Plan SECTIONS for the given page only.\n\n" +
        "OUTPUT (JSON only): {\"sections\":[{\"id\":\"snake_case\",\"label\":\"short English label\",\"mode\":\"generate|facts|expand|shell|blank\",\"rule\":\"short English instruction for AI-2 from hearing facts\"}]}\n" +
        "- Keys allowed: id, label, mode, rule ONLY. No page copy."
      );
    }
    if (tid === "type3") {
      return (
        "TYPE 3 — SATELLITE (hearing-driven CONTENT SECTIONS + NESTED ITEMS).\n" +
        "Plan section blocks only from THIS Type 3 hearing sheet. Do not invent facts.\n" +
        "Output JSON sections with id, label, mode, rule only. No page copy.\n\n" +
        "You are AI-1 (Sections Planner) for Type 3 — Satellite (サテライト).\n" +
        "PAGE SCOPE: plan the template_hint_ids / nested fields on THIS PAGE block.\n" +
        "Use site_purpose / site_category / production_kind from THIS hearing for tone rules.\n" +
        "Follow ページの追加 for THIS hearing via the PAGE block.\n" +
        "Never use layout word \"hero\" as a section id. Template placement is AI-3.\n" +
        "You do NOT write website content.\n\n" +
        "HEARING SHEET IS THE SOURCE OF TRUTH. Do not invent services, prices, staff, reviews, jobs, pages, or claims.\n" +
        "If live_site_structure is provided: STRUCTURE and topic headings only. Never copy live body text.\n\n" +
        "OUTPUT (JSON only): {\"sections\":[{\"id\":\"snake_case\",\"label\":\"short English label\",\"mode\":\"generate|facts|expand|shell|blank\",\"rule\":\"short English instruction for AI-2 from hearing facts\"}]}\n" +
        "- Keys allowed: id, label, mode, rule ONLY. id 2–32 chars. No page copy."
      );
    }
    var n = String(tid || "type3").replace("type", "");
    return (
      "TYPE " + n + " — hearing-driven structure.\n" +
      "Plan section blocks only from THIS hearing sheet. Do not invent facts.\n" +
      "Output JSON sections with id, label, mode, rule only. No page copy.\n\n" +
      "You are BBS WordPress section planner (AI-1).\n" +
      "Plan section BLOCK STRUCTURE for AI-2. Do NOT write website content.\n" +
      "HEARING SHEET IS THE SOURCE OF TRUTH. Do not invent facts.\n" +
      "PAGE COMPOSITION RULES: must pages always; reviews/recruit/AI-blog only when hearing flags say so.\n" +
      "Output JSON: {\"sections\":[{\"id\":\"...\",\"label\":\"...\",\"mode\":\"...\",\"rule\":\"English instruction for AI-2\"}]} — id/label/mode/rule only."
    );
  }

  function defaultWriterForType(tid) {
    var heads = {
      type1: (
        "TYPE 1 — NEW SITE (hearing-driven content):\n" +
        "- This hearing is a NEW site (not a renewal of an existing URL).\n" +
        "- Build Japanese section copy only from this Type 1 hearing sheet.\n" +
        "- Follow page-add / blank / writing_guidance directives from the hearing.\n" +
        "- Do not use existing-site URL or renewal copy policies — they do not apply.\n" +
        "- Follow CONTENT SCOPE: reviews/recruit/AI-blog copy only when those hearing flags/items exist.\n"
      ),
      type2: (
        "TYPE 2 — RENEWAL (hearing-driven content):\n" +
        "- This hearing renews an existing client site.\n" +
        "- Hearing sheet facts are still the only allowed content source.\n" +
        "- Existing URL / existing page fields are structure reference only.\n" +
        "- Follow CONTENT SCOPE: reviews/recruit/AI-blog copy only when those hearing flags/items exist.\n"
      ),
      type3: (
        "TYPE 3 — SATELLITE (hearing-driven NESTED CONTENT BLOCKS):\n" +
        "- Build THIS satellite from THIS hearing (サイト制作目的 + 制作種別 decide category).\n" +
        "- PAGE SCOPE: fill only the section ids in {page_rules} for THIS page.\n" +
        "- Follow SITE BRIEF + PLAYBOOK in page_rules for THIS hearing's category and tone.\n" +
        "- For each id, fill nested fields exactly as page_rules lists them (description not body when required).\n" +
        "- Never name a section \"hero\" (layout word).\n" +
        "- Never invent rankings/awards (地域1番 / No.1) unless hearing states them.\n" +
        "- CATCHCOPY: ONE emotional phrase 15–28 Japanese chars; longer story only in short_description.\n" +
        "- AREA: use composed area from SITE BRIEF (半島・県 when both appear) — not prefecture-only.\n" +
        "- ALL SECTIONS: meaningful title+body from 売り / page-add / focus seeds — no thin filler.\n" +
        "- CTA label: clear inquiry action for lead_gen (無料相談・お見積り).\n" +
        "- LIVE SITE: structure/topic hints only; NEVER paste live body. Hearing facts win.\n" +
        "- UNIQUE LANDING COPY: each SEO page opens on its keyword; never reuse TOP brand-origin story (太陽さん / 名前になりました).\n" +
        "- Reviews/greeting/FAQ bodies empty when hearing lacks real 口コミ本文 / staff facts / FAQ Q&A.\n" +
        "- Follow CONTENT SCOPE: conditional pages only when hearing flags/items exist.\n"
      ),
      type4: (
        "TYPE 4 — SATELLITE RENEWAL (hearing-driven content):\n" +
        "- This hearing is satellite structure + renewal policy.\n" +
        "- Hearing sheet facts are the only allowed content source.\n" +
        "- Existing URL = structure only. Follow CONTENT SCOPE for reviews/recruit/AI-blog.\n" +
        "- UNIQUE LANDING COPY: each SEO page should follow its primary angle; never reuse brand-origin TOP story (太陽さん / 名前になりました).\n"
      )
    };
    var shared = (
      "\nYou are a website copywriter for BBS WordPress sites (AI-2).\n" +
      "Write customer-facing section text in Japanese. All instructions below are in English.\n\n" +
      "HEARING SHEET IS THE SOURCE OF TRUTH:\n" +
      "- Every fact must come from THIS hearing sheet (and page rules derived from it).\n" +
      "- If the hearing omits a topic, leave that section empty (\"\"). Never invent.\n\n" +
      "CONTENT SCOPE (pages already chosen by blueprint — do not invent pages):\n" +
      "- Write ONLY the section ids listed in the page rules for THIS page.\n" +
      "- Reviews/recruit/AI-blog copy only when hearing flags/items exist.\n" +
      "- leave_blank pages: every section value must be \"\".\n\n" +
      "Constraints:\n" +
      "- Use shop name, address, station, walk minutes, phone, hours, holidays, prices, menu names, payment, reservation, and parking exactly as given in meaning.\n" +
      "- Do not invent guarantees, medical effects, qualifications, awards, or unstated policies.\n" +
      "- Use polite Japanese (desu/masu). No Markdown. Draft only.\n" +
      "- Values may be Japanese strings OR nested objects when the page rule shows nested fields.\n" +
      "- Always return {\"sections\": { … }}."
    );
    return (heads[tid] || heads.type3) + shared;
  }

  var DEFAULT_USER_PROMPT_TEMPLATE = (
    "Following the permitted facts and page rules, write Japanese copy for each section id.\n" +
    "Output JSON key: sections (object) — each key is a section id, value is a Japanese body string.\n" +
    "No Markdown. If the hearing has no fact for a section, use an empty string. Do not invent topics.\n" +
    "{page_rules}\n\n" +
    "{hearing}"
  );

  function promptLooksJapanese(text) {
    var t = String(text || "");
    return t.indexOf("あなたは") >= 0 ||
      t.indexOf("次の許可された事実") >= 0 ||
      t.indexOf("出力JSONキー") >= 0 ||
      t.indexOf("Markdown禁止") >= 0 ||
      t.indexOf("です・ます") >= 0 ||
      t.indexOf("一字一句") >= 0;
  }

  function packValueFor(tid, field) {
    var cfg = state.config || {};
    var sections = (cfg.prompt_pack && cfg.prompt_pack.sections) || [];
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].id === tid || sections[i].type_id === tid) {
        return String(sections[i][field] || "").trim();
      }
    }
    var slot = (cfg.type_prompts && cfg.type_prompts[tid]) || {};
    if (field === "planner_value") return String(slot.planner_system_prompt || "").trim();
    if (field === "value") return String(slot.system_prompt || "").trim();
    if (field === "user_value") return String(slot.user_prompt_template || "").trim();
    return "";
  }

  function isGoodWriterPrompt(v) {
    var t = String(v || "");
    if (!(t.indexOf("hearing-driven") >= 0 &&
      t.indexOf("CONTENT SCOPE") >= 0 &&
      t.indexOf("TYPE FOCUS") < 0 &&
      !promptLooksJapanese(t))) {
      return false;
    }
    // Type 3 must be nested from page_rules, not flat hero_* stubs.
    if (t.indexOf("TYPE 3 — SATELLITE") >= 0) {
      return t.indexOf("PAGE SCOPE") >= 0 &&
        t.indexOf("HEARING-DYNAMIC") < 0 &&
        (t.indexOf("NESTED") >= 0 || t.indexOf("nested") >= 0) &&
        (t.indexOf("page_rules") >= 0 || t.indexOf("THIS page") >= 0) &&
        (t.indexOf("CATCHCOPY") >= 0 || t.indexOf("catchphrase") >= 0) &&
        (t.indexOf("SITE BRIEF") >= 0 || t.indexOf("サイト制作目的") >= 0 || t.indexOf("lead_gen") >= 0) &&
        t.indexOf("PLAYBOOK") >= 0 &&
        t.indexOf("hero_brand_name") < 0 &&
        t.indexOf("branch landing site") < 0;
    }
    return true;
  }

  function isGoodPlannerPrompt(tid, v) {
    var t = String(v || "");
    if (!t || promptLooksJapanese(t)) return false;
    if (tid === "type1") {
      return t.indexOf("TYPE 1 — hearing-driven structure") >= 0 &&
        t.indexOf("No page copy") >= 0 &&
        (t.indexOf("PAGE LIST CONTEXT") >= 0 || t.length > 500);
    }
    if (tid === "type3") {
      // Accept nested planner from THIS hearing — reject legacy flat hero_brand_name stubs.
      return t.indexOf("PAGE SCOPE") >= 0 &&
        t.indexOf("HEARING-DYNAMIC") < 0 &&
        (t.indexOf("NESTED") >= 0 || t.indexOf("CONTENT SECTIONS + NESTED") >= 0) &&
        t.indexOf("NESTED PATTERN") < 0 &&
        (t.indexOf("No page copy") >= 0 || t.indexOf("id, label, mode, rule") >= 0) &&
        (t.indexOf("template_hint") >= 0 || t.indexOf("PAGE block") >= 0) &&
        t.indexOf("hero_brand_name") < 0;
    }
    if (t.indexOf("hearing-driven structure") < 0) return false;
    return t.indexOf("PAGE COMPOSITION RULES") >= 0 || t.length > 500;
  }

  function englishSystemForType(tid) {
    var fromPack = packValueFor(tid, "value");
    if (isGoodWriterPrompt(fromPack)) return fromPack;
    return defaultWriterForType(tid);
  }

  function resolvePromptValue(tid, raw) {
    var v = String(raw || "").trim();
    if (isGoodWriterPrompt(v)) return v;
    var fromPack = packValueFor(tid, "value");
    if (isGoodWriterPrompt(fromPack)) return fromPack;
    return defaultWriterForType(tid);
  }

  function resolvePlannerValue(tid, raw) {
    var v = String(raw || "").trim();
    if (isGoodPlannerPrompt(tid, v)) return v;
    var fromPack = packValueFor(tid, "planner_value");
    if (isGoodPlannerPrompt(tid, fromPack)) return fromPack;
    return defaultPlannerForType(tid);
  }

  function resolveUserTemplate(tid, raw) {
    var v = String(raw || "").trim();
    if (!v || promptLooksJapanese(v) || v.indexOf("{page_rules}") < 0) {
      var label = {
        type1: "Type 1 (new site)",
        type2: "Type 2 (renewal)",
        type3: "Type 3 (satellite)",
        type4: "Type 4 (satellite renewal)"
      }[tid] || tid;
      return label + " — write Japanese section copy from THIS hearing sheet only.\n" +
        "Following the permitted facts and page rules, write Japanese copy for each section id.\n" +
        "Output JSON key: sections (object) — each key is a section id, value is a Japanese body string.\n" +
        "No Markdown. If the hearing has no fact for a section, use an empty string. Do not invent topics.\n" +
        "{page_rules}\n\n{hearing}";
    }
    return v;
  }

  function promptPackFromConfig() {
    var cfg = state.config || {};
    var titles = {
      type1: "Type 1 — New site",
      type2: "Type 2 — Renewal",
      type3: "Type 3 — Satellite",
      type4: "Type 4 — Satellite renewal"
    };
    var descriptions = {
      type1: "AI-1 structure + AI-2 content for Type 1 (new site).",
      type2: "AI-1 structure + AI-2 content for Type 2 (renewal).",
      type3: "AI-1 structure + AI-2 content for Type 3 (satellite).",
      type4: "AI-1 structure + AI-2 content for Type 4 (satellite renewal)."
    };
    var tp = cfg.type_prompts || {};
    var packSections = (cfg.prompt_pack && cfg.prompt_pack.sections) || [];
    var byId = {};
    packSections.forEach(function (s) {
      if (s && (s.id || s.type_id)) byId[s.id || s.type_id] = s;
    });
    var sections = ["type1", "type2", "type3", "type4"].map(function (tid) {
      var fromPack = byId[tid] || {};
      var slot = tp[tid] || {};
      return {
        id: tid,
        type_id: tid,
        title: fromPack.title || titles[tid],
        description: descriptions[tid],
        value: resolvePromptValue(tid, fromPack.value || slot.system_prompt || ""),
        planner_value: resolvePlannerValue(
          tid,
          fromPack.planner_value || slot.planner_system_prompt || ""
        ),
        user_value: resolveUserTemplate(
          tid,
          fromPack.user_value || slot.user_prompt_template || ""
        )
      };
    });
    return {
      mode: "per_type",
      language: "en",
      hint: "One AI-1 (structure) and AI-2 (content) prompt set per hearing type.",
      sections: sections
    };
  }

  function promptPackPanelHtml() {
    var pack = promptPackFromConfig();
    var sections = pack.sections || [];
    var activeId = state.promptPackTab || "type1";
    var active = null;
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].id === activeId) { active = sections[i]; break; }
    }
    if (!active && sections.length) active = sections[0];
    if (active) state.promptPackTab = active.id;
    var tabs = sections.map(function (s) {
      var short = String(s.id || "").replace("type", "Type ");
      return '<button type="button" data-prompt-pack="' + esc(s.id) + '"' +
        (active && active.id === s.id ? ' class="on"' : "") +
        ' title="' + esc(s.title || s.id) + '">' +
        esc(short) + "</button>";
    }).join("");
    var tid = active ? (active.type_id || active.id || "") : "";
    var body = active
      ? '<p class="prompt-note" style="margin-top:0">' + esc(active.description || "") + "</p>" +
        '<label class="prompt-pack-label">AI-1 — Structure prompt (' + esc(active.title || tid) + ")</label>" +
        '<textarea id="promptPackPlanner" data-prompt-type="' + esc(tid) +
        '" class="prompt-pack-ta">' + esc(active.planner_value || "") + "</textarea>" +
        '<label class="prompt-pack-label" style="margin-top:14px">AI-2 — Writer system prompt</label>' +
        '<textarea id="promptPackBody" data-prompt-type="' + esc(tid) +
        '" class="prompt-pack-ta">' + esc(active.value || "") + "</textarea>" +
        '<label class="prompt-pack-label" style="margin-top:14px">AI-2 — User template (this type only)</label>' +
        '<textarea id="promptPackUser" data-prompt-type="' + esc(tid) +
        '" class="prompt-pack-ta" style="min-height:120px">' + esc(active.user_value || "") + "</textarea>"
      : "";
    return '<div class="prompt-pack" id="promptPackPanel">' +
      '<p class="prompt-note">' + esc(pack.hint || "") + "</p>" +
      '<div class="prompt-tabs" id="promptPackTabs">' + tabs + "</div>" +
      body +
      "</div>";
  }

  function collectPromptPackValues(prevCfg) {
    prevCfg = prevCfg || {};
    var pack = promptPackFromConfig();
    var typePrompts = {};
    var prevTp = prevCfg.type_prompts || {};
    ["type1", "type2", "type3", "type4"].forEach(function (tid) {
      var prev = (prevTp[tid] && typeof prevTp[tid] === "object") ? prevTp[tid] : {};
      var fromPack = null;
      (pack.sections || []).forEach(function (s) {
        if (s.id === tid || s.type_id === tid) fromPack = s;
      });
      typePrompts[tid] = {
        system_prompt: resolvePromptValue(tid, (fromPack && fromPack.value) || prev.system_prompt || ""),
        planner_system_prompt: resolvePlannerValue(tid, (fromPack && fromPack.planner_value) || prev.planner_system_prompt || ""),
        user_prompt_template: resolveUserTemplate(tid, (fromPack && fromPack.user_value) || prev.user_prompt_template || "")
      };
    });
    var tidEl = document.getElementById("promptPackBody");
    var tid = tidEl ? (tidEl.getAttribute("data-prompt-type") || "") : "";
    if (tid && typePrompts[tid]) {
      var plannerEl = document.getElementById("promptPackPlanner");
      var userEl = document.getElementById("promptPackUser");
      if (plannerEl) typePrompts[tid].planner_system_prompt = resolvePlannerValue(tid, plannerEl.value);
      if (tidEl) typePrompts[tid].system_prompt = resolvePromptValue(tid, tidEl.value);
      if (userEl) typePrompts[tid].user_prompt_template = resolveUserTemplate(tid, userEl.value);
    }
    return {
      type_prompts: typePrompts,
      system_prompt: (typePrompts.type3 && typePrompts.type3.system_prompt) || prevCfg.system_prompt || "",
      planner_system_prompt: (typePrompts.type3 && typePrompts.type3.planner_system_prompt) || prevCfg.planner_system_prompt || "",
      user_prompt_template: (typePrompts.type3 && typePrompts.type3.user_prompt_template) || prevCfg.user_prompt_template || "",
      type24_extras_prompt: prevCfg.type24_extras_prompt || ""
    };
  }

  function bindPromptPackTabs() {
    var root = document.getElementById("promptPackPanel");
    if (!root) return;
    root.querySelectorAll("[data-prompt-pack]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!state.config) state.config = {};
        if (!state.config.type_prompts) state.config.type_prompts = {};
        var tidEl = document.getElementById("promptPackBody");
        var tid = tidEl ? (tidEl.getAttribute("data-prompt-type") || "") : "";
        if (tid) {
          if (!state.config.type_prompts[tid]) state.config.type_prompts[tid] = {};
          var plannerEl = document.getElementById("promptPackPlanner");
          var userEl = document.getElementById("promptPackUser");
          if (plannerEl) state.config.type_prompts[tid].planner_system_prompt = plannerEl.value;
          if (tidEl) state.config.type_prompts[tid].system_prompt = tidEl.value;
          if (userEl) state.config.type_prompts[tid].user_prompt_template = userEl.value;
          if (state.config.prompt_pack && state.config.prompt_pack.sections) {
            state.config.prompt_pack.sections.forEach(function (s) {
              if (s.id === tid || s.type_id === tid) {
                if (plannerEl) s.planner_value = plannerEl.value;
                if (tidEl) s.value = tidEl.value;
                if (userEl) s.user_value = userEl.value;
              }
            });
          }
        }
        state.promptPackTab = btn.getAttribute("data-prompt-pack") || "type1";
        var openAdv = document.querySelector("details.prompt-advanced");
        state.showAdvanced = !!(openAdv && openAdv.open);
        draw();
      });
    });
  }

  function viewConfig() {
    var cfg = state.config || { keys: {}, models: [], system_prompt: "", user_prompt_template: "" };
    var san = sanitizeSelectedForKeys(state.selected || []);
    if (san.swaps.length) {
      state.selected = san.selected;
      state._lastKeySwapHint = san.swaps.map(function (s) {
        return modelLabel(s.from) + " → " + modelLabel(s.to);
      }).join("; ");
    }
    var selected = state.selected || [];
    var byId = {};
    (cfg.models || []).forEach(function (m) { byId[m.id] = m; });
    var needed = neededKeyFields(selected);
    // Credentials only for paid-path models that are NOT already on the server.
    // GEMINI_PAID_API_KEY (and other .env paid keys) → no paste UI, same as free.
    var needPaste = needed.filter(function (k) { return k.paid && !k.ready; });
    // Auto-accept server-ready paid keys so Save is not blocked.
    needed.forEach(function (k) {
      if (k.paid && k.ready) {
        state.acceptedKeys = state.acceptedKeys || {};
        state.acceptedKeys[k.field] = true;
      }
    });
    // Prefer showing unpaid ready Gemini as optional (not blocking) unless paid selected.
    var prevFilter = state.modelFilter;
    state.modelFilter = "free";
    var freeList = filteredModels(cfg);
    state.modelFilter = "paid";
    var paidList = filteredModels(cfg);
    state.modelFilter = prevFilter || "all";

    var stack = selectedModelsBoardHtml(selected, byId);

    function keyRowHtml(k) {
      var draft = state.draftKeys[k.field] || "";
      var modelsForKey = (selected || []).filter(function (id) {
        var m = byId[id];
        return m && m.key_field === k.field &&
          (m.pricing === "paid" || !!(state.paidKeyModels && state.paidKeyModels[id]));
      }).map(function (id) { return (byId[id] && byId[id].name) || id; });
      var forModels = modelsForKey.length ? modelsForKey.slice(0, 3).join(", ") : "";
      var must = !k.ready;
      var ph = k.ready
        ? "Key saved — paste to replace (optional)"
        : ("Paste " + (k.label || "provider") + " API key");
      var badge = k.ready
        ? '<span class="badge ok">Saved</span>'
        : '<span class="badge req">Required</span>';
      return '<div class="cred-row">' +
        '<div class="cred-label">' +
        '<span class="kl">' + esc(k.label) + (must ? " *" : "") + "</span>" +
        (forModels ? '<span class="key-hint">For ' + esc(forModels) + "</span>" : "") +
        (k.field === "gemini_paid_api_key"
          ? '<span class="key-hint">Auto-used for all Paid Gemini models when set on server</span>'
          : k.field === "gemini_api_key"
          ? '<span class="key-hint">Free Flash / Flash-Lite only</span>'
          : '<span class="key-hint">One key for this provider</span>') +
        "</div>" +
        '<div class="cred-field">' +
        '<input type="password" data-key="' + esc(k.field) + '"' +
        ' data-paid="1"' +
        (must ? ' aria-required="true"' : "") +
        ' placeholder="' + esc(ph) + '" autocomplete="off" value="' +
        esc(draft) + '">' +
        badge +
        "</div></div>";
    }

    var keyRows = needPaste.map(keyRowHtml).join("");
    var gateErr = configGateError(selected, Object.assign({}, state.draftKeys), "config");

    return '<div class="card"><h2>Config</h2>' +
      '<p class="lead">Choose up to 2 models. Order sets the pipeline roles.</p>' +
      '<div class="picker-notes">' +
      '<div><b>1 model</b> — AI-1 section map only (AI-2 needs a 2nd model; that is not a quota block).</div>' +
      '<div><b>2 models</b> — AI-1 section map + AI-2 Japanese section content.</div>' +
      '<div class="best-pairs">' +
      '<div class="best-pairs-title">Free Best Pair <span>— #1 planner + #2 writer</span></div>' +
      '<ul class="best-pairs-list">' +
      '<li><span class="bp-num">1</span><span class="bp-ai1">Gemini 3.5</span><span class="bp-plus">+</span><span class="bp-ai2">Gemini 3.5 Lite</span></li>' +
      '<li><span class="bp-num">2</span><span class="bp-ai1">Gemini 3.5</span><span class="bp-plus">+</span><span class="bp-ai2">Nemotron 120B</span></li>' +
      '</ul></div>' +
      "</div>" +
      '<div class="dual-pick">' +
      hoverMenuHtml("free", freeList, selected) +
      hoverMenuHtml("paid", paidList, selected) +
      "</div>" +
      stack +
      (keyRows
        ? '<div class="cred-panel"><div class="cred-head"><h3>API credentials</h3>' +
          '<p>Only for paid models. Free models never ask for a key.</p></div>' +
          '<div class="key-slim" id="keyInputs">' + keyRows + "</div></div>"
        : "") +
      (state._lastKeySwapHint
        ? '<div class="gate-bar ok" id="configSwapBar">' +
          '<div><p class="gate-title">Using ready free models</p>' +
          '<p class="gate-hint">' + esc(state._lastKeySwapHint) +
          " — server key missing for that free pick. Or choose the same model under Paid and paste your key.</p></div></div>"
        : "") +
      (gateErr
        ? '<div class="gate-bar bad" id="configGateBar">' +
          '<div><p class="gate-title" id="configGateTitle">Cannot continue yet</p>' +
          '<p class="gate-hint" id="configGateHint">' + esc(gateErr) + "</p></div></div>"
        : '<div class="gate-bar ok hid" id="configGateBar" aria-hidden="true">' +
          '<div><p class="gate-title" id="configGateTitle"></p>' +
          '<p class="gate-hint" id="configGateHint"></p></div></div>') +
      '<details class="prompt-advanced" style="margin-top:16px"' + (state.showAdvanced ? " open" : "") + ">" +
      '<summary style="cursor:pointer;font-weight:700">Advanced: prompts</summary>' +
      (state.showAdvanced
        ? (
          promptPackPanelHtml() +
          '<p class="prompt-note" style="margin-top:16px"><b>After AI-1</b> — page &amp; block map (observe structure accuracy):</p>' +
          promptSectionPanelHtml()
        )
        : '<p class="prompt-note">Open this section to edit per-type AI-1 / AI-2 prompts.</p>') +
      "</details>" +
      '<div class="actions">' +
      '<button class="btn g" id="saveConfig"' + (gateErr ? " disabled" : "") +
      ' title="' + esc(gateErr || "Save models and continue") +
      '">Save &amp; continue</button></div></div>';
  }

  function selectedModelsFromDom() {
    return (state.selected || []).slice();
  }

  function preserveDraftKeys() {
    document.querySelectorAll("[data-key]").forEach(function (inp) {
      state.draftKeys[inp.getAttribute("data-key")] = inp.value;
    });
  }

  function addModelFromSelect() {
    toggleModelFromSelect();
  }

  function toggleModel(id, tier) {
    if (!id) return;
    tier = tier === "paid" ? "paid" : "free";
    preserveDraftKeys();
    state.paidKeyModels = state.paidKeyModels || {};
    var cfg = state.config || { models: [] };
    var byId = {};
    (cfg.models || []).forEach(function (m) { byId[m.id] = m; });
    var m = byId[id];
    var wantPaid = tier === "paid" || !!(m && m.pricing === "paid");
    var idx = state.selected.indexOf(id);
    if (idx >= 0) {
      var wasPaid = !!(state.paidKeyModels[id]) || !!(m && m.pricing === "paid");
      // Same Flash id in both menus: switching free↔paid updates path, does not deselect.
      if (wasPaid !== wantPaid && !(m && m.pricing === "paid")) {
        if (wantPaid) state.paidKeyModels[id] = true;
        else delete state.paidKeyModels[id];
        state._lastKeySwapHint = "";
        pruneDraftKeysForSelection();
        clearMsg();
        draw();
        return;
      }
      state.selected.splice(idx, 1);
      delete state.paidKeyModels[id];
      state._lastKeySwapHint = "";
      pruneDraftKeysForSelection();
      clearMsg();
      draw();
      return;
    }
    if ((state.selected || []).length >= V2_MAX_MODELS) {
      msg("Maximum 2 models. Remove one to add another.", false);
      return;
    }
    // Free menu + no server key → silent GLM/NIM fallback (never ask client for free keys).
    if (!wantPaid && m && !modelKeyReady(m)) {
      var fb = pickReadyFreeFallback(state.selected);
      if (!fb) {
        msg("No free model with a server key is ready. Pick the model under Paid and paste your key, or check .env.", false);
        return;
      }
      if (state.selected.indexOf(fb) < 0) state.selected.push(fb);
      delete state.paidKeyModels[fb];
      state._lastKeySwapHint = modelLabel(id) + " → " + modelLabel(fb);
      pruneDraftKeysForSelection();
      msg(
        modelLabel(id) + " has no server key. Using " + modelLabel(fb) +
          ". For your own key, pick the same model under Paid.",
        true
      );
      draw();
      return;
    }
    state.selected.push(id);
    if (wantPaid) state.paidKeyModels[id] = true;
    else delete state.paidKeyModels[id];
    state._lastKeySwapHint = "";
    pruneDraftKeysForSelection();
    clearMsg();
    draw();
  }

  function toggleModelFromSelect() {
    var sel = document.getElementById("modelSelect");
    if (!sel || !sel.value) return;
    toggleModel(sel.value);
  }

  function removeModel(id) {
    preserveDraftKeys();
    state.selected = (state.selected || []).filter(function (x) { return x !== id; });
    if (state.paidKeyModels) delete state.paidKeyModels[id];
    pruneDraftKeysForSelection();
    clearMsg();
    draw();
  }

  async function saveConfig() {
    var saveBtn = document.getElementById("saveConfig");
    var prevLabel = saveBtn ? saveBtn.textContent : "";
    try {
      preserveDraftKeys();
      var keys = collectPastedKeys();
      var san = sanitizeSelectedForKeys(selectedModelsFromDom());
      state.selected = san.selected;
      if (san.swaps.length) {
        state._lastKeySwapHint = san.swaps.map(function (s) {
          return modelLabel(s.from) + " → " + modelLabel(s.to);
        }).join("; ");
      }
      var gate = configGateError(state.selected, keys, "config");
      if (gate) {
        refreshConfigGateUi();
        var firstBad = document.querySelector("[data-key].invalid");
        if (firstBad) firstBad.focus();
        throw new Error(gate);
      }
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = Object.keys(keys).length ? "Checking key…" : "Saving…";
      }
      var prompts = collectPromptPackValues(state.config || {});
      var body = {
        keys: keys,
        selected_models: (state.selected || []).slice(0, V2_MAX_MODELS),
        system_prompt: prompts.system_prompt || "",
        user_prompt_template: prompts.user_prompt_template || "",
        planner_system_prompt: prompts.planner_system_prompt || "",
        type24_extras_prompt: prompts.type24_extras_prompt || "",
        type_prompts: prompts.type_prompts || {}
      };
      var res = await fetch(api("/v2/lab/config"), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      if (!res.ok) {
        var errBody = {};
        try { errBody = await res.json(); } catch (e) {}
        var detail = errBody.detail;
        if (Array.isArray(detail)) {
          detail = detail.map(function (x) {
            return typeof x === "string" ? x : (x && x.msg) || JSON.stringify(x);
          }).join(" ");
        } else if (detail && typeof detail === "object") {
          detail = JSON.stringify(detail);
        }
        throw new Error(detail || ("HTTP " + res.status));
      }
      state.config = mergeV2ConfigMeta(await res.json());
      if (state.config && state.config.prompt_sections) {
        delete state.config.prompt_sections;
      }
      state.selected = (state.config.selected_models || []).slice(0, V2_MAX_MODELS);
      syncPaidKeyModelsFromSelection();
      state.committedSelected = state.selected.slice();
      markAcceptedKeys(state.selected, keys);
      // Clear pasted drafts for keys that are now saved server-side.
      Object.keys(keys).forEach(function (f) {
        if (state.config.keys && state.config.keys[f] && state.config.keys[f].set) {
          delete state.draftKeys[f];
        }
      });
      go("hearing", 1);
      msg("Config saved. Continue with Hearing.", true);
    } catch (e) {
      msg(e.message || "Save failed", false);
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = prevLabel || "Save & continue";
        refreshConfigGateUi();
      }
    }
  }

  function rememberMegaOpen(kind, company) {
    if (kind) state._megaRestore = { kind: kind, company: company || "" };
    else state._megaRestore = null;
  }

  function placeMegaSubmenu(co) {
    if (!co || window.matchMedia("(max-width: 800px)").matches) return;
    var btn = co.querySelector(".mega-co-btn");
    var sub = co.querySelector(".mega-sub");
    if (!btn || !sub) return;
    var r = btn.getBoundingClientRect();
    var gap = 6;
    var top = r.top;
    var left = r.right + gap;
    sub.style.top = "0px";
    sub.style.left = "0px";
    sub.style.visibility = "hidden";
    sub.style.display = "block";
    var sh = sub.offsetHeight || 280;
    var sw = sub.offsetWidth || 260;
    sub.style.display = "";
    sub.style.visibility = "";
    if (top + sh > window.innerHeight - 10) {
      top = Math.max(10, window.innerHeight - sh - 10);
    }
    if (left + sw > window.innerWidth - 10) {
      left = Math.max(10, r.left - sw - gap);
    }
    sub.style.top = Math.round(top) + "px";
    sub.style.left = Math.round(left) + "px";
  }

  function closeAllMegaCos(except) {
    document.querySelectorAll(".mega-co.open").forEach(function (el) {
      if (except && el === except) return;
      el.classList.remove("open");
      var b = el.querySelector(".mega-co-btn");
      if (b) b.setAttribute("aria-expanded", "false");
    });
  }

  function openMegaCo(co) {
    if (!co) return;
    if (state._megaCoCloseTimer) {
      clearTimeout(state._megaCoCloseTimer);
      state._megaCoCloseTimer = null;
    }
    var panel = co.parentElement;
    if (panel) {
      panel.querySelectorAll(".mega-co.open").forEach(function (el) {
        if (el !== co) {
          el.classList.remove("open");
          var b = el.querySelector(".mega-co-btn");
          if (b) b.setAttribute("aria-expanded", "false");
        }
      });
    }
    co.classList.add("open");
    var btn = co.querySelector(".mega-co-btn");
    if (btn) btn.setAttribute("aria-expanded", "true");
    placeMegaSubmenu(co);
    var dd = co.closest(".mega-dd");
    rememberMegaOpen(
      dd && dd.getAttribute("data-kind"),
      co.getAttribute("data-company") || ""
    );
  }

  function scheduleCloseMegaCo(co) {
    if (state._megaCoCloseTimer) clearTimeout(state._megaCoCloseTimer);
    state._megaCoCloseTimer = setTimeout(function () {
      if (!co) return;
      co.classList.remove("open");
      var b = co.querySelector(".mega-co-btn");
      if (b) b.setAttribute("aria-expanded", "false");
      var dd = co.closest(".mega-dd");
      if (dd && dd.classList.contains("open")) {
        rememberMegaOpen(dd.getAttribute("data-kind"), "");
      }
      state._megaCoCloseTimer = null;
    }, 180);
  }

  function bindConfig() {
    var save = document.getElementById("saveConfig");
    if (save) save.onclick = saveConfig;
    var adv = document.querySelector("details.prompt-advanced");
    if (adv) {
      adv.addEventListener("toggle", function () {
        var wantOpen = !!adv.open;
        if (wantOpen === !!state.showAdvanced) return;
        state.showAdvanced = wantOpen;
        // Lazy-render heavy prompt editors only when opened
        draw();
      });
    }
    bindPromptPackTabs();
    bindPageBrowser("promptPageBrowser", function (pick) {
      if (pick.group) {
        state.pageGroup = pick.group;
        var tabs = (promptSectionsCatalog().tabs || []);
        state.promptPage = ensureActiveInGroup(tabs, state.promptPage, state.pageGroup);
      }
      if (pick.id) state.promptPage = pick.id;
      // Only keep open if the Advanced panel is already open (user is editing inside it)
      var openAdv = document.querySelector("details.prompt-advanced");
      state.showAdvanced = !!(openAdv && openAdv.open);
      draw();
    });
    document.querySelectorAll("[data-mega-trigger]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        var kind = btn.getAttribute("data-mega-trigger");
        var dd = document.getElementById(kind + "MegaDd");
        document.querySelectorAll(".mega-dd.open").forEach(function (el) {
          if (el !== dd) {
            el.classList.remove("open");
            var t = el.querySelector("[data-mega-trigger]");
            if (t) t.setAttribute("aria-expanded", "false");
            closeAllMegaCos();
          }
        });
        if (dd) {
          var willOpen = !dd.classList.contains("open");
          dd.classList.toggle("open", willOpen);
          btn.setAttribute("aria-expanded", willOpen ? "true" : "false");
          if (!willOpen) closeAllMegaCos();
          rememberMegaOpen(willOpen ? kind : null, willOpen ? ((state._megaRestore && state._megaRestore.company) || "") : "");
          if (willOpen) {
            var openCo = dd.querySelector(".mega-co.open");
            if (openCo) placeMegaSubmenu(openCo);
          }
        }
      };
    });
    document.querySelectorAll(".mega-co").forEach(function (co) {
      co.addEventListener("mouseenter", function () { openMegaCo(co); });
      co.addEventListener("mouseleave", function () { scheduleCloseMegaCo(co); });
    });
    document.querySelectorAll("[data-company-toggle]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        var co = btn.closest(".mega-co");
        if (!co) return;
        if (co.classList.contains("open")) {
          co.classList.remove("open");
          btn.setAttribute("aria-expanded", "false");
          var dd = co.closest(".mega-dd");
          rememberMegaOpen(dd && dd.getAttribute("data-kind"), "");
        } else {
          openMegaCo(co);
        }
      };
    });
    document.querySelectorAll("[data-pick-model]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        // Close menus after pick so the pipeline board is the focus.
        rememberMegaOpen(null);
        toggleModel(
          btn.getAttribute("data-pick-model") || "",
          btn.getAttribute("data-pick-tier") || "free"
        );
      };
    });
    document.querySelectorAll("[data-remove]").forEach(function (btn) {
      btn.onclick = function () { removeModel(btn.getAttribute("data-remove")); };
    });
    document.querySelectorAll("[data-key]").forEach(function (el) {
      el.oninput = function () { refreshConfigGateUi(); };
    });
    if (!state._megaDocCloseBound) {
      state._megaDocCloseBound = true;
      document.addEventListener("click", function (e) {
        if (e.target && e.target.closest && e.target.closest(".mega-dd")) return;
        if (e.target && e.target.closest && e.target.closest(".mega-sub")) return;
        document.querySelectorAll(".mega-dd.open").forEach(function (el) {
          el.classList.remove("open");
          var t = el.querySelector("[data-mega-trigger]");
          if (t) t.setAttribute("aria-expanded", "false");
        });
        closeAllMegaCos();
        state._megaRestore = null;
      });
      document.addEventListener("keydown", function (e) {
        if (e.key !== "Escape") return;
        document.querySelectorAll(".mega-dd.open").forEach(function (el) {
          el.classList.remove("open");
          var t = el.querySelector("[data-mega-trigger]");
          if (t) t.setAttribute("aria-expanded", "false");
        });
        closeAllMegaCos();
        state._megaRestore = null;
      });
      window.addEventListener("resize", function () {
        document.querySelectorAll(".mega-co.open").forEach(placeMegaSubmenu);
      });
      window.addEventListener("scroll", function () {
        document.querySelectorAll(".mega-co.open").forEach(placeMegaSubmenu);
      }, true);
    }
    // Reposition restored submenu after paint.
    document.querySelectorAll(".mega-co.open").forEach(function (co) {
      requestAnimationFrame(function () { placeMegaSubmenu(co); });
    });
    if (document.getElementById("saveConfig")) refreshConfigGateUi();
  }
  function isLabHearing(h) {
    h = h || state.hearing || {};
    return h.production_type === "type1" ||
      h.production_type === "type3" ||
      h.production_type === "type2" ||
      h.production_type === "type4";
  }

  function hearingSummary(h) {
    h = h || {};
    var p = h.project || {};
    var store = h.store || {};
    var typeLabel = h.production_label || "—";
    if (h.production_type === "type1") typeLabel = "Type 1 · New Site";
    else if (h.production_type === "type2") typeLabel = "Type 2 · Renewal";
    else if (h.production_type === "type3") typeLabel = "Type 3 · Satellite";
    else if (h.production_type === "type4") typeLabel = "Type 4 · Satellite Renewal";
    return {
      name: p.business_name || store.name || "—",
      type: typeLabel,
      domain: p.domain || p.existing_url || "—",
      area: p.area || "—",
      pages: (h.pages || []).length + (h.existing_pages || []).length
    };
  }

  function pageTabs() {
    var bp = state.blueprint || {};
    var tabs = [];
    (bp.pages || []).forEach(function (p) {
      tabs.push({ id: p.slug || p.id, label: p.nav_label || p.slug || p.id, group: "nav" });
    });
    (bp.seo_pages || []).forEach(function (p) {
      tabs.push({ id: p.slug || p.id, label: (p.nav_label || p.slug || p.id) + " (SEO)", group: "seo" });
    });
    (bp.tag_pages || []).forEach(function (p) {
      tabs.push({ id: p.slug || p.id, label: (p.nav_label || p.slug || p.id) + " (tag)", group: "tag" });
    });
    return tabs;
  }

  function blueprintStatsLine(stats) {
    stats = stats || {};
    var nav = stats.nav_pages || stats.content_pages || 0;
    var seo = stats.seo_pages || 0;
    var tag = stats.tag_pages || 0;
    var all = stats.all_pages || (nav + seo + tag);
    var sections = stats.total_sections || 0;
    var writeN = stats.write_pages;
    var shellN = stats.shell_pages;
    var fillN = stats.content_fill_pages;
    var line = all + " pages (" + nav + " nav · " + seo + " SEO · " + tag + " tag) · " + sections + " sections";
    if (fillN != null) {
      line += " · content " + fillN;
      if (writeN != null || shellN != null) {
        line += " (AI-2 " + (writeN != null ? writeN : "?");
        if (shellN) line += " + shell " + shellN;
        line += ")";
      }
    } else if (writeN != null) {
      line += " · AI-2 " + writeN + " pages";
    }
    var omitted = stats.omitted_pages || 0;
    if (omitted) line += " · omitted " + omitted + " empty";
    return line;
  }

  var TYPE1_BLUEPRINT_VERSION = 1;
  var TYPE2_BLUEPRINT_VERSION = 1;
  var TYPE3_BLUEPRINT_VERSION = 3;
  var TYPE4_BLUEPRINT_VERSION = 1;
  var TYPE3_MIN_NAV_PAGES = 12;
  var TYPE2_MIN_NAV_PAGES = 8;
  var TYPE1_MIN_NAV_PAGES = 12;

  function currentHearingType() {
    return (state.hearing && state.hearing.production_type) ||
      (state.blueprint && state.blueprint.production_type) || "";
  }

  function expectedNavPages() {
    var t = currentHearingType();
    if (t === "type2") return TYPE2_MIN_NAV_PAGES;
    if (t === "type1") return TYPE1_MIN_NAV_PAGES;
    if (state.config && state.config.type3_nav_pages) return state.config.type3_nav_pages;
    return TYPE3_MIN_NAV_PAGES;
  }

  function expectedBlueprintVersion() {
    var t = currentHearingType();
    if (t === "type1") return TYPE1_BLUEPRINT_VERSION;
    if (t === "type2") return TYPE2_BLUEPRINT_VERSION;
    if (t === "type4") return TYPE4_BLUEPRINT_VERSION;
    return TYPE3_BLUEPRINT_VERSION;
  }

  function serverBuildOk(cfg) {
    cfg = cfg || state.config || {};
    var probe = cfg.server_nav_probe;
    var ver = cfg.blueprint_version;
    if (probe == null && ver == null) return true;
    if (ver != null && ver < TYPE3_BLUEPRINT_VERSION) return false;
    if (probe != null && probe < TYPE3_MIN_NAV_PAGES) return false;
    var t = currentHearingType();
    if ((t === "type1" || t === "type2" || t === "type4") && cfg.active_production_types &&
        cfg.active_production_types.indexOf(t) < 0) {
      return false;
    }
    return true;
  }

  function serverProbeKnownBad() {
    var cfg = state.config || {};
    var probe = cfg.server_nav_probe;
    var ver = cfg.blueprint_version;
    if (ver != null && ver < TYPE3_BLUEPRINT_VERSION) return true;
    if (probe != null && probe < TYPE3_MIN_NAV_PAGES) return true;
    var t = currentHearingType();
    if ((t === "type1" || t === "type2" || t === "type4") && cfg.active_production_types &&
        cfg.active_production_types.indexOf(t) < 0) {
      return true;
    }
    return false;
  }

  function assertBlueprintNav(data) {
    var expect = expectedNavPages();
    var minVer = expectedBlueprintVersion();
    var nav = ((data.blueprint && data.blueprint.pages) || []).length;
    var previewNav = data.export_preview && data.export_preview.nav_pages;
    if (previewNav != null) nav = Math.max(nav, previewNav);
    if (nav >= Math.max(1, expect - 1) &&
        (data.blueprint.blueprint_version || 0) >= minVer) {
      return data;
    }
    if (!serverBuildOk()) {
      throw new Error(
        "Server is outdated (probe " + ((state.config && state.config.server_nav_probe) || "?") +
        ", need " + expect + " nav). Stop ALL old servers, then run: " +
        "./scripts/run_demo.sh --stop && ./scripts/run_demo.sh --daemon"
      );
    }
    throw new Error(
      "AI-1 returned " + nav + " nav pages (need ~" + expect + "). Click Run AI-1 again."
    );
  }

  function syncBlueprintStats(bp, sections) {
    bp = bp || {};
    bp.stats = bp.stats || {};
    var pages = bp.pages || [];
    var seo = bp.seo_pages || [];
    var tags = bp.tag_pages || [];
    bp.stats.nav_pages = pages.length;
    bp.stats.content_pages = pages.length;
    bp.stats.seo_pages = seo.length;
    bp.stats.tag_pages = tags.length;
    bp.stats.all_pages = pages.length + seo.length + tags.length;
    if (sections && sections.length) {
      bp.stats.total_sections = sections.length;
    }
    if (bp.stats.write_pages == null && pages.length) {
      var blankSlugs = {};
      pages.forEach(function (p) {
        if (p.leave_blank) blankSlugs[p.slug || p.id] = true;
      });
      var writeN = pages.length + seo.length + tags.length;
      Object.keys(blankSlugs).forEach(function () { writeN -= 1; });
      bp.stats.write_pages = Math.max(0, writeN);
    }
    return bp;
  }

  var progressTimer = null;

  function formatElapsed(ms) {
    var sec = Math.max(0, Math.floor((ms || 0) / 1000));
    var m = Math.floor(sec / 60);
    var s = sec % 60;
    return m ? (m + "m " + s + "s") : (s + "s");
  }

  function pushProgressLog(prog, line) {
    prog.log = prog.log || [];
    if (!line) return;
    if (prog.log[0] === line) return;
    prog.log.unshift(line);
    if (prog.log.length > 10) prog.log.length = 10;
  }

  function stopProgressTimer() {
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
  }

  function startProgressTimer() {
    stopProgressTimer();
    progressTimer = setInterval(function () {
      if (!state.planning && !state.running && !state.exporting) {
        stopProgressTimer();
        return;
      }
      patchLiveProgress();
    }, 1000);
  }

  function runProgressHtml(prog, title) {
    prog = prog || {};
    var isExport = prog.kind === "export";
    var isWrite = prog.kind === "write" || /AI-2|本文|Content Creator/i.test(String(title || ""));
    var pageTotal = prog.total || 0;
    var pageIndex = prog.index || 0;
    var total = pageTotal;
    var index = pageIndex;
    // AI-2: show AI page counts as primary (avoid misleading 2/37 shell+SEO totals).
    if (isWrite && prog.aiTotal > 0) {
      total = prog.aiTotal;
      index = prog.aiDone != null ? prog.aiDone : 0;
    }
    var pct = (prog.soft_pct != null && prog.soft_pct >= 0)
      ? Math.min(100, Math.round(prog.soft_pct))
      : (total > 0 ? Math.min(100, Math.round((index / total) * 100)) : 0);
    var elapsed = prog.startedAt ? formatElapsed(Date.now() - prog.startedAt) : "0s";
    var stage = prog.label || prog.page || "準備中…";
    var active = prog.active || [];
    var remaining = (total > index) ? (total - index) : 0;
    var charsTotal = prog.chars_display || prog.chars_total || 0;
    var countWord = isExport ? "step" : (isWrite ? "AI本文" : "AI");
    var logHtml = (prog.log || []).map(function (line) {
      return "<li>" + esc(line) + "</li>";
    }).join("");
    var activeHtml = "";
    if (prog.partial) {
      activeHtml = '<p class="rp-active"><b>未完了</b> — ' +
        esc(prog.partialHint || "一部のみ生成済み。再実行するか部分結果を確認してください。") + "</p>";
    } else if (active.length) {
      activeHtml = isExport
        ? '<p class="rp-active">作業中: <b>' + esc(active.join("、")) + "</b></p>"
        : (isWrite
          ? '<p class="rp-active">いまAIが本文作成中: <b>' + esc(active.join("、")) + "</b>" +
            (charsTotal ? (" · 受信 <b>" + charsTotal.toLocaleString() + "</b>文字") : "") + "</p>"
          : '<p class="rp-active">いまAIが計画中: <b>' + esc(active.join("、")) + "</b>" +
            (charsTotal ? (" · 受信 <b>" + charsTotal.toLocaleString() + "</b>文字") : "") + "</p>");
    } else if (!isExport && remaining && total && pct < 100) {
      activeHtml = isWrite
        ? '<p class="rp-active">AI本文応答待ち… 残り <b>' + remaining + "</b>ページ（Geminiは最大約4分/ページ）</p>"
        : '<p class="rp-active">AI応答待ち… 残り <b>' + remaining + "</b>ページ（最大約35秒/ページ）</p>";
    } else if (isExport && remaining && total && pct < 100) {
      activeHtml = '<p class="rp-active">エクスポート進行中… 残り <b>' + remaining + "</b> step</p>";
    }
    return '<div class="run-progress" id="runProgress">' +
      '<div class="run-progress-head">' +
      '<p class="rp-title">' + esc(title || "Progress") + "</p>" +
      '<div class="rp-pct">' + pct + "%</div>" +
      "</div>" +
      '<div class="run-progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' +
      pct + '"><i style="width:' + pct + '%"></i></div>' +
      '<div class="run-progress-meta">' +
      '<span class="rp-stage">' + esc(stage) + "</span>" +
      '<span id="runProgressElapsed">経過 ' + esc(elapsed) +
      (total ? (" · " + countWord + " " + index + "/" + total) : "") +
      (isWrite && pageTotal
        ? (" · 全体 " + pageIndex + "/" + pageTotal)
        : "") +
      (charsTotal ? (" · " + charsTotal.toLocaleString() + "文字") : "") +
      (remaining ? (" · 残り " + remaining) : "") + "</span>" +
      "</div>" +
      activeHtml +
      (logHtml ? '<ul class="run-log">' + logHtml + "</ul>" : "") +
      "</div>";
  }

  function plannerButtonLabel() {
    if (!state.planning) return "Run AI-1";
    var p = state.planningProgress || {};
    if (p.total > 0) {
      var left = Math.max(0, (p.total || 0) - (p.index || 0));
      return "AI " + (p.index || 0) + "/" + p.total + (left ? (" · left " + left) : "");
    }
    return "Planning…";
  }

  function writeButtonLabel() {
    if (!state.running) return "Write section content";
    var p = state.writeProgress || {};
    if (p.aiTotal > 0) return "AI本文 " + (p.aiDone || 0) + "/" + p.aiTotal;
    if (p.total > 0) return "Content " + (p.index || 0) + "/" + p.total;
    return "Writing section content…";
  }

  function patchLiveProgress() {
    var prog = state.planning
      ? state.planningProgress
      : (state.running ? state.writeProgress : (state.exporting ? state.exportProgress : null));
    if (!prog) return;
    var title = state.planning
      ? "AI-1 ライブ進捗"
      : (state.running ? "AI-2 セクション本文作成" : "Google Spreadsheet 出力");
    var el = document.getElementById("runProgress");
    if (el) el.outerHTML = runProgressHtml(prog, title);
    var btn = document.getElementById(
      state.planning ? "runPlanner" : (state.running ? "runWrite" : "downloadSheets")
    );
    if (btn && state.planning) btn.textContent = plannerButtonLabel();
    if (btn && state.running) btn.textContent = writeButtonLabel();
    if (btn && state.exporting) btn.textContent = exportButtonLabel();
    var elapsedEl = document.getElementById("runProgressElapsed");
    if (elapsedEl && prog.startedAt) {
      var total = prog.total || 0;
      var index = prog.index || 0;
      var remaining = (total > index) ? (total - index) : 0;
      var charsTotal = prog.chars_display || prog.chars_total || 0;
      var countWord = prog.kind === "export" ? "step" : "AI";
      elapsedEl.textContent = "経過 " + formatElapsed(Date.now() - prog.startedAt) +
        (total ? (" · " + countWord + " " + index + "/" + total) : "") +
        (prog.kind === "write" && prog.aiTotal
          ? (" · AI本文 " + (prog.aiDone || 0) + "/" + prog.aiTotal)
          : "") +
        (charsTotal ? (" · " + Number(charsTotal).toLocaleString() + "文字") : "") +
        (remaining ? (" · 残り " + remaining) : "");
    }
  }

  function exportButtonLabel() {
    if (!state.exporting) return "Google Spreadsheet";
    var p = state.exportProgress || {};
    if (p.total > 0) return "Export " + (p.index || 0) + "/" + p.total;
    return "Exporting…";
  }

  function expectedType3NavPages() {
    return expectedNavPages();
  }

  function staleBlueprintReason(bp, sections) {
    bp = bp || {};
    if (!bp || !bp.pages) return "";
    if (!bp.stats) return "missing stats";
    var expectNav = expectedNavPages();
    var minVer = expectedBlueprintVersion();
    var nav = bp.stats.nav_pages || (bp.pages || []).length || 0;
    // Allow one omitted empty page (e.g. blank 料金表) below probe without forcing re-run.
    if (nav > 0 && nav < Math.max(1, expectNav - 1)) {
      return "incomplete nav (" + nav + " pages, need ~" + expectNav + ") — click Run AI-1 again";
    }
    if ((bp.blueprint_version || 0) < minVer) {
      return "old blueprint version — click Run AI-1 again";
    }
    if (bp.stats.write_pages == null) return "missing write_pages — click Run AI-1 again";
    if (!(bp.seo_pages || []).length && (bp.stats.seo_pages || 0) > 0) {
      return "SEO pages missing from blueprint — re-run AI-1";
    }
    var rowN = (sections || []).length;
    var secN = bp.stats.total_sections || 0;
    if (rowN > 0 && secN > 0 && Math.abs(rowN - secN) > 2) {
      return "section count mismatch (" + secN + " vs " + rowN + " rows) — re-run AI-1";
    }
    return "";
  }

  function staleGateHtml(bp, sections, prefix) {
    if (!bp) return "";
    var stale = staleBlueprintReason(bp, sections);
    if (!stale) return "";
    return '<div class="gate-bar bad"><p class="gate-hint">' + esc(prefix + stale) + ".</p></div>";
  }

  function serverProbeHtml() {
    if (!serverProbeKnownBad()) return "";
    var probe = state.config && state.config.server_nav_probe;
    var expect = expectedType3NavPages();
    return '<div class="gate-bar bad"><p class="gate-hint">Server outdated' +
      (probe != null ? " (probe " + probe + ", need " + expect + ")" : "") +
      '. Run: <code>./scripts/run_demo.sh --stop && ./scripts/run_demo.sh --daemon</code>' +
      " then hard-refresh this page.</p></div>";
  }

  function blueprintLooksStale(bp, sections) {
    return !!staleBlueprintReason(bp, sections);
  }

  function sectionsForPage(slug) {
    return (state.sections || []).filter(function (r) {
      return String(r.page_slug || r.page_id) === String(slug);
    });
  }

  function plannerBoardHtml() {
    var bp = state.blueprint;
    if (!bp) return "";
    var st = bp.ai_stages || {};
    var stats = bp.stats || {};
    return '<div class="pipeline-board"><p class="pb-title">AI pipeline · ' + esc(bp.clone_mode || "") + "</p>" +
      '<div class="pb-row"><span class="pb-model"><span class="step-badge inline">AI-1</span> Sections Planner</span><span class="pb-status ok">' +
      esc(st.planner_model ? modelLabel(st.planner_model) : (st.planner_mode === "llm" ? "LLM" : st.planner || "pending")) +
      "</span></div>" +
      '<div class="pb-row"><span class="pb-model"><span class="step-badge inline ai2">AI-2</span> Sections Content Creator</span><span class="pb-status ' +
      (st.writer === "complete" ? "ok" : "skipped") + '">' + esc(st.writer || "pending") + "</span></div>" +
      '<p class="key-hint" style="margin:8px 0 0">' + esc(blueprintStatsLine(stats)) + "</p>" +
      omittedNoteHtml(bp) +
      "</div>";
  }

  function omittedNoteHtml(bp) {
    var rows = (bp && bp.omitted_pages) || [];
    if (!rows.length) return "";
    return '<p class="prompt-note" style="margin:8px 0 0">除外した空ページ: ' +
      rows.map(function (r) {
        return esc(r.label || r.slug) +
          (r.reason ? ' <span class="key-hint">(' + esc(String(r.reason).slice(0, 80)) + ")</span>" : "");
      }).join("、") +
      "</p>";
  }

  function renderSectionBlocks(rows) {
    if (!rows.length) return '<p class="lead">No sections.</p>';
    var writerDone = !!(state.blueprint && state.blueprint.ai_stages &&
      state.blueprint.ai_stages.writer === "complete");
    return rows.map(function (r) {
      var text = String(r.text || "").trim();
      var mode = String(r.mode || "");
      var emptyHint;
      if (text) {
        emptyHint = null;
      } else if (mode === "shell") {
        emptyHint = writerDone
          ? "（シェル枠 — 一覧ページの固定文言）"
          : "（シェル枠 — AI-2後に自動記入）";
      } else if (mode === "blank") {
        emptyHint = "（空白 — 本文なし）";
      } else if (writerDone) {
        emptyHint = "（本文なし — ヒアリングに該当情報なし／要再実行）";
      } else {
        emptyHint = "（セクション本文 — AI-2 待ち）";
      }
      return '<div class="sec"><div class="sec-label">' + esc(r.section_label || r.section_id) +
        ' <span class="tag">' + esc(mode) + "</span></div>" +
        (text ? '<div class="sec-text">' + esc(text) + "</div>" :
          '<div class="sec-text writing-hint">' + emptyHint + "</div>") +
        (r.seeds ? '<p class="key-hint">Seeds: ' + esc(String(r.seeds).slice(0, 120)) + "</p>" : "") +
        "</div>";
    }).join("");
  }

  function viewHearing() {
    var h = state.hearing;
    if (!h) {
      return '<div class="card"><h2>Hearing</h2><p class="lead">Upload the hearing CSV file.</p>' +
        '<div class="dropzone" id="hearingDrop"><strong>Drop CSV here</strong><p>Hearing sheet (Type 1 New Site, Type 2 Renewal, Type 3 Satellite, or Type 4 Satellite Renewal)</p>' +
        '<label class="btn g" style="display:inline-block"><input type="file" id="hearingUp" accept=".csv,.txt" hidden>Choose file</label></div></div>';
    }
    var s = hearingSummary(h);
    return '<div class="card"><h2>Hearing loaded</h2><p class="lead">Confirm details, then AI-1 Sections Planner.</p>' +
      '<div class="hearing-meta">' +
      '<div class="cell"><div class="k">Shop</div><div class="v">' + esc(s.name) + "</div></div>" +
      '<div class="cell"><div class="k">Type</div><div class="v">' + esc(s.type) + "</div></div>" +
      '<div class="cell"><div class="k">Domain</div><div class="v">' + esc(s.domain) + "</div></div>" +
      '<div class="cell"><div class="k">Pages</div><div class="v">' + esc(s.pages) + "</div></div>" +
      '<div class="cell"><div class="k">File</div><div class="v">' + esc(state.hearingFile || "—") + "</div></div>" +
      "</div>" +
      (!isLabHearing(h)
        ? '<div class="gate-bar bad"><p class="gate-hint">This hearing type is not supported in this lab (use Type 1–4 hearing sheets).</p></div>'
        : '<div class="gate-bar ok"><p class="gate-hint">Ready for AI-1.</p></div>') +
      '<div class="actions"><label class="btn"><input type="file" id="hearingUp" accept=".csv,.txt" hidden>Replace</label>' +
      newGenerationBtnHtml() +
      '<button class="btn g" id="toPlanner"' + (!isLabHearing(h) ? " disabled" : "") + ">Next: AI-1 Sections Planner</button></div></div>";
  }

  function viewPlanner() {
    var canRun = state.hearing && isLabHearing(state.hearing) && !state.planning &&
      (state.selected || []).length >= 1;
    var sectionsOnly = v2SectionsOnly(state.selected || []);
    var nextBtn = state.blueprint
      ? (sectionsOnly
        ? '<button class="btn g" id="toSections">Next: Sections</button>'
        : '<button class="btn g" id="toDraft">Next: AI-2 Sections Content Creator</button>')
      : "";
    return '<div class="card ai-stage-card ai1"><h2><span class="step-badge">AI-1</span> Sections Planner</h2><p class="lead">Builds the <b>section map</b> (pages &amp; blocks) from the hearing. Review below — then AI-2 writes each section’s Japanese content.</p>' +
      serverProbeHtml() +
      (!(state.selected || []).length
        ? '<div class="gate-bar bad"><p class="gate-hint">Select model #1 in Config — required for AI-1.</p></div>'
        : "") +
      staleGateHtml(state.blueprint, state.sections, "Blueprint outdated: ") +
      (sectionsOnly && state.blueprint
        ? '<div class="gate-bar ok"><p class="gate-hint">1 model — section map ready. Add a 2nd model for AI-2 Sections Content Creator.</p></div>'
        : "") +
      (state.planning ? runProgressHtml(state.planningProgress, "AI-1 ライブ進捗") : "") +
      plannerBoardHtml() +
      (hasBlueprintPromptSections()
        ? '<div class="section-review" style="margin-top:16px">' +
          '<h3 style="margin:0 0 8px;font-size:15px">ページ構成を確認</h3>' +
          '<p class="prompt-note" style="margin:0 0 10px">ナビ / SEO / タグでページを選び、ブロック名と役割を確認。次の Step 4 で各セクションの本文を作成します。</p>' +
          promptSectionPanelHtml() + "</div>"
        : "") +
      '<div class="actions"><button class="btn" id="toHearing">Back</button>' +
      newGenerationBtnHtml() +
      '<button class="btn g" id="runPlanner"' + (canRun ? "" : " disabled") + ">" +
      esc(plannerButtonLabel()) + "</button>" +
      nextBtn +
      "</div></div>";
  }

  function viewDraft() {
    var selected = state.selected || [];
    var pipe = pipelinePreview(selected);
    var sectionsOnly = pipe.sectionsOnly;
    var canRun = !state.running && state.hearing && state.blueprint && selected.length >= 2 && pipe.writer;
    var roleRows = "";
    if (pipe.planner) {
      roleRows += "<tr><td>" + roleBadgeHtml("AI-1") + "</td><td><b>" + esc(modelLabel(pipe.planner)) + "</b></td></tr>";
    }
    if (pipe.writer) {
      roleRows += "<tr><td>" + roleBadgeHtml("AI-2") + "</td><td><b>" + esc(modelLabel(pipe.writer)) + "</b></td></tr>";
    }
    return '<div class="card ai-stage-card ai2"><h2><span class="step-badge ai2">AI-2</span> Sections Content Creator</h2><p class="lead">Writes the <b>Japanese content of each section</b> (every block on every page), using only facts from the hearing sheet.</p>' +
      serverProbeHtml() +
      staleGateHtml(state.blueprint, state.sections, "Section content blocked — ") +
      (sectionsOnly
        ? '<div class="gate-bar bad"><p class="gate-hint">1 model selected — section map only. Add a 2nd model in Config to write section content.</p></div>'
        : (pipe.hint ? '<div class="gate-bar ok"><p class="gate-hint">' + esc(pipe.hint) + "</p></div>" : "")) +
      (state.running ? runProgressHtml(state.writeProgress, "AI-2 セクション本文作成") :
        (state.writePartial && state.writeProgress && state.writeProgress.aiDone
          ? runProgressHtml(state.writeProgress, "AI-2 未完了（部分結果）")
          : "")) +
      plannerBoardHtml() +
      (selected.length ? "<table><thead><tr><th>Role</th><th>Model</th></tr></thead><tbody>" + roleRows + "</tbody></table>" :
        '<p class="msg err">No models — go to Config.</p>') +
      '<div class="actions"><button class="btn" id="toPlanner">Back</button>' +
      newGenerationBtnHtml() +
      '<button class="btn g" id="runWrite"' + (canRun ? "" : " disabled") +
      ' title="' + esc(sectionsOnly ? "Add a 2nd model in Config" : "Write Japanese content for each section") + '">' +
      esc(writeButtonLabel()) + "</button>" +
      (state.sections.some(function (r) { return String(r.text || "").trim(); })
        ? '<button class="btn g" id="toSections">' +
          (state.writePartial ? "View partial section content" : "View section content") +
          "</button>" : "") +
      "</div></div>";
  }

  function viewSections() {
    var tabs = pageTabs();
    if (!state.sections.length) {
      return '<div class="card"><h2>Sections</h2><p class="lead">Run AI-1 Planner first.</p>' +
        '<div class="actions"><button class="btn g" id="toPlanner">Go to AI-1</button></div></div>';
    }
    state.sectionsPage = ensureActiveInGroup(tabs, state.sectionsPage, state.pageGroup || "nav");
    var shown = sectionsForPage(state.sectionsPage);
    var structureOnly = v2SectionsOnly(state.selected) &&
      !state.sections.some(function (r) { return String(r.text || "").trim(); });
    var panel = '<div class="draft-top"><div><strong>' +
      esc((tabs.filter(function (t) { return t.id === state.sectionsPage; })[0] || {}).label || state.sectionsPage) +
      "</strong><small>" + shown.length + " blocks</small></div>" +
      '<span class="pill ok">' + (structureOnly ? "structure" : "sections") + "</span></div>" +
      '<div class="draft-scroll">' + renderSectionBlocks(shown) + "</div>";
    return '<div class="card"><h2>Sections</h2><p class="lead">' +
      (structureOnly
        ? "Confirm the section map. AI-2 writes each section’s Japanese content in Step 4."
        : "Review section content per page. Use ナビ / SEO / タグ to switch groups.") +
      "</p>" +
      (structureOnly
        ? '<div class="gate-bar ok"><p class="gate-hint">Add a 2nd model in Config, then run Section Content (AI-2).</p></div>'
        : "") +
      plannerBoardHtml() +
      '<div class="actions"><button class="btn" id="' + (structureOnly ? "toPlanner" : "toDraft") + '">Back</button>' +
      newGenerationBtnHtml() +
      '<button class="btn g" id="toExport">' + (structureOnly ? "Download structure" : "Download") + "</button></div></div>" +
      '<div class="draft page-browser-wrap">' +
      pageBrowserHtml({
        rootId: "sectionsPageBrowser",
        tabs: tabs,
        activeId: state.sectionsPage,
        group: state.pageGroup || "nav",
        countFn: function (id) { return sectionsForPage(id).length; },
        panelHtml: panel
      }) +
      "</div>";
  }

  function viewExport() {
    var n = (state.sections || []).length;
    var sheetsOk = !!(window.BbsV2Sheets && window.BbsV2Sheets.isConfigured(state.config));
    var sheetsHint = sheetsOk
      ? "Google Spreadsheet（タブ2つ: AI-1 Sections / AI-2 Contents）→ Drive「" +
        esc((state.config && state.config.google_sheets && state.config.google_sheets.folderName) || "BBS-CMS-LAB") +
        "」"
      : "GOOGLE_CLIENT_ID が未設定です（.env）";
    var reopenBtn = (state.sheetsUrl && !state.exporting)
      ? '<button type="button" class="btn g" id="reopenSheets">Go to spreadsheet</button>'
      : "";
    var exportBtn = (!state.sheetsUrl)
      ? ('<button class="btn g" id="downloadSheets"' + (n && sheetsOk && !state.exporting ? "" : " disabled") +
        ">" + esc(exportButtonLabel()) + "</button>")
      : "";
    return '<div class="card"><h2>Download</h2><p class="lead">Excel / Google Spreadsheet（AI-1 + AI-2 test packs）で出力。</p>' +
      "<p>Rows: <b>" + n + "</b></p>" +
      (state.sessionRestored
        ? '<div class="gate-bar ok"><p class="gate-hint">前回の進捗を復元しました。<b>New generation</b> でクリア。</p></div>'
        : "") +
      '<div class="gate-bar ' + (sheetsOk ? "ok" : "") + '" style="margin-bottom:12px">' +
      '<p class="gate-hint">' + sheetsHint + "</p></div>" +
      (state.exporting ? runProgressHtml(state.exportProgress, "Google Spreadsheet 出力") : "") +
      '<div class="actions"><button class="btn" id="toSections"' + (state.exporting ? " disabled" : "") + ">Back</button>" +
      (state.exporting ? "" : newGenerationBtnHtml()) +
      '<button class="btn g" id="downloadXlsx"' + (n && !state.exporting ? "" : " disabled") + ">Excel (AI-1+AI-2)</button>" +
      '<button class="btn" id="downloadCsv"' + (n && !state.exporting ? "" : " disabled") + ">CSV</button>" +
      exportBtn +
      reopenBtn +
      "</div></div>";
  }

  function bindHearing() {
    var up = document.getElementById("hearingUp");
    if (up) up.onchange = function (e) {
      var f = e.target.files && e.target.files[0];
      if (f) uploadHearing(f).catch(function (err) { msg(err.message, false); });
      e.target.value = "";
    };
    var drop = document.getElementById("hearingDrop");
    if (drop) {
      drop.addEventListener("dragover", function (e) { e.preventDefault(); drop.classList.add("drag"); });
      drop.addEventListener("dragleave", function () { drop.classList.remove("drag"); });
      drop.addEventListener("drop", function (e) {
        e.preventDefault(); drop.classList.remove("drag");
        var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) uploadHearing(f).catch(function (err) { msg(err.message, false); });
      });
    }
  }

  function bindNav() {
    var m = {
      toPlanner: ["planner", 2], toHearing: ["hearing", 1], toDraft: ["draft", 3],
      toSections: ["sections", 4], toExport: ["export", 5]
    };
    Object.keys(m).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.onclick = function () { go(m[id][0], m[id][1]); };
    });
    var runPlanner = document.getElementById("runPlanner");
    if (runPlanner) runPlanner.onclick = runPlannerJob;
    var runWrite = document.getElementById("runWrite");
    if (runWrite) runWrite.onclick = runWriteStream;
    bindPageBrowser("promptPageBrowser", function (pick) {
      if (pick.group) {
        state.pageGroup = pick.group;
        var tabs = (promptSectionsCatalog().tabs || []);
        state.promptPage = ensureActiveInGroup(tabs, state.promptPage, state.pageGroup);
      }
      if (pick.id) state.promptPage = pick.id;
      draw();
    });
    bindPageBrowser("sectionsPageBrowser", function (pick) {
      if (pick.group) {
        state.pageGroup = pick.group;
        state.sectionsPage = ensureActiveInGroup(pageTabs(), state.sectionsPage, state.pageGroup);
      }
      if (pick.id) state.sectionsPage = pick.id;
      draw();
    });
    var dlCsv = document.getElementById("downloadCsv");
    if (dlCsv) dlCsv.onclick = downloadCsv;
    var dlXlsx = document.getElementById("downloadXlsx");
    if (dlXlsx) dlXlsx.onclick = downloadXlsx;
    var dlSheets = document.getElementById("downloadSheets");
    if (dlSheets) dlSheets.onclick = downloadGoogleSheets;
    var reopen = document.getElementById("reopenSheets");
    if (reopen) reopen.onclick = openExportedSpreadsheet;
    var ng = document.getElementById("newGeneration");
    if (ng) ng.onclick = confirmNewGeneration;
  }

  function draw() {
    var stepIds = { config: 1, hearing: 1, planner: 1, draft: 1, sections: 1, export: 1 };
    if (!stepIds[state.step]) state.step = "config";
    try {
      stepper();
      var view = document.getElementById("view");
      if (!view) return;
      var renderer = {
        config: viewConfig,
        hearing: viewHearing,
        planner: viewPlanner,
        draft: viewDraft,
        sections: viewSections,
        export: viewExport
      }[state.step];
      view.innerHTML = typeof renderer === "function" ? renderer() : viewConfig();
      bindConfig();
      bindHearing();
      bindNav();
    } catch (err) {
      state.step = "config";
      state.showAdvanced = false;
      var viewEl = document.getElementById("view");
      if (viewEl) {
        viewEl.innerHTML = '<div class="card"><h2>Config</h2><p class="lead">UI recovered after a render error.</p>' +
          '<p class="msg err">' + esc((err && err.message) || String(err)) + "</p>" +
          '<div class="actions"><button class="btn g" id="saveConfig">Save &amp; continue</button></div></div>';
      }
      try { bindConfig(); } catch (e2) { /* ignore */ }
      msg((err && err.message) || "UI render failed", false);
    }
  }

  async function uploadHearingText(text, filename) {
    var res = await fetch(api("/v2/lab/hearing/parse"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csv_text: text })
    });
    var data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Parse failed");
    state.hearing = data.hearing;
    state.hearingFile = filename || "upload.csv";
    state.blueprint = null;
    state.sections = [];
    state.promptSections = null;
    if (!isLabHearing(state.hearing)) msg("This hearing type is not supported in this lab.", false);
    else msg("Hearing loaded.", true);
    go("hearing", 1);
  }

  async function uploadHearing(file) {
    await uploadHearingText(await file.text(), file.name);
  }

  async function runPlannerJob() {
    if (!state.hearing) return;
    var gate = configGateError(state.selected || [], collectPastedKeys(), "nav");
    if (gate) {
      msg(gate, false);
      go("config", 0);
      return;
    }
    if (!(state.selected || []).length) {
      msg("Select model #1 (AI-1 Sections Planner) in Config.", false);
      go("config", 0);
      return;
    }
    state.planning = true;
    state.planningProgress = {
      index: 0, total: 0, aiTotal: 0, soft_pct: 0, chars_total: 0, page: "", phase: "",
      label: "AI-1 接続中…", active: [], log: ["接続中…"], startedAt: Date.now()
    };
    draw();
    startProgressTimer();
    try {
      var res = await fetch(api("/v2/lab/blueprint/stream"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hearing: state.hearing, model_ids: state.selected })
      });
      if (!res.ok || !res.body) {
        var errBody = {};
        try { errBody = await res.json(); } catch (e) {}
        throw new Error(errBody.detail || ("HTTP " + res.status));
      }
      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buf = "";
      var data = null;
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += decoder.decode(chunk.value, { stream: true });
        var parts = buf.split("\n\n");
        buf = parts.pop() || "";
        parts.forEach(function (block) {
          var line = block.split("\n").find(function (l) { return l.indexOf("data:") === 0; });
          if (!line) return;
          var ev;
          try { ev = JSON.parse(line.slice(5).trim()); } catch (e) { return; }
          if (ev.type === "hello") {
            state.planningProgress.label = ev.label || "AI-1 接続中…";
            msg(state.planningProgress.label, true);
            patchLiveProgress();
          } else if (ev.type === "start") {
            // Bar = AI pages only. Reject stale servers that still count templates.
            var startTotal = ev.llm_pages != null ? ev.llm_pages : (ev.total || 0);
            var schemaOk = ev.progress_schema === "ai_chars_v1" || ev.progress_schema === "ai_only_v1";
            if (!schemaOk && ev.all_pages && startTotal === ev.all_pages) {
              pushProgressLog(state.planningProgress,
                "警告: サーバーが古い進捗形式です。デモを再起動してください。");
            }
            state.planningProgress.index = 0;
            state.planningProgress.total = startTotal;
            state.planningProgress.aiTotal = startTotal;
            state.planningProgress.soft_pct = 0;
            state.planningProgress.chars_total = 0;
            state.planningProgress.label = ev.label || "AI計画を開始します";
            state.planningProgress.active = [];
            pushProgressLog(state.planningProgress, state.planningProgress.label);
            if (ev.template_pages != null) {
              pushProgressLog(state.planningProgress,
                "テンプレート " + ev.template_pages + "ページは即時適用（進捗バー対象外）");
            }
            msg(state.planningProgress.label, true);
            patchLiveProgress();
          } else if (ev.type === "page") {
            var aiTotal = (ev.llm_total != null ? ev.llm_total
              : (ev.progress_kind === "ai_sections" ? ev.total : null));
            if (aiTotal == null || aiTotal <= 0) {
              aiTotal = state.planningProgress.aiTotal || state.planningProgress.total || 0;
            }
            // Ignore inflated totals from stale API (e.g. 36/38 templates counted).
            if (state.planningProgress.aiTotal && aiTotal > state.planningProgress.aiTotal) {
              aiTotal = state.planningProgress.aiTotal;
            }
            var aiDone = (ev.llm_done != null ? ev.llm_done : ev.index) || 0;
            if (ev.phase === "template") {
              aiDone = 0;
            }
            if (aiTotal && aiDone > aiTotal) {
              aiDone = aiTotal;
            }
            state.planningProgress.index = aiDone;
            state.planningProgress.total = aiTotal;
            state.planningProgress.aiTotal = aiTotal || state.planningProgress.aiTotal;
            state.planningProgress.page = ev.page || "";
            state.planningProgress.phase = ev.phase || "";
            state.planningProgress.active = ev.active || [];
            state.planningProgress.label = ev.label || "";
            if (ev.soft_pct != null) state.planningProgress.soft_pct = ev.soft_pct;
            else if (aiTotal) state.planningProgress.soft_pct = Math.round(1000 * aiDone / aiTotal) / 10;
            if (ev.chars_total != null) state.planningProgress.chars_total = ev.chars_total;
            if (ev.chars_display != null) state.planningProgress.chars_display = ev.chars_display;
            else if (ev.chars_total != null) state.planningProgress.chars_display = ev.chars_total;
            if (ev.chars != null) state.planningProgress.chars = ev.chars;
            // Stream/wait ticks update the bar only — keep log for milestones.
            if (ev.phase !== "llm_stream" && ev.phase !== "llm_wait") {
              pushProgressLog(state.planningProgress, state.planningProgress.label);
            }
            msg(state.planningProgress.label, true);
            patchLiveProgress();
          } else if (ev.type === "pulse") {
            var act = (state.planningProgress.active || []).join("、");
            var left = Math.max(0, (state.planningProgress.total || 0) - (state.planningProgress.index || 0));
            var waitLabel = ev.label ||
              (act
                ? ("AI応答待ち: " + act + "（残り " + left + "）")
                : ("AI応答待ち… 残り " + left + "ページ"));
            state.planningProgress.label = waitLabel;
            msg(waitLabel + " · 経過 " + formatElapsed(Date.now() - state.planningProgress.startedAt), true);
            patchLiveProgress();
          } else if (ev.type === "done") {
            data = ev;
            state.planningProgress.index = state.planningProgress.total || state.planningProgress.index;
            state.planningProgress.soft_pct = 100;
            state.planningProgress.active = [];
            state.planningProgress.label = "AI-1 完了 — 結果を反映中";
            pushProgressLog(state.planningProgress, state.planningProgress.label);
            patchLiveProgress();
          } else if (ev.type === "error") {
            throw new Error(ev.detail || "Blueprint failed");
          }
        });
      }
      if (!data || !data.blueprint) throw new Error("Blueprint stream ended without result");
      assertBlueprintNav(data);
      state.blueprint = syncBlueprintStats(data.blueprint, data.sections || []);
      state.sections = data.sections || [];
      state.promptSections = data.prompt_sections || null;
      if (state.promptSections && state.promptSections.tabs && state.promptSections.tabs.length) {
        state.promptPage = state.promptSections.tabs[0].id || "home";
      }
      var st = state.blueprint.stats || {};
      msg("AI-1 complete — " + state.sections.length + " rows · " +
        (st.nav_pages || 0) + " nav · " +
        (st.write_pages != null ? st.write_pages + " AI-2 section-content pages" : "stats ok"), true);
      go("planner", 2);
    } catch (err) { msg(err.message, false); }
    finally {
      stopProgressTimer();
      state.planning = false;
      state.planningProgress = { index: 0, total: 0, page: "", phase: "", label: "", active: [], log: [], startedAt: 0 };
      try { await loadConfig(); } catch (e) { /* ignore */ }
      draw();
    }
  }

  async function runWriteStream() {
    if (v2SectionsOnly(state.selected)) {
      msg("1 model — section map only. Add a 2nd model in Config for AI-2 section content.", false);
      go("config", 0);
      return;
    }
    var gate = configGateError(state.selected, collectPastedKeys(), "nav");
    if (gate) { msg(gate, false); go("config", 0); return; }
    if (!state.blueprint) { msg("Run AI-1 first.", false); return; }
    if (blueprintLooksStale(state.blueprint, state.sections)) {
      msg("Re-run AI-1 Planner — " + staleBlueprintReason(state.blueprint, state.sections), false);
      go("planner", 2);
      return;
    }
    state.running = true;
    state.writePartial = false;
    state.writeProgress = {
      kind: "write",
      index: 0, total: 0, aiTotal: 0, aiDone: 0, page: "", label: "AI-2 セクション本文 接続中…",
      active: [], log: ["各セクションの本文作成を開始します"], startedAt: Date.now(),
      soft_pct: 0, chars_display: 0, partial: false
    };
    go("draft", 3);
    startProgressTimer();
    msg("AI-2 writing section content…", true);
    var writeFinished = false;
    try {
      var res = await fetch(api("/v2/lab/write/stream"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hearing: state.hearing, blueprint: state.blueprint,
          model_ids: state.selected, use_lab_prompt: true, mode: "production"
        })
      });
      if (!res.ok || !res.body) {
        var err = {}; try { err = await res.json(); } catch (e) {}
        throw new Error(err.detail || ("HTTP " + res.status));
      }
      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buf = "";
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += decoder.decode(chunk.value, { stream: true });
        var parts = buf.split("\n\n");
        buf = parts.pop() || "";
        parts.forEach(function (block) {
          var line = block.trim();
          if (!line.startsWith("data:")) return;
          var ev = JSON.parse(line.slice(5).trim());
          if (ev.type === "start") {
            state.writeProgress.total = ev.total || (ev.pages || []).length || 0;
            state.writeProgress.aiTotal = ev.ai_pages || state.writeProgress.aiTotal || 0;
            state.writeProgress.aiDone = 0;
            if (ev.soft_pct != null) state.writeProgress.soft_pct = ev.soft_pct;
            else state.writeProgress.soft_pct = 0;
            state.writeProgress.label = ev.label || ("セクション本文開始 — AI " +
              (state.writeProgress.aiTotal || state.writeProgress.total) + "ページ");
            pushProgressLog(state.writeProgress, state.writeProgress.label);
            msg(state.writeProgress.label, true);
            patchLiveProgress();
          }
          if (ev.type === "stage") {
            state.writeProgress.page = ev.page || "";
            state.writeProgress.index = (ev.index != null) ? ev.index : state.writeProgress.index;
            state.writeProgress.total = ev.total || state.writeProgress.total;
            if (ev.ai_pages != null) state.writeProgress.aiTotal = ev.ai_pages;
            if (ev.ai_done != null) state.writeProgress.aiDone = ev.ai_done;
            state.writeProgress.active = ev.page ? [ev.page] : [];
            state.writeProgress.label = ev.label || ("作成中: " + (ev.page || ""));
            state.writeProgress.chars_display = 0;
            if (ev.soft_pct != null) state.writeProgress.soft_pct = ev.soft_pct;
            else if (state.writeProgress.aiTotal > 0) {
              state.writeProgress.soft_pct = Math.round(
                1000 * (state.writeProgress.aiDone || 0) / state.writeProgress.aiTotal
              ) / 10;
            }
            pushProgressLog(state.writeProgress, state.writeProgress.label);
            msg(state.writeProgress.label, true);
            patchLiveProgress();
          }
          if (ev.type === "heartbeat") {
            state.writeProgress.page = ev.page || state.writeProgress.page;
            state.writeProgress.index = (ev.index != null) ? ev.index : state.writeProgress.index;
            state.writeProgress.total = ev.total || state.writeProgress.total;
            if (ev.ai_pages != null) state.writeProgress.aiTotal = ev.ai_pages;
            if (ev.ai_done != null) state.writeProgress.aiDone = ev.ai_done;
            state.writeProgress.active = ev.page ? [ev.page] : state.writeProgress.active;
            state.writeProgress.label = ev.label || state.writeProgress.label;
            if (ev.soft_pct != null) state.writeProgress.soft_pct = ev.soft_pct;
            if (ev.chars != null) state.writeProgress.chars_display = ev.chars;
            patchLiveProgress();
          }
          if (ev.type === "page_done") {
            if (ev.sections && ev.page) {
              Object.keys(ev.sections).forEach(function (sid) {
                state.sections.forEach(function (row) {
                  if (String(row.page_slug || row.page_id) === String(ev.page) && row.section_id === sid) {
                    row.text = ev.sections[sid];
                  }
                });
              });
            }
            state.writeProgress.index = (ev.index != null) ? ev.index : ((state.writeProgress.index || 0) + 1);
            state.writeProgress.total = ev.total || state.writeProgress.total;
            if (ev.ai_pages != null) state.writeProgress.aiTotal = ev.ai_pages;
            if (ev.ai_done != null) state.writeProgress.aiDone = ev.ai_done;
            state.writeProgress.page = ev.page || "";
            state.writeProgress.active = [];
            if (ev.soft_pct != null) state.writeProgress.soft_pct = ev.soft_pct;
            else if (state.writeProgress.aiTotal > 0) {
              state.writeProgress.soft_pct = Math.round(
                1000 * (state.writeProgress.aiDone || 0) / state.writeProgress.aiTotal
              ) / 10;
            }
            state.writeProgress.label = ev.label ||
              ("完了: " + (ev.nav_label || ev.page || "") +
                "（AI " + (state.writeProgress.aiDone || 0) + "/" +
                (state.writeProgress.aiTotal || "?") + "）");
            pushProgressLog(state.writeProgress, state.writeProgress.label);
            msg(state.writeProgress.label, true);
            patchLiveProgress();
          }
          if (ev.type === "done") {
            state.sections = ev.sections || state.sections;
            state.blueprint = ev.blueprint || state.blueprint;
            state.writeProgress.index = state.writeProgress.total || state.writeProgress.index;
            if (ev.ai_done != null) state.writeProgress.aiDone = ev.ai_done;
            if (ev.ai_pages != null) state.writeProgress.aiTotal = ev.ai_pages;
            state.writeProgress.soft_pct = (ev.soft_pct != null) ? ev.soft_pct : 100;
            state.writeProgress.label = "Section content complete in " + (ev.speed_sec || "?") + "s";
            state.writePartial = false;
            writeFinished = true;
            pushProgressLog(state.writeProgress, state.writeProgress.label);
            msg(state.writeProgress.label, true);
            patchLiveProgress();
          }
          if (ev.type === "error") {
            if (ev.sections) state.sections = ev.sections;
            if (ev.ai_done != null) state.writeProgress.aiDone = ev.ai_done;
            if (ev.ai_pages != null) state.writeProgress.aiTotal = ev.ai_pages;
            if (ev.index != null) state.writeProgress.index = ev.index;
            if (ev.total != null) state.writeProgress.total = ev.total;
            if (ev.soft_pct != null) state.writeProgress.soft_pct = ev.soft_pct;
            state.writeProgress.partial = true;
            state.writePartial = true;
            var doneHint = "AI本文 " + (state.writeProgress.aiDone || 0) + "/" +
              (state.writeProgress.aiTotal || "?");
            state.writeProgress.partialHint = doneHint + " まで完了。再実行で続きを生成できます。";
            state.writeProgress.label = ev.label || ("中断 — " + doneHint);
            pushProgressLog(state.writeProgress, state.writeProgress.label);
            var errMsg = ev.detail || "Write failed";
            if (ev.page) errMsg = ev.page + ": " + errMsg;
            throw new Error(errMsg + " (" + doneHint + ")");
          }
        });
      }
      if (writeFinished) go("sections", 4);
      else if (state.writeProgress.aiDone > 0) {
        state.writePartial = true;
        msg("Stream ended early — partial content saved (" +
          (state.writeProgress.aiDone || 0) + "/" + (state.writeProgress.aiTotal || "?") +
          " AI pages). Use View partial section content or retry.", false);
      }
    } catch (err) {
      state.writePartial = true;
      var m = err && err.message ? err.message : "Write failed";
      if (/network|failed to fetch|load failed/i.test(m)) {
        m = "Network interrupted during AI-2 (" +
          ((state.writeProgress && state.writeProgress.aiDone) || 0) + "/" +
          ((state.writeProgress && state.writeProgress.aiTotal) || "?") +
          " AI pages). Partial content may still be available — retry when Ready.";
      }
      msg(m, false);
    } finally {
      stopProgressTimer();
      state.running = false;
      // Keep last progress snapshot when partial so the user sees N/M, not a wipe to 0.
      if (!state.writePartial) {
        state.writeProgress = { index: 0, total: 0, page: "", label: "", active: [], log: [], startedAt: 0 };
      } else {
        state.writeProgress.partial = true;
        state.writeProgress.active = [];
      }
      try { await loadConfig(); } catch (e) { /* keep chips stale rather than fail */ }
      draw();
    }
  }

  function exportBody(format) {
    var cfg = state.config || {};
    var tid = String((state.hearing && state.hearing.production_type) ||
      (state.blueprint && state.blueprint.production_type) || "type3");
    var slot = (cfg.type_prompts && cfg.type_prompts[tid]) || {};
    return {
      blueprint: state.blueprint,
      sections: state.sections,
      format: format || "packs",
      hearing: state.hearing || {},
      hearing_file: state.hearingFile || "",
      hearing_url: "",
      model_ids: (state.selected || []).slice(0, 2),
      planner_system_prompt: slot.planner_system_prompt || cfg.planner_system_prompt || "",
      system_prompt: slot.system_prompt || cfg.system_prompt || ""
    };
  }

  async function downloadCsv() {
    var res = await fetch(api("/v2/lab/export"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(exportBody("csv"))
    });
    var data = await res.json();
    if (!res.ok || !data.csv) { msg("Export failed", false); return; }
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([data.csv], { type: "text/csv;charset=utf-8" }));
    a.download = (state.blueprint.site_name || "site") + "-sections.csv";
    a.click();
  }

  async function downloadXlsx() {
    if (!(state.sections || []).length) {
      msg("No sections to export — run AI-1 / Section Content first.", false);
      return;
    }
    var res = await fetch(api("/v2/lab/export"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(exportBody("xlsx"))
    });
    var data = await res.json();
    if (!res.ok || !data.xlsx_base64) {
      msg((data && data.xlsx_error) || "Excel export failed", false);
      return;
    }
    var bin = atob(data.xlsx_base64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([bytes], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }));
    a.download = (state.blueprint.site_name || "site") + "-AI1-AI2-packs.xlsx";
    a.click();
    msg("Downloaded AI-1 + AI-2 Excel packs", true);
  }

  function openExportedSpreadsheet() {
    if (!state.sheetsUrl) {
      msg("No spreadsheet URL yet — run Google Spreadsheet export first.", false);
      return;
    }
    if (state.sheetTabRef && !state.sheetTabRef.closed) {
      try {
        state.sheetTabRef.focus();
        return;
      } catch (e) { /* open a new tab below */ }
    }
    var w = null;
    try { w = window.open(state.sheetsUrl, "_blank", "noopener"); } catch (e2) { w = null; }
    if (w) {
      state.sheetTabRef = w;
      return;
    }
    var a = document.createElement("a");
    a.href = state.sheetsUrl;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function downloadGoogleSheets() {
    if (!window.BbsV2Sheets) {
      msg("Google Sheets script not loaded — hard refresh.", false);
      return;
    }
    if (!window.BbsV2Sheets.isConfigured(state.config)) {
      msg("GOOGLE_CLIENT_ID is not set in .env", false);
      return;
    }
    if (!(state.sections || []).length) {
      msg("No sections to export — run AI-1 / Section Content first.", false);
      return;
    }
    if (!window.BbsV2Sheets.exportTestPacks) {
      msg("Sheets script outdated — hard refresh (Ctrl+Shift+R).", false);
      return;
    }
    if (state.exporting) return;

    state.exporting = true;
    state.exportProgress = {
      index: 0,
      total: 0,
      page: "",
      label: "Export packs 準備中…",
      active: [],
      log: [],
      startedAt: Date.now(),
      soft_pct: 0,
      kind: "export"
    };
    draw();
    startProgressTimer();
    try {
      var packRes = await fetch(api("/v2/lab/export"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(exportBody("packs"))
      });
      var packData = await packRes.json();
      if (!packRes.ok || !packData.packs) {
        throw new Error((packData && packData.detail) || "Failed to build AI-1/AI-2 packs");
      }
      var result = await window.BbsV2Sheets.exportTestPacks({
        config: state.config,
        packs: packData.packs,
        title: (state.blueprint && state.blueprint.site_name ? state.blueprint.site_name : "site") +
          "-AI1-AI2-" + new Date().toISOString().slice(0, 10),
        onProgress: function (p) {
          state.exportProgress.index = p.index || state.exportProgress.index;
          state.exportProgress.total = p.total || state.exportProgress.total;
          state.exportProgress.soft_pct = p.soft_pct != null ? p.soft_pct : state.exportProgress.soft_pct;
          state.exportProgress.label = p.label || state.exportProgress.label;
          state.exportProgress.active = p.active || [];
          state.exportProgress.page = (p.active && p.active[0]) || "";
          pushProgressLog(state.exportProgress, state.exportProgress.label);
          msg(state.exportProgress.label, true);
          patchLiveProgress();
        }
      });
      state.sheetsUrl = result.spreadsheetUrl || "";
      state.exportProgress.soft_pct = 100;
      state.exportProgress.index = state.exportProgress.total || state.exportProgress.index;
      state.exportProgress.label = "完了 — AI-1 + AI-2 packs";
      state.exportProgress.active = [];
      pushProgressLog(state.exportProgress, state.exportProgress.label);
      persistLabSession();
      msg(state.exportProgress.label, true);
      patchLiveProgress();
      if (state.sheetsUrl) {
        var w = null;
        try { w = window.open(state.sheetsUrl, "_blank", "noopener"); } catch (e0) { w = null; }
        state.sheetTabRef = w;
      } else {
        msg("Spreadsheet created but URL missing", false);
      }
    } catch (err) {
      msg((err && err.message) || "Google Spreadsheet export failed", false);
    } finally {
      stopProgressTimer();
      state.exporting = false;
      draw();
    }
  }

  async function init() {
    state.showAdvanced = false;
    var viewBoot = document.getElementById("view");
    if (viewBoot) {
      viewBoot.innerHTML = '<div class="card"><p class="lead">Loading config…</p></div>';
    }
    try {
      await loadConfig();
    } catch (e) {
      msg("Config load failed" + (e && e.message ? (": " + e.message) : ""), false);
    }
    if (window.BbsV2Sheets && window.BbsV2Sheets.preload) {
      window.BbsV2Sheets.preload().catch(function () { /* ignore */ });
    }
    var restored = false;
    try {
      restored = restoreLabSession();
    } catch (e) {
      restored = false;
    }
    state.showAdvanced = false;
    if (restored) {
      msg("前回の進捗を復元しました（" + state.step + "）", true);
    }
    draw();
  }
  init();
})();
