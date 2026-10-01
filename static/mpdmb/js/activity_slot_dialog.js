(function () {
  "use strict";

  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function init() {
    var dialog = document.getElementById("activity-slot-dialog");
    if (!dialog) return;
    var host = dialog.querySelector(".activity-slot-dialog-host");
    var formUrl = dialog.getAttribute("data-form-url") || "";
    var saveUrl = dialog.getAttribute("data-save-url") || "";

    function closeDialog() {
      if (typeof dialog.close === "function") dialog.close();
    }

    function showError(root, msg) {
      var err = root && root.querySelector(".activity-slot-error");
      if (!err) return;
      err.textContent = msg || "Uložení selhalo.";
      err.hidden = false;
    }

    function updateManagement(root) {
      var rows = root.querySelectorAll("[data-slot-row]");
      var total = root.querySelector('[name$="-TOTAL_FORMS"]');
      if (total) total.value = String(rows.length);
    }

    function reindexRows(root) {
      var prefix = "slot";
      var rows = root.querySelectorAll("[data-slot-row]");
      rows.forEach(function (row, index) {
        row.querySelectorAll("input, select, textarea, label").forEach(function (el) {
          ["name", "id", "for"].forEach(function (attr) {
            var val = el.getAttribute(attr);
            if (!val) return;
            el.setAttribute(
              attr,
              val.replace(
                new RegExp(prefix + "-(\\d+|__prefix__)-"),
                prefix + "-" + index + "-"
              )
            );
          });
        });
      });
      updateManagement(root);
    }

    function lastRowEndTime(wrap) {
      var rows = wrap.querySelectorAll("[data-slot-row]");
      var slotStart = wrap.getAttribute("data-slot-start") || "";
      var slotEnd = wrap.getAttribute("data-slot-end") || "";
      var lastTo = "";
      rows.forEach(function (row) {
        var toInput = row.querySelector('[name$="-time_to"]');
        var fromInput = row.querySelector('[name$="-time_from"]');
        if (toInput && toInput.value) {
          lastTo = toInput.value;
        } else if (fromInput && fromInput.value) {
          lastTo = fromInput.value;
        }
      });
      return { lastTo: lastTo, slotStart: slotStart, slotEnd: slotEnd };
    }

    function bindForm(root) {
      var form = root.querySelector(".activity-slot-form");
      if (!form) return;

      var closeBtn = root.querySelector("[data-activity-close-slot]");
      if (closeBtn) {
        closeBtn.addEventListener("click", function (e) {
          e.preventDefault();
          closeDialog();
        });
      }

      var addBtn = root.querySelector("[data-activity-add-row]");
      if (addBtn) {
        addBtn.addEventListener("click", function (e) {
          e.preventDefault();
          var wrap = root.querySelector(".activity-slot-rows");
          var tpl = root.querySelector("#activity-slot-empty-row");
          var max = parseInt(wrap.getAttribute("data-slot-max") || "10", 10);
          if (wrap.querySelectorAll("[data-slot-row]").length >= max) {
            showError(root, "Nejvýše " + max + " činností v hodině.");
            return;
          }
          var times = lastRowEndTime(wrap);
          var node = tpl.content.cloneNode(true);
          var temp = document.createElement("div");
          temp.appendChild(node);
          var newRow = temp.firstElementChild;
          var fromInput = newRow.querySelector('[name$="-time_from"]');
          var toInput = newRow.querySelector('[name$="-time_to"]');
          if (fromInput && toInput) {
            var od = times.lastTo || times.slotStart;
            if (od && times.slotEnd && od >= times.slotEnd) {
              fromInput.value = "";
              toInput.value = "";
            } else {
              fromInput.value = od || "";
              toInput.value = times.slotEnd || "";
            }
          }
          wrap.appendChild(newRow);
          reindexRows(root);
        });
      }

      root.addEventListener("click", function (e) {
        var rem = e.target.closest("[data-activity-remove-row]");
        if (rem) {
          e.preventDefault();
          var row = rem.closest("[data-slot-row]");
          if (row) row.remove();
          reindexRows(root);
          return;
        }
        var del = e.target.closest("[data-activity-delete-item]");
        if (del) {
          e.preventDefault();
          if (!confirm("Smazat tuto činnost?")) return;
          var fd = new FormData();
          fd.append("csrfmiddlewaretoken", csrfToken());
          fd.append("employee", form.querySelector('[name="employee"]').value);
          fd.append("day", form.querySelector('[name="day"]').value);
          fd.append("delete", "1");
          fd.append("item_id", del.getAttribute("data-item-id"));
          fetch(saveUrl, {
            method: "POST",
            body: fd,
            headers: {
              Accept: "application/json",
              "X-CSRFToken": csrfToken(),
            },
            credentials: "same-origin",
          })
            .then(function (res) {
              return res.json().then(function (data) {
                return { ok: res.ok, data: data };
              });
            })
            .then(function (result) {
              if (result.ok && result.data && result.data.ok) {
                var row = del.closest("[data-slot-row]");
                if (row) row.remove();
                reindexRows(root);
                return;
              }
              showError(
                root,
                (result.data && result.data.error) || "Smazání selhalo."
              );
            })
            .catch(function () {
              showError(root, "Síťová chyba při mazání.");
            });
          return;
        }
        var clear = e.target.closest("[data-activity-clear-slot]");
        if (clear) {
          e.preventDefault();
          if (!confirm("Vymazat všechny činnosti v této hodině?")) return;
          root.querySelectorAll("[data-slot-row]").forEach(function (r) {
            r.remove();
          });
          reindexRows(root);
          form.requestSubmit();
        }
      });

      form.addEventListener("submit", function (e) {
        e.preventDefault();
        reindexRows(root);
        var fd = new FormData(form);
        fetch(saveUrl || form.action, {
          method: "POST",
          body: fd,
          headers: {
            Accept: "application/json",
            "X-CSRFToken": csrfToken(),
          },
          credentials: "same-origin",
        })
          .then(function (res) {
            return res.json().then(function (data) {
              return { ok: res.ok, data: data };
            });
          })
          .then(function (result) {
            if (result.ok && result.data && result.data.ok) {
              closeDialog();
              window.location.reload();
              return;
            }
            showError(
              root,
              (result.data && result.data.error) || "Uložení selhalo."
            );
          })
          .catch(function () {
            showError(root, "Síťová chyba při ukládání.");
          });
      });
    }

    function openSlot(employeeId, day, startsAt, endsAt) {
      if (!formUrl || !host) return;
      var url =
        formUrl +
        "?employee=" +
        encodeURIComponent(employeeId) +
        "&day=" +
        encodeURIComponent(day) +
        "&starts_at=" +
        encodeURIComponent(startsAt) +
        "&ends_at=" +
        encodeURIComponent(endsAt);
      host.innerHTML = '<p class="muted">Načítání…</p>';
      if (typeof dialog.showModal === "function") dialog.showModal();
      fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "text/html" },
      })
        .then(function (res) {
          if (!res.ok) throw new Error("load");
          return res.text();
        })
        .then(function (html) {
          host.innerHTML = html;
          bindForm(host);
        })
        .catch(function () {
          host.innerHTML =
            '<p class="notice danger-soft" role="alert">Nepodařilo se načíst formulář.</p>' +
            '<button type="button" class="secondary" data-activity-close-slot>Zavřít</button>';
          var b = host.querySelector("[data-activity-close-slot]");
          if (b) b.addEventListener("click", closeDialog);
        });
    }

    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-activity-open-slot]");
      if (!btn) return;
      e.preventDefault();
      openSlot(
        btn.getAttribute("data-employee-id"),
        btn.getAttribute("data-day"),
        btn.getAttribute("data-starts-at") || "",
        btn.getAttribute("data-ends-at") || ""
      );
    });

    dialog.addEventListener("click", function (e) {
      if (e.target === dialog) closeDialog();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
