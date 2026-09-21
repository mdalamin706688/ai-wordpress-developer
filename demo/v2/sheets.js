/**
 * Google Sheets export — browser GIS OAuth + Drive + multi-tab workbook.
 */
(function (global) {
  var GIS_SRC = "https://accounts.google.com/gsi/client";
  var SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file"
  ].join(" ");
  var SESSION_KEY = "bbs_v2_google_sheets_session_v1";
  var ROOT_FOLDER_NAME = "BBS-CMS-LAB";
  var DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder";
  var DRIVE_SHEET_MIME = "application/vnd.google-apps.spreadsheet";

  /** Machine keys → display headers (client-facing JP) */
  var SECTION_COLUMNS = [
    { key: "site", header: "サイト", width: 140 },
    { key: "group", header: "区分", width: 72 },
    { key: "page_id", header: "ページID", width: 120 },
    { key: "page_slug", header: "スラッグ", width: 140 },
    { key: "page_type", header: "ページ種別", width: 100 },
    { key: "section_id", header: "セクションID", width: 140 },
    { key: "section_label", header: "セクション名", width: 160 },
    { key: "mode", header: "モード", width: 90 },
    { key: "text", header: "本文", width: 420 },
    { key: "seeds", header: "シード", width: 220 }
  ];

  var PAGE_COLUMNS = [
    { key: "group", header: "区分", width: 72 },
    { key: "page_id", header: "ページID", width: 120 },
    { key: "page_slug", header: "スラッグ", width: 160 },
    { key: "page_type", header: "ページ種別", width: 110 },
    { key: "section_count", header: "セクション数", width: 100 },
    { key: "filled_count", header: "本文あり", width: 90 }
  ];

  var GROUP_TABS = [
    { id: "nav", title: "ナビ", match: function (g) { return g === "page" || g === "nav"; }, color: { red: 0.22, green: 0.45, blue: 0.72 } },
    { id: "seo", title: "SEO", match: function (g) { return g === "seo"; }, color: { red: 0.18, green: 0.55, blue: 0.38 } },
    { id: "tag", title: "タグ", match: function (g) { return g === "tag"; }, color: { red: 0.72, green: 0.48, blue: 0.16 } }
  ];

  var TAB_COLORS = {
    overview: { red: 0.35, green: 0.38, blue: 0.42 },
    pages: { red: 0.25, green: 0.52, blue: 0.55 },
    all: { red: 0.42, green: 0.35, blue: 0.55 }
  };

  var gisLoadPromise = null;
  var memorySession = null;

  function getClientId(cfg) {
    return String((cfg && cfg.google_client_id) || "").trim();
  }

  function getFolderId(cfg) {
    return String((cfg && cfg.google_sheets_folder_id) || "").trim() || null;
  }

  function isConfigured(cfg) {
    return !!getClientId(cfg);
  }

  function readSession() {
    if (memorySession && memorySession.expiresAt > Date.now() + 30000) {
      return memorySession;
    }
    try {
      var raw = sessionStorage.getItem(SESSION_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || !parsed.accessToken || !parsed.expiresAt) return null;
      if (parsed.expiresAt <= Date.now() + 30000) {
        sessionStorage.removeItem(SESSION_KEY);
        memorySession = null;
        return null;
      }
      memorySession = parsed;
      return parsed;
    } catch (e) {
      return null;
    }
  }

  function writeSession(session) {
    memorySession = session;
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch (e) { /* ignore */ }
  }

  function clearSession() {
    memorySession = null;
    try { sessionStorage.removeItem(SESSION_KEY); } catch (e) { /* ignore */ }
  }

  function loadGis() {
    if (global.google && global.google.accounts && global.google.accounts.oauth2) {
      return Promise.resolve();
    }
    if (gisLoadPromise) return gisLoadPromise;
    gisLoadPromise = new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[src="' + GIS_SRC + '"]');
      if (existing) {
        existing.addEventListener("load", function () { resolve(); });
        existing.addEventListener("error", function () {
          reject(new Error("Failed to load Google auth script"));
        });
        if (global.google && global.google.accounts && global.google.accounts.oauth2) resolve();
        return;
      }
      var script = document.createElement("script");
      script.src = GIS_SRC;
      script.async = true;
      script.onload = function () { resolve(); };
      script.onerror = function () {
        reject(new Error("Failed to load Google auth script"));
      };
      document.head.appendChild(script);
    });
    return gisLoadPromise;
  }

  function hasSession() {
    return !!readSession();
  }

  function requestAccessToken(clientId, forcePrompt) {
    var existing = readSession();
    if (!forcePrompt && existing) {
      return Promise.resolve(existing.accessToken);
    }
    return loadGis().then(function () {
      if (!global.google || !global.google.accounts || !global.google.accounts.oauth2) {
        throw new Error("Google auth could not initialize");
      }
      return new Promise(function (resolve, reject) {
        var client = global.google.accounts.oauth2.initTokenClient({
          client_id: clientId,
          scope: SCOPES,
          callback: function (response) {
            if (response.error || !response.access_token) {
              reject(new Error(
                response.error_description || response.error || "Google sign-in failed"
              ));
              return;
            }
            var ttl = Math.max(60, Number(response.expires_in) || 3600);
            writeSession({
              accessToken: response.access_token,
              expiresAt: Date.now() + ttl * 1000
            });
            resolve(response.access_token);
          },
          error_callback: function (err) {
            var m = (err && (err.message || err.type)) || "Google sign-in cancelled";
            if (/popup/i.test(String(m))) {
              m = "Google sign-in popup was blocked. Allow popups for this site, then try again.";
            }
            reject(new Error(m));
          }
        });
        client.requestAccessToken({ prompt: forcePrompt ? "consent" : "" });
      });
    });
  }

  function authHeaders(token) {
    return {
      Authorization: "Bearer " + token,
      "Content-Type": "application/json"
    };
  }

  function driveCreate(token, name, mimeType, parentId) {
    var meta = { name: name, mimeType: mimeType };
    if (parentId) meta.parents = [parentId];
    return fetch("https://www.googleapis.com/drive/v3/files?supportsAllDrives=true", {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(meta)
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          throw new Error((data.error && data.error.message) || ("Drive create failed HTTP " + res.status));
        }
        return data.id;
      });
    });
  }

  function ensureRootFolder(token, configuredFolderId) {
    if (configuredFolderId) {
      return fetch(
        "https://www.googleapis.com/drive/v3/files/" + encodeURIComponent(configuredFolderId) +
          "?supportsAllDrives=true&fields=id,name,trashed",
        { headers: { Authorization: "Bearer " + token } }
      ).then(function (res) {
        return res.json().then(function (data) {
          if (res.ok && data && data.id && !data.trashed) return data.id;
          return findOrCreateNamedRoot(token);
        });
      }).catch(function () { return findOrCreateNamedRoot(token); });
    }
    return findOrCreateNamedRoot(token);
  }

  function findOrCreateNamedRoot(token) {
    var q = [
      "mimeType='" + DRIVE_FOLDER_MIME + "'",
      "name='" + ROOT_FOLDER_NAME + "'",
      "'root' in parents",
      "trashed=false"
    ].join(" and ");
    var url = "https://www.googleapis.com/drive/v3/files?fields=files(id,name)&q=" + encodeURIComponent(q);
    return fetch(url, { headers: { Authorization: "Bearer " + token } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var files = (data && data.files) || [];
        if (files.length) return files[0].id;
        return driveCreate(token, ROOT_FOLDER_NAME, DRIVE_FOLDER_MIME, "root");
      });
  }

  function groupLabel(g) {
    var x = String(g || "").toLowerCase();
    if (x === "page" || x === "nav") return "ナビ";
    if (x === "seo") return "SEO";
    if (x === "tag") return "タグ";
    return g || "";
  }

  function cell(v) {
    return String(v == null ? "" : v);
  }

  function filterRows(rows, matcher) {
    return (rows || []).filter(function (r) {
      return matcher(String((r && r.group) || "").toLowerCase());
    });
  }

  function buildPagesFromRows(rows) {
    var map = {};
    var order = [];
    (rows || []).forEach(function (r) {
      var key = [r.group, r.page_id || r.page_slug].join("|");
      if (!map[key]) {
        map[key] = {
          group: groupLabel(r.group),
          page_id: r.page_id || "",
          page_slug: r.page_slug || "",
          page_type: r.page_type || "",
          section_count: 0,
          filled_count: 0
        };
        order.push(key);
      }
      map[key].section_count += 1;
      if (String(r.text || "").trim()) map[key].filled_count += 1;
    });
    return order.map(function (k) { return map[k]; });
  }

  function sectionValues(rows) {
    var headers = SECTION_COLUMNS.map(function (c) { return c.header; });
    var values = [headers];
    (rows || []).forEach(function (row) {
      values.push(SECTION_COLUMNS.map(function (c) {
        if (c.key === "group") return groupLabel(row.group);
        return cell(row[c.key]);
      }));
    });
    return values;
  }

  function pageValues(pages) {
    var headers = PAGE_COLUMNS.map(function (c) { return c.header; });
    var values = [headers];
    (pages || []).forEach(function (p) {
      values.push(PAGE_COLUMNS.map(function (c) { return cell(p[c.key]); }));
    });
    return values;
  }

  function overviewValues(rows, blueprint) {
    var bp = blueprint || {};
    var stats = bp.stats || {};
    var site = bp.site_name || (rows[0] && rows[0].site) || "";
    var now = new Date();
    var pages = buildPagesFromRows(rows);
    var filled = (rows || []).filter(function (r) { return String(r.text || "").trim(); }).length;
    var counts = { nav: 0, seo: 0, tag: 0 };
    pages.forEach(function (p) {
      if (p.group === "ナビ") counts.nav += 1;
      else if (p.group === "SEO") counts.seo += 1;
      else if (p.group === "タグ") counts.tag += 1;
    });

    var prodLabel = bp.production_label || bp.production_type || "";
    if (/サテライトリニューアル|satellite.?renewal|type4/i.test(String(prodLabel))) prodLabel = "Type 4";
    else if (/サテライト|satellite|sateraito|type3/i.test(String(prodLabel))) prodLabel = "Type 3";
    else if (/リニューアル|renewal|type2/i.test(String(prodLabel))) prodLabel = "Type 2";
    else if (/新規|shinki|type1/i.test(String(prodLabel))) prodLabel = "Type 1";
    var meta = [
      ["BBS-CMS · Site Content Export", ""],
      ["サイト名", site],
      ["制作タイプ", prodLabel],
      ["クローンモード", bp.clone_mode || ""],
      ["エクスポート日時", now.toISOString()],
      ["", ""],
      ["集計", ""],
      ["ページ数（合計）", String(pages.length)],
      ["ナビページ", String(counts.nav)],
      ["SEOページ", String(counts.seo)],
      ["タグページ", String(counts.tag)],
      ["セクション行", String((rows || []).length)],
      ["本文あり", String(filled)],
      ["", ""],
      ["このブックの使い方", ""],
      ["Overview", "案件サマリーとタブ説明（このシート）"],
      ["Pages", "ページ一覧（1ページ＝1行）"],
      ["ナビ / SEO / タグ", "区分ごとのセクション本文（制作投入用）"],
      ["All", "全セクションの統合一覧（インポート用）"],
      ["", ""],
      ["注意", "本文列は AI-2（Section Content）出力です。空欄は未生成またはシェルページです。"]
    ];

    var statsKeys = Object.keys(stats);
    if (statsKeys.length) {
      meta.push(["", ""]);
      meta.push(["Blueprint stats", ""]);
      statsKeys.forEach(function (k) {
        meta.push([k, cell(stats[k])]);
      });
    }

    return meta;
  }

  function sheetsBatchUpdate(token, spreadsheetId, requests) {
    if (!requests || !requests.length) return Promise.resolve();
    return fetch(
      "https://sheets.googleapis.com/v4/spreadsheets/" + encodeURIComponent(spreadsheetId) + ":batchUpdate",
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({ requests: requests })
      }
    ).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          throw new Error((data.error && data.error.message) || ("Sheets batchUpdate failed HTTP " + res.status));
        }
        return data;
      });
    });
  }

  function valuesBatchUpdate(token, spreadsheetId, data) {
    return fetch(
      "https://sheets.googleapis.com/v4/spreadsheets/" + encodeURIComponent(spreadsheetId) +
        "/values:batchUpdate",
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({
          valueInputOption: "RAW",
          data: data
        })
      }
    ).then(function (res) {
      return res.json().then(function (body) {
        if (!res.ok) {
          throw new Error((body.error && body.error.message) || ("Sheets values write failed HTTP " + res.status));
        }
        return body;
      });
    });
  }

  function thinBorder() {
    return {
      style: "SOLID",
      width: 1,
      color: { red: 0.75, green: 0.78, blue: 0.82 }
    };
  }

  function allBorders() {
    var b = thinBorder();
    return { top: b, bottom: b, left: b, right: b };
  }

  function formatDataSheetRequests(sheetId, colDefs, dataRowCount, opts) {
    opts = opts || {};
    var titleRows = opts.titleRows || 1;
    var headerRow = titleRows; // 0-based index of header
    var dataStart = headerRow + 1;
    var dataEnd = dataStart + Math.max(0, dataRowCount);
    var colCount = colDefs.length;
    var requests = [];

    // Title banner
    if (titleRows > 0) {
      requests.push({
        mergeCells: {
          range: {
            sheetId: sheetId,
            startRowIndex: 0,
            endRowIndex: 1,
            startColumnIndex: 0,
            endColumnIndex: Math.min(colCount, 4)
          },
          mergeType: "MERGE_ALL"
        }
      });
      requests.push({
        repeatCell: {
          range: {
            sheetId: sheetId,
            startRowIndex: 0,
            endRowIndex: 1,
            startColumnIndex: 0,
            endColumnIndex: colCount
          },
          cell: {
            userEnteredFormat: {
              textFormat: {
                bold: true,
                fontSize: 13,
                fontFamily: "Noto Sans JP",
                foregroundColor: { red: 1, green: 1, blue: 1 }
              },
              horizontalAlignment: "LEFT",
              verticalAlignment: "MIDDLE",
              backgroundColor: { red: 0.12, green: 0.22, blue: 0.36 }
            }
          },
          fields: "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment,backgroundColor)"
        }
      });
      requests.push({
        updateDimensionProperties: {
          range: { sheetId: sheetId, dimension: "ROWS", startIndex: 0, endIndex: 1 },
          properties: { pixelSize: 40 },
          fields: "pixelSize"
        }
      });
    }

    // Header
    requests.push({
      repeatCell: {
        range: {
          sheetId: sheetId,
          startRowIndex: headerRow,
          endRowIndex: headerRow + 1,
          startColumnIndex: 0,
          endColumnIndex: colCount
        },
        cell: {
          userEnteredFormat: {
            textFormat: { bold: true, fontSize: 10, fontFamily: "Noto Sans JP", foregroundColor: { red: 1, green: 1, blue: 1 } },
            horizontalAlignment: "CENTER",
            verticalAlignment: "MIDDLE",
            wrapStrategy: "WRAP",
            backgroundColor: { red: 0.18, green: 0.35, blue: 0.55 },
            borders: allBorders()
          }
        },
        fields: "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment,wrapStrategy,backgroundColor,borders)"
      }
    });
    requests.push({
      updateDimensionProperties: {
        range: { sheetId: sheetId, dimension: "ROWS", startIndex: headerRow, endIndex: headerRow + 1 },
        properties: { pixelSize: 32 },
        fields: "pixelSize"
      }
    });

    // Freeze title + header
    requests.push({
      updateSheetProperties: {
        properties: {
          sheetId: sheetId,
          gridProperties: { frozenRowCount: headerRow + 1 }
        },
        fields: "gridProperties.frozenRowCount"
      }
    });

    // Column widths
    colDefs.forEach(function (c, i) {
      requests.push({
        updateDimensionProperties: {
          range: { sheetId: sheetId, dimension: "COLUMNS", startIndex: i, endIndex: i + 1 },
          properties: { pixelSize: c.width || 120 },
          fields: "pixelSize"
        }
      });
    });

    if (dataRowCount > 0) {
      requests.push({
        repeatCell: {
          range: {
            sheetId: sheetId,
            startRowIndex: dataStart,
            endRowIndex: dataEnd,
            startColumnIndex: 0,
            endColumnIndex: colCount
          },
          cell: {
            userEnteredFormat: {
              textFormat: { fontSize: 10, fontFamily: "Noto Sans JP" },
              verticalAlignment: "TOP",
              wrapStrategy: "WRAP",
              borders: allBorders()
            }
          },
          fields: "userEnteredFormat(textFormat,verticalAlignment,wrapStrategy,borders)"
        }
      });
      requests.push({
        addBanding: {
          bandedRange: {
            range: {
              sheetId: sheetId,
              startRowIndex: dataStart,
              endRowIndex: dataEnd,
              startColumnIndex: 0,
              endColumnIndex: colCount
            },
            rowProperties: {
              firstBandColor: { red: 1, green: 1, blue: 1 },
              secondBandColor: { red: 0.95, green: 0.96, blue: 0.98 }
            }
          }
        }
      });
      requests.push({
        setBasicFilter: {
          filter: {
            range: {
              sheetId: sheetId,
              startRowIndex: headerRow,
              endRowIndex: dataEnd,
              startColumnIndex: 0,
              endColumnIndex: colCount
            }
          }
        }
      });
    }

    if (opts.tabColor) {
      requests.push({
        updateSheetProperties: {
          properties: { sheetId: sheetId, tabColor: opts.tabColor },
          fields: "tabColor"
        }
      });
    }

    return requests;
  }

  function formatOverviewRequests(sheetId, rowCount) {
    var requests = [
      {
        updateSheetProperties: {
          properties: {
            sheetId: sheetId,
            tabColor: TAB_COLORS.overview,
            gridProperties: { frozenRowCount: 1 }
          },
          fields: "tabColor,gridProperties.frozenRowCount"
        }
      },
      {
        repeatCell: {
          range: {
            sheetId: sheetId,
            startRowIndex: 0,
            endRowIndex: 1,
            startColumnIndex: 0,
            endColumnIndex: 2
          },
          cell: {
            userEnteredFormat: {
              textFormat: { bold: true, fontSize: 14, fontFamily: "Noto Sans JP", foregroundColor: { red: 1, green: 1, blue: 1 } },
              backgroundColor: { red: 0.12, green: 0.22, blue: 0.36 },
              verticalAlignment: "MIDDLE"
            }
          },
          fields: "userEnteredFormat(textFormat,backgroundColor,verticalAlignment)"
        }
      },
      {
        mergeCells: {
          range: {
            sheetId: sheetId,
            startRowIndex: 0,
            endRowIndex: 1,
            startColumnIndex: 0,
            endColumnIndex: 2
          },
          mergeType: "MERGE_ALL"
        }
      },
      {
        updateDimensionProperties: {
          range: { sheetId: sheetId, dimension: "COLUMNS", startIndex: 0, endIndex: 1 },
          properties: { pixelSize: 200 },
          fields: "pixelSize"
        }
      },
      {
        updateDimensionProperties: {
          range: { sheetId: sheetId, dimension: "COLUMNS", startIndex: 1, endIndex: 2 },
          properties: { pixelSize: 520 },
          fields: "pixelSize"
        }
      },
      {
        updateDimensionProperties: {
          range: { sheetId: sheetId, dimension: "ROWS", startIndex: 0, endIndex: 1 },
          properties: { pixelSize: 42 },
          fields: "pixelSize"
        }
      }
    ];
    if (rowCount > 1) {
      requests.push({
        repeatCell: {
          range: {
            sheetId: sheetId,
            startRowIndex: 1,
            endRowIndex: rowCount,
            startColumnIndex: 0,
            endColumnIndex: 1
          },
          cell: {
            userEnteredFormat: {
              textFormat: { bold: true, fontSize: 10, fontFamily: "Noto Sans JP" },
              backgroundColor: { red: 0.93, green: 0.95, blue: 0.97 }
            }
          },
          fields: "userEnteredFormat(textFormat,backgroundColor)"
        }
      });
      requests.push({
        repeatCell: {
          range: {
            sheetId: sheetId,
            startRowIndex: 1,
            endRowIndex: rowCount,
            startColumnIndex: 0,
            endColumnIndex: 2
          },
          cell: {
            userEnteredFormat: {
              textFormat: { fontFamily: "Noto Sans JP", fontSize: 10 },
              wrapStrategy: "WRAP",
              verticalAlignment: "TOP",
              borders: allBorders()
            }
          },
          fields: "userEnteredFormat(textFormat,wrapStrategy,verticalAlignment,borders)"
        }
      });
    }
    return requests;
  }

  function buildWorkbookPlan(rows, blueprint) {
    var pages = buildPagesFromRows(rows);
    var tabs = [];
    var overview = overviewValues(rows, blueprint);
    tabs.push({
      title: "Overview",
      kind: "overview",
      values: overview,
      color: TAB_COLORS.overview
    });
    tabs.push({
      title: "Pages",
      kind: "pages",
      values: (function () {
        var v = pageValues(pages);
        return [["Pages · ページ一覧"].concat(PAGE_COLUMNS.slice(1).map(function () { return ""; }))].concat(v);
      })(),
      color: TAB_COLORS.pages,
      colDefs: PAGE_COLUMNS,
      dataCount: pages.length
    });

    GROUP_TABS.forEach(function (g) {
      var subset = filterRows(rows, g.match);
      if (!subset.length) return;
      var body = sectionValues(subset);
      tabs.push({
        title: g.title,
        kind: "sections",
        values: [[g.title + " · セクション本文"].concat(SECTION_COLUMNS.slice(1).map(function () { return ""; }))].concat(body),
        color: g.color,
        colDefs: SECTION_COLUMNS,
        dataCount: subset.length
      });
    });

    var allBody = sectionValues(rows);
    tabs.push({
      title: "All",
      kind: "sections",
      values: [["All · 全セクション"].concat(SECTION_COLUMNS.slice(1).map(function () { return ""; }))].concat(allBody),
      color: TAB_COLORS.all,
      colDefs: SECTION_COLUMNS,
      dataCount: (rows || []).length
    });

    return tabs;
  }

  function setupSheetsStructure(token, spreadsheetId, tabTitles) {
    // Rename Sheet1 → first tab, add remaining tabs
    var requests = [{
      updateSheetProperties: {
        properties: { sheetId: 0, title: tabTitles[0] },
        fields: "title"
      }
    }];
    for (var i = 1; i < tabTitles.length; i++) {
      requests.push({
        addSheet: {
          properties: {
            title: tabTitles[i],
            index: i
          }
        }
      });
    }
    return sheetsBatchUpdate(token, spreadsheetId, requests).then(function (data) {
      var ids = [0];
      var replies = (data && data.replies) || [];
      for (var r = 1; r < replies.length; r++) {
        var added = replies[r] && replies[r].addSheet && replies[r].addSheet.properties;
        ids.push(added ? added.sheetId : null);
      }
      // If any id missing, re-fetch spreadsheet
      if (ids.some(function (x) { return x == null; })) {
        return fetch(
          "https://sheets.googleapis.com/v4/spreadsheets/" + encodeURIComponent(spreadsheetId) +
            "?fields=sheets.properties",
          { headers: { Authorization: "Bearer " + token } }
        ).then(function (res) { return res.json(); }).then(function (meta) {
          var byTitle = {};
          ((meta && meta.sheets) || []).forEach(function (s) {
            byTitle[s.properties.title] = s.properties.sheetId;
          });
          return tabTitles.map(function (t) { return byTitle[t]; });
        });
      }
      return ids;
    });
  }

  /**
   * @param {object} opts
   * @param {object} opts.config
   * @param {Array<object>} opts.rows
   * @param {object} [opts.blueprint]
   * @param {string} [opts.title]
   * @param {function} [opts.onStatus] - legacy string status
   * @param {function} [opts.onProgress] - { index, total, soft_pct, label, phase, active }
   */
  function exportSectionRows(opts) {
    opts = opts || {};
    var cfg = opts.config || {};
    var clientId = getClientId(cfg);
    if (!clientId) {
      return Promise.reject(new Error("GOOGLE_CLIENT_ID is not set in .env"));
    }
    var rows = opts.rows || [];
    if (!rows.length) {
      return Promise.reject(new Error("No section rows to export"));
    }
    var title = String(opts.title || "BBS-CMS sections").replace(/[\\/:*?"<>|]/g, "-").slice(0, 120);
    var onStatus = typeof opts.onStatus === "function" ? opts.onStatus : function () {};
    var onProgress = typeof opts.onProgress === "function" ? opts.onProgress : function () {};
    var plan = buildWorkbookPlan(rows, opts.blueprint || {});
    var stepTotal = 4 + plan.length + 1;
    var stepIndex = 0;

    function emit(label, phase, active) {
      stepIndex += 1;
      var soft = Math.min(99, Math.round((stepIndex / stepTotal) * 1000) / 10);
      var payload = {
        index: stepIndex,
        total: stepTotal,
        soft_pct: soft,
        label: label,
        phase: phase || "",
        active: active || []
      };
      onStatus(label);
      onProgress(payload);
    }

    emit("Google 接続中…", "auth");
    return requestAccessToken(clientId, false).then(function (token) {
      emit("Drive フォルダ準備…", "folder");
      return ensureRootFolder(token, getFolderId(cfg)).then(function (parentId) {
        emit("スプレッドシート作成…", "create");
        return driveCreate(token, title, DRIVE_SHEET_MIME, parentId).then(function (spreadsheetId) {
          emit("タブ構成…", "tabs", plan.map(function (t) { return t.title; }));
          var titles = plan.map(function (t) { return t.title; });
          return setupSheetsStructure(token, spreadsheetId, titles).then(function (sheetIds) {
            var chain = Promise.resolve();
            plan.forEach(function (tab, i) {
              chain = chain.then(function () {
                emit(
                  "書込中: " + tab.title + "（" + (i + 1) + "/" + plan.length + "）",
                  "write",
                  [tab.title]
                );
                return valuesBatchUpdate(token, spreadsheetId, [{
                  range: "'" + tab.title.replace(/'/g, "''") + "'!A1",
                  values: tab.values
                }]);
              });
            });
            return chain.then(function () {
              emit("書式設定…", "format", titles.slice());
              var fmt = [];
              plan.forEach(function (tab, i) {
                var sid = sheetIds[i];
                if (sid == null) return;
                if (tab.kind === "overview") {
                  fmt = fmt.concat(formatOverviewRequests(sid, tab.values.length));
                } else {
                  fmt = fmt.concat(formatDataSheetRequests(sid, tab.colDefs, tab.dataCount || 0, {
                    titleRows: 1,
                    tabColor: tab.color
                  }));
                }
              });
              return sheetsBatchUpdate(token, spreadsheetId, fmt).then(function () {
                onProgress({
                  index: stepTotal,
                  total: stepTotal,
                  soft_pct: 100,
                  label: "完了",
                  phase: "done",
                  active: []
                });
                return {
                  spreadsheetId: spreadsheetId,
                  spreadsheetUrl: "https://docs.google.com/spreadsheets/d/" + spreadsheetId,
                  rowCount: rows.length,
                  tabs: titles
                };
              });
            });
          });
        });
      });
    });
  }

  function formatTestPackSheetRequests(sheetId, rowCount, tabColor) {
    var requests = [];
    var color = tabColor || { red: 0.12, green: 0.22, blue: 0.36 };
    // Title banner
    requests.push({
      mergeCells: {
        range: {
          sheetId: sheetId,
          startRowIndex: 0,
          endRowIndex: 1,
          startColumnIndex: 0,
          endColumnIndex: 3
        },
        mergeType: "MERGE_ALL"
      }
    });
    requests.push({
      repeatCell: {
        range: {
          sheetId: sheetId,
          startRowIndex: 0,
          endRowIndex: 1,
          startColumnIndex: 0,
          endColumnIndex: 3
        },
        cell: {
          userEnteredFormat: {
            textFormat: {
              bold: true,
              fontSize: 13,
              fontFamily: "Noto Sans JP",
              foregroundColor: { red: 1, green: 1, blue: 1 }
            },
            horizontalAlignment: "LEFT",
            verticalAlignment: "MIDDLE",
            backgroundColor: color
          }
        },
        fields: "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment,backgroundColor)"
      }
    });
    requests.push({
      updateDimensionProperties: {
        range: { sheetId: sheetId, dimension: "ROWS", startIndex: 0, endIndex: 1 },
        properties: { pixelSize: 40 },
        fields: "pixelSize"
      }
    });
    // Header row
    requests.push({
      repeatCell: {
        range: {
          sheetId: sheetId,
          startRowIndex: 1,
          endRowIndex: 2,
          startColumnIndex: 0,
          endColumnIndex: 3
        },
        cell: {
          userEnteredFormat: {
            textFormat: { bold: true, fontSize: 10, fontFamily: "Noto Sans JP" },
            backgroundColor: { red: 0.93, green: 0.95, blue: 0.97 }
          }
        },
        fields: "userEnteredFormat(textFormat,backgroundColor)"
      }
    });
    // Column widths
    requests.push({
      updateDimensionProperties: {
        range: { sheetId: sheetId, dimension: "COLUMNS", startIndex: 0, endIndex: 1 },
        properties: { pixelSize: 260 },
        fields: "pixelSize"
      }
    });
    requests.push({
      updateDimensionProperties: {
        range: { sheetId: sheetId, dimension: "COLUMNS", startIndex: 1, endIndex: 2 },
        properties: { pixelSize: 720 },
        fields: "pixelSize"
      }
    });
    requests.push({
      updateDimensionProperties: {
        range: { sheetId: sheetId, dimension: "COLUMNS", startIndex: 2, endIndex: 3 },
        properties: { pixelSize: 180 },
        fields: "pixelSize"
      }
    });
    // Wrap Field labels + Value cells; tall prompt/result rows
    // Do NOT set textFormat on Value column — Result uses textFormatRuns (bold keys).
    if (rowCount > 2) {
      requests.push({
        repeatCell: {
          range: {
            sheetId: sheetId,
            startRowIndex: 2,
            endRowIndex: rowCount,
            startColumnIndex: 0,
            endColumnIndex: 1
          },
          cell: {
            userEnteredFormat: {
              textFormat: { fontFamily: "Noto Sans JP", fontSize: 10 },
              wrapStrategy: "WRAP",
              verticalAlignment: "TOP",
              borders: allBorders()
            }
          },
          fields: "userEnteredFormat(textFormat,wrapStrategy,verticalAlignment,borders)"
        }
      });
      requests.push({
        repeatCell: {
          range: {
            sheetId: sheetId,
            startRowIndex: 2,
            endRowIndex: rowCount,
            startColumnIndex: 1,
            endColumnIndex: 3
          },
          cell: {
            userEnteredFormat: {
              wrapStrategy: "WRAP",
              verticalAlignment: "TOP",
              borders: allBorders()
            }
          },
          fields: "userEnteredFormat(wrapStrategy,verticalAlignment,borders)"
        }
      });
      requests.push({
        repeatCell: {
          range: {
            sheetId: sheetId,
            startRowIndex: 2,
            endRowIndex: rowCount,
            startColumnIndex: 0,
            endColumnIndex: 1
          },
          cell: {
            userEnteredFormat: {
              textFormat: { bold: true, fontSize: 10, fontFamily: "Noto Sans JP" },
              backgroundColor: { red: 0.95, green: 0.96, blue: 0.98 }
            }
          },
          fields: "userEnteredFormat(textFormat,backgroundColor)"
        }
      });
    }
    // Prompt + Result rows (index 7–8 = sheet rows 8–9)
    [7, 8].forEach(function (idx) {
      if (idx < rowCount) {
        requests.push({
          updateDimensionProperties: {
            range: { sheetId: sheetId, dimension: "ROWS", startIndex: idx, endIndex: idx + 1 },
            properties: { pixelSize: 280 },
            fields: "pixelSize"
          }
        });
      }
    });
    if (tabColor) {
      requests.push({
        updateSheetProperties: {
          properties: { sheetId: sheetId, tabColor: tabColor },
          fields: "tabColor"
        }
      });
    }
    return requests;
  }

  function buildTestPackWorkbookPlan(packs) {
    packs = packs || {};
    var ai1 = packs.ai1 || {};
    var ai2 = packs.ai2 || {};
    return [
      {
        title: String(ai1.title || "AI-1 Sections").slice(0, 100),
        kind: "test_pack",
        values: ai1.values || [],
        color: { red: 0.12, green: 0.35, blue: 0.55 },
        dataCount: Math.max(0, ((ai1.values || []).length) - 2)
      },
      {
        title: String(ai2.title || "AI-2 Contents").slice(0, 100),
        kind: "test_pack",
        values: ai2.values || [],
        color: { red: 0.18, green: 0.48, blue: 0.32 },
        dataCount: Math.max(0, ((ai2.values || []).length) - 2)
      }
    ];
  }

  function chunkSheetCellValues(values, maxChars) {
    // Google Sheets rejects any cell over 50_000 characters.
    var limit = Math.max(1000, Math.min(49000, maxChars || 49000));
    var out = [];
    (values || []).forEach(function (row) {
      var field = row && row[0] != null ? String(row[0]) : "";
      var value = row && row[1] != null ? String(row[1]) : "";
      var note = row && row[2] != null ? String(row[2]) : "";
      // Also guard Field/Note columns though Value is the usual offender.
      if (field.length > limit) field = field.slice(0, limit - 20) + "…(truncated)";
      if (note.length > limit) note = note.slice(0, limit - 20) + "…(truncated)";
      if (value.length <= limit) {
        out.push([field, value, note]);
        return;
      }
      var parts = Math.ceil(value.length / limit);
      for (var i = 0; i < parts; i++) {
        var slice = value.slice(i * limit, (i + 1) * limit);
        var label = i === 0
          ? field
          : (field + " cont. " + (i + 1) + "/" + parts);
        out.push([label, slice, i === 0 ? note : "continuation (Sheets 50k cell limit)"]);
      }
    });
    return out;
  }

  function stripPackHeader(values) {
    var rows = values || [];
    if (rows.length >= 2 && String((rows[1] && rows[1][0]) || "") === "Field") {
      return rows.slice(2);
    }
    if (rows.length >= 1 && String((rows[0] && rows[0][0]) || "") === "Field") {
      return rows.slice(1);
    }
    return rows.slice();
  }

  /** Two tabs in one spreadsheet: AI-1 Sections + AI-2 Contents (chunked for 50k). */
  function buildSeparateTestPackTabs(packs) {
    packs = packs || {};
    var ai1 = packs.ai1 || {};
    var ai2 = packs.ai2 || {};
    // Fixed tab titles — never combine into one sheet.
    return [
      {
        title: "AI-1 Sections",
        kind: "test_pack",
        values: chunkSheetCellValues(ai1.values || []),
        color: { red: 0.12, green: 0.35, blue: 0.55 },
        resultRuns: ai1.result_runs || []
      },
      {
        title: "AI-2 Contents",
        kind: "test_pack",
        values: chunkSheetCellValues(ai2.values || []),
        color: { red: 0.18, green: 0.48, blue: 0.32 },
        resultRuns: ai2.result_runs || []
      }
    ];
  }

  function findResultRowIndex(values) {
    var rows = values || [];
    for (var i = 0; i < rows.length; i++) {
      var field = String((rows[i] && rows[i][0]) || "");
      if (field === "Result" || field.indexOf("Result") === 0) return i;
    }
    return -1;
  }

  function mergeOutlineRuns(runs) {
    var merged = [];
    (runs || []).forEach(function (pair) {
      var text = "";
      var bold = false;
      if (Array.isArray(pair)) {
        text = pair[0] != null ? String(pair[0]) : "";
        bold = !!pair[1];
      } else if (pair && typeof pair === "object") {
        text = pair.text != null ? String(pair.text) : "";
        bold = !!pair.bold;
      }
      if (!text) return;
      if (merged.length && merged[merged.length - 1].bold === bold) {
        merged[merged.length - 1].text += text;
      } else {
        merged.push({ text: text, bold: bold });
      }
    });
    return merged;
  }

  function textFormatRunsFromOutline(runs) {
    // Google Sheets textFormatRuns: startIndex + format; next run ends previous.
    var merged = mergeOutlineRuns(runs);
    var out = [];
    var cursor = 0;
    merged.forEach(function (seg) {
      out.push({
        startIndex: cursor,
        format: { bold: !!seg.bold, fontFamily: "Consolas", fontSize: 10 }
      });
      cursor += seg.text.length;
    });
    return { runs: out, plain: merged.map(function (s) { return s.text; }).join("") };
  }

  function formatResultOutlineBoldRequests(sheetId, rowIndex, runs) {
    if (sheetId == null || rowIndex < 0 || !(runs && runs.length)) return [];
    var built = textFormatRunsFromOutline(runs);
    if (!built.runs.length || !built.plain) return [];
    return [{
      updateCells: {
        start: { sheetId: sheetId, rowIndex: rowIndex, columnIndex: 1 },
        rows: [{
          values: [{
            userEnteredValue: { stringValue: built.plain },
            userEnteredFormat: {
              wrapStrategy: "WRAP",
              verticalAlignment: "TOP",
              textFormat: { fontFamily: "Consolas", fontSize: 10, bold: false }
            },
            textFormatRuns: built.runs
          }]
        }],
        fields: "userEnteredValue,userEnteredFormat,textFormatRuns"
      }
    }];
  }

  function writeSheetValuesInChunks(token, spreadsheetId, sheetTitle, values) {
    // Keep each values.batchUpdate payload modest (cell count × size).
    var ROWS_PER_WRITE = 40;
    var safeTitle = "'" + String(sheetTitle).replace(/'/g, "''") + "'";
    var chain = Promise.resolve();
    var rows = values || [];
    for (var start = 0; start < rows.length; start += ROWS_PER_WRITE) {
      (function (from) {
        var chunk = rows.slice(from, from + ROWS_PER_WRITE);
        var a1row = from + 1; // 1-based
        chain = chain.then(function () {
          return valuesBatchUpdate(token, spreadsheetId, [{
            range: safeTitle + "!A" + a1row,
            values: chunk
          }]);
        });
      })(start);
    }
    return chain;
  }

  function assertTwoPackTabs(token, spreadsheetId, expectedTitles) {
    return fetch(
      "https://sheets.googleapis.com/v4/spreadsheets/" + encodeURIComponent(spreadsheetId) +
        "?fields=sheets.properties",
      { headers: { Authorization: "Bearer " + token } }
    ).then(function (res) { return res.json(); }).then(function (meta) {
      var sheets = (meta && meta.sheets) || [];
      var titles = sheets.map(function (s) {
        return s && s.properties && s.properties.title;
      }).filter(Boolean);
      if (titles.length < 2) {
        throw new Error("Google Sheet tab setup failed (need 2 tabs, got " + titles.length + ")");
      }
      expectedTitles.forEach(function (t) {
        if (titles.indexOf(t) < 0) {
          throw new Error("Missing sheet tab: " + t + " (have: " + titles.join(", ") + ")");
        }
      });
      return titles;
    });
  }

  function exportTestPacks(opts) {
    opts = opts || {};
    var cfg = opts.config || {};
    var clientId = getClientId(cfg);
    if (!clientId) {
      return Promise.reject(new Error("GOOGLE_CLIENT_ID is not set in .env"));
    }
    var packs = opts.packs || {};
    if (!packs.ai1 || !packs.ai2) {
      return Promise.reject(new Error("Missing AI-1 / AI-2 export packs"));
    }
    var title = String(opts.title || "BBS-CMS test packs").replace(/[\\/:*?"<>|]/g, "-").slice(0, 120);
    var onStatus = typeof opts.onStatus === "function" ? opts.onStatus : function () {};
    var onProgress = typeof opts.onProgress === "function" ? opts.onProgress : function () {};
    // Same spreadsheet file, TWO separate tabs (never merged).
    var plan = buildSeparateTestPackTabs(packs);
    if (plan.length !== 2) {
      return Promise.reject(new Error("Internal error: expected 2 export tabs"));
    }
    var writeSteps = plan.reduce(function (n, tab) {
      return n + Math.max(1, Math.ceil((tab.values || []).length / 40));
    }, 0);
    var stepTotal = 5 + writeSteps + 1;
    var stepIndex = 0;

    function emit(label, phase, active) {
      stepIndex += 1;
      var soft = Math.min(99, Math.round((stepIndex / stepTotal) * 1000) / 10);
      var payload = {
        index: stepIndex,
        total: stepTotal,
        soft_pct: soft,
        label: label,
        phase: phase || "",
        active: active || []
      };
      onStatus(label);
      onProgress(payload);
    }

    emit("Google 接続中…", "auth");
    return requestAccessToken(clientId, false).then(function (token) {
      emit("Drive フォルダ準備…", "folder");
      return ensureRootFolder(token, getFolderId(cfg)).then(function (parentId) {
        emit("スプレッドシート作成…", "create");
        return driveCreate(token, title, DRIVE_SHEET_MIME, parentId).then(function (spreadsheetId) {
          var titles = plan.map(function (t) { return t.title; });
          emit("タブ構成（AI-1 / AI-2 分離）…", "tabs", titles);
          return setupSheetsStructure(token, spreadsheetId, titles).then(function (sheetIds) {
            return assertTwoPackTabs(token, spreadsheetId, titles).then(function () {
              var chain = Promise.resolve();
              plan.forEach(function (tab, i) {
                chain = chain.then(function () {
                  emit(
                    "書込中: " + tab.title + "（タブ " + (i + 1) + "/2）",
                    "write",
                    [tab.title]
                  );
                  return writeSheetValuesInChunks(token, spreadsheetId, tab.title, tab.values);
                });
              });
              return chain.then(function () {
                emit("書式設定…", "format", titles.slice());
                var fmt = [];
                plan.forEach(function (tab, i) {
                  var sid = sheetIds[i];
                  if (sid == null) return;
                  fmt = fmt.concat(formatTestPackSheetRequests(sid, (tab.values || []).length, tab.color));
                });
                return sheetsBatchUpdate(token, spreadsheetId, fmt).then(function () {
                  // Bold page names + main section keys inside Result outline cells.
                  var boldReqs = [];
                  plan.forEach(function (tab, i) {
                    var sid = sheetIds[i];
                    if (sid == null) return;
                    var ridx = findResultRowIndex(tab.values);
                    boldReqs = boldReqs.concat(
                      formatResultOutlineBoldRequests(sid, ridx, tab.resultRuns)
                    );
                  });
                  var afterBold = boldReqs.length
                    ? sheetsBatchUpdate(token, spreadsheetId, boldReqs)
                    : Promise.resolve();
                  return afterBold.then(function () {
                    onProgress({
                      index: stepTotal,
                      total: stepTotal,
                      soft_pct: 100,
                      label: "完了（AI-1 / AI-2 別タブ）",
                      phase: "done",
                      active: []
                    });
                    return {
                      spreadsheetId: spreadsheetId,
                      spreadsheetUrl: "https://docs.google.com/spreadsheets/d/" + spreadsheetId,
                      rowCount: plan.reduce(function (n, t) { return n + (t.values || []).length; }, 0),
                      tabs: titles
                    };
                  });
                });
              });
            });
          });
        });
      });
    });
  }

  global.BbsV2Sheets = {
    isConfigured: isConfigured,
    hasSession: hasSession,
    clearSession: clearSession,
    exportSectionRows: exportSectionRows,
    exportTestPacks: exportTestPacks,
    preload: loadGis,
    ROOT_FOLDER_NAME: ROOT_FOLDER_NAME
  };
})(window);
