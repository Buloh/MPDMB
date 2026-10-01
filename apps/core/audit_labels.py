"""České popisky auditních kódů (DB zůstává anglicky)."""

from __future__ import annotations

OPERATION_LABELS: dict[str, str] = {
    # Směny
    "shift_create": "Vytvoření směny",
    "shift_update": "Úprava směny",
    "shift_cell_create": "Vytvoření směny v buňce",
    "shift_cell_update": "Úprava směny v buňce",
    "shift_publish": "Publikace směny",
    "shift_cancel": "Zrušení směny",
    "shift_bulk_delete_oct": "Hromadné smazání směn (říjen)",
    # Zaměstnanci
    "employee_create": "Vytvoření zaměstnance",
    "employee_update": "Úprava zaměstnance",
    "employee_archive": "Archivace zaměstnance",
    "employment_create": "Vytvoření pracovního vztahu",
    "employment_update": "Úprava pracovního vztahu",
    "qualification_save": "Uložení kvalifikace",
    "qualification_delete": "Smazání kvalifikace",
    "workplace_assign": "Přiřazení pracoviště",
    "workplace_unassign": "Odebrání pracoviště",
    "work_time_create": "Vytvoření profilu pracovní doby",
    "work_time_update": "Úprava profilu pracovní doby",
    "work_time_close": "Ukončení profilu pracovní doby",
    "work_time_profile_bulk_create": "Hromadné vytvoření profilů pracovní doby",
    "balancing_period_bulk_create": "Hromadné vytvoření vyrovnávacích období",
    "leave_settings_save": "Uložení nastavení dovolené",
    # Docházka
    "attendance.ad_hoc_work": "Docházka: ad-hoc práce",
    "attendance.ad_hoc_delete": "Docházka: smazání ad-hoc práce",
    "attendance.confirm_work": "Docházka: potvrzení práce",
    "attendance.set_absence": "Docházka: nastavení absence",
    "attendance.update_absence": "Docházka: úprava absence",
    "attendance.clear": "Docházka: vymazání u směny",
    # Dovolená
    "leave.plan_create": "Dovolená: vytvoření plánu",
    "leave.plan_approve": "Dovolená: schválení plánu",
    "leave.plan_cancel": "Dovolená: zrušení plánu",
    # Činnosti
    "activity.create": "Činnost: vytvoření",
    "activity.update": "Činnost: úprava",
    "activity.delete": "Činnost: smazání",
    "activity.generate": "Činnost: generování plánu dne",
    "activity.clear_day": "Činnost: vymazání plánu dne",
    "activity_preference.save": "Činnost: uložení preferencí",
    "activity_location.create": "Lokalita činnosti: vytvoření",
    "activity_location.update": "Lokalita činnosti: úprava",
    # Technika
    "vehicle_create": "Vytvoření vozidla",
    "vehicle_update": "Úprava vozidla",
    "vehicle_archive": "Archivace vozidla",
    "vehicle_document_save": "Uložení dokladu vozidla",
    "vehicle_document_delete": "Smazání dokladu vozidla",
    # Dokumenty (Word)
    "document_template_create": "Vytvoření šablony dokumentu",
    "document_template_version": "Nová verze šablony dokumentu",
    "document_template_placeholder": "Vložení placeholderu do šablony",
    "document_template_deactivate": "Deaktivace šablony dokumentu",
    "document_template_activate": "Aktivace šablony dokumentu",
    "document_generate": "Vygenerování dokumentu",
    "document_upload": "Nahrání dokumentu",
    "document_archive": "Archivace dokumentu",
    "document_delete": "Smazání dokumentu",
}

OBJECT_TYPE_LABELS: dict[str, str] = {
    "Shift": "Směna",
    "Employee": "Zaměstnanec",
    "Employment": "Pracovní vztah",
    "EmployeeQualification": "Kvalifikace zaměstnance",
    "QualificationType": "Typ kvalifikace",
    "WorkTimeProfile": "Profil pracovní doby",
    "BalancingPeriod": "Vyrovnávací období",
    "Workplace": "Pracoviště",
    "EmployeeWorkplace": "Přiřazení pracoviště",
    "ScheduleTemplate": "Šablona směn",
    "ShiftType": "Typ směny",
    "WorkInterval": "Pracovní interval",
    "Absence": "Absence",
    "LeavePlan": "Plán dovolené",
    "ActivityItem": "Položka činnosti",
    "ActivityLocation": "Lokalita činnosti",
    "ActivityPreference": "Preference činnosti",
    "EmployeeLeaveSettings": "Nastavení dovolené zaměstnance",
    "Vehicle": "Vozidlo",
    "VehicleDocument": "Doklad vozidla",
    "VehicleDocumentType": "Typ dokladu vozidla",
    "DocumentTemplate": "Šablona dokumentu",
    "DocumentTemplateVersion": "Verze šablony dokumentu",
    "StoredDocument": "Uložený dokument",
}


def operation_label(code: str) -> str:
    if not code:
        return "—"
    label = OPERATION_LABELS.get(code)
    if label:
        return label
    return f"{code} (bez české mapy)"


def object_type_label(code: str) -> str:
    if not code:
        return "—"
    label = OBJECT_TYPE_LABELS.get(code)
    if label:
        return label
    return f"{code} (bez české mapy)"
