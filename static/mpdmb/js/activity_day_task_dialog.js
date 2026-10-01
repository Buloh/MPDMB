(function () {
  "use strict";

  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function init() {
    var dialog = document.getElementById("activity-day-task-dialog");
    if (!dialog) return;
    var host = dialog.querySelector(".activity-day-task-dialog-host");
    var formUrl = dialog.getAttribute("data-form-url") || "";
    var saveUrl = dialog.getAttribute("data-save-url") || "";

    function closeDialog() {
      if (typeof dialog.close === "function") dialog.close();
    }

    function showError(root, msg) {
      var err = root && root.querySelector(".activity-day-task-error");
      if (!err) return;
      err.textContent = msg || "Uložení selhalo.";
      err.hidden = false;
    }

    function bindForm(root) {
      var form = root.querySelector(".activity-day-task-form");
      if (!form) return;

      var closeBtn = root.querySelector("[data-activity-close-day-task]");
      if (closeBtn) {
        closeBtn.addEventListener("click", function (e) {
          e.preventDefault();
          closeDialog();
        });
      }

      form.addEventListener("submit", function (e) {
        e.preventDefault();
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

    function openDayTask(employeeId, day, workplaceId) {
      if (!formUrl || !host) return;
      var url =
        formUrl +
        "?employee=" +
        encodeURIComponent(employeeId) +
        "&day=" +
        encodeURIComponent(day);
      if (workplaceId) {
        url += "&workplace=" + encodeURIComponent(workplaceId);
      }
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
            '<button type="button" class="secondary" data-activity-close-day-task>Zavřít</button>';
          var b = host.querySelector("[data-activity-close-day-task]");
          if (b) b.addEventListener("click", closeDialog);
        });
    }

    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-activity-open-day-task]");
      if (!btn) return;
      e.preventDefault();
      openDayTask(
        btn.getAttribute("data-employee-id"),
        btn.getAttribute("data-day"),
        btn.getAttribute("data-workplace") || ""
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
