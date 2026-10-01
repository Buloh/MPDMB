(function () {
  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function initCellMenu() {
    var menu = document.getElementById("shift-cell-menu");
    if (!menu) return;
    var list = menu.querySelector(".shift-cell-menu-list");
    var errEl = menu.querySelector(".shift-cell-menu-error");
    var postUrl = menu.getAttribute("data-post-url") || "";
    var types = [];
    try {
      types = JSON.parse(menu.getAttribute("data-types") || "[]");
    } catch (e) {
      types = [];
    }

    var active = null;

    function hide() {
      menu.hidden = true;
      active = null;
      if (errEl) {
        errEl.hidden = true;
        errEl.textContent = "";
      }
    }

    function showError(msg) {
      if (!errEl) return;
      errEl.textContent = msg;
      errEl.hidden = false;
    }

    function placeMenu(x, y) {
      menu.hidden = false;
      var pad = 8;
      var rect = menu.getBoundingClientRect();
      var left = x;
      var top = y;
      if (left + rect.width > window.innerWidth - pad) {
        left = Math.max(pad, window.innerWidth - rect.width - pad);
      }
      if (top + rect.height > window.innerHeight - pad) {
        top = Math.max(pad, window.innerHeight - rect.height - pad);
      }
      menu.style.left = left + "px";
      menu.style.top = top + "px";
    }

    function openFor(link, clientX, clientY) {
      active = {
        employee: link.getAttribute("data-employee"),
        day: link.getAttribute("data-day"),
        year: link.getAttribute("data-year"),
        month: link.getAttribute("data-month"),
      };
      if (!list) return;
      list.innerHTML = "";
      if (!types.length) {
        list.innerHTML = "<li class=\"muted\">Žádné typy směn</li>";
      } else {
        types.forEach(function (t) {
          var li = document.createElement("li");
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "shift-cell-menu-item";
          btn.textContent = t.code + " – " + t.name;
          btn.setAttribute("data-type-id", String(t.id));
          btn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            submitType(t.id);
          });
          li.appendChild(btn);
          list.appendChild(li);
        });
      }
      placeMenu(clientX, clientY);
    }

    function submitType(typeId) {
      if (!active || !postUrl) return;
      var body = new FormData();
      body.append("partial", "1");
      body.append("year", active.year);
      body.append("month", active.month);
      body.append("employee", active.employee);
      body.append("day", active.day);
      body.append("shift_type", String(typeId));
      body.append("publish", "on");
      body.append("csrfmiddlewaretoken", csrfToken());
      fetch(postUrl + "?partial=1", {
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
              showError((data && data.error) || "Uložení selhalo.");
            });
          }
          return res.text().then(function () {
            showError("Směnu se nepodařilo uložit (chybí pracoviště?).");
          });
        })
        .catch(function () {
          showError("Nepodařilo se spojit se serverem.");
        });
    }

    document.querySelectorAll(".cell-empty[data-employee]").forEach(function (link) {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        openFor(link, e.clientX, e.clientY);
      });
    });

    document.addEventListener("click", function (e) {
      if (!menu.hidden && !menu.contains(e.target)) hide();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") hide();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCellMenu);
  } else {
    initCellMenu();
  }
})();
