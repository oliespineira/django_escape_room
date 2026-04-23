(function () {
  const axisColor = "rgba(212, 236, 255, 0.92)";
  const gridColor = "rgba(82, 228, 255, 0.14)";
  const legend = {
    labels: {
      color: axisColor,
      boxWidth: 12,
      boxHeight: 12,
      usePointStyle: false,
    },
  };

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
          backgroundColor: "rgba(69, 135, 255, 0.45)",
          borderColor: "rgba(69, 135, 255, 1)",
          borderWidth: 1,
        },
        {
          label: "Avg solve (min)",
          data: actual,
          backgroundColor: "rgba(127, 96, 255, 0.48)",
          borderColor: "rgba(127, 96, 255, 1)",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: legend },
      scales: {
        x: {
          ticks: { color: axisColor, maxRotation: 45, minRotation: 45 },
          grid: { color: gridColor },
        },
        y: {
          beginAtZero: true,
          ticks: { color: axisColor },
          grid: { color: gridColor },
        },
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
            backgroundColor: ["#2e85ff", "#46ecff", "#7f60ff", "#2df194", "#ffc55a"],
            borderColor: "rgba(8, 17, 30, 0.92)",
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { ...legend, position: "bottom" } },
      },
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
            borderColor: "rgba(45, 241, 148, 1)",
            backgroundColor: "rgba(45, 241, 148, 0.18)",
            pointBackgroundColor: "rgba(45, 241, 148, 1)",
            pointBorderColor: "rgba(8, 17, 30, 0.95)",
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: legend },
        scales: {
          x: {
            ticks: { color: axisColor, maxRotation: 0, minRotation: 0 },
            grid: { color: gridColor },
          },
          y: {
            beginAtZero: true,
            ticks: { color: axisColor },
            grid: { color: gridColor },
          },
        },
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
            backgroundColor: "rgba(255, 197, 90, 0.4)",
            borderColor: "rgba(255, 197, 90, 1)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: legend },
        scales: {
          x: {
            ticks: { color: axisColor },
            grid: { color: gridColor },
          },
          y: {
            beginAtZero: true,
            max: 1,
            ticks: { color: axisColor },
            grid: { color: gridColor },
          },
        },
      },
    });
  }
})();
