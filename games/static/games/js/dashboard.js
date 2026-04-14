(function () {
  const root = document.getElementById("dashboard-root");
  if (!root) return;

  const csrfInput = document.querySelector("[name=csrfmiddlewaretoken]");
  const csrfToken = csrfInput ? csrfInput.value : "";
  const refreshMs = parseInt(root.dataset.refreshMs || "10000", 10);

  function badgeClass(action) {
    if (action === "hint") return "badge-rec-hint";
    if (action === "monitor") return "badge-rec-monitor";
    return "badge-rec-wait";
  }

  function renderRow(item) {
    const rec = item.recommendation || {};
    const action = rec.action || "wait";
    const badge = badgeClass(action);
    const puzzle = item.current_puzzle || "—";
    return (
      "<tr data-session-id=\"" +
      item.session_id +
      "\">" +
      "<td><a class=\"text-decoration-none\" href=\"/sessions/" +
      item.session_id +
      "/\"><strong>" +
      escapeHtml(item.team) +
      "</strong></a><div class=\"small text-muted\">#" +
      item.session_id +
      "</div></td>" +
      "<td>" +
      escapeHtml(item.room) +
      "</td>" +
      "<td>" +
      escapeHtml(puzzle) +
      "</td>" +
      "<td>" +
      item.elapsed_minutes +
      " min</td>" +
      "<td>" +
      item.hints_given +
      "</td>" +
      "<td><span class=\"font-monospace\">" +
      item.priority_score +
      "</span></td>" +
      "<td><span class=\"badge " +
      badge +
      "\">" +
      escapeHtml(action) +
      "</span><div class=\"small text-muted mt-1\">" +
      escapeHtml(rec.reason || "") +
      "</div></td>" +
      "<td><button type=\"button\" class=\"btn btn-sm btn-outline-primary btn-give-hint\" data-session-id=\"" +
      item.session_id +
      "\">Give hint</button></td>" +
      "</tr>"
    );
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function bindHintButtons(tbody) {
    tbody.querySelectorAll(".btn-give-hint").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const id = btn.getAttribute("data-session-id");
        fetch("/api/sessions/" + id + "/hint/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
          },
          body: JSON.stringify({ auto_suggested: false, hint_text: "GM delivered hint" }),
        })
          .then(function (r) {
            if (!r.ok) throw new Error("Hint failed");
            return r.json();
          })
          .then(function () {
            btn.classList.remove("btn-outline-primary");
            btn.classList.add("btn-success");
            btn.textContent = "Logged";
            setTimeout(function () {
              refresh();
            }, 400);
          })
          .catch(function () {
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
          "<strong>" +
          escapeHtml(o.team) +
          "</strong> — " +
          escapeHtml(o.room) +
          " · hints " +
          o.hints_given +
          " (z=" +
          o.z +
          ")</div>"
        );
      })
      .join("");
  }

  function refresh() {
    fetch("/api/queue/")
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        const tbody = document.querySelector("#dashboard-queue-body");
        if (!tbody) return;
        const items = data.queue || [];
        tbody.innerHTML = items.map(renderRow).join("");
        bindHintButtons(tbody);
        renderFairness(data.fairness, document.getElementById("fairness-outliers"));
      })
      .catch(function () {
        /* ignore transient errors */
      });
  }

  const tbodyInit = document.querySelector("#dashboard-queue-body");
  if (tbodyInit) bindHintButtons(tbodyInit);

  setInterval(refresh, refreshMs);
})();
