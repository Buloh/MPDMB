(function () {
  "use strict";

  var STORAGE_PREFIX = "mpdmb-att-plan-emp-";

  function initPlanRowToggles() {
    var checks = document.querySelectorAll(".att-plan-emp-check");
    if (!checks.length) return;

    function apply(empId, show) {
      document
        .querySelectorAll('.att-plan-row[data-employee="' + empId + '"]')
        .forEach(function (row) {
          row.hidden = !show;
        });
    }

    checks.forEach(function (input) {
      var empId = input.getAttribute("data-employee");
      if (!empId) return;
      var stored = null;
      try {
        stored = localStorage.getItem(STORAGE_PREFIX + empId);
      } catch (e) {
        stored = null;
      }
      if (stored === "0") {
        input.checked = false;
        apply(empId, false);
      } else {
        input.checked = true;
        apply(empId, true);
      }
      input.addEventListener("change", function () {
        var show = input.checked;
        apply(empId, show);
        try {
          localStorage.setItem(STORAGE_PREFIX + empId, show ? "1" : "0");
        } catch (e) {
          /* ignore */
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPlanRowToggles);
  } else {
    initPlanRowToggles();
  }
})();
