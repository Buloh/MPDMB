(function () {
  "use strict";

  var input = document.getElementById("help-search");
  var results = document.getElementById("search-results");
  var empty = document.getElementById("search-empty");
  if (!input || !results) {
    return;
  }

  var indexPromise = fetch(indexUrl())
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Index nápovědy se nepodařilo načíst.");
      }
      return response.json();
    })
    .catch(function () {
      return [];
    });

  function indexUrl() {
    var script = document.currentScript;
    if (script && script.getAttribute("data-index")) {
      return script.getAttribute("data-index");
    }
    var base = document.body.getAttribute("data-help-base") || "/napoveda/";
    return base.replace(/\/?$/, "/") + "search-index.json";
  }

  function normalize(text) {
    return String(text || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  function scoreEntry(entry, query) {
    var haystack = normalize(
      [entry.title, entry.headings.join(" "), entry.text].join(" ")
    );
    var terms = normalize(query).split(/\s+/).filter(Boolean);
    if (!terms.length) {
      return 0;
    }
    var score = 0;
    for (var i = 0; i < terms.length; i += 1) {
      var term = terms[i];
      if (normalize(entry.title).indexOf(term) !== -1) {
        score += 8;
      }
      if (normalize(entry.headings.join(" ")).indexOf(term) !== -1) {
        score += 4;
      }
      if (haystack.indexOf(term) === -1) {
        return 0;
      }
      score += 1;
    }
    return score;
  }

  function snippetFor(entry, query) {
    var text = entry.text || "";
    var terms = normalize(query).split(/\s+/).filter(Boolean);
    var lower = normalize(text);
    var pos = 0;
    for (var i = 0; i < terms.length; i += 1) {
      var found = lower.indexOf(terms[i]);
      if (found !== -1) {
        pos = found;
        break;
      }
    }
    var start = Math.max(0, pos - 40);
    var chunk = text.slice(start, start + 120).trim();
    if (start > 0) {
      chunk = "… " + chunk;
    }
    if (start + 120 < text.length) {
      chunk += " …";
    }
    return chunk;
  }

  function render(matches, query) {
    results.innerHTML = "";
    if (!query.trim()) {
      results.setAttribute("data-open", "false");
      if (empty) {
        empty.setAttribute("data-open", "false");
      }
      return;
    }
    if (!matches.length) {
      results.setAttribute("data-open", "false");
      if (empty) {
        empty.setAttribute("data-open", "true");
      }
      return;
    }
    if (empty) {
      empty.setAttribute("data-open", "false");
    }
    matches.slice(0, 12).forEach(function (entry) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = entry.url;
      a.innerHTML =
        '<span class="result-title"></span>' +
        '<span class="result-snippet"></span>';
      a.querySelector(".result-title").textContent = entry.title;
      a.querySelector(".result-snippet").textContent = snippetFor(entry, query);
      li.appendChild(a);
      results.appendChild(li);
    });
    results.setAttribute("data-open", "true");
  }

  input.addEventListener("input", function () {
    var query = input.value;
    indexPromise.then(function (index) {
      var ranked = index
        .map(function (entry) {
          return { entry: entry, score: scoreEntry(entry, query) };
        })
        .filter(function (item) {
          return item.score > 0;
        })
        .sort(function (a, b) {
          return b.score - a.score;
        })
        .map(function (item) {
          return item.entry;
        });
      render(ranked, query);
    });
  });

  document.addEventListener("click", function (event) {
    if (!event.target.closest(".search-wrap")) {
      results.setAttribute("data-open", "false");
    }
  });
})();
