"""Plán činností v rámci směny (oddělený od docházky a úkolů)."""

from __future__ import annotations

import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


LOCATION_COLOR_PALETTE = (
    "#166999",
    "#21759B",
    "#237A35",
    "#865600",
    "#B42318",
    "#6EC1E4",
    "#7B2D8E",
    "#C45C26",
    "#2F6F7E",
    "#5B6B2F",
)

_color_hex_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Zadejte barvu ve formátu #RRGGBB.",
)


def next_location_color() -> str:
    """Další výchozí barva z palety podle počtu lokalit."""
    count = ActivityLocation.objects.count()
    return LOCATION_COLOR_PALETTE[count % len(LOCATION_COLOR_PALETTE)]


class ActivityType(models.Model):
    class TravelMode(models.TextChoices):
        NONE = "none", "Bez přesunu"
        CAR = "car", "Automobilem"
        WALK = "walk", "Pěšky"

    code = models.CharField("kód", max_length=32, unique=True)
    name = models.CharField("název", max_length=80)
    travel_mode = models.CharField(
        "způsob přesunu",
        max_length=16,
        choices=TravelMode.choices,
        default=TravelMode.NONE,
        help_text="Pro budoucí výpočet přejezdů; v této etapě jen evidence.",
    )
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField("pořadí", default=100)

    class Meta:
        verbose_name = "typ činnosti"
        verbose_name_plural = "typy činností"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class MapCity(models.Model):
    """Střed mapy pro výběr města (více měst činností)."""

    code = models.CharField("kód", max_length=32, unique=True)
    name = models.CharField("název", max_length=120)
    center_lat = models.DecimalField(
        "zeměpisná šířka (lat)",
        max_digits=9,
        decimal_places=6,
        help_text="Pořadí: lat, lon (např. Mladá Boleslav ≈ 50.411350, 14.903180).",
    )
    center_lon = models.DecimalField(
        "zeměpisná délka (lon)",
        max_digits=9,
        decimal_places=6,
        help_text="Nepřehazujte lat a lon.",
    )
    default_zoom = models.PositiveSmallIntegerField(
        "výchozí zoom",
        default=14,
        help_text="Typicky 12–16.",
    )
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    is_default = models.BooleanField(
        "výchozí město",
        default=False,
        help_text="Nejvýše jedno výchozí aktivní město.",
    )
    sort_order = models.PositiveSmallIntegerField("pořadí", default=100)

    class Meta:
        verbose_name = "mapové město"
        verbose_name_plural = "mapová města"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.default_zoom < 1 or self.default_zoom > 20:
            raise ValidationError(
                {"default_zoom": "Zoom musí být v rozsahu 1–20."}
            )
        if self.is_default and self.is_active:
            qs = MapCity.objects.filter(is_default=True, is_active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    {
                        "is_default": "Jiná aktivní lokalita už je nastavená jako výchozí."
                    }
                )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default and self.is_active:
            MapCity.objects.filter(is_default=True).exclude(pk=self.pk).update(
                is_default=False
            )


class ActivityLocation(models.Model):
    code = models.CharField("kód", max_length=32, unique=True)
    name = models.CharField("název", max_length=120)
    description = models.TextField("popis", blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="nadřazená lokace",
        help_text="Prázdné = hlavní lokace. Jinak podlokace (max. jedna úroveň).",
    )
    workplace = models.ForeignKey(
        "workplaces.Workplace",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_locations",
        verbose_name="pracoviště",
    )
    geojson = models.TextField(
        "GeoJSON polygon",
        help_text="Polygon lokality (GeoJSON Feature nebo Geometry).",
    )
    color = models.CharField(
        "barva",
        max_length=7,
        default="#166999",
        validators=[_color_hex_validator],
        help_text="Barva polygonu na mapě (#RRGGBB).",
    )
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField("pořadí", default=100)
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "lokalita činnosti"
        verbose_name_plural = "lokality činností"
        ordering = ["sort_order", "code"]

    def __str__(self) -> str:
        return self.hierarchy_label()

    @property
    def is_main(self) -> bool:
        return self.parent_id is None

    def hierarchy_label(self) -> str:
        own = f"{self.code} – {self.name}"
        if self.parent_id:
            parent = self.parent
            return f"{parent.code} › {own}"
        return own

    def clean(self) -> None:
        super().clean()
        if self.parent_id:
            if self.pk and self.parent_id == self.pk:
                raise ValidationError(
                    {"parent": "Lokalita nemůže být nadřazená sama sobě."}
                )
            parent = self.parent
            if parent is not None and parent.parent_id is not None:
                raise ValidationError(
                    {
                        "parent": "Nadřazená lokace musí být hlavní (bez další nadřazené)."
                    }
                )
            if self.pk and self.children.exists():
                raise ValidationError(
                    {
                        "parent": "Lokalita s podlokacemi nemůže být podlokací."
                    }
                )
        if not self.geojson or not str(self.geojson).strip():
            raise ValidationError({"geojson": "Zadejte polygon lokality."})
        if self.color:
            self.color = str(self.color).strip().upper()
        try:
            data = json.loads(self.geojson)
        except json.JSONDecodeError as exc:
            raise ValidationError({"geojson": "Neplatný JSON."}) from exc
        geom = data
        if isinstance(data, dict) and data.get("type") == "Feature":
            geom = data.get("geometry") or {}
        if not isinstance(geom, dict) or geom.get("type") != "Polygon":
            raise ValidationError(
                {"geojson": "Očekáván GeoJSON typu Polygon (nebo Feature s Polygon)."}
            )
        coords = geom.get("coordinates")
        if not coords or not isinstance(coords, list) or not coords[0]:
            raise ValidationError({"geojson": "Polygon musí obsahovat souřadnice."})

    def geometry_dict(self) -> dict:
        data = json.loads(self.geojson)
        if isinstance(data, dict) and data.get("type") == "Feature":
            return data.get("geometry") or {}
        return data


class ActivityItem(models.Model):
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="activity_items",
        verbose_name="zaměstnanec",
    )
    day = models.DateField("den", db_index=True)
    shift = models.ForeignKey(
        "shifts.Shift",
        on_delete=models.PROTECT,
        related_name="activity_items",
        verbose_name="směna",
    )
    location = models.ForeignKey(
        ActivityLocation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activity_items",
        verbose_name="lokalita",
        help_text="Volitelné — činnost může být i bez lokality (požadavek, poznámka).",
    )
    activity_type = models.ForeignKey(
        ActivityType,
        on_delete=models.PROTECT,
        related_name="activity_items",
        verbose_name="typ činnosti",
    )
    vehicle = models.ForeignKey(
        "technika.Vehicle",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activity_items",
        verbose_name="vozidlo",
        help_text="Volitelné — jen pokud je vozidlo potřeba.",
    )
    starts_at = models.DateTimeField("začátek")
    ends_at = models.DateTimeField("konec")
    sort_order = models.PositiveSmallIntegerField("pořadí", default=100)
    note = models.TextField("poznámka", blank=True)
    all_day = models.BooleanField(
        "celý den",
        default=False,
        db_index=True,
        help_text="Denní úkol mimo hodinovou mřížku (např. kontrola 4×).",
    )
    version = models.PositiveIntegerField("verze", default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_activity_items",
        verbose_name="vytvořil",
    )
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "činnost"
        verbose_name_plural = "činnosti"
        ordering = ["day", "sort_order", "starts_at", "id"]
        permissions = [
            (
                "export_activity_plan",
                "Může exportovat plán činností",
            ),
        ]
        indexes = [
            models.Index(fields=["employee", "day"]),
            models.Index(fields=["shift"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="activity_item_ends_after_starts",
            ),
        ]

    def __str__(self) -> str:
        loc = self.location.code if self.location_id else "bez lokality"
        return f"{self.day:%d.%m.%Y} · {loc} · {self.activity_type}"

    def clean(self) -> None:
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError(
                {"ends_at": "Konec musí být později než začátek."}
            )


class ActivityPreference(models.Model):
    """Preferovaná lokalita zaměstnance a relativní četnost (váha) pro generátor.

    Další požadavky / typy lze později navázat přes default_activity_type
    nebo samostatnou entitu — matice slotů to nevyžaduje.
    """

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="activity_preferences",
        verbose_name="zaměstnanec",
    )
    location = models.ForeignKey(
        ActivityLocation,
        on_delete=models.PROTECT,
        related_name="activity_preferences",
        verbose_name="lokalita",
    )
    frequency = models.PositiveSmallIntegerField(
        "četnost (váha)",
        default=1,
        help_text="Relativní podíl hodin ve směně (např. 2 a 1 = 2/3 a 1/3).",
    )
    sort_order = models.PositiveSmallIntegerField("pořadí", default=100)
    default_activity_type = models.ForeignKey(
        ActivityType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_preferences",
        verbose_name="výchozí typ činnosti",
        help_text="Pro generátor a budoucí požadavky; prázdné = výchozí typ z číselníku.",
    )

    class Meta:
        verbose_name = "preference činnosti"
        verbose_name_plural = "preference činností"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "location"],
                name="activity_pref_employee_location_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(frequency__gte=1),
                name="activity_pref_frequency_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee} · {self.location.code} ×{self.frequency}"

    def clean(self) -> None:
        super().clean()
        if self.frequency is not None and self.frequency < 1:
            raise ValidationError({"frequency": "Četnost musí být alespoň 1."})
