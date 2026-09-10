/* Shared lab config UI (from v1). Requires host: api(), esc(), msg(), go(), draw(), state. */
window.BbsLabConfig = (function () {
  async function loadConfig() {
    var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, 15000) : null;
    try {
      var res = await fetch(api("/v2/lab/config"), ctrl ? { signal: ctrl.signal } : undefined);
      if (!res.ok) throw new Error("HTTP " + res.status);
      state.config = await res.json();
      state.selected = (state.config.selected_models || []).slice();
      var san = sanitizeSelectedForKeys(state.selected);
      if (san.swaps.length) {
        state.selected = san.selected;
        state._lastKeySwapHint = san.swaps.map(function (s) {
          return modelLabel(s.from) + " → " + modelLabel(s.to);
        }).join("; ");
      }
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
    // Mark fields used by any paid selected model.
    (selectedIds || []).forEach(function (id) {
      var m = byId[id];
      if (!m || m.pricing !== "paid" || !m.key_field) return;
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
   *  phase "config": need a paste OR an already-saved/.env key (ready).
   *  phase "nav": trust server-ready keys (Hearing / Draft / Run).
   *  Free and paid both accept ready keys — "free" means $0, not "no key".
   */
  function unresolvedKeyFields(selectedIds, pastedKeys, phase) {
    pastedKeys = pastedKeys || {};
    phase = phase || "config";
    return neededKeyFields(selectedIds).filter(function (k) {
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
      var paidMiss = miss.filter(function (k) { return k.paid; });
      if (paidMiss.length) {
        return "Paid model selected — paste API key for: " +
          paidMiss.map(function (k) { return k.label; }).join(", ");
      }
      return "Free model still needs a free API key for: " +
        miss.map(function (k) { return k.label; }).join(", ") +
        ". Or pick GLM Flash / NIM (keys already in .env).";
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
      var mustFree = meta && !meta.paid && !meta.ready && !has;
      if (must || mustFree) inp.classList.add("invalid");
      else inp.classList.remove("invalid");
    });
  }


  function roleBadgeClass(role) {
    var r = String(role || "").toLowerCase();
    if (r.indexOf("writer") === 0) return "role-writer";
    if (r.indexOf("improve") === 0) return "role-improve";
    if (r.indexOf("verifier") === 0) return "role-verifier";
    return "role-unused";
  }

  function roleBadgeHtml(role) {
    return '<span class="badge ' + roleBadgeClass(role) + '">' + esc(role) + "</span>";
  }

  function plannedPipelineBoardHtml(selected) {
    var planned = pipelinePreview(selected || []);
    var lines = [];
    function push(badge, id) {
      if (!id) return;
      lines.push(
        '<div class="pb-row">' + roleBadgeHtml(badge) +
        '<span class="pb-model">' + esc(modelLabel(id)) + "</span>" +
        '<span class="pb-status">running</span></div>'
      );
    }
    if (planned.writer) push("Writer", planned.writer);
    if (planned.polish) push("Improve", planned.polish);
    (runtimeVerifyIds(selected) || []).forEach(function (id, i) {
      var list = runtimeVerifyIds(selected);
      var label = (list.length > 1) ? ("Verifier #" + (i + 1)) : "Verifier";
      push(label, id);
    });
    if (!lines.length) return "";
    return '<div class="pipeline-board">' +
      '<p class="pb-title">Running pipeline</p>' +
      lines.join("") +
      "</div>";
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
    var s = selected || [];
    if (!s.length) {
      return { writer: "", polish: "", verify: [], unused: [], hint: "" };
    }
    if (s.length === 1) {
      return {
        writer: s[0], polish: "", verify: [], unused: [],
        hint: modelLabel(s[0]) + " writes the page (no Improve / Verifier)."
      };
    }
    if (s.length === 2) {
      return {
        writer: s[0], polish: "", verify: [s[1]], unused: [],
        hint: modelLabel(s[0]) + " writes · " + modelLabel(s[1]) + " verifies."
      };
    }
    var verify = s.slice(2, 5);
    var unused = s.slice(5);
    var hint = modelLabel(s[0]) + " writes · " + modelLabel(s[1]) + " improves · " +
      verify.map(modelLabel).join(", ") + (verify.length === 1 ? " verifies." : " verify.");
    if (unused.length) hint += " (extra models skipped)";
    return { writer: s[0], polish: s[1], verify: verify, unused: unused, hint: hint };
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
      // Paid without key: keep so the paste gate still asks for the paid key.
      if (m.pricing === "paid") {
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

  function filteredModels(cfg) {
    var q = String(state.modelQuery || "").trim().toLowerCase();
    var filter = state.modelFilter || "all";
    return (cfg.models || []).filter(function (m) {
      var price = m.pricing === "free" ? "free" : "paid";
      if (filter === "free" && price !== "free") return false;
      if (filter === "paid" && price !== "paid") return false;
      if (!q) return true;
      var hay = [m.name, m.id, m.provider, providerLabel(m), price].join(" ").toLowerCase();
      return hay.indexOf(q) >= 0;
    }).slice().sort(function (a, b) {
      var ap = a.pricing === "free" ? 0 : 1;
      var bp = b.pricing === "free" ? 0 : 1;
      if (ap !== bp) return ap - bp;
      // Newest official GLMs first within paid/free groups.
      var ar = modelRank(a.id);
      var br = modelRank(b.id);
      if (ar !== br) return ar - br;
      return String(a.name || a.id).localeCompare(String(b.name || b.id));
    });
  }

  function modelRank(id) {
    var order = [
      "glm-5.3", "glm-5.2", "glm-5.1", "glm-5-turbo", "glm-5",
      "glm-4.7-flash", "glm-4.5-flash", "nvidia-nemotron-super-49b", "nvidia-minimax-m3",
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

  /** Hover menu: companies first; models appear on company hover (side cascade). */
  function hoverMenuHtml(kind, list, selected) {
    var cos = companiesFor(list);
    var badge = kind === "free" ? "free" : "paid";
    var title = kind === "free" ? "Free models" : "Paid models";
    var placeholder = kind === "free" ? "— Select free model —" : "— Select paid model —";
    var restore = state._megaRestore || {};
    var ddOpen = restore.kind === kind;
    var companies = cos.map(function (p) {
      var items = (list || []).filter(function (m) { return m.provider === p; });
      var models = items.map(function (m) {
        var on = selected.indexOf(m.id) >= 0;
        var ready = modelKeyReady(m);
        var needs = kind === "free" && !ready;
        var label = esc(m.name || m.id) + (needs ? " · needs key → GLM/NIM" : "");
        return '<button type="button" class="' + (on ? "on" : "") +
          (needs ? " needs-key" : "") +
          '" data-pick-model="' + esc(m.id) + '"' +
          (needs ? ' title="No API key yet — will use GLM/NIM from .env instead"' : "") + ">" +
          "<span>" + label + "</span>" +
          (on ? '<span class="pick-check">✓</span>' : "") +
          "</button>";
      }).join("");
      var coOpen = ddOpen && restore.company === p;
      return '<div class="mega-co' + (coOpen ? " open" : "") + '" data-company="' + esc(p) + '">' +
        '<button type="button" class="mega-co-btn" data-company-toggle="' + esc(p) + '">' +
        esc(PROVIDER_LABELS[p] || p) + '<span class="arrow">›</span></button>' +
        '<div class="mega-models">' + (models || '<button type="button" disabled>No models</button>') +
        "</div></div>";
    }).join("");
    return '<div class="pick-box">' +
      '<h3><span class="badge ' + badge + '">' + badge + "</span> " + title + "</h3>" +
      '<div class="mega-dd' + (ddOpen ? " open" : "") + '" data-kind="' + kind + '" id="' + kind + 'MegaDd">' +
      '<button type="button" class="mega-trigger" data-mega-trigger="' + kind + '">' +
      '<span>' + placeholder + '</span><span class="chev">▾</span></button>' +
      '<div class="mega-panel">' +
      (companies || '<div class="key-hint" style="padding:8px">No models</div>') +
      "</div></div></div>";
  }

  var DEFAULT_PROMPT_SECTIONS = {
    tabs: [
      {
        id: "top",
        label: "TOP",
        web_path: "/",
        description: "Production homepage section order for WordPress drafts.",
        items: [
          { id: "hero", label: "Hero", web: "ファーストビュー（店名・キャッチ）", rule: "brand_name・catchcopy・CTA。ヒアリングの店名とキャッチをそのまま。" },
          { id: "about", label: "About", web: "About / 当店について", rule: "コンセプト説明のみ。設備・効果の発明禁止。" },
          { id: "concept", label: "Concept", web: "Concept（ポイント最大3）", rule: "concept / target / tone から最大3点。未記載の設備を足さない。" },
          { id: "greeting", label: "Greeting", web: "ご挨拶 / スタッフ", rule: "スタッフ情報が無いときは書かない（省略）。発明しない。" },
          { id: "menu", label: "Menu", web: "メニュー（料金プレビュー）", rule: "menu の name / duration / price を全件・正確に。" },
          { id: "access", label: "Access", web: "アクセス", rule: "駅・徒歩・住所・電話・営業・定休・支払い・駐車場を省略せず。" },
          { id: "reviews", label: "Reviews", web: "お客様の声", rule: "口コミが無いときは書かない（省略）。発明しない。" },
          { id: "reservation", label: "Reservation", web: "ご予約", rule: "予約方法・電話・営業時間。CTA例: ご予約はこちら。" }
        ]
      },
      {
        id: "service",
        label: "Service",
        web_path: "/service/",
        description: "Production service-page section order for WordPress drafts.",
        items: [
          { id: "hero", label: "Service intro", web: "サービス導入（見出し＋全体説明）", rule: "提供サービスの概要。ヒアリング事実のみ。効果効能の断定禁止。" },
          { id: "services", label: "Service blocks", web: "サービス説明ブロック（メニュー各コース）", rule: "menu 各コースに1ブロック。名前を変えない。料金は原文どおり。" },
          { id: "reservation", label: "Reservation", web: "ご予約", rule: "電話・営業時間・CTA。Menu（料金表）の役割を奪わない。" }
        ]
      }
    ]
  };

  function promptSectionsCatalog() {
    var cfg = state.config || {};
    var fromApi = cfg.prompt_sections;
    if (fromApi && Array.isArray(fromApi.tabs) && fromApi.tabs.length) {
      return fromApi;
    }
    return DEFAULT_PROMPT_SECTIONS;
  }

  function promptSectionItemsHtml(page) {
    var catalog = promptSectionsCatalog();
    var tabs = catalog.tabs || [];
    var tab = null;
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].id === page) { tab = tabs[i]; break; }
    }
    if (!tab) {
      tab = tabs[0] || null;
    }
    if (!tab) {
      return '<p class="prompt-note">No section rules configured.</p>';
    }
    var items = tab.items || [];
    var rows = items.map(function (it, idx) {
      return "<tr>" +
        "<td>" + esc(String(idx + 1)) + "</td>" +
        "<td><strong>" + esc(it.label || it.id) + "</strong><div class=\"pi-web\">" + esc(it.id || "") + "</div></td>" +
        "<td>" + esc(it.web || "") + "</td>" +
        "<td>" + esc(it.rule || "") + "</td>" +
        "</tr>";
    }).join("");
    return '<p class="prompt-note">' + esc(tab.description || "") +
      (tab.web_path ? " · " + esc(tab.web_path) : "") + "</p>" +
      '<div style="overflow:auto">' +
      '<table class="prompt-table">' +
      "<thead><tr><th>#</th><th>Section</th><th>On the website</th><th>AI rule</th></tr></thead>" +
      "<tbody>" + rows + "</tbody></table></div>";
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
    // Paid still needs paste; free without a key is remapped above (no Gemini paste gate).
    var needPaste = needed.filter(function (k) { return k.paid || !k.ready; });
    var prevFilter = state.modelFilter;
    state.modelFilter = "free";
    var freeList = filteredModels(cfg);
    state.modelFilter = "paid";
    var paidList = filteredModels(cfg);
    state.modelFilter = prevFilter || "all";

    var stack = selected.length
      ? '<div class="stack-chips">' + selected.map(function (id, idx) {
          var m = byId[id] || { id: id };
          var price = m.pricing === "paid" ? "paid" : "free";
          var role = roleLabel(selected, idx);
          return '<span class="stack-chip">' +
            '<span class="n">' + (idx + 1) + "</span>" +
            "<b>" + esc(m.name || id) + "</b>" +
            roleBadgeHtml(role) +
            '<span class="badge ' + price + '">' + price + "</span>" +
            '<button type="button" data-remove="' + esc(id) + '" title="Remove" aria-label="Remove">×</button>' +
            "</span>";
        }).join("") + "</div>"
      : '<div class="stack-chips"><span class="empty">None selected — pick from Free or Paid</span></div>';

    function keyRowHtml(k) {
      var draft = state.draftKeys[k.field] || "";
      var modelsForKey = (selected || []).filter(function (id) {
        var m = byId[id];
        return m && m.key_field === k.field;
      }).map(function (id) { return (byId[id] && byId[id].name) || id; });
      var forModels = modelsForKey.length ? modelsForKey.slice(0, 2).join(", ") : "";
      var ph = "Paste " + (k.label || "provider") + " API key only";
      var badge = k.paid
        ? '<span class="badge req">paid key</span>'
        : '<span class="badge req">free key needed</span>';
      var hint = k.paid
        ? "Paid provider key"
        : "Free tier key (no charge) — or choose GLM/NIM which already have keys in .env";
      return '<div class="key-slim-row" style="grid-template-columns:140px 1fr auto;align-items:start">' +
        '<div><span class="kl">' + esc(k.label) + (k.paid ? " *" : "") + "</span>" +
        (forModels ? '<div class="key-hint">For: ' + esc(forModels) + "</div>" : "") +
        '<div class="key-hint">' + esc(hint) + "</div></div>" +
        '<input type="password" data-key="' + esc(k.field) + '"' +
        (k.paid ? ' data-paid="1"' : "") +
        ' aria-required="true" placeholder="' + esc(ph) + '" autocomplete="off" value="' +
        esc(draft) + '">' +
        badge +
        "</div>";
    }

    var keyRows = needPaste.map(keyRowHtml).join("");
    var gateErr = configGateError(selected, Object.assign({}, state.draftKeys), "config");

    return '<div class="card"><h2>Config</h2>' +
      '<p class="lead">How many models you pick decides the jobs:</p>' +
      '<div class="picker-notes">' +
      '<div><b>1 model</b> — <span class="t-writer">#1</span> is <b>Writer</b> only (no Improve / Verifier; ground filter still runs).</div>' +
      '<div><b>2 models</b> — <span class="t-writer">#1</span> is <b>Writer</b>, <span class="t-verifier">#2</span> is <b>Verifier</b>.</div>' +
      '<div><b>3+ models</b> — <span class="t-writer">#1</span> <b>Writer</b>, <span class="t-improve">#2</span> <b>Improve</b> (polishes the draft), <span class="t-verifier">#3–5</span> <b>Verifier</b>.</div>' +
      "</div>" +
      '<div class="dual-pick">' +
      hoverMenuHtml("free", freeList, selected) +
      hoverMenuHtml("paid", paidList, selected) +
      "</div>" +
      '<label style="margin-top:14px">Selected models</label>' +
      '<div id="selectedChips">' + stack + "</div>" +
      (keyRows
        ? '<div class="cred-panel"><h3>API credentials</h3>' +
          '<div class="key-slim" id="keyInputs">' + keyRows + "</div></div>"
        : "") +
      (state._lastKeySwapHint
        ? '<div class="gate-bar ok" id="configSwapBar">' +
          '<div><p class="gate-title">Using ready free models</p>' +
          '<p class="gate-hint">' + esc(state._lastKeySwapHint) +
          " — Gemini Flash is free to call but still needs GEMINI_API_KEY. " +
          "GLM/NIM keys are already in .env.</p></div></div>"
        : "") +
      (gateErr
        ? '<div class="gate-bar bad" id="configGateBar">' +
          '<div><p class="gate-title" id="configGateTitle">Cannot continue yet</p>' +
          '<p class="gate-hint" id="configGateHint">' + esc(gateErr) + "</p></div></div>"
        : '<div class="gate-bar ok hid" id="configGateBar" aria-hidden="true">' +
          '<div><p class="gate-title" id="configGateTitle"></p>' +
          '<p class="gate-hint" id="configGateHint"></p></div></div>') +
      '<details style="margin-top:16px"' + (state.showAdvanced ? " open" : "") + ">" +
      '<summary style="cursor:pointer;font-weight:700">Advanced: prompts</summary>' +
      "<label>System prompt</label><textarea id=\"systemPrompt\">" + esc(cfg.system_prompt) + "</textarea>" +
      "<label>User prompt template (use {hearing})</label><textarea id=\"userPrompt\">" + esc(cfg.user_prompt_template) + "</textarea>" +
      '<p class="prompt-note" style="margin-top:16px">Draft writes <b>all header pages</b> from the hearing (TOP, concept, service, greeting, menu, faq, feature, access, reviews — plus blog/column listing shells). Dynamic blog/feature sub-pages are not generated. Tabs below are for viewing checklists only.</p>' +
      '<div class="prompt-tabs" id="promptTabs">' +
      (promptSectionsCatalog().tabs || []).map(function (t) {
        return '<button type="button" data-prompt-page="' + esc(t.id) + '"' +
          (state.promptPage === t.id ? ' class="on"' : "") + ">" + esc(t.label || t.id) +
          (t.shell ? ' <span class="key-hint">(shell)</span>' : "") +
          "</button>";
      }).join("") +
      "</div>" +
      '<div id="promptSectionItems">' + promptSectionItemsHtml(state.promptPage) + "</div>" +
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

  function toggleModel(id) {
    if (!id) return;
    preserveDraftKeys();
    var idx = state.selected.indexOf(id);
    if (idx >= 0) {
      state.selected.splice(idx, 1);
      state._lastKeySwapHint = "";
      pruneDraftKeysForSelection();
      clearMsg();
      draw();
      return;
    }
    var cfg = state.config || { models: [] };
    var byId = {};
    (cfg.models || []).forEach(function (m) { byId[m.id] = m; });
    var m = byId[id];
    // Free model with no key (typical: Gemini) → use GLM/NIM that already has .env keys.
    if (m && m.pricing !== "paid" && !modelKeyReady(m)) {
      var fb = pickReadyFreeFallback(state.selected);
      if (!fb) {
        msg("No free model with an API key is ready. Add GEMINI_API_KEY or check .env.", false);
        return;
      }
      if (state.selected.indexOf(fb) < 0) state.selected.push(fb);
      state._lastKeySwapHint = modelLabel(id) + " → " + modelLabel(fb);
      pruneDraftKeysForSelection();
      msg(
        modelLabel(id) + " needs a free API key. Using " + modelLabel(fb) +
          " instead (key already in .env). Paste GEMINI_API_KEY to use Gemini.",
        true
      );
      draw();
      return;
    }
    state.selected.push(id);
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
      var sysEl = document.getElementById("systemPrompt");
      var userEl = document.getElementById("userPrompt");
      var body = {
        keys: keys,
        selected_models: state.selected,
        system_prompt: sysEl ? sysEl.value : ((state.config && state.config.system_prompt) || ""),
        user_prompt_template: userEl ? userEl.value : ((state.config && state.config.user_prompt_template) || "")
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
      state.config = await res.json();
      state.selected = (state.config.selected_models || []).slice();
      state.committedSelected = state.selected.slice();
      markAcceptedKeys(state.selected, keys);
      // Clear pasted drafts for keys that are now saved server-side.
      Object.keys(keys).forEach(function (f) {
        if (state.config.keys && state.config.keys[f] && state.config.keys[f].set) {
          delete state.draftKeys[f];
        }
      });
      go("hearing", 1);
      msg("Config saved. Continue with Hearing CSV.", true);
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

  function bindConfig() {
    var save = document.getElementById("saveConfig");
    if (save) save.onclick = saveConfig;
    var promptTabs = document.getElementById("promptTabs");
    if (promptTabs) {
      promptTabs.querySelectorAll("[data-prompt-page]").forEach(function (btn) {
        btn.onclick = function () {
          state.promptPage = btn.getAttribute("data-prompt-page") || "top";
          state.showAdvanced = true;
          draw();
        };
      });
    }
    document.querySelectorAll("[data-mega-trigger]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        var kind = btn.getAttribute("data-mega-trigger");
        var dd = document.getElementById(kind + "MegaDd");
        document.querySelectorAll(".mega-dd.open").forEach(function (el) {
          if (el !== dd) el.classList.remove("open");
        });
        document.querySelectorAll(".mega-co.open").forEach(function (el) {
          el.classList.remove("open");
        });
        if (dd) {
          var willOpen = !dd.classList.contains("open");
          dd.classList.toggle("open");
          rememberMegaOpen(willOpen ? kind : null, "");
        }
      };
    });
    document.querySelectorAll("[data-company-toggle]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        var row = btn.closest(".mega-co");
        if (!row) return;
        var dd = row.closest(".mega-dd");
        var panel = row.parentElement;
        if (panel) {
          panel.querySelectorAll(".mega-co.open").forEach(function (el) {
            if (el !== row) el.classList.remove("open");
          });
        }
        var willOpen = !row.classList.contains("open");
        row.classList.toggle("open");
        rememberMegaOpen(
          dd && dd.getAttribute("data-kind"),
          willOpen ? (row.getAttribute("data-company") || "") : ""
        );
      };
    });
    document.querySelectorAll("[data-pick-model]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        var row = btn.closest(".mega-co");
        var dd = btn.closest(".mega-dd");
        rememberMegaOpen(
          dd && dd.getAttribute("data-kind"),
          row && row.getAttribute("data-company")
        );
        toggleModel(btn.getAttribute("data-pick-model") || "");
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
        document.querySelectorAll(".mega-dd.open").forEach(function (el) {
          el.classList.remove("open");
        });
        document.querySelectorAll(".mega-co.open").forEach(function (el) {
          el.classList.remove("open");
        });
        state._megaRestore = null;
      });
    }
    if (document.getElementById("saveConfig")) refreshConfigGateUi();
  }

  return {
    loadConfig: loadConfig,
    viewConfig: viewConfig,
    bindConfig: bindConfig,
    saveConfig: saveConfig,
    configGateError: configGateError,
    collectPastedKeys: collectPastedKeys,
    refreshConfigGateUi: refreshConfigGateUi,
    pipelinePreview: pipelinePreview,
    roleBadgeHtml: roleBadgeHtml,
    modelLabel: modelLabel,
    promptSectionsCatalog: promptSectionsCatalog,
    promptSectionItemsHtml: promptSectionItemsHtml
  };
})();
