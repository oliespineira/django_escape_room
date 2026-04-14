(function () {
  const el = document.getElementById("chart-puzzle-difficulty");
  if (!el || typeof Chart === "undefined") return;

  const labels = JSON.parse(el.dataset.labels || "[]");
  const expected = JSON.parse(el.dataset.expected || "[]");
  const actual = JSON.parse(el.dataset.actual || "[]");

  new Chart(el, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Expected (min)",
          data: expected,
          backgroundColor: "rgba(13, 110, 253, 0.35)",
          borderColor: "rgba(13, 110, 253, 1)",
          borderWidth: 1,
        },
        {
          label: "Avg solve (min)",
          data: actual,
          backgroundColor: "rgba(111, 66, 193, 0.35)",
          borderColor: "rgba(111, 66, 193, 1)",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      scales: {
        x: { ticks: { maxRotation: 45, minRotation: 45 } },
        y: { beginAtZero: true },
      },
    },
  });

  const doughnutEl = document.getElementById("chart-room-success");
  if (doughnutEl) {
    new Chart(doughnutEl, {
      type: "doughnut",
      data: {
        labels: JSON.parse(doughnutEl.dataset.labels || "[]"),
        datasets: [
          {
            data: JSON.parse(doughnutEl.dataset.values || "[]"),
            backgroundColor: ["#0d6efd", "#6610f2", "#6f42c1", "#d63384", "#fd7e14"],
          },
        ],
      },
      options: { responsive: true, plugins: { legend: { position: "bottom" } } },
    });
  }

  const lineEl = document.getElementById("chart-hint-timing");
  if (lineEl) {
    new Chart(lineEl, {
      type: "line",
      data: {
        labels: JSON.parse(lineEl.dataset.labels || "[]"),
        datasets: [
          {
            label: "Hint events",
            data: JSON.parse(lineEl.dataset.values || "[]"),
            fill: true,
            tension: 0.25,
            borderColor: "rgba(25, 135, 84, 1)",
            backgroundColor: "rgba(25, 135, 84, 0.15)",
          },
        ],
      },
      options: {
        responsive: true,
        scales: { y: { beginAtZero: true } },
      },
    });
  }

  const teamEl = document.getElementById("chart-team-size");
  if (teamEl) {
    new Chart(teamEl, {
      type: "bar",
      data: {
        labels: JSON.parse(teamEl.dataset.labels || "[]"),
        datasets: [
          {
            label: "Success rate",
            data: JSON.parse(teamEl.dataset.values || "[]"),
            backgroundColor: "rgba(253, 126, 20, 0.5)",
            borderColor: "rgba(253, 126, 20, 1)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        scales: { y: { beginAtZero: true, max: 1 } },
      },
    });
  }
})();
