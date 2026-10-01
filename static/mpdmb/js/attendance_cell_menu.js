(function () {
  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function urlForShift(tpl, shiftId) {
    return String(tpl || "").replace(/\/0\//, "/" + shiftId + "/");
  }

  function initUnresolvedMenu() {
    var menu = document.getElementById("att-cell-menu");
    if (!menu) return;
    var list = menu.querySelector(".shift-cell-menu-list");
    var titleEl = menu.querySelector(".shift-cell-menu-title");
    var errEl = menu.querySelector(".shift-cell-menu-error");
    var confirmTpl = menu.getAttribute("data-confirm-url-tpl") || "";
    var editTpl = menu.getAttribute("data-edit-url-tpl") || "";
    var absenceTpl = menu.getAttribute("data-absence-url-tpl") || "";
    var absences = [];
    try {
      absences = JSON.parse(menu.getAttribute("data-absences") || "[]");
    } catch (e) {
      absences = [];
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

    function showError(msg, employeeUrl) {
      if (!errEl) return;
      errEl.textContent = "";
      errEl.appendChild(document.createTextNode(msg || "Akce selhala."));
      if (employeeUrl) {
        errEl.appendChild(document.createTextNode(" "));
        var link = document.createElement("a");
        link.href = employeeUrl;
        link.textContent = "Otevřít kartu zaměstnance";
        errEl.appendChild(link);
      }
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

    function addItem(label, onClick) {
      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "shift-cell-menu-item";
      btn.textContent = label;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        onClick();
      });
      li.appendChild(btn);
      list.appendChild(li);
    }

    function postAction(url, extraFields) {
      if (!active) return;
      var body = new FormData();
      body.append("partial", "1");
      body.append("year", active.year);
      body.append("month", active.month);
      body.append("csrfmiddlewaretoken", csrfToken());
      Object.keys(extraFields || {}).forEach(function (key) {
        body.append(key, extraFields[key]);
      });
      fetch(url, {
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
              showError(
                (data && data.error) || "Uložení selhalo.",
                data && data.employee_url
              );
            });
          }
          if (res.ok || res.redirected) {
            window.location.reload();
            return;
          }
          showError("Akci se nepodařilo dokončit.");
        })
        .catch(function () {
          showError("Nepodařilo se spojit se serverem.");
        });
    }

    function openUnresolved(link, clientX, clientY) {
      active = {
        shift: link.getAttribute("data-shift"),
        employee: link.getAttribute("data-employee"),
        day: link.getAttribute("data-day"),
        year: link.getAttribute("data-year"),
        month: link.getAttribute("data-month"),
        dayUrl: link.getAttribute("data-day-url") || "",
        missingEmployment: link.getAttribute("data-missing-employment") === "1",
        employeeEditUrl: link.getAttribute("data-employee-edit-url") || "",
      };
      if (!list || !active.shift) return;
      if (titleEl) titleEl.textContent = "Docházka dne";
      list.innerHTML = "";
      if (errEl) {
        errEl.hidden = true;
        errEl.textContent = "";
      }

      addItem("Potvrdit jako plán", function () {
        postAction(urlForShift(confirmTpl, active.shift), { as_plan: "1" });
      });
      addItem("Upravit časy", function () {
        hide();
        var url =
          urlForShift(editTpl, active.shift) +
          "?partial=1&year=" +
          encodeURIComponent(active.year) +
          "&month=" +
          encodeURIComponent(active.month);
        openConfirmModal(url);
      });
      absences.forEach(function (t) {
        addItem(t.name, function () {
          postAction(urlForShift(absenceTpl, active.shift), {
            absence_code: t.code,
          });
        });
      });
      if (active.dayUrl) {
        addItem("Detail dne", function () {
          hide();
          var url = active.dayUrl;
          url += url.indexOf("?") >= 0 ? "&partial=1" : "?partial=1";
          openDayModal(url);
        });
      }
      placeMenu(clientX, clientY);
      if (active.missingEmployment) {
        showError(
          "U zaměstnance chybí aktivní pracovní vztah k datu směny. Doplňte den nástupu na kartě zaměstnance.",
          active.employeeEditUrl
        );
      }
    }

    document.querySelectorAll(".att-unresolved-menu").forEach(function (link) {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        openUnresolved(link, e.clientX, e.clientY);
      });
    });

    document.addEventListener("click", function (e) {
      if (!menu.hidden && !menu.contains(e.target)) hide();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") hide();
    });
  }

  function initAdhocDialog() {
    var dialog = document.getElementById("att-adhoc-dialog");
    if (!dialog) return;
    var postUrl = dialog.getAttribute("data-post-url") || "";
    var subtitle = document.getElementById("att-adhoc-subtitle");
    var errEl = document.getElementById("att-adhoc-error");
    var form = document.getElementById("att-adhoc-custom-form");
    var active = null;

    function closeDialog() {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
      active = null;
      if (errEl) {
        errEl.hidden = true;
        errEl.textContent = "";
      }
    }

    function showError(msg, employeeUrl) {
      if (!errEl) return;
      errEl.textContent = "";
      errEl.appendChild(document.createTextNode(msg || "Akce selhala."));
      if (employeeUrl) {
        errEl.appendChild(document.createTextNode(" "));
        var link = document.createElement("a");
        link.href = employeeUrl;
        link.textContent = "Otevřít kartu zaměstnance";
        errEl.appendChild(link);
      }
      errEl.hidden = false;
    }

    function openDialog(link) {
      active = {
        employee: link.getAttribute("data-employee"),
        employeeLabel: link.getAttribute("data-employee-label") || "",
        day: link.getAttribute("data-day"),
        dayLabel: link.getAttribute("data-day-label") || "",
        year: link.getAttribute("data-year"),
        month: link.getAttribute("data-month"),
      };
      if (subtitle) {
        subtitle.textContent =
          (active.employeeLabel || "") +
          (active.employeeLabel && active.dayLabel ? " · " : "") +
          (active.dayLabel || active.day || "");
      }
      if (errEl) {
        errEl.hidden = true;
        errEl.textContent = "";
      }
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "open");
    }

    function postAdhoc(extraFields) {
      if (!active || !postUrl) return;
      var body = new FormData();
      body.append("partial", "1");
      body.append("employee", active.employee);
      body.append("day", active.day);
      body.append("year", active.year);
      body.append("month", active.month);
      body.append("csrfmiddlewaretoken", csrfToken());
      Object.keys(extraFields || {}).forEach(function (key) {
        body.append(key, extraFields[key]);
      });
      fetch(postUrl, {
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
              showError(
                (data && data.error) || "Uložení selhalo.",
                data && data.employee_url
              );
            });
          }
          showError("Uložení selhalo.");
        })
        .catch(function () {
          showError("Nepodařilo se spojit se serverem.");
        });
    }

    document.querySelectorAll(".att-empty-menu").forEach(function (link) {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        openDialog(link);
      });
    });

    dialog.querySelectorAll(".att-adhoc-type").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        var typeId = btn.getAttribute("data-shift-type");
        if (!typeId) return;
        var wp = document.getElementById("att-adhoc-workplace");
        var fields = { shift_type: typeId };
        if (wp && wp.value) fields.workplace = wp.value;
        postAdhoc(fields);
      });
    });

    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var body = {};
        new FormData(form).forEach(function (value, key) {
          body[key] = value;
        });
        postAdhoc(body);
      });
    }

    dialog.querySelectorAll("[data-close-att-adhoc]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        closeDialog();
      });
    });

    dialog.addEventListener("cancel", function () {
      active = null;
    });
  }

  function openDayModal(url) {
    var dialog = document.getElementById("att-day-dialog");
    if (!dialog || !url) {
      window.location.href = String(url || "").replace("&partial=1", "").replace("?partial=1", "");
      return;
    }
    var host = dialog.querySelector(".att-day-dialog-host");
    if (!host) return;

    function closeDialog() {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }

    function showDayError(msg) {
      var errEl = host.querySelector(".att-day-modal-error");
      if (!errEl) {
        errEl = document.createElement("div");
        errEl.className = "notice danger-soft att-day-modal-error";
        errEl.setAttribute("role", "alert");
        host.insertBefore(errEl, host.firstChild);
      }
      errEl.textContent = msg;
      errEl.hidden = false;
    }

    function bindDayBody() {
      host.querySelectorAll("[data-close-att-day]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          closeDialog();
        });
      });
      host.querySelectorAll("[data-confirm-modal-url]").forEach(function (link) {
        link.addEventListener("click", function (e) {
          e.preventDefault();
          var confirmUrl = link.getAttribute("data-confirm-modal-url");
          if (confirmUrl) {
            closeDialog();
            openConfirmModal(confirmUrl);
          }
        });
      });
      host.querySelectorAll("form.att-day-ajax-form").forEach(function (form) {
        form.addEventListener("submit", function (e) {
          e.preventDefault();
          var body = new FormData(form);
          if (!body.get("partial")) body.append("partial", "1");
          fetch(form.action, {
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
                  showDayError((data && data.error) || "Akce selhala.");
                });
              }
              if (res.ok || res.redirected) {
                window.location.reload();
                return;
              }
              showDayError("Akci se nepodařilo dokončit.");
            })
            .catch(function () {
              showDayError("Nepodařilo se spojit se serverem.");
            });
        });
      });
    }

    host.innerHTML = "<p class=\"muted\">Načítám…</p>";
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "open");

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
        bindDayBody();
      })
      .catch(function () {
        host.innerHTML =
          '<div class="notice danger-soft" role="alert">Nepodařilo se načíst detail dne.</div>' +
          '<p><button type="button" class="secondary" data-close-att-day>Zavřít</button></p>';
        bindDayBody();
      });
  }

  function openConfirmModal(url) {
    var dialog = document.getElementById("att-confirm-dialog");
    if (!dialog || !url) {
      window.location.href = String(url || "").replace("partial=1&", "").replace("?partial=1", "");
      return;
    }
    var host = dialog.querySelector(".att-confirm-dialog-host");
    if (!host) return;

    function closeDialog() {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }

    function bindForm() {
      host.querySelectorAll("[data-close-att-confirm]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          closeDialog();
        });
      });
      var form = host.querySelector("form.att-confirm-form");
      if (!form) return;
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var body = new FormData(form);
        if (!body.get("partial")) body.append("partial", "1");
        fetch(form.action, {
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
                var err =
                  (data && data.error) || "Uložení selhalo.";
                var notice = host.querySelector(".att-confirm-live-error");
                if (!notice) {
                  notice = document.createElement("div");
                  notice.className =
                    "notice danger-soft att-confirm-live-error";
                  notice.setAttribute("role", "alert");
                  host.insertBefore(notice, host.firstChild);
                }
                notice.textContent = "";
                notice.appendChild(document.createTextNode(err));
                if (data && data.employee_url) {
                  notice.appendChild(document.createTextNode(" "));
                  var empLink = document.createElement("a");
                  empLink.href = data.employee_url;
                  empLink.textContent = "Otevřít kartu zaměstnance";
                  notice.appendChild(empLink);
                }
                notice.hidden = false;
              });
            }
            return res.text().then(function (html) {
              host.innerHTML = html;
              bindForm();
            });
          })
          .catch(function () {
            var notice = document.createElement("div");
            notice.className = "notice danger-soft";
            notice.setAttribute("role", "alert");
            notice.textContent = "Nepodařilo se spojit se serverem.";
            host.insertBefore(notice, host.firstChild);
          });
      });
    }

    host.innerHTML = "<p class=\"muted\">Načítám…</p>";
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "open");

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
        bindForm();
      })
      .catch(function () {
        host.innerHTML =
          '<div class="notice danger-soft" role="alert">Nepodařilo se načíst formulář.</div>' +
          '<p><button type="button" class="secondary" data-close-att-confirm>Zavřít</button></p>';
        bindForm();
      });
  }

  function initConfirmModalLinks() {
    document.querySelectorAll("[data-confirm-modal-url]").forEach(function (link) {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        var url = link.getAttribute("data-confirm-modal-url");
        if (url) openConfirmModal(url);
      });
    });
  }

  function init() {
    initUnresolvedMenu();
    initAdhocDialog();
    initConfirmModalLinks();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
