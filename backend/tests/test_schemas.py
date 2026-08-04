import json
import unittest
from datetime import datetime, timedelta, timezone

from backend.schemas import AnalysisResponse, CrashSummary, SymbolPackageSummary


class UtcDateTimeSerializationTests(unittest.TestCase):
    def test_naive_database_datetime_is_serialized_as_utc(self):
        crash = CrashSummary(
            id="crash-1",
            upload_time=datetime(2026, 8, 3, 9, 36, 2),
            status="parsed",
        )

        payload = json.loads(crash.model_dump_json())

        self.assertEqual(payload["upload_time"], "2026-08-03T09:36:02Z")

    def test_aware_datetime_is_converted_to_utc(self):
        report = AnalysisResponse(
            id=1,
            crash_id="crash-1",
            agent_type="copilot",
            created_at=datetime(
                2026,
                8,
                3,
                17,
                36,
                2,
                tzinfo=timezone(timedelta(hours=8)),
            ),
        )

        payload = json.loads(report.model_dump_json())

        self.assertEqual(payload["created_at"], "2026-08-03T09:36:02Z")

    def test_symbol_upload_time_uses_the_same_utc_contract(self):
        symbol = SymbolPackageSummary(
            id="symbol-1",
            platform="Windows",
            status="ready",
            upload_time=datetime(2026, 8, 3, 9, 36, 2),
        )

        payload = json.loads(symbol.model_dump_json())

        self.assertEqual(payload["upload_time"], "2026-08-03T09:36:02Z")


if __name__ == "__main__":
    unittest.main()
