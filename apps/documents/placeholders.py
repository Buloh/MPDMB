"""Katalog Word placeholderů (tokenů) pro šablony dokumentů."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlaceholderDef:
    key: str
    label: str
    scopes: frozenset[str]
    help_text: str = ""


SCOPE_EMPLOYEE = "zamestnanec"
SCOPE_VEHICLE = "vozidlo"
SCOPE_COMMON = "spolecne"

COMMON_PLACEHOLDERS: tuple[PlaceholderDef, ...] = (
    PlaceholderDef(
        "dnes",
        "Dnešní datum",
        frozenset({SCOPE_COMMON}),
        "Datum generování ve formátu dd.mm.rrrr (Europe/Prague).",
    ),
    PlaceholderDef(
        "cas",
        "Aktuální čas",
        frozenset({SCOPE_COMMON}),
        "Čas generování ve formátu HH:mm (Europe/Prague).",
    ),
    PlaceholderDef(
        "datum_cas",
        "Datum a čas",
        frozenset({SCOPE_COMMON}),
        "Datum i čas generování: dd.mm.rrrr HH:mm.",
    ),
    PlaceholderDef(
        "vystavil",
        "Vystavil (jméno)",
        frozenset({SCOPE_COMMON}),
        "Celé jméno přihlášeného uživatele; pokud chybí, uživatelské jméno.",
    ),
    PlaceholderDef(
        "vystavil_uzivatel",
        "Vystavil (uživatel)",
        frozenset({SCOPE_COMMON}),
        "Přihlašovací jméno (username) uživatele, který dokument vytvořil.",
    ),
    PlaceholderDef(
        "aplikace",
        "Název aplikace",
        frozenset({SCOPE_COMMON}),
        "Název systému (SYNERA).",
    ),
    PlaceholderDef(
        "verze_aplikace",
        "Verze aplikace",
        frozenset({SCOPE_COMMON}),
        "Číslo verze SYNERA v okamžiku generování.",
    ),
)

EMPLOYEE_PLACEHOLDERS: tuple[PlaceholderDef, ...] = (
    PlaceholderDef(
        "zamestnanec.jmeno",
        "Jméno",
        frozenset({SCOPE_EMPLOYEE}),
        "Křestní jméno z karty zaměstnance.",
    ),
    PlaceholderDef(
        "zamestnanec.prijmeni",
        "Příjmení",
        frozenset({SCOPE_EMPLOYEE}),
        "Příjmení z karty zaměstnance.",
    ),
    PlaceholderDef(
        "zamestnanec.cele_jmeno",
        "Celé jméno",
        frozenset({SCOPE_EMPLOYEE}),
        "Jméno a příjmení dohromady.",
    ),
    PlaceholderDef(
        "zamestnanec.interni_cislo",
        "Interní číslo",
        frozenset({SCOPE_EMPLOYEE}),
        "Interní evidenční číslo zaměstnance.",
    ),
    PlaceholderDef(
        "zamestnanec.funkce",
        "Funkce",
        frozenset({SCOPE_EMPLOYEE}),
        "Funkce uvedená na kartě zaměstnance.",
    ),
    PlaceholderDef(
        "zamestnanec.telefon",
        "Telefon",
        frozenset({SCOPE_EMPLOYEE}),
        "Telefon z karty zaměstnance.",
    ),
    PlaceholderDef(
        "zamestnanec.email",
        "E-mail",
        frozenset({SCOPE_EMPLOYEE}),
        "E-mail z karty zaměstnance.",
    ),
    PlaceholderDef(
        "zamestnanec.pracovni_kontakt",
        "Pracovní kontakt",
        frozenset({SCOPE_EMPLOYEE}),
        "Volitelný pracovní kontakt z karty.",
    ),
    PlaceholderDef(
        "zamestnanec.poznamka",
        "Poznámka",
        frozenset({SCOPE_EMPLOYEE}),
        "Poznámka z karty zaměstnance.",
    ),
    PlaceholderDef(
        "zamestnanec.stav",
        "Stav",
        frozenset({SCOPE_EMPLOYEE}),
        "Text „aktivní“ nebo „archivovaný“.",
    ),
    PlaceholderDef(
        "zamestnanec.den_nastupu",
        "Den nástupu",
        frozenset({SCOPE_EMPLOYEE}),
        "Den nástupu z aktuálního pracovního vztahu (dd.mm.rrrr).",
    ),
    PlaceholderDef(
        "zamestnanec.den_ukonceni",
        "Den ukončení",
        frozenset({SCOPE_EMPLOYEE}),
        "Den ukončení vztahu, pokud je vyplněn; jinak prázdné.",
    ),
    PlaceholderDef(
        "zamestnanec.mzdove_cislo",
        "Mzdové číslo",
        frozenset({SCOPE_EMPLOYEE}),
        "Mzdové číslo z pracovního vztahu (včetně počátečních nul).",
    ),
    PlaceholderDef(
        "zamestnanec.druh_vztahu",
        "Druh pracovního vztahu",
        frozenset({SCOPE_EMPLOYEE}),
        "Např. Pracovní poměr, DPP, DPČ.",
    ),
    PlaceholderDef(
        "zamestnanec.rezim_odmenovani",
        "Režim odměňování",
        frozenset({SCOPE_EMPLOYEE}),
        "Mzda nebo plat.",
    ),
    PlaceholderDef(
        "zamestnanec.funkce_ve_vztahu",
        "Funkce ve vztahu",
        frozenset({SCOPE_EMPLOYEE}),
        "Funkce uvedená u pracovního vztahu.",
    ),
    PlaceholderDef(
        "zamestnanec.uvazek",
        "Sjednaný úvazek",
        frozenset({SCOPE_EMPLOYEE}),
        "Sjednaná týdenní doba v hodinách (např. 40 nebo 37:30).",
    ),
    PlaceholderDef(
        "zamestnanec.stanovena_tydenni",
        "Stanovená týdenní doba",
        frozenset({SCOPE_EMPLOYEE}),
        "Stanovená týdenní pracovní doba z profilu úvazku.",
    ),
    PlaceholderDef(
        "zamestnanec.rezim_rozvrhu",
        "Režim rozvrhu",
        frozenset({SCOPE_EMPLOYEE}),
        "Jednosměnný / dvousměnný / vícesměnný / nepřetržitý.",
    ),
    PlaceholderDef(
        "zamestnanec.rozvrzeni",
        "Rozvržení",
        frozenset({SCOPE_EMPLOYEE}),
        "Rovnoměrné nebo nerovnoměrné rozvržení.",
    ),
    PlaceholderDef(
        "zamestnanec.platnost_uvazku_od",
        "Platnost úvazku od",
        frozenset({SCOPE_EMPLOYEE}),
        "Datum začátku platnosti aktivního profilu úvazku.",
    ),
    PlaceholderDef(
        "zamestnanec.platnost_uvazku_do",
        "Platnost úvazku do",
        frozenset({SCOPE_EMPLOYEE}),
        "Datum konce platnosti profilu úvazku, pokud je vyplněno.",
    ),
    PlaceholderDef(
        "pracoviste.nazev",
        "Pracoviště (hlavní)",
        frozenset({SCOPE_EMPLOYEE}),
        "Název prvního aktuálně platného přiřazeného pracoviště.",
    ),
    PlaceholderDef(
        "pracoviste.typ",
        "Typ pracoviště",
        frozenset({SCOPE_EMPLOYEE}),
        "Typ hlavního pracoviště (parkovací dům, kancelář…).",
    ),
    PlaceholderDef(
        "pracoviste.adresa",
        "Adresa pracoviště",
        frozenset({SCOPE_EMPLOYEE}),
        "Adresa hlavního pracoviště.",
    ),
    PlaceholderDef(
        "pracoviste.seznam",
        "Seznam pracovišť",
        frozenset({SCOPE_EMPLOYEE}),
        "Aktuálně platná pracoviště oddělená čárkou.",
    ),
)

VEHICLE_PLACEHOLDERS: tuple[PlaceholderDef, ...] = (
    PlaceholderDef(
        "vozidlo.spz",
        "SPZ",
        frozenset({SCOPE_VEHICLE}),
        "Registrační značka vozidla.",
    ),
    PlaceholderDef(
        "vozidlo.oznaceni",
        "Označení",
        frozenset({SCOPE_VEHICLE}),
        "Volitelný popis vozidla.",
    ),
    PlaceholderDef(
        "vozidlo.poznamka",
        "Poznámka",
        frozenset({SCOPE_VEHICLE}),
        "Poznámka u vozidla.",
    ),
    PlaceholderDef(
        "vozidlo.stav",
        "Stav",
        frozenset({SCOPE_VEHICLE}),
        "Text „aktivní“ nebo „archivované“.",
    ),
    PlaceholderDef(
        "vozidlo.odpovedna_osoba",
        "Odpovědná osoba",
        frozenset({SCOPE_VEHICLE}),
        "Celé jméno odpovědné osoby.",
    ),
    PlaceholderDef(
        "vozidlo.odpovedna_osoba_telefon",
        "Telefon odpovědné osoby",
        frozenset({SCOPE_VEHICLE}),
        "Telefon z karty odpovědné osoby.",
    ),
    PlaceholderDef(
        "vozidlo.odpovedna_osoba_email",
        "E-mail odpovědné osoby",
        frozenset({SCOPE_VEHICLE}),
        "E-mail z karty odpovědné osoby.",
    ),
    PlaceholderDef(
        "vozidlo.odpovedna_osoba_interni_cislo",
        "Interní číslo odpovědné osoby",
        frozenset({SCOPE_VEHICLE}),
        "Interní číslo odpovědné osoby.",
    ),
    PlaceholderDef(
        "vozidlo.stk_platnost_do",
        "Platnost STK do (zkratka)",
        frozenset({SCOPE_VEHICLE}),
        "Stejné jako doklad.stk.platnost_do.",
    ),
    PlaceholderDef(
        "vozidlo.pojistka_platnost_do",
        "Platnost pojistky do (zkratka)",
        frozenset({SCOPE_VEHICLE}),
        "Stejné jako doklad.pojistka.platnost_do.",
    ),
)

STATIC_PLACEHOLDERS: tuple[PlaceholderDef, ...] = (
    COMMON_PLACEHOLDERS + EMPLOYEE_PLACEHOLDERS + VEHICLE_PLACEHOLDERS
)
ALL_PLACEHOLDERS = STATIC_PLACEHOLDERS

_BY_KEY = {item.key: item for item in STATIC_PLACEHOLDERS}

QUAL_SUFFIXES = (
    ("cislo", "číslo / evidenční znak"),
    ("skupiny", "skupiny / rozsah"),
    ("platnost_od", "platnost od (dd.mm.rrrr)"),
    ("platnost_do", "platnost do (dd.mm.rrrr)"),
    ("vydal", "vydal"),
)

DOC_SUFFIXES = (
    ("cislo", "číslo / evidenční znak"),
    ("platnost_od", "platnost od (dd.mm.rrrr)"),
    ("platnost_do", "platnost do (dd.mm.rrrr)"),
    ("vydal", "vydal"),
    ("poznamka", "poznámka dokladu"),
)


def token_for(key: str) -> str:
    return "{{" + key + "}}"


def _dynamic_qualification_placeholders() -> list[PlaceholderDef]:
    from apps.employees.models import QualificationType

    items: list[PlaceholderDef] = []
    for qtype in QualificationType.objects.filter(is_active=True).order_by(
        "sort_order", "name"
    ):
        for suffix, suffix_label in QUAL_SUFFIXES:
            key = f"kvalifikace.{qtype.code}.{suffix}"
            items.append(
                PlaceholderDef(
                    key,
                    f"{qtype.name}: {suffix_label}",
                    frozenset({SCOPE_EMPLOYEE}),
                    f"Údaj „{suffix_label}“ z aktivní kvalifikace typu {qtype.name}.",
                )
            )
    return items


def _dynamic_vehicle_doc_placeholders() -> list[PlaceholderDef]:
    from apps.technika.models import VehicleDocumentType

    items: list[PlaceholderDef] = []
    for dtype in VehicleDocumentType.objects.filter(is_active=True).order_by(
        "sort_order", "name"
    ):
        for suffix, suffix_label in DOC_SUFFIXES:
            key = f"doklad.{dtype.code}.{suffix}"
            items.append(
                PlaceholderDef(
                    key,
                    f"{dtype.name}: {suffix_label}",
                    frozenset({SCOPE_VEHICLE}),
                    f"Údaj „{suffix_label}“ z aktivního dokladu typu {dtype.name}.",
                )
            )
    return items


def placeholders_for_scope(scope: str) -> list[PlaceholderDef]:
    """Společné + placeholdery daného okruhu včetně dynamických z číselníků."""
    result: list[PlaceholderDef] = []
    for item in STATIC_PLACEHOLDERS:
        if SCOPE_COMMON in item.scopes or scope in item.scopes:
            result.append(item)
    if scope == SCOPE_EMPLOYEE:
        result.extend(_dynamic_qualification_placeholders())
    elif scope == SCOPE_VEHICLE:
        result.extend(_dynamic_vehicle_doc_placeholders())
    return result


def allowed_keys_for_scope(scope: str) -> frozenset[str]:
    return frozenset(item.key for item in placeholders_for_scope(scope))


def get_placeholder(key: str, scope: str | None = None) -> PlaceholderDef | None:
    found = _BY_KEY.get(key)
    if found is not None:
        return found
    if scope:
        for item in placeholders_for_scope(scope):
            if item.key == key:
                return item
    return None
