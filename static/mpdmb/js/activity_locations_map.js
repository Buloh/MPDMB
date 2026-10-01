(function () {
  "use strict";

  function mapCenterFromEl(el) {
    function coord(raw, fallback) {
      var n = parseFloat(String(raw || "").replace(",", "."));
      return isNaN(n) ? fallback : n;
    }
    var lat = coord(el.getAttribute("data-center-lat"), 50.41135);
    var lon = coord(el.getAttribute("data-center-lon"), 14.90318);
    var zoom = parseInt(el.getAttribute("data-zoom") || "14", 10);
    if (isNaN(zoom) || zoom < 1) {
      zoom = 14;
    }
    return { lat: lat, lon: lon, zoom: zoom };
  }

  function styleForFeature(feature) {
    var props = feature.properties || {};
    var level = props.level || "main";
    var color = props.color || "";
    if (/^#[0-9A-Fa-f]{6}$/.test(color)) {
      return {
        color: color,
        weight: level === "sub" ? 1.5 : 3,
        fillColor: color,
        fillOpacity: level === "sub" ? 0.45 : 0.28,
      };
    }
    if (level === "sub") {
      return {
        color: "#21759B",
        weight: 1.5,
        fillColor: "#6EC1E4",
        fillOpacity: 0.4,
      };
    }
    return {
      color: "#166999",
      weight: 3,
      fillColor: "#166999",
      fillOpacity: 0.15,
    };
  }

  function selectedStyle(feature) {
    var base = styleForFeature(feature);
    return {
      color: "#12567D",
      weight: Math.max(base.weight + 2, 4),
      fillColor: base.fillColor,
      fillOpacity: Math.min((base.fillOpacity || 0.2) + 0.25, 0.65),
    };
  }

  function setText(el, value) {
    if (el) {
      el.textContent = value == null ? "" : String(value);
    }
  }

  function showLocationDetail(props) {
    var panel = document.getElementById("location-map-detail");
    var empty = document.getElementById("location-map-detail-empty");
    if (!panel) {
      return;
    }
    var p = props || {};
    setText(
      document.getElementById("location-map-detail-title"),
      p.label || ((p.code || "") + " – " + (p.name || ""))
    );
    setText(document.getElementById("location-map-detail-code"), p.code || "—");
    setText(
      document.getElementById("location-map-detail-parent"),
      p.parent_code || "—"
    );
    setText(
      document.getElementById("location-map-detail-workplace"),
      p.workplace || "—"
    );
    var descEl = document.getElementById("location-map-detail-desc");
    var desc = (p.description || "").trim();
    if (descEl) {
      descEl.textContent = desc || "Bez popisu.";
      descEl.hidden = false;
    }
    var edit = document.getElementById("location-map-detail-edit");
    if (edit) {
      if (p.edit_url) {
        edit.href = p.edit_url;
        edit.hidden = false;
      } else {
        edit.removeAttribute("href");
        edit.hidden = true;
      }
    }
    panel.hidden = false;
    if (empty) {
      empty.hidden = true;
    }
  }

  function initMap() {
    var el = document.getElementById("locations-map");
    var dataEl = document.getElementById("locations-geojson");
    if (!el || !dataEl || typeof L === "undefined") {
      return;
    }
    var collection;
    try {
      collection = JSON.parse(dataEl.textContent);
    } catch (err) {
      collection = { type: "FeatureCollection", features: [] };
    }
    // Střed = zvolené MapCity (data-center-*). Pohled se nepřepisuje
    // podle všech polygonů (ty mohou ležet v jiném městě).
    var center = mapCenterFromEl(el);
    var map = L.map(el).setView([center.lat, center.lon], center.zoom);
    if (window.MPDMBMapTiles) {
      window.MPDMBMapTiles.addBaseTiles(map);
    }

    var selectedLayer = null;

    L.geoJSON(collection, {
      style: styleForFeature,
      onEachFeature: function (feature, lyr) {
        var p = feature.properties || {};
        var label = p.label || (p.code || "") + " – " + (p.name || "");
        lyr.bindPopup(label);
        lyr.on("click", function () {
          if (selectedLayer && selectedLayer !== lyr) {
            selectedLayer.setStyle(styleForFeature(selectedLayer.feature));
          }
          selectedLayer = lyr;
          lyr.setStyle(selectedStyle(feature));
          if (lyr.bringToFront) {
            lyr.bringToFront();
          }
          showLocationDetail(p);
        });
      },
    }).addTo(map);

    requestAnimationFrame(function () {
      map.invalidateSize();
      map.setView([center.lat, center.lon], center.zoom);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMap);
  } else {
    initMap();
  }
})();
