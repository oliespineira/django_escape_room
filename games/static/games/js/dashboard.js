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

  function badgeClass(action) {
    if (action === "hint") return "badge-rec-hint";
    if (action === "monitor") return "badge-rec-monitor";
    return "badge-rec-wait";
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderPuzzleCell(item) {
    const order = item.current_puzzle_order;
    const name = item.current_puzzle || "—";
    const title =
      order != null && item.current_puzzle
        ? "#" + order + " - " + escapeHtml(name)
        : escapeHtml(name);
    const available = item.available_puzzles || [];
    const locked = item.locked_puzzles_count || 0;
    let badges = available
      .map(function (n) {
        return '<span class="badge bg-secondary me-1">' + escapeHtml(n) + "</span>";
      })
      .join("");
    if (locked > 0) {
      badges +=
        '<span class="badge bg-light text-muted border">' + locked + " locked</span>";
    }
    const sub = badges.length ? '<div class="small text-muted mt-1">' + badges + "</div>" : "";
    return '<div class="fw-semibold">' + title + "</div>" + sub;
  }

  function renderRow(item) {
    const rec = item.recommendation || {};
    const action = rec.action || "wait";
    const badge = badgeClass(action);
    const status = item.status || "active";

    let rowClass = "";
    if (status === "active") {
      if (action === "hint") rowClass = "table-danger";
      else if (action === "monitor") rowClass = "table-warning";
      else rowClass = "table-success";
    } else if (status === "paused") {
      rowClass = "table-secondary";
    } else if (status === "pending") {
      rowClass = "table-light";
    }

    let elapsedCell = item.elapsed_minutes + " min";
    if (status === "pending") {
      elapsedCell = '<span class="badge bg-secondary">Not started</span>';
    } else if (status === "paused") {
      elapsedCell = '<span class="badge bg-warning text-dark">Paused &mdash; ' + item.elapsed_minutes + " min</span>";
    }

    let recCell = "";
    if (status === "active") {
      recCell =
        '<span class="badge ' + badge + ' fs-6">' +
        (action === "hint" ? "HELP NOW" : action === "monitor" ? "WATCH" : "OK") +
        "</span>" +
        '<div class="small text-muted mt-1">' + escapeHtml(rec.reason || "") + "</div>";
    } else if (status === "pending") {
      recCell = '<span class="text-muted small">Start session to see recommendations</span>';
    } else if (status === "paused") {
      recCell = '<span class="text-muted small">Session paused</span>';
    }

    let buttons = "";
    if (status === "pending") {
      buttons =
        '<button class="btn btn-sm btn-success btn-session-action" ' +
        'data-session-id="' + item.session_id + '" data-action="start">Start</button>';
    } else if (status === "active") {
      buttons =
        '<button class="btn btn-sm btn-outline-warning btn-session-action me-1" ' +
        'data-session-id="' + item.session_id + '" data-action="pause">Pause</button>' +
        '<button class="btn btn-sm btn-outline-primary btn-give-hint me-1" ' +
        'data-session-id="' + item.session_id + '"' +
        (action !== "hint" ? ' style="opacity:0.4"' : "") +
        ">Hint</button>" +
        '<button class="btn btn-sm btn-success btn-session-action me-1" ' +
        'data-session-id="' + item.session_id + '" data-action="complete_puzzle">Puzzle done</button>' +
        '<button class="btn btn-sm btn-outline-danger btn-session-action" ' +
        'data-session-id="' + item.session_id + '" data-action="end" ' +
        'data-confirm="End session for ' + escapeHtml(item.team) + '?">End</button>';
    } else if (status === "paused") {
      buttons =
        '<button class="btn btn-sm btn-success btn-session-action me-1" ' +
        'data-session-id="' + item.session_id + '" data-action="start">Resume</button>' +
        '<button class="btn btn-sm btn-outline-danger btn-session-action" ' +
        'data-session-id="' + item.session_id + '" data-action="end" ' +
        'data-confirm="End session for ' + escapeHtml(item.team) + '?">End</button>';
    }

    return (
      '<tr class="' + rowClass + '" data-session-id="' + item.session_id + '">' +
      '<td><a class="text-decoration-none fw-bold" href="/sessions/' + item.session_id + '/">' +
      escapeHtml(item.team) + '</a><div class="small text-muted">#' + item.session_id + "</div></td>" +
      "<td>" + escapeHtml(item.room) + "</td>" +
      "<td>" + renderPuzzleCell(item) + "</td>" +
      "<td>" + elapsedCell + "</td>" +
      "<td>" + item.hints_given + "</td>" +
      "<td>" + recCell + "</td>" +
      "<td><div class='d-flex gap-1 flex-wrap'>" + buttons + "</div></td>" +
      "</tr>"
    );
  }

  function bindSessionActionButtons(tbody) {
    if (!tbody) return;
    tbody.querySelectorAll(".btn-session-action").forEach(function (btn) {
      btn.addEventListener("click", function () {
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
            window.setTimeout(function () {
              btn.classList.remove("btn-danger");
              btn.textContent = action === "complete_puzzle" ? "Puzzle done" : btn.textContent;
            }, 1200);
          });
      });
    });
  }

  function bindHintButtons(tbody) {
    if (!tbody) return;
    tbody.querySelectorAll(".btn-give-hint").forEach(function (btn) {
      btn.addEventListener("click", function () {
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
      });
    });
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
        const tbody = document.querySelector("#dashboard-queue-body");
        if (!tbody) return;
        const items = data.queue || [];
        tbody.innerHTML = items.map(renderRow).join("");
        bindHintButtons(tbody);
        bindSessionActionButtons(tbody);
        renderFairness(data.fairness, document.getElementById("fairness-outliers"));
      })
      .catch(function () {});
  }

  const tbodyInit = document.querySelector("#dashboard-queue-body");
  if (tbodyInit) bindHintButtons(tbodyInit);
  if (tbodyInit) bindSessionActionButtons(tbodyInit);

  setInterval(refresh, refreshMs);
})();
