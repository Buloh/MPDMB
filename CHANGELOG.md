# Changelog SYNERA (MPDMB)

Evidence uživatelsky viditelných změn. Číslo verze musí souhlasit
s `apps/core/version.py`.

## 0.8.3 — 01.10.2026

### Opravy

- Časové rozsahy jednotně s mezerami (`06:00 – 14:00`) napříč Provozem,
  docházkou a činností.
- Kompaktnější formuláře typu směny a šablony (mřížka dnů cyklu).
- Hustší dlouhodobý plán a seznamy šablon / fond / typy směn.

## 0.8.2 — 01.10.2026

### Opravy

- Kompaktnější měsíční Docházka: shrnutí ve čtyřech metrikách vedle sebe,
  hustší toolbar a matice.

## 0.8.1 — 01.10.2026

### Opravy

- Django admin: vyšší kontrast (tmavě modré hlavičky tabulek a sekcí,
  výraznější navigace, čitelnější text a filtry).

## 0.8.0 — 01.10.2026

### Funkce

- Rozcestník Administrace (`/administrace/`) ve stylu SYNERA: účty,
  skupiny, audit a číselníky jako dlaždice s odkazy do Django adminu.
- Vizuální sjednocení Django `/admin/` s paletou MPDMB (header, pozadí,
  hustší úvodní stránka).

## 0.7.4 — 01.10.2026

### Opravy

- Kompaktnější detail zaměstnance: údaje a pracovní vztah v mřížce,
  panely vedle sebe, hustší tabulky.
- Kompaktnější detail techniky: údaje v mřížce, doklady vedle údajů,
  hustší tabulky.

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
