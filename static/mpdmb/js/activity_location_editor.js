(function () {
  "use strict";

  function mapCenterFromEl(el) {
    function coord(raw, fallback) {
      var n = parseFloat(String(raw || "").replace(",", "."));
      return isNaN(n) ? fallback : n;
    }
    var lat = coord(el.getAttribute("data-center-lat"), 50.41135);
    var lon = coord(el.getAttribute("data-center-lon"), 14.90318);
    var zoom = parseInt(el.getAttribute("data-zoom") || "15", 10);
    if (isNaN(zoom) || zoom < 1) {
      zoom = 15;
    }
    return { lat: lat, lon: lon, zoom: zoom };
  }

  function parseExisting(raw) {
    if (!raw || !String(raw).trim()) {
      return null;
    }
    try {
      var data = JSON.parse(raw);
      if (data && data.type === "Feature") {
        return data.geometry;
      }
      if (data && data.type === "FeatureCollection" && data.features && data.features[0]) {
        return data.features[0].geometry || data.features[0];
      }
      return data;
    } catch (err) {
      return null;
    }
  }

  function setStatus(hasPolygon) {
    var status = document.getElementById("polygon-status");
    if (!status) {
      return;
    }
    status.textContent = hasPolygon
      ? "Polygon připraven k uložení."
      : "Nakreslete polygon na mapě.";
  }

  function syncHidden(layerGroup, input) {
    var layers = layerGroup.getLayers();
    if (!layers.length) {
      input.value = "";
      setStatus(false);
      return;
    }
    var geo = layers[0].toGeoJSON();
    var geometry = geo.geometry || geo;
    input.value = JSON.stringify(geometry);
    setStatus(true);
  }

  function polygonStyle() {
    var colorEl = document.getElementById("id_color");
    var color =
      colorEl && /^#[0-9A-Fa-f]{6}$/i.test(colorEl.value)
        ? colorEl.value
        : "#166999";
    return {
      color: color,
      weight: 2,
      fillColor: color,
      fillOpacity: 0.35,
    };
  }

  function applyStyleToDrawn(drawn) {
    var style = polygonStyle();
    drawn.eachLayer(function (lyr) {
      if (lyr.setStyle) {
        lyr.setStyle(style);
      }
    });
  }

  function initEditor() {
    var mapEl = document.getElementById("location-editor-map");
    var input = document.getElementById("id_geojson");
    if (!mapEl || !input || typeof L === "undefined" || !L.Control || !L.Control.Draw) {
      return;
    }

    var center = mapCenterFromEl(mapEl);
    var map = L.map(mapEl).setView([center.lat, center.lon], center.zoom);
    if (window.MPDMBMapTiles) {
      window.MPDMBMapTiles.addBaseTiles(map);
    }

    var drawn = new L.FeatureGroup();
    map.addLayer(drawn);

    var contextEl = document.getElementById("locations-context-geojson");
    if (contextEl) {
      try {
        var contextData = JSON.parse(contextEl.textContent);
        if (contextData && contextData.features && contextData.features.length) {
          L.geoJSON(contextData, {
            style: function (feature) {
              var color =
                feature &&
                feature.properties &&
                feature.properties.color
                  ? feature.properties.color
                  : "#166999";
              return {
                color: color,
                weight: 2,
                fillColor: color,
                fillOpacity: 0.28,
                opacity: 0.85,
                dashArray: "6 3",
              };
            },
            onEachFeature: function (feature, layer) {
              var props = feature.properties || {};
              var label = props.label || props.code || props.name || "";
              if (label) {
                layer.bindTooltip(label, { sticky: true });
              }
            },
          }).addTo(map);
        }
      } catch (err) {
        /* ignore */
      }
    }

    var existing = parseExisting(input.value);
    if (existing && existing.type === "Polygon") {
      var layer = L.geoJSON(
        { type: "Feature", geometry: existing, properties: {} },
        { style: polygonStyle }
      );
      layer.eachLayer(function (lyr) {
        drawn.addLayer(lyr);
      });
      try {
        map.fitBounds(drawn.getBounds(), { padding: [24, 24], maxZoom: 17 });
      } catch (e) {
        /* ignore */
      }
      setStatus(true);
    } else {
      setStatus(false);
      requestAnimationFrame(function () {
        map.invalidateSize();
        map.setView([center.lat, center.lon], center.zoom);
      });
    }

    var drawControl = new L.Control.Draw({
      edit: { featureGroup: drawn, remove: true },
      draw: {
        polygon: {
          allowIntersection: false,
          showArea: false,
          shapeOptions: polygonStyle(),
        },
        polyline: false,
        rectangle: false,
        circle: false,
        marker: false,
        circlemarker: false,
      },
    });
    map.addControl(drawControl);

    var colorInput = document.getElementById("id_color");
    if (colorInput) {
      colorInput.addEventListener("input", function () {
        applyStyleToDrawn(drawn);
      });
    }

    map.on(L.Draw.Event.CREATED, function (e) {
      drawn.clearLayers();
      e.layer.setStyle(polygonStyle());
      drawn.addLayer(e.layer);
      syncHidden(drawn, input);
    });
    map.on(L.Draw.Event.EDITED, function () {
      syncHidden(drawn, input);
    });
    map.on(L.Draw.Event.DELETED, function () {
      syncHidden(drawn, input);
    });

    var form = document.getElementById("location-form");
    if (form) {
      form.addEventListener("submit", function (ev) {
        syncHidden(drawn, input);
        if (!input.value.trim()) {
          ev.preventDefault();
          setStatus(false);
          alert("Nakreslete polygon lokality na mapě.");
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initEditor);
  } else {
    initEditor();
  }
})();
