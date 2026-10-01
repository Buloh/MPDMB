(function () {
  "use strict";

  function init() {
    var form = document.getElementById("activity-pref-form");
    if (!form) return;
    var tbody = form.querySelector(".activity-pref-rows");
    var tpl = form.querySelector("#activity-pref-empty-row");
    var totalInput = form.querySelector('[name$="-TOTAL_FORMS"]');
    var max = parseInt(form.getAttribute("data-pref-max") || "20", 10);

    function visibleRows() {
      return tbody.querySelectorAll("[data-pref-row]:not([hidden])");
    }

    function nextIndex() {
      return parseInt(totalInput.value, 10) || 0;
    }

    function renameFields(row, index) {
      row.querySelectorAll("input, select, textarea").forEach(function (el) {
        if (el.name) {
          el.name = el.name
            .replace(/pref-__prefix__-/, "pref-" + index + "-")
            .replace(/pref-\d+-/, "pref-" + index + "-");
        }
        if (el.id) {
          el.id = el.id
            .replace(/id_pref-__prefix__-/, "id_pref-" + index + "-")
            .replace(/id_pref-\d+-/, "id_pref-" + index + "-");
        }
      });
    }

    var addBtn = form.querySelector("[data-pref-add]");
    if (addBtn) {
      addBtn.addEventListener("click", function (e) {
        e.preventDefault();
        if (visibleRows().length >= max) {
          window.alert("Nejvýše " + max + " lokalit v šabloně.");
          return;
        }
        var index = nextIndex();
        var node = tpl.content.cloneNode(true);
        var temp = document.createElement("tbody");
        temp.appendChild(node);
        var row = temp.firstElementChild;
        renameFields(row, index);
        var del = row.querySelector('[name$="-DELETE"]');
        if (del) {
          del.value = "";
          del.checked = false;
        }
        tbody.appendChild(row);
        totalInput.value = String(index + 1);
      });
    }

    form.addEventListener("click", function (e) {
      var rem = e.target.closest("[data-pref-remove]");
      if (!rem) return;
      e.preventDefault();
      var row = rem.closest("[data-pref-row]");
      if (!row) return;
      var del = row.querySelector('[name$="-DELETE"]');
      if (del) {
        del.value = "on";
        if (del.type === "checkbox") del.checked = true;
        row.hidden = true;
      } else {
        row.remove();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
