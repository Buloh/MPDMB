/**
 * Sdílený podklad mapy (OpenStreetMap Deutschland – globální pokrytí včetně ČR).
 * Nepoužívat oficiální OSM.org tile servery (403), Carto CDN (API klíč)
 * ani OSM France (slabé dlaždice ČR při přiblížení).
 */
(function (global) {
  "use strict";

  var TILE_URL = "https://tile.openstreetmap.de/{z}/{x}/{y}.png";
  var TILE_OPTS = {
    maxZoom: 19,
    maxNativeZoom: 18,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  };

  function addBaseTiles(map) {
    if (typeof L === "undefined" || !map) {
      return null;
    }
    return L.tileLayer(TILE_URL, TILE_OPTS).addTo(map);
  }

  global.MPDMBMapTiles = {
    url: TILE_URL,
    options: TILE_OPTS,
    addBaseTiles: addBaseTiles,
  };
})(window);
