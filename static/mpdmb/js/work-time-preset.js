(function () {
  var preset = document.getElementById("id_wt-preset");
  var statutory = document.getElementById("id_wt-statutory_weekly_minutes");
  var agreed = document.getElementById("id_wt-agreed_weekly_minutes");
  var regime = document.getElementById("id_wt-regime");
  var dailyLabel = document.getElementById("work-time-daily-label");
  if (!preset || !statutory || !agreed) {
    return;
  }

  function formatDecimalHours(minutes) {
    var n = parseInt(minutes, 10);
    if (!Number.isFinite(n) || n < 0) {
      return "—";
    }
    var h = Math.round((n / 60) * 100) / 100;
    var text = h.toFixed(2).replace(/\.?0+$/, "").replace(".", ",");
    return "= " + text + " h";
  }

  function formatHm(minutes) {
    var n = Math.max(0, parseInt(minutes, 10) || 0);
    var wh = Math.floor(n / 60);
    var wm = n % 60;
    return wm ? wh + ":" + String(wm).padStart(2, "0") : String(wh);
  }

  function updateHoursHints() {
    document.querySelectorAll("[data-minutes-hours-for]").forEach(function (el) {
      var input = document.getElementById(el.getAttribute("data-minutes-hours-for"));
      el.textContent = input ? formatDecimalHours(input.value) : "—";
    });
  }

  function updateDailyLabel() {
    if (!dailyLabel) {
      return;
    }
    var agreedMin = parseInt(agreed.value, 10);
    if (!Number.isFinite(agreedMin) || agreedMin < 1) {
      agreedMin = 2400;
    }
    var days = regime && regime.value === "continuous" ? 7 : 5;
    var daily = Math.max(1, Math.floor(agreedMin / days));
    dailyLabel.textContent =
      formatHm(agreedMin) +
      " h/týden → " +
      formatHm(daily) +
      " h/den (÷" +
      days +
      ")";
  }

  function refresh() {
    updateHoursHints();
    updateDailyLabel();
  }

  preset.addEventListener("change", function () {
    var opt = preset.options[preset.selectedIndex];
    if (!opt) {
      return;
    }
    var minutes = opt.getAttribute("data-minutes");
    if (!minutes) {
      return;
    }
    statutory.value = minutes;
    agreed.value = minutes;
    refresh();
  });

  ["input", "change"].forEach(function (evt) {
    statutory.addEventListener(evt, refresh);
    agreed.addEventListener(evt, refresh);
  });
  if (regime) {
    regime.addEventListener("change", refresh);
  }

  refresh();
})();
