(function () {
  var root = document.getElementById("modelAnalytics");
  if (!root) return;

  var data = {};
  try {
    data = JSON.parse(root.getAttribute("data-analytics") || "{}");
  } catch (err) {
    console.error(err);
  }

  function fmtPct(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toFixed(1) + "%";
  }

  function fmtNum(value, digits) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toFixed(digits == null ? 2 : digits);
  }

  // Confusion matrix toggle
  var matrix = document.getElementById("confusionMatrix");
  document.querySelectorAll("[data-matrix-mode]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll("[data-matrix-mode]").forEach(function (b) {
        b.classList.toggle("is-on", b === btn);
      });
      if (!matrix) return;
      var mode = btn.getAttribute("data-matrix-mode");
      matrix.querySelectorAll("td[data-count]").forEach(function (cell) {
        cell.textContent =
          mode === "pct" ? cell.getAttribute("data-pct") + "%" : cell.getAttribute("data-count");
      });
    });
  });

  // Charts
  var chartsBuilt = false;
  function buildCharts() {
    if (typeof Chart === "undefined") return false;
    if (chartsBuilt) return true;
    chartsBuilt = true;

    var hunter = "#2F5A45";
    var midnight = "#331832";
    var grape = "#694D75";
    var dusk = "#1B5299";
    var soft = "#5A4063";

    var perf = data.performance || {};
    var headlineEl = document.getElementById("headlineMetricsChart");
    if (headlineEl && perf.available) {
      var values = [
        perf.accuracy_pct,
        perf.precision_pct,
        perf.recall_pct,
        perf.f1_pct
      ].map(function (v) {
        return v == null || Number.isNaN(Number(v)) ? null : Number(v);
      });
      new Chart(headlineEl, {
        type: "bar",
        data: {
          labels: ["Accuracy", "Precision", "Recall", "F1-score"],
          datasets: [
            {
              label: "Held-out %",
              data: values,
              backgroundColor: [
                "rgba(47, 90, 69, 0.85)",
                "rgba(105, 77, 117, 0.85)",
                "rgba(27, 82, 153, 0.85)",
                "rgba(51, 24, 50, 0.8)"
              ],
              borderColor: [hunter, grape, dusk, midnight],
              borderWidth: 1.5,
              borderRadius: 8,
              maxBarThickness: 64
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              enabled: true,
              intersect: true,
              mode: "nearest",
              backgroundColor: midnight,
              titleColor: "#F3EBE3",
              bodyColor: "#F3EBE3",
              padding: 10,
              displayColors: false,
              callbacks: {
                title: function (items) {
                  return items[0] ? items[0].label : "";
                },
                label: function (ctx) {
                  var v = ctx.parsed.y;
                  if (v == null || Number.isNaN(v)) return "No value";
                  return v.toFixed(1) + "%";
                }
              }
            }
          },
          scales: {
            x: {
              ticks: { color: soft, font: { weight: "600" } },
              grid: { display: false }
            },
            y: {
              min: 0,
              max: 100,
              ticks: {
                color: soft,
                callback: function (value) {
                  return value + "%";
                }
              },
              grid: { color: "rgba(51, 24, 50, 0.08)" },
              title: { display: true, text: "Percent", color: soft }
            }
          }
        }
      });
    }

    var history = data.history || {};
    if (history.available) {
      var epochs = history.epochs || [];
      var series = history.series || {};
      var common = {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { labels: { color: soft, boxWidth: 12 } },
          tooltip: { mode: "index", intersect: false }
        },
        scales: {
          x: {
            title: { display: true, text: "Epoch", color: soft },
            ticks: { color: soft, maxTicksLimit: 10 },
            grid: { color: "rgba(51,24,50,0.06)" }
          },
          y: {
            ticks: { color: soft },
            grid: { color: "rgba(51,24,50,0.06)" }
          }
        }
      };

      var accEl = document.getElementById("accuracyChart");
      if (accEl && series.accuracy && series.val_accuracy) {
        new Chart(accEl, {
          type: "line",
          data: {
            labels: epochs,
            datasets: [
              {
                label: "Train accuracy",
                data: series.accuracy,
                borderColor: hunter,
                backgroundColor: "rgba(47,90,69,0.12)",
                tension: 0.25,
                pointRadius: 2
              },
              {
                label: "Val accuracy",
                data: series.val_accuracy,
                borderColor: grape,
                backgroundColor: "rgba(105,77,117,0.12)",
                tension: 0.25,
                pointRadius: 2
              }
            ]
          },
          options: common
        });
      }

      var lossEl = document.getElementById("lossChart");
      if (lossEl && series.loss && series.val_loss) {
        new Chart(lossEl, {
          type: "line",
          data: {
            labels: epochs,
            datasets: [
              {
                label: "Train loss",
                data: series.loss,
                borderColor: hunter,
                backgroundColor: "rgba(47,90,69,0.12)",
                tension: 0.25,
                pointRadius: 2
              },
              {
                label: "Val loss",
                data: series.val_loss,
                borderColor: dusk,
                backgroundColor: "rgba(27,82,153,0.12)",
                tension: 0.25,
                pointRadius: 2
              }
            ]
          },
          options: common
        });
      }
    }
    return true;
  }

  function tryBuildCharts() {
    if (!buildCharts()) setTimeout(tryBuildCharts, 150);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", tryBuildCharts);
  } else {
    tryBuildCharts();
  }

  // Version comparison
  var versions = data.versions || [];
  var byId = {};
  versions.forEach(function (v) {
    byId[v.id] = v;
  });

  function renderCompare() {
    var out = document.getElementById("compareOut");
    var a = byId[(document.getElementById("compareA") || {}).value];
    var b = byId[(document.getElementById("compareB") || {}).value];
    if (!out || !a || !b) return;

    function card(v) {
      var ev = v.evaluation || {};
      return (
        '<article class="ma-compare-card"><h4>' +
        (v.label || v.id) +
        "</h4><dl>" +
        "<dt>Status</dt><dd>" +
        (v.status || "—") +
        "</dd>" +
        "<dt>Accuracy</dt><dd>" +
        fmtPct(ev.accuracy_pct) +
        "</dd>" +
        "<dt>Macro precision</dt><dd>" +
        fmtPct(ev.precision_pct) +
        "</dd>" +
        "<dt>Macro recall</dt><dd>" +
        fmtPct(ev.recall_pct) +
        "</dd>" +
        "<dt>Macro F1</dt><dd>" +
        fmtPct(ev.macro_f1_pct) +
        "</dd>" +
        "<dt>Size</dt><dd>" +
        (v.file_size_mb != null ? v.file_size_mb + " MB" : "—") +
        "</dd>" +
        "<dt>Eval set</dt><dd>" +
        (ev.dataset_note || ev.note || "—") +
        "</dd>" +
        "</dl></article>"
      );
    }

    var warn = "";
    if (!a.comparable || !b.comparable) {
      warn =
        '<div class="ma-compare-warn">One or both versions lack a held-out evaluation report. Numeric ranking is not valid.</div>';
    } else if (a.id === b.id) {
      warn = '<div class="ma-compare-warn">Select two different versions to compare.</div>';
    } else if (
      a.evaluation &&
      b.evaluation &&
      a.evaluation.test_images != null &&
      b.evaluation.test_images != null &&
      a.evaluation.test_images !== b.evaluation.test_images
    ) {
      warn =
        '<div class="ma-compare-warn">These versions report different evaluation sample counts. Treat metric deltas cautiously.</div>';
    } else if (a.comparable && b.comparable && a.evaluation.accuracy_pct != null && b.evaluation.accuracy_pct != null) {
      var delta = Number(a.evaluation.accuracy_pct) - Number(b.evaluation.accuracy_pct);
      warn =
        '<div class="ma-compare-warn" style="background:#e6efe9;color:#1e3a2f">Accuracy difference (A − B): ' +
        (delta >= 0 ? "+" : "") +
        delta.toFixed(1) +
        " pp. Do not promote on accuracy alone.</div>";
    }

    out.innerHTML = card(a) + card(b) + warn;
  }

  ["compareA", "compareB"].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("change", renderCompare);
  });
  renderCompare();

  // Export
  var exportBtn = document.getElementById("exportAnalyticsJson");
  if (exportBtn) {
    exportBtn.addEventListener("click", function () {
      var blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download =
        "model-analytics-" + ((data.overview && data.overview.version) || "export") + ".json";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () {
        URL.revokeObjectURL(url);
      }, 1000);
    });
  }
})();
