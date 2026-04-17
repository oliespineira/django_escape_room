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
        '<button type="button" class="btn btn-sm btn-outline-primary btn-give-hint me-1" ' +
        'data-session-id="' + item.session_id + '"' +
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
      "<div class='eris-session-actions'>" + buttons + "</div>" +
      "</article>"
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

  function submitHint(btn) {
    const id = btn.getAttribute("data-session-id");
    btn.disabled = true;
    fetch("/api/sessions/" + id + "/hint/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ auto_suggested: true }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("Hint failed");
        return r.json();
      })
      .then(function () {
        refresh();
      })
      .catch(function () {
        btn.disabled = false;
        btn.classList.add("btn-danger");
        btn.textContent = "Error";
      });
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

  setInterval(refresh, refreshMs);
})();
