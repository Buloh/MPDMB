"""Testy jádra (auditní popisky)."""

from django.test import SimpleTestCase

from .audit_labels import object_type_label, operation_label


class AuditLabelsTests(SimpleTestCase):
    def test_known_operations_are_czech(self):
        self.assertEqual(
            operation_label("activity_location.create"),
            "Lokalita činnosti: vytvoření",
        )
        self.assertEqual(
            operation_label("workplace_assign"),
            "Přiřazení pracoviště",
        )
        self.assertEqual(operation_label("shift_cell_create"), "Vytvoření směny v buňce")

    def test_unknown_operation_marks_missing_map(self):
        label = operation_label("totally.unknown_op")
        self.assertIn("totally.unknown_op", label)
        self.assertIn("bez české mapy", label)

    def test_object_types(self):
        self.assertEqual(object_type_label("ActivityLocation"), "Lokalita činnosti")
        self.assertIn("bez české mapy", object_type_label("UnknownThing"))
