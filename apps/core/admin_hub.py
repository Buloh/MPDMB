"""Rozcestník Administrace — odkazy do Django adminu."""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from apps.core.dashboard import DashboardTile


@dataclass(frozen=True)
class AdminHubSection:
    title: str
    tiles: tuple[DashboardTile, ...]


def _tile(
    key: str,
    title: str,
    description: str,
    icon: str,
    admin_name: str,
) -> DashboardTile:
    return DashboardTile(
        key=key,
        title=title,
        description=description,
        icon=icon,
        url_path=reverse(f"admin:{admin_name}"),
    )


def admin_hub_sections() -> list[AdminHubSection]:
    """Sekce dlaždic na rozcestníku Administrace."""
    return [
        AdminHubSection(
            title="Účty a oprávnění",
            tiles=(
                _tile(
                    "users",
                    "Uživatelé",
                    "Účty, role a přístup do administrace.",
                    "users",
                    "accounts_user_changelist",
                ),
                _tile(
                    "groups",
                    "Skupiny",
                    "Role a oprávnění skupin.",
                    "admin",
                    "auth_group_changelist",
                ),
            ),
        ),
        AdminHubSection(
            title="Audit",
            tiles=(
                _tile(
                    "audit",
                    "Auditní události",
                    "Záznamy důležitých změn v systému.",
                    "audit",
                    "core_auditevent_changelist",
                ),
            ),
        ),
        AdminHubSection(
            title="Číselníky provozu",
            tiles=(
                _tile(
                    "shift_types",
                    "Typy směn",
                    "Kódy a pravidla typů směn.",
                    "shifts",
                    "shifts_shifttype_changelist",
                ),
                _tile(
                    "work_time_presets",
                    "Předvolby úvazku",
                    "Šablony týdenní pracovní doby.",
                    "ops",
                    "employees_worktimepreset_changelist",
                ),
                _tile(
                    "qualification_types",
                    "Typy kvalifikací",
                    "Řidičské průkazy a zkoušky.",
                    "employees",
                    "employees_qualificationtype_changelist",
                ),
                _tile(
                    "absence_types",
                    "Typy absencí",
                    "Dovolená, nemoc a další nepřítomnosti.",
                    "attendance",
                    "attendance_absencetype_changelist",
                ),
                _tile(
                    "meal",
                    "Stravné",
                    "Prahové minuty pro stravenky.",
                    "attendance",
                    "attendance_mealallowancesettings_changelist",
                ),
                _tile(
                    "leave_policy",
                    "Pravidla dovolené",
                    "Výchozí nároky a nastavení.",
                    "leave",
                    "leave_leavepolicysettings_changelist",
                ),
                _tile(
                    "leave_settings",
                    "Nastavení dovolené zaměstnanců",
                    "Individuální odchylky nároku.",
                    "leave",
                    "leave_employeeleavesettings_changelist",
                ),
                _tile(
                    "leave_entitlement",
                    "Nároky dovolené",
                    "Roční nároky a zůstatky.",
                    "leave",
                    "leave_leaveentitlement_changelist",
                ),
            ),
        ),
        AdminHubSection(
            title="Činnost, technika a dokumenty",
            tiles=(
                _tile(
                    "map_cities",
                    "Mapová města",
                    "Města pro mapu lokalit.",
                    "activities",
                    "activities_mapcity_changelist",
                ),
                _tile(
                    "activity_types",
                    "Typy činností",
                    "Číselník typů plánovaných činností.",
                    "activities",
                    "activities_activitytype_changelist",
                ),
                _tile(
                    "activity_locations",
                    "Lokality činností",
                    "Správa lokalit (pokročilé).",
                    "activities",
                    "activities_activitylocation_changelist",
                ),
                _tile(
                    "vehicle_doc_types",
                    "Typy dokladů vozidel",
                    "STK, pojistka a další doklady.",
                    "technika",
                    "technika_vehicledocumenttype_changelist",
                ),
                _tile(
                    "doc_templates",
                    "Šablony dokumentů",
                    "Word šablony s placeholdery.",
                    "documents",
                    "documents_documenttemplate_changelist",
                ),
                _tile(
                    "doc_versions",
                    "Verze šablon",
                    "Historie nahraných verzí šablon.",
                    "documents",
                    "documents_documenttemplateversion_changelist",
                ),
                _tile(
                    "stored_docs",
                    "Uložené dokumenty",
                    "Vygenerované Word soubory.",
                    "documents",
                    "documents_storeddocument_changelist",
                ),
            ),
        ),
    ]
