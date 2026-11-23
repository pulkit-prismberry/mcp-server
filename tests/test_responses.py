"""Unit tests for response formatting helpers."""
import unittest
from utils.responses import success_response, error_response


class TestResponseHelpers(unittest.TestCase):
    def test_success_response(self):
        payload = {"id": 1, "name": "Item"}
        res = success_response(payload)
        self.assertEqual(res, {
            "success": True,
            "data": payload,
            "error": None
        })

    def test_error_response(self):
        res = error_response("TEST_CODE", "Something broke")
        self.assertEqual(res, {
            "success": False,
            "data": None,
            "error": {
                "code": "TEST_CODE",
                "message": "Something broke",
                "details": None,
            }
        })


if __name__ == "__main__":
    unittest.main()
