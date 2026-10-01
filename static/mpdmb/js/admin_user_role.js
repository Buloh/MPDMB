(function () {
  "use strict";

  function getSelects() {
    return {
      from: document.getElementById("id_user_permissions_from"),
      to: document.getElementById("id_user_permissions_to"),
      role: document.getElementById("id_role"),
    };
  }

  function optionMap(select) {
    const map = new Map();
    if (!select) {
      return map;
    }
    Array.prototype.forEach.call(select.options, function (opt) {
      map.set(String(opt.value), opt);
    });
    return map;
  }

  function redisplay(selectId) {
    if (window.SelectBox && typeof window.SelectBox.redisplay === "function") {
      window.SelectBox.redisplay(selectId);
    }
  }

  function rebuildSelects(from, to, keepToIds, allOptions, newPerms) {
    const keep = new Set(Array.from(keepToIds).map(String));
    const newIds = new Set(newPerms.map(function (p) {
      return String(p.id);
    }));

    from.innerHTML = "";
    to.innerHTML = "";

    const used = new Set();

    function addTo(target, value, label) {
      const key = String(value);
      if (used.has(key)) {
        return;
      }
      used.add(key);
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = label;
      target.appendChild(opt);
    }

    newPerms.forEach(function (p) {
      addTo(to, p.id, p.label);
    });

    keep.forEach(function (id) {
      if (newIds.has(id)) {
        return;
      }
      const existing = allOptions.get(id);
      addTo(to, id, existing ? existing.textContent : id);
    });

    allOptions.forEach(function (opt, id) {
      if (!used.has(id)) {
        addTo(from, id, opt.textContent);
      }
    });

    if (window.SelectBox && typeof window.SelectBox.init === "function") {
      window.SelectBox.init("id_user_permissions_from");
      window.SelectBox.init("id_user_permissions_to");
    } else {
      redisplay("id_user_permissions_from");
      redisplay("id_user_permissions_to");
    }
  }

  function currentRolePermIds(role) {
    const raw = (role && role.getAttribute("data-role-perm-ids")) || "";
    if (!raw.trim()) {
      return new Set();
    }
    return new Set(
      raw.split(",").map(function (s) {
        return s.trim();
      }).filter(Boolean)
    );
  }

  function setRolePermIds(role, ids) {
    role.setAttribute(
      "data-role-perm-ids",
      Array.from(ids).sort().join(",")
    );
  }

  async function onRoleChange() {
    const sels = getSelects();
    if (!sels.role || !sels.from || !sels.to) {
      return;
    }
    const urlBase = sels.role.getAttribute("data-perms-url") || "";
    if (!urlBase) {
      return;
    }
    const oldRoleIds = currentRolePermIds(sels.role);
    const selectedBefore = optionMap(sels.to);
    const allOptions = new Map([
      ...optionMap(sels.from),
      ...selectedBefore,
    ]);

    const exceptionIds = new Set();
    selectedBefore.forEach(function (_opt, id) {
      if (!oldRoleIds.has(id)) {
        exceptionIds.add(id);
      }
    });

    const groupId = sels.role.value || "";
    const url =
      urlBase +
      (urlBase.indexOf("?") >= 0 ? "&" : "?") +
      "group=" +
      encodeURIComponent(groupId);

    let payload;
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        return;
      }
      payload = await response.json();
    } catch (_err) {
      return;
    }

    const newPerms = payload.permissions || [];
    rebuildSelects(sels.from, sels.to, exceptionIds, allOptions, newPerms);
    setRolePermIds(
      sels.role,
      newPerms.map(function (p) {
        return String(p.id);
      })
    );
  }

  function bind() {
    const role = document.getElementById("id_role");
    if (!role || role.dataset.roleBound === "1") {
      return;
    }
    role.dataset.roleBound = "1";
    role.addEventListener("change", onRoleChange);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
