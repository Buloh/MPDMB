(function () {
  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function initCellDialog() {
    var dialog = document.getElementById("shift-cell-dialog");
    if (!dialog) return;
    var host = dialog.querySelector(".cell-dialog-content");
    if (!host) return;

    function closeDialog() {
      if (typeof dialog.close === "function") dialog.close();
    }

    function bindCloseButtons(root) {
      root.querySelectorAll("[data-close-cell-dialog]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          closeDialog();
        });
      });
    }

    function bindForm(root) {
      var form = root.querySelector("form.cell-modal-form");
      if (!form) return;
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var body = new FormData(form);
        fetch(form.action + "?partial=1", {
          method: "POST",
          body: body,
          headers: {
            "X-CSRFToken": csrfToken(),
            Accept: "application/json",
          },
          credentials: "same-origin",
        })
          .then(function (res) {
            var type = res.headers.get("content-type") || "";
            if (type.indexOf("application/json") !== -1) {
              return res.json().then(function (data) {
                if (data && data.ok) {
                  window.location.reload();
                  return;
                }
                throw new Error((data && data.error) || "Uložení selhalo.");
              });
            }
            return res.text().then(function (html) {
              host.innerHTML = html;
              bindCloseButtons(host);
              bindForm(host);
            });
          })
          .catch(function () {
            host.insertAdjacentHTML(
              "afterbegin",
              '<div class="notice danger-soft" role="alert">Nepodařilo se uložit směnu.</div>'
            );
          });
      });
    }

    document.querySelectorAll("[data-cell-url]").forEach(function (link) {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        var url = link.getAttribute("data-cell-url");
        if (!url) return;
        host.innerHTML = "<p class=\"muted\">Načítám…</p>";
        if (typeof dialog.showModal === "function") dialog.showModal();
        else dialog.setAttribute("open", "open");
        fetch(url, { credentials: "same-origin", headers: { Accept: "text/html" } })
          .then(function (res) {
            if (!res.ok) throw new Error("load");
            return res.text();
          })
          .then(function (html) {
            host.innerHTML = html;
            bindCloseButtons(host);
            bindForm(host);
          })
          .catch(function () {
            host.innerHTML =
              '<div class="notice danger-soft" role="alert">Nepodařilo se načíst formulář.</div>' +
              '<button type="button" class="button secondary" data-close-cell-dialog>Zavřít</button>';
            bindCloseButtons(host);
          });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCellDialog);
  } else {
    initCellDialog();
  }
})();
