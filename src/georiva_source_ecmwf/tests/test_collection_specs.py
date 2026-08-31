"""
Collection-spec tests: the AIFS and IFS specs parse through the core
collection-definition parser, and the shared-core variables (keys and
exposed units) are identical between the two models. No Django, no network.
"""

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

    def test_surface_carries_exactly_the_shared_core_variables(self):
        surface = self.defs["ecmwf-ifs-surface"]
        self.assertEqual(
            [v.key for v in surface.variables],
            SHARED_SURFACE_KEYS,
        )

    def test_pressure_levels_are_the_aifs_list(self):
        self.assertEqual(IFS_PRESSURE_LEVELS, AIFS_PRESSURE_LEVELS)
        pl = self.defs["ecmwf-ifs-pressure-levels"]
        expected_keys = [
            f"{base}_{lv}"
            for base in ("t", "u", "v", "z", "q")
            for lv in AIFS_PRESSURE_LEVELS
        ]
        self.assertEqual([v.key for v in pl.variables], expected_keys)

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
        aifs_surface = self.aifs["ecmwf-aifs-surface"]
        ifs_surface = self.ifs["ecmwf-ifs-surface"]
        for key in SHARED_SURFACE_KEYS:
            self.assertEqual(
                aifs_surface.get_variable(key), ifs_surface.get_variable(key), key
            )

    def test_pressure_level_variables_match_aifs_exactly(self):
        aifs_pl = self.aifs["ecmwf-aifs-pressure-levels"]
        ifs_pl = self.ifs["ecmwf-ifs-pressure-levels"]
        self.assertEqual(aifs_pl.variables, ifs_pl.variables)


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
