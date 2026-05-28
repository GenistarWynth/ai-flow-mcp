from __future__ import annotations

import json
import unittest

from scripts.ai_flow.usage import metrics_from_output, metrics_from_text, metrics_from_value, with_usage


class UsageMetricsTest(unittest.TestCase):
    def test_extracts_claude_stream_json_result_usage(self) -> None:
        output = "\n".join(
            [
                json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]}}),
                json.dumps(
                    {
                        "type": "result",
                        "total_cost_usd": 0.012345,
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 20,
                            "cache_creation_input_tokens": 5,
                            "cache_read_input_tokens": 7,
                        },
                    }
                ),
            ]
        )

        metrics = metrics_from_text(output)

        self.assertTrue(metrics["token_usage"]["known"])
        self.assertEqual(metrics["token_usage"]["input_tokens"], 100)
        self.assertEqual(metrics["token_usage"]["output_tokens"], 20)
        self.assertEqual(metrics["token_usage"]["cached_tokens"], 12)
        self.assertEqual(metrics["token_usage"]["total_tokens"], 132)
        self.assertTrue(metrics["cost"]["known"])
        self.assertEqual(metrics["cost"]["estimated_total"], 0.012345)

    def test_attached_usage_survives_string_contracts(self) -> None:
        output = with_usage(
            "PASS\n",
            metrics_from_value({"usage": {"prompt_tokens": 30, "completion_tokens": 10}, "cost_usd": 0.004}),
        )

        metrics = metrics_from_output(output)

        self.assertTrue(isinstance(output, str))
        self.assertEqual(metrics["token_usage"]["total_tokens"], 40)
        self.assertEqual(metrics["cost"]["estimated_total"], 0.004)


if __name__ == "__main__":
    unittest.main()
