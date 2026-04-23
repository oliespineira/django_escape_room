(function () {
  const root = document.getElementById("dashboard-root");
  if (!root) return;

  function getCsrfToken() {
    const csrfInput = document.querySelector("[name=csrfmiddlewaretoken]");
    if (csrfInput && csrfInput.value) return csrfInput.value;
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  const refreshMs = parseInt(root.dataset.refreshMs || "10000", 10);

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function hintAckFromStorage(sessionId) {
    try {
      const raw = sessionStorage.getItem("eris_last_hint_" + String(sessionId));
      if (!raw) return null;
      const o = JSON.parse(raw);
      if (!o || !o.ts || Date.now() - o.ts > 300000) return null;
      return o;
    } catch (e) {
      return null;
    }
  }

  function renderSessionCard(item) {
    const rec = item.recommendation || {};
    const action = rec.action || "wait";
    const status = item.status || "active";
    const order = item.current_puzzle_order;
    const puzzleName = item.current_puzzle || "NO PUZZLE";
    const puzzleLabel =
      order != null && item.current_puzzle
        ? "#" + order + " · " + escapeHtml(puzzleName).toUpperCase()
        : escapeHtml(puzzleName).toUpperCase();
    const roomCode = "ROOM_" + String(item.session_id);

    let cardClass = "";
    if (status === "active") {
      if (action === "hint") cardClass = "is-critical";
      else if (action === "monitor") cardClass = "is-watch";
      else cardClass = "is-stable";
    } else if (status === "paused") {
      cardClass = "is-paused";
    } else if (status === "pending") {
      cardClass = "is-pending";
    }

    let elapsedDisplay = String(item.elapsed_minutes) + "m";
    if (status === "pending") {
      elapsedDisplay = "--:--";
    }

    let statusChip = "ENDED";
    let puzzleState = "FLOWING";
    if (status === "active") {
      statusChip = action === "hint" ? "STUCK" : action === "monitor" ? "MONITOR" : "IN_PROGRESS";
      puzzleState = item.locked_puzzles_count > 0 ? "LOCKED" : "FLOWING";
    } else if (status === "paused") {
      statusChip = "PAUSED";
      puzzleState = "PAUSED";
    } else if (status === "pending") {
      statusChip = "READY";
      puzzleState = "READY";
    }

    let buttons = "";
    if (status === "pending") {
      buttons =
        '<button type="button" class="btn btn-sm btn-success btn-session-action" ' +
        'data-session-id="' + item.session_id + '" data-action="start">Start</button>';
    } else if (status === "active") {
      buttons =
        '<button type="button" class="btn btn-sm btn-outline-warning btn-session-action me-1" ' +
        'data-session-id="' + item.session_id + '" data-action="pause">Pause</button>' +
        '<button type="button" class="btn btn-sm btn-outline-primary btn-give-hint eris-hint-btn me-1" ' +
        'data-session-id="' + item.session_id + '"' +
        ' title="Log a row in hint_events (FKs to session & puzzle)"' +
        (action !== "hint" ? ' style="opacity:0.45"' : "") +
        ">Send hint</button>" +
        '<button type="button" class="btn btn-sm btn-success btn-session-action me-1" ' +
        'data-session-id="' + item.session_id + '" data-action="complete_puzzle">Puzzle done</button>' +
        '<button type="button" class="btn btn-sm btn-outline-danger btn-session-action" ' +
        'data-session-id="' + item.session_id + '" data-action="end" ' +
        'data-confirm="End session for ' + escapeHtml(item.team) + '?">End</button>';
    } else if (status === "paused") {
      buttons =
        '<button type="button" class="btn btn-sm btn-success btn-session-action me-1" ' +
        'data-session-id="' + item.session_id + '" data-action="start">Resume</button>' +
        '<button type="button" class="btn btn-sm btn-outline-danger btn-session-action" ' +
        'data-session-id="' + item.session_id + '" data-action="end" ' +
        'data-confirm="End session for ' + escapeHtml(item.team) + '?">End</button>';
    }

    let lastHintBlock = "";
    if (item.last_hint && item.last_hint.text) {
      const lhPuzzle = item.last_hint.puzzle || "";
      const lhAt = item.last_hint.at || "";
      const meta = [lhPuzzle, lhAt].filter(Boolean).join(" · ");
      lastHintBlock =
        '<div class="eris-last-hint small mt-2 p-3 rounded border border-success border-2" style="background: rgba(25, 80, 60, 0.35);">' +
        '<div class="text-uppercase fw-bold text-success mb-1" style="font-size: 0.7rem; letter-spacing: 0.04em;">Last message sent to team</div>' +
        '<p class="mb-2 text-break" style="white-space: pre-wrap;">' + escapeHtml(item.last_hint.text) + "</p>" +
        (meta
          ? '<div class="text-muted mb-0" style="font-size: 0.8rem;">' + escapeHtml(meta) + "</div>"
          : "") +
        "</div>";
    }

    return (
      '<article class="eris-session-card ' + cardClass + '" data-session-id="' + item.session_id + '">' +
      '<header class="d-flex justify-content-between align-items-start mb-3">' +
      "<div>" +
      '<div class="eris-room-code">' + roomCode + "</div>" +
      '<a class="eris-room-name" href="/sessions/' + item.session_id + '/">' + escapeHtml(item.room).toUpperCase() + "</a>" +
      "</div>" +
      '<span class="eris-status-chip">' + statusChip + "</span>" +
      "</header>" +
      '<section class="eris-session-panel mb-3">' +
      '<div class="eris-session-panel-row"><span>CURRENT PUZZLE</span><span>STATUS</span></div>' +
      '<div class="eris-session-panel-values"><div class="eris-puzzle-name">' + puzzleLabel + '</div><div class="eris-puzzle-state">' + puzzleState + "</div></div>" +
      "</section>" +
      '<div class="eris-session-metrics mb-3"><div><span>Elapsed</span><strong>' + elapsedDisplay + "</strong></div><div><span>Hint count</span><strong>" + item.hints_given + "</strong></div></div>" +
      '<div class="eris-rec-reason small mb-2">' + escapeHtml(rec.reason || "Session awaiting command.") + "</div>" +
      lastHintBlock +
      "<div class='eris-session-actions'>" + buttons + "</div>" +
      renderHintAckBlock(item.session_id) +
      "</article>"
    );
  }

  function renderHintAckBlock(sessionId) {
    const o = hintAckFromStorage(sessionId);
    if (!o || !o.text) return "";
    const n = o.n != null ? String(o.n) : "—";
    const dbLine =
      o.event_id != null
        ? '<div class="font-monospace small text-info mt-2 pt-2 border-top border-info border-opacity-25">hint_events.id=' +
          escapeHtml(String(o.event_id)) +
          (o.logged_at ? " · " + escapeHtml(String(o.logged_at)) : "") +
          "</div>"
        : "";
    return (
      '<div class="eris-hint-sent-ack alert alert-success border border-2 border-success py-3 px-3 mb-0 mt-2" role="status">' +
      '<div class="fw-bold text-success mb-2">Message sent successfully</div>' +
      '<div class="text-break mb-3" style="white-space:pre-wrap;font-size:0.95rem;">' + escapeHtml(o.text) + "</div>" +
      '<div class="small text-muted">Sent to the room for this run · ' + escapeHtml(n) + " hint(s) total</div>" +
      dbLine +
      "</div>"
    );
  }

  function submitSessionAction(btn) {
    const id = btn.getAttribute("data-session-id");
    const action = btn.getAttribute("data-action");
    const confirmMsg = btn.getAttribute("data-confirm");
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    let body = {};
    if (action === "end") {
      const success = window.confirm("Did the team escape successfully?\n\nOK = Yes\nCancel = No");
      body = { success: success };
    }
    btn.disabled = true;
    btn.textContent = "...";
    const actionPath = action.replace(/_/g, "-");
    fetch("/api/sessions/" + id + "/" + actionPath + "/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        if (!r.ok) {
          return r
            .json()
            .catch(function () {
              return {};
            })
            .then(function (payload) {
              throw new Error(payload.detail || "Action failed");
            });
        }
        const contentType = r.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) return {};
        return r.json().catch(function () {
          return {};
        });
      })
      .then(function () {
        refresh();
      })
      .catch(function (err) {
        btn.disabled = false;
        btn.classList.add("btn-danger");
        btn.textContent = err && err.message ? "Error" : "Error";
      });
  }

  const hintModalState = { btn: null, sessionId: null, roomCode: "", roomName: "" };

  function openHintModal(btn) {
    const id = btn.getAttribute("data-session-id");
    const card = btn.closest(".eris-session-card");
    const roomName = card
      ? (card.querySelector(".eris-room-name") && card.querySelector(".eris-room-name").textContent.trim()) || ""
      : "";
    const roomCode = card
      ? (card.querySelector(".eris-room-code") && card.querySelector(".eris-room-code").textContent.trim()) || "ROOM_" + id
      : "ROOM_" + id;
    hintModalState.btn = btn;
    hintModalState.sessionId = id;
    hintModalState.roomName = roomName;
    hintModalState.roomCode = roomCode;
    const roomLine = document.getElementById("eris-hint-modal-room");
    if (roomLine) {
      roomLine.textContent = roomCode + (roomName ? " · " + roomName : "");
    }
    const sub = document.getElementById("eris-hint-modal-sub");
    if (sub) {
      sub.innerHTML =
        "Inserts one row into <code class='text-info'>hint_events</code> with <code>session_id</code> &rarr; " +
        "<code>GameSession</code> and <code>puzzle_id</code> &rarr; <code>Puzzle</code>; updates " +
        "<code>GameSession.hints_given</code> in the same request.";
    }
    const ta = document.getElementById("eris-hint-body");
    if (ta) ta.value = "";
    updateHintCharCount();
    const modalEl = document.getElementById("eris-hint-modal");
    if (!modalEl || typeof bootstrap === "undefined") {
      window.alert("Could not open hint composer. Reload the page.");
      return;
    }
    const m = bootstrap.Modal.getOrCreateInstance(modalEl);
    m.show();
    function focusTa() {
      if (ta) ta.focus();
      modalEl.removeEventListener("shown.bs.modal", focusTa);
    }
    modalEl.addEventListener("shown.bs.modal", focusTa);
  }

  function updateHintCharCount() {
    const ta = document.getElementById("eris-hint-body");
    const c = document.getElementById("eris-hint-char-count");
    const send = document.getElementById("eris-hint-modal-send");
    if (!ta || !c || !send) return;
    c.textContent = String(ta.value.length);
    send.disabled = ta.value.trim().length < 1;
  }

  function resetHintSendButton() {
    const send = document.getElementById("eris-hint-modal-send");
    if (!send) return;
    send.disabled = false;
    if (window.__erisHintSendDefaultHtml) {
      send.innerHTML = window.__erisHintSendDefaultHtml;
    } else {
      send.innerHTML =
        '<span class="eris-hint-btn-icon" aria-hidden="true"></span> Commit to database &amp; send';
    }
  }

  function sendHintFromModal() {
    const id = hintModalState.sessionId;
    const btn = hintModalState.btn;
    const roomName = hintModalState.roomName;
    const roomCode = hintModalState.roomCode;
    const ta = document.getElementById("eris-hint-body");
    const send = document.getElementById("eris-hint-modal-send");
    if (!ta || !id) return;
    const trimmed = String(ta.value).trim();
    if (!trimmed) return;
    if (send) {
      if (!window.__erisHintSendDefaultHtml) {
        window.__erisHintSendDefaultHtml = send.innerHTML;
      }
      send.disabled = true;
      send.innerHTML =
        '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>INSERT…';
    }
    fetch("/api/sessions/" + id + "/hint/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ auto_suggested: false, hint_text: trimmed }),
    })
      .then(function (r) {
        return r.json().then(function (payload) {
          if (!r.ok) {
            let detail = (payload && (payload.detail || payload.error)) || r.statusText || "Hint failed";
            if (Array.isArray(detail)) {
              detail = detail
                .map(function (d) {
                  return d && d.string ? d.string : String(d);
                })
                .join(" ");
            }
            throw new Error(String(detail));
          }
          return payload;
        });
      })
      .then(function (payload) {
        const shownText = payload.hint_text != null ? payload.hint_text : trimmed;
        const dbMeta = {
          hint_event_id: payload.hint_event_id,
          session_id: payload.session_id,
          puzzle_id: payload.puzzle_id,
          puzzle_name: payload.puzzle_name,
          logged_at: payload.logged_at,
        };
        try {
          sessionStorage.setItem(
            "eris_last_hint_" + String(id),
            JSON.stringify({
              text: shownText,
              n: payload.hints_given,
              ts: Date.now(),
              event_id: payload.hint_event_id,
              logged_at: payload.logged_at,
              puzzle_name: payload.puzzle_name,
            })
          );
        } catch (e) {}
        const modalEl = document.getElementById("eris-hint-modal");
        if (modalEl && typeof bootstrap !== "undefined") {
          const inst = bootstrap.Modal.getInstance(modalEl);
          if (inst) inst.hide();
        }
        resetHintSendButton();
        showGlobalHintToast(
          roomCode,
          roomName,
          payload.hints_given != null ? String(payload.hints_given) : "—",
          shownText,
          dbMeta
        );
        showHintSentOnCard(id, {
          hints_given: payload.hints_given,
          hint_text: shownText,
          hint_event_id: payload.hint_event_id,
          session_id: payload.session_id,
          puzzle_id: payload.puzzle_id,
          puzzle_name: payload.puzzle_name,
          logged_at: payload.logged_at,
        });
        if (btn) {
          btn.textContent = "Sent!";
          btn.classList.remove("btn-danger");
        }
        appendTacticalLogHint(id, roomName, shownText, dbMeta);
        window.setTimeout(function () {
          refresh();
        }, 200);
        window.setTimeout(function () {
          if (btn && !btn.classList.contains("btn-danger")) {
            btn.textContent = "Send hint";
          }
        }, 2500);
      })
      .catch(function (err) {
        resetHintSendButton();
        updateHintCharCount();
        if (btn) {
          btn.classList.add("btn-danger");
          btn.textContent = "Error";
        }
        window.alert(err && err.message ? err.message : "Could not send hint.");
      });
  }

  function submitHint(btn) {
    openHintModal(btn);
  }

  function bindSessionActionButtons(rootEl) {
    if (!rootEl) return;
    if (rootEl.dataset.actionsBound === "1") return;
    rootEl.addEventListener("click", function (event) {
      const sessionBtn = event.target.closest(".btn-session-action");
      if (sessionBtn && rootEl.contains(sessionBtn)) {
        submitSessionAction(sessionBtn);
        return;
      }
      const hintBtn = event.target.closest(".btn-give-hint");
      if (hintBtn && rootEl.contains(hintBtn)) {
        submitHint(hintBtn);
      }
    });
    rootEl.dataset.actionsBound = "1";
  }

  function appendTacticalLogHint(sessionId, roomName, message, dbMeta) {
    const log = document.getElementById("dashboard-tactical-log");
    if (!log) return;
    const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const line = document.createElement("div");
    line.className = "mb-2";
    const head = document.createElement("div");
    head.innerHTML = '<strong class="text-success">[HINT ' + time + "]</strong> " + "ROOM_" + String(sessionId);
    if (roomName) {
      head.appendChild(document.createTextNode(" · " + String(roomName)));
    }
    const body = document.createElement("div");
    body.className = "text-break mt-1 ps-0";
    body.style.maxHeight = "4.5rem";
    body.style.overflow = "auto";
    body.textContent = message;
    line.appendChild(head);
    if (dbMeta && dbMeta.hint_event_id != null) {
      const sub = document.createElement("div");
      sub.className = "font-monospace text-muted";
      sub.style.fontSize = "0.7rem";
      sub.textContent = "hint_events.id=" + String(dbMeta.hint_event_id);
      line.appendChild(sub);
    }
    line.appendChild(body);
    log.insertBefore(line, log.firstChild);
    while (log.children.length > 15) {
      log.removeChild(log.lastChild);
    }
  }

  function showGlobalHintToast(roomCode, roomName, totalHints, message, dbMeta) {
    const el = document.getElementById("eris-hint-toast");
    const meta = document.getElementById("eris-hint-toast-meta");
    const body = document.getElementById("eris-hint-toast-body");
    const title = document.getElementById("eris-hint-toast-title");
    const dbEl = document.getElementById("eris-hint-toast-db");
    if (!el || !meta || !body) return;
    if (title) {
      title.textContent = "Message sent successfully";
    }
    body.textContent = message || "";
    meta.textContent =
      roomCode + (roomName ? " · " + roomName : "") + " · " + totalHints + " hint(s) in DB for this run";
    if (dbEl) {
      if (dbMeta && dbMeta.hint_event_id != null) {
        dbEl.classList.remove("d-none");
        const ts = dbMeta.logged_at
          ? new Date(dbMeta.logged_at).toLocaleString([], { dateStyle: "short", timeStyle: "medium" })
          : "";
        dbEl.textContent =
          "hint_events PK " +
          String(dbMeta.hint_event_id) +
          " · session " +
          String(dbMeta.session_id) +
          " · puzzle: " +
          (dbMeta.puzzle_name || dbMeta.puzzle_id || "—") +
          (ts ? " · " + ts : "");
      } else {
        dbEl.classList.add("d-none");
        dbEl.textContent = "";
      }
    }
    el.classList.add("eris-hint-toast-pop");
    el.classList.remove("d-none");
    window.setTimeout(function () {
      el.classList.remove("eris-hint-toast-pop");
    }, 500);
    try {
      el.scrollIntoView({ block: "nearest" });
    } catch (e) {}
    clearTimeout(window.__erisHintToastTimer);
    window.__erisHintToastTimer = setTimeout(function () {
      el.classList.add("d-none");
    }, 15000);
  }

  (function wireHintToastClose() {
    const btn = document.getElementById("eris-hint-toast-close");
    const el = document.getElementById("eris-hint-toast");
    if (btn && el) {
      btn.addEventListener("click", function () {
        el.classList.add("d-none");
        clearTimeout(window.__erisHintToastTimer);
      });
    }
  })();

  function showHintSentOnCard(sessionId, payload) {
    const card = document.querySelector('.eris-session-card[data-session-id="' + String(sessionId) + '"]');
    if (!card) return;
    const prev = card.querySelector(".eris-hint-sent-ack");
    if (prev) prev.remove();
    const ack = document.createElement("div");
    ack.className = "eris-hint-sent-ack alert alert-success border border-2 border-success py-3 px-3 mb-0 mt-2";
    ack.setAttribute("role", "status");
    const n = payload.hints_given != null ? String(payload.hints_given) : "—";
    const head = document.createElement("div");
    head.className = "fw-bold text-success mb-2";
    head.textContent = "Message sent successfully";
    const msg = document.createElement("div");
    msg.className = "text-break mb-3";
    msg.style.whiteSpace = "pre-wrap";
    msg.style.fontSize = "0.95rem";
    msg.style.lineHeight = "1.45";
    msg.textContent = payload.hint_text || "";
    const sub = document.createElement("div");
    sub.className = "small text-muted";
    sub.textContent = "Sent to the room for this run · " + n + " hint(s) total";
    ack.appendChild(head);
    if (payload.hint_text) ack.appendChild(msg);
    ack.appendChild(sub);
    if (payload.hint_event_id != null) {
      const db = document.createElement("div");
      db.className = "font-monospace small text-info mt-2 pt-2 border-top border-info border-opacity-25";
      db.textContent =
        "Row hint_events.id=" +
        String(payload.hint_event_id) +
        (payload.logged_at ? " · " + String(payload.logged_at) : "");
      ack.appendChild(db);
    }
    const actions = card.querySelector(".eris-session-actions");
    if (actions && actions.parentNode) {
      actions.parentNode.insertBefore(ack, actions.nextSibling);
    } else {
      card.appendChild(ack);
    }
    const hintBtn = card.querySelector(".btn-give-hint");
    if (hintBtn) {
      hintBtn.disabled = false;
      hintBtn.classList.remove("btn-danger");
    }
    const metrics = card.querySelectorAll(".eris-session-metrics strong");
    if (metrics.length >= 2 && payload.hints_given != null) {
      metrics[1].textContent = String(payload.hints_given);
    }
  }

  function renderFairness(fairness, outliersEl) {
    if (!fairness) return;
    const avgEl = document.getElementById("fairness-avg-hints");
    const firstEl = document.getElementById("fairness-first-hint");
    const activeEl = document.getElementById("fairness-active-count");
    if (avgEl) avgEl.textContent = String(fairness.avg_hints_active ?? "—");
    if (firstEl) firstEl.textContent = String(fairness.avg_time_to_first_hint_minutes ?? "—");
    if (activeEl) activeEl.textContent = String(fairness.active_sessions ?? "—");
    if (!outliersEl) return;
    const outliers = fairness.outliers || [];
    if (!outliers.length) {
      outliersEl.innerHTML = '<p class="text-muted small mb-0">No outliers detected.</p>';
      return;
    }
    outliersEl.innerHTML = outliers
      .map(function (o) {
        return (
          '<div class="alert alert-warning py-2 px-3 mb-2 small">' +
          "<strong>" + escapeHtml(o.team) + "</strong> — " +
          escapeHtml(o.room) + " · hints " + o.hints_given +
          " (z=" + o.z + ")</div>"
        );
      })
      .join("");
  }

  function refresh() {
    fetch("/api/queue/")
      .then(function (r) {
        if (r.status === 403 || r.status === 401) {
          window.location.href = "/accounts/login/?next=/dashboard/";
          return;
        }
        return r.json();
      })
      .then(function (data) {
        if (!data) return;
        const cardsRoot = document.querySelector("#dashboard-session-cards");
        if (!cardsRoot) return;
        const items = data.queue || [];
        cardsRoot.innerHTML = items.length
          ? items.map(renderSessionCard).join("")
          : '<div class="text-center text-muted py-5">No sessions yet. <a href="/setup/">Go to Setup</a> to create them.</div>';
        bindSessionActionButtons(cardsRoot);
        renderFairness(data.fairness, document.getElementById("fairness-outliers"));
      })
      .catch(function () {});
  }

  const cardsInit = document.querySelector("#dashboard-session-cards");
  if (cardsInit) bindSessionActionButtons(cardsInit);

  (function initHintModal() {
    const ta = document.getElementById("eris-hint-body");
    const send = document.getElementById("eris-hint-modal-send");
    if (send && !window.__erisHintSendDefaultHtml) {
      window.__erisHintSendDefaultHtml = send.innerHTML;
    }
    if (ta) {
      ta.addEventListener("input", updateHintCharCount);
      ta.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          if (send && !send.disabled) sendHintFromModal();
        }
      });
    }
    if (send) {
      send.addEventListener("click", sendHintFromModal);
    }
    updateHintCharCount();
  })();

  setInterval(refresh, refreshMs);
})();
