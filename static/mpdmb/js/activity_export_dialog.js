(function () {
  "use strict";

  function init() {
    var dialog = document.getElementById("activity-export-dialog");
    if (!dialog) return;

    var pdfBase = dialog.getAttribute("data-pdf-url") || "";
    var xlsxBase = dialog.getAttribute("data-xlsx-url") || "";
    var day = dialog.getAttribute("data-day") || "";
    var workplaceId = dialog.getAttribute("data-workplace") || "";
    var empField = dialog.querySelector("[data-export-employee-field]");
    var empSelect = dialog.querySelector("[data-export-employee]");
    var errEl = dialog.querySelector(".activity-export-error");

    function showError(msg) {
      if (!errEl) return;
      errEl.textContent = msg || "";
      errEl.hidden = !msg;
    }

    function selectedScope() {
      var el = dialog.querySelector('input[name="export_scope"]:checked');
      return el ? el.value : "workplace";
    }

    function selectedFormat() {
      var el = dialog.querySelector('input[name="export_format"]:checked');
      return el ? el.value : "pdf";
    }

    function syncEmployeeField() {
      var isEmp = selectedScope() === "employee";
      if (empField) empField.hidden = !isEmp;
    }

    function buildUrl() {
      var params = new URLSearchParams();
      params.set("day", day);
      if (selectedScope() === "workplace") {
        if (!workplaceId) {
          showError("Chybí pracoviště pro export.");
          return null;
        }
        params.set("workplace", workplaceId);
      } else {
        var empId = empSelect ? empSelect.value : "";
        if (!empId) {
          showError("Vyberte zaměstnance.");
          return null;
        }
        params.set("employee", empId);
        if (workplaceId) params.set("workplace", workplaceId);
      }
      var base = selectedFormat() === "xlsx" ? xlsxBase : pdfBase;
      return base + "?" + params.toString();
    }

    function openDialog(btn) {
      showError("");
      var defaultScope = btn.getAttribute("data-export-default-scope") || "workplace";
      var defaultEmp = btn.getAttribute("data-export-default-employee") || "";
      var scopeWp = dialog.querySelector('input[name="export_scope"][value="workplace"]');
      var scopeEmp = dialog.querySelector('input[name="export_scope"][value="employee"]');
      if (defaultScope === "employee" && scopeEmp && !scopeEmp.disabled) {
        scopeEmp.checked = true;
      } else if (scopeWp && !scopeWp.disabled) {
        scopeWp.checked = true;
      } else if (scopeEmp) {
        scopeEmp.checked = true;
      }
      if (empSelect && defaultEmp) {
        empSelect.value = defaultEmp;
      }
      var fmtPdf = dialog.querySelector('input[name="export_format"][value="pdf"]');
      if (fmtPdf) fmtPdf.checked = true;
      syncEmployeeField();
      if (typeof dialog.showModal === "function") dialog.showModal();
    }

    document.querySelectorAll("[data-activity-open-export]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        openDialog(btn);
      });
    });

    dialog.querySelectorAll('input[name="export_scope"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        showError("");
        syncEmployeeField();
      });
    });

    var closeBtn = dialog.querySelector("[data-activity-close-export]");
    if (closeBtn) {
      closeBtn.addEventListener("click", function (e) {
        e.preventDefault();
        if (typeof dialog.close === "function") dialog.close();
      });
    }

    var submitBtn = dialog.querySelector("[data-activity-export-submit]");
    if (submitBtn) {
      submitBtn.addEventListener("click", function (e) {
        e.preventDefault();
        var url = buildUrl();
        if (!url) return;
        if (selectedFormat() === "pdf") {
          window.open(url, "_blank", "noopener");
        } else {
          window.location.href = url;
        }
        if (typeof dialog.close === "function") dialog.close();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
