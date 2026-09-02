"""
Collection-spec tests: the AIFS and IFS specs parse through the core
collection-definition parser, and the shared-core variables (keys and
exposed units) are identical between the two models. No Django, no network.
"""

import dataclasses
import unittest

from georiva.sources.collection_definitions import parse_collection_defs

from georiva_source_ecmwf.collection_specs import (
    AIFS_COLLECTIONS,
    AIFS_PRESSURE_LEVELS,
    IFS_COLLECTIONS,
    IFS_PRESSURE_LEVELS,
)

SHARED_SURFACE_KEYS = [
    "2t",
    "10u",
    "10v",
    "msl",
    "tp",
    "sp",
    "wind_speed_10m",
    "wind_dir_10m",
]

# The variables that make IFS worth having beyond AIFS parity. Convective
# precipitation (cp) is deliberately absent: the 0.25° oper open-data
# files do not publish it (verified against live .index files).
IFS_ONLY_SURFACE_KEYS = ["cape", "ptype", "10fg", "2d", "tcwv", "ssrd"]


def _by_key(definitions):
    return {d.key: d for d in definitions}


class IFSCollectionSpecTest(unittest.TestCase):
    def setUp(self):
        self.defs = _by_key(parse_collection_defs(IFS_COLLECTIONS))

    def test_parses_into_the_two_expected_collections(self):
        self.assertEqual(
            set(self.defs),
            {"ecmwf-ifs-surface", "ecmwf-ifs-pressure-levels"},
        )
        for d in self.defs.values():
            self.assertTrue(d.is_forecast)

    def test_surface_carries_shared_core_plus_ifs_only_variables(self):
        surface = self.defs["ecmwf-ifs-surface"]
        self.assertEqual(
            [v.key for v in surface.variables],
            SHARED_SURFACE_KEYS + IFS_ONLY_SURFACE_KEYS,
        )

    def test_pressure_levels_extend_the_aifs_list(self):
        self.assertEqual(
            IFS_PRESSURE_LEVELS,
            [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50],
        )
        self.assertEqual(
            set(IFS_PRESSURE_LEVELS) - set(AIFS_PRESSURE_LEVELS),
            {600, 400, 150, 100},
        )
        pl = self.defs["ecmwf-ifs-pressure-levels"]
        expected_keys = [
            f"{base}_{lv}"
            for base in ("t", "u", "v", "z", "q")
            for lv in IFS_PRESSURE_LEVELS
        ]
        self.assertEqual([v.key for v in pl.variables], expected_keys)

    def test_each_pressure_level_has_a_group(self):
        pl = self.defs["ecmwf-ifs-pressure-levels"]
        groups = {g.key: g for g in pl.groups}
        for lv in IFS_PRESSURE_LEVELS:
            self.assertIn(f"pl-{lv}", groups)
            self.assertEqual(
                list(groups[f"pl-{lv}"].variable_keys),
                [f"t_{lv}", f"u_{lv}", f"v_{lv}", f"z_{lv}", f"q_{lv}"],
            )

    def test_derived_wind_variables_use_vector_transforms(self):
        surface = self.defs["ecmwf-ifs-surface"]
        self.assertEqual(
            surface.get_variable("wind_speed_10m").transform, "vector_magnitude"
        )
        self.assertEqual(
            surface.get_variable("wind_dir_10m").transform, "vector_direction"
        )


class SharedCoreParityTest(unittest.TestCase):
    """Shared-core variables must match AIFS exactly: same keys, same
    exposed (output) units, same source addressing — so the two models
    render comparably side by side."""

    def setUp(self):
        self.aifs = _by_key(parse_collection_defs(AIFS_COLLECTIONS))
        self.ifs = _by_key(parse_collection_defs(IFS_COLLECTIONS))

    def test_surface_shared_core_matches_aifs_exactly(self):
        # Parity is on what the platform exposes: key, name, exposed unit,
        # transform, addressing, range. Source units may differ per model —
        # the two portals stamp the same field differently (tp: IFS metres,
        # AIFS kg m-2) — as long as both land on the same exposed unit.
        aifs_surface = self.aifs["ecmwf-aifs-surface"]
        ifs_surface = self.ifs["ecmwf-ifs-surface"]
        for key in SHARED_SURFACE_KEYS:
            a = aifs_surface.get_variable(key)
            i = ifs_surface.get_variable(key)
            self.assertEqual(
                dataclasses.replace(
                    a, source_units=i.source_units, output_units=i.output_units
                ),
                i,
                key,
            )
            self.assertEqual(a.exposed_units, i.exposed_units, key)

    def test_pressure_level_variables_match_aifs_at_shared_levels(self):
        aifs_pl = self.aifs["ecmwf-aifs-pressure-levels"]
        ifs_pl = self.ifs["ecmwf-ifs-pressure-levels"]
        for v in aifs_pl.variables:
            self.assertEqual(v, ifs_pl.get_variable(v.key), v.key)


class AIFSTpUnitsTest(unittest.TestCase):
    """AIFS open-data tp is published as kg m-2 (paramId 228228) — numerically
    millimetres — unlike IFS, whose tp is metres (paramId 228). The AIFS spec
    must not apply the m->mm x1000 conversion (issue #15)."""

    def test_aifs_tp_is_millimetres_with_no_conversion(self):
        surface = _by_key(parse_collection_defs(AIFS_COLLECTIONS))["ecmwf-aifs-surface"]
        tp = surface.get_variable("tp")
        self.assertEqual(tp.source_units, "mm")
        self.assertEqual(tp.exposed_units, "mm")

    def test_ifs_tp_still_converts_metres_to_millimetres(self):
        surface = _by_key(parse_collection_defs(IFS_COLLECTIONS))["ecmwf-ifs-surface"]
        tp = surface.get_variable("tp")
        self.assertEqual(tp.source_units, "m")
        self.assertEqual(tp.output_units, "mm")


class IFSOnlySurfaceVariablesTest(unittest.TestCase):
    """The IFS-only surface variables. shortNames, units, levels and
    value spans were verified against live IFS GRIB2 messages; the
    `.index` param names against the committed portal index fixture."""

    def setUp(self):
        defs = _by_key(parse_collection_defs(IFS_COLLECTIONS))
        self.surface = defs["ecmwf-ifs-surface"]

    def test_cape_reads_the_published_mucape_message(self):
        # The portal publishes most-unstable CAPE under index param /
        # shortName "mucape"; there is no plain "cape" message.
        cape = self.surface.get_variable("cape")
        self.assertEqual(cape.source_variable.name, "mucape")
        self.assertEqual(cape.source_units, "J kg-1")
        self.assertIsNone(cape.output_units)

    def test_dewpoint_converts_to_celsius_at_2m(self):
        d2 = self.surface.get_variable("2d")
        self.assertEqual(d2.source_units, "K")
        self.assertEqual(d2.output_units, "degC")
        self.assertEqual(d2.source_variable.name, "2d")
        self.assertEqual(d2.source_variable.level.dimension, "heightAboveGround")
        self.assertEqual(d2.source_variable.level.value, 2)

    def test_gust_is_a_10m_height_field_in_metres_per_second(self):
        gust = self.surface.get_variable("10fg")
        self.assertEqual(gust.source_units, "m/s")
        self.assertEqual(gust.source_variable.level.value, 10)

    def test_solar_radiation_exposes_megajoules(self):
        ssrd = self.surface.get_variable("ssrd")
        self.assertEqual(ssrd.source_units, "J m-2")
        self.assertEqual(ssrd.output_units, "MJ m-2")

    def test_precipitation_type_is_a_dimensionless_code(self):
        ptype = self.surface.get_variable("ptype")
        self.assertEqual(ptype.source_units, "dimensionless")
        self.assertIsNone(ptype.output_units)
        self.assertEqual(ptype.value_range, (0.0, 12.0))

    def test_every_ifs_only_variable_declares_a_value_range(self):
        for key in IFS_ONLY_SURFACE_KEYS:
            self.assertIsNotNone(self.surface.get_variable(key).value_range, key)

    def test_ifs_only_variables_are_grouped_by_theme(self):
        groups = {g.key: g for g in self.surface.groups}
        self.assertEqual(
            list(groups["convection"].variable_keys), ["cape", "ptype", "10fg"]
        )
        self.assertEqual(
            list(groups["moisture-radiation"].variable_keys), ["2d", "tcwv", "ssrd"]
        )
        # The shared-core groups keep their AIFS shape.
        self.assertEqual(
            list(groups["temp-pressure"].variable_keys), ["2t", "msl", "sp", "tp"]
        )


class AIFSSpecUnchangedTest(unittest.TestCase):
    """Locks the spec-sharing refactor: the AIFS definitions keep their
    exact shape (collections, variable count, keys)."""

    def test_aifs_definitions_keep_their_shape(self):
        defs = _by_key(parse_collection_defs(AIFS_COLLECTIONS))
        self.assertEqual(
            set(defs), {"ecmwf-aifs-surface", "ecmwf-aifs-pressure-levels"}
        )
        self.assertEqual(len(defs["ecmwf-aifs-surface"].variables), 8)
        self.assertEqual(
            len(defs["ecmwf-aifs-pressure-levels"].variables),
            5 * len(AIFS_PRESSURE_LEVELS),
        )


if __name__ == "__main__":
    unittest.main()
