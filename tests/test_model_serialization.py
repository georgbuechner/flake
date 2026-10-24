"""Round-trip experiment state used by generated documents."""
import unittest

from data_manager.tables import General, table_to_json


class ModelSerializationTests(unittest.TestCase):
    def test_general_round_trip_preserves_dates_and_weight_data(self):
        original = General("animal", "Protocol/Subprotocol", True, "Leicht")
        original.start = "2025-01-01"
        original.end = "2025-01-03"
        original.start_weight = 22.5
        original.weights = "[22.5, null, 23.0]"
        original.watercontrol_mask = "[false, true, false]"
        payload = table_to_json(original)

        restored = General.from_json(payload)

        self.assertEqual(table_to_json(restored), payload)


if __name__ == "__main__":
    unittest.main()
