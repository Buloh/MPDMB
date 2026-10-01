(function () {
  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function init() {
    var dialog = document.getElementById("leave-plan-dialog");
    if (!dialog) return;
    var host = dialog.querySelector(".leave-plan-dialog-host");
    var formUrl = dialog.getAttribute("data-form-url") || "";
    var createUrl = dialog.getAttribute("data-create-url") || "";

    function closeDialog() {
      if (typeof dialog.close === "function") dialog.close();
    }

    function showError(formRoot, msg) {
      var err = formRoot && formRoot.querySelector(".leave-plan-error");
      if (!err) return;
      err.textContent = msg || "Uložení selhalo.";
      err.hidden = false;
    }

    function bindForm(root) {
      var form = root.querySelector(".leave-plan-form");
      if (!form) return;
      var closeBtn = root.querySelector("[data-leave-close-dialog]");
      if (closeBtn) {
        closeBtn.addEventListener("click", function (e) {
          e.preventDefault();
          closeDialog();
        });
      }
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var fd = new FormData(form);
        fetch(createUrl || form.action, {
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

    function openDialog(employeeId, year, startsOn, endsOn) {
      if (!formUrl || !host) return;
      var url =
        formUrl +
        "?employee_id=" +
        encodeURIComponent(employeeId) +
        "&year=" +
        encodeURIComponent(year);
      if (startsOn) {
        url += "&starts_on=" + encodeURIComponent(startsOn);
      }
      if (endsOn) {
        url += "&ends_on=" + encodeURIComponent(endsOn);
      }
      host.innerHTML = '<p class="muted">Načítání…</p>';
      if (typeof dialog.showModal === "function") dialog.showModal();
      fetch(url, { credentials: "same-origin", headers: { Accept: "text/html" } })
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
            '<button type="button" class="secondary" data-leave-close-dialog>Zavřít</button>';
          var b = host.querySelector("[data-leave-close-dialog]");
          if (b) b.addEventListener("click", closeDialog);
        });
    }

    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-leave-open-dialog]");
      if (!btn) return;
      e.preventDefault();
      openDialog(
        btn.getAttribute("data-employee-id"),
        btn.getAttribute("data-year"),
        btn.getAttribute("data-starts-on") || "",
        btn.getAttribute("data-ends-on") || ""
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
