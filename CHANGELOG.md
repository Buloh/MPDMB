# Changelog SYNERA (MPDMB)

Evidence uživatelsky viditelných změn. Číslo verze musí souhlasit
s `apps/core/version.py`.

## 0.7.3 — 01.10.2026

### Opravy

- Kompaktnější plán dne (Činnost): filtry a kalendář bez prázdného
  mezisloupce, užší pole, směny vedle kalendáře.
- Kompaktnější detail pracoviště: údaje v mřížce, panely vedle sebe,
  hustší tabulka přiřazení.

## 0.7.2 — 01.10.2026

### Funkce

- Dokumenty (Word): univerzální šablony, MERGEFIELD s českým popiskem
  a komentářem nápovědy, CSV polí, mazání/deaktivace šablon a dokumentů.
- Vazba Korespondence (CSV) u šablon se při nahrání zachová; u vyplněného
  dokumentu se odstraňuje (bez SQL dialogu u hotových souborů).
- Administrace účtů: jedna role na uživatele; při změně role se dual-list
  oprávnění dynamicky přepočítá; přehled práv ze skupiny ve Vybrané.
- Příkaz `assign_employee_role` (s `--replace`); pravidlo verzování
  a tento changelog.

### Opravy

- Po nahrání šablony s CSV dříve mizela vazba Word Korespondence — opraveno.
- Uzavřený upload souboru při validaci šablony — čtení bajtů před validací.
