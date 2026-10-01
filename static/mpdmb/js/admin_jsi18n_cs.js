/**
 * Doplní chybějící české překlady SelectFilter2 (filter_horizontal).
 * Django cs/djangojs.po zatím nemá msgid s %s (Choose all %s, nápovědy Choose/Remove…).
 * Načíst po /admin/jsi18n/ a před SelectFilter.init ({{ media }}).
 */
(function () {
  "use strict";
  if (typeof django === "undefined" || !django.catalog) {
    return;
  }
  Object.assign(django.catalog, {
    'Choose %s by selecting them and then select the "Choose" arrow button.':
      "Vyberte položky „%s“ jejich označením a klepnutím na šipku „Vybrat“.",
    'Remove %s by selecting them and then select the "Remove" arrow button.':
      "Odeberte položky „%s“ jejich označením a klepnutím na šipku „Odebrat“.",
    "Choose all %s": "Vybrat všechny: %s",
    "Remove all %s": "Odebrat všechny: %s",
    "Choose selected %s": "Vybrat označené: %s",
    "Remove selected %s": "Odebrat označené: %s",
    "Chosen %s": "Vybrané položky: %s",
    "(click to clear)": "(klepnutím vymazat)",
    "Type into this box to filter down the list of available %s.":
      "Psaním do tohoto pole filtrujte seznam dostupných položek „%s“.",
    "Type into this box to filter down the list of selected %s.":
      "Psaním do tohoto pole filtrujte seznam vybraných položek „%s“.",
  });
})();
