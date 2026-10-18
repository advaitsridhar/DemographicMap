"""The Central Africa probe prints no signed credential into the committed log."""

import unittest
from unittest import mock

from scripts.fetch_census import central_africa_probe as probe
from scripts.fetch_census import surveys_probe


SIGNED = ("https://s3.us-east-1.amazonaws.com/hdx-production-filestore/resources/abc/"
          "tcd_admpop_adm1_2023.csv?AWSAccessKeyId=ASIAEXAMPLE&Signature=c2lnbmF0dXJl"
          "&x-amz-security-token=FwoGZXIvYXdzEXAMPLE&Expires=1792267372")


class Credentials(unittest.TestCase):

    def test_a_presigned_address_loses_its_credentials(self):
        shown = probe.safe(SIGNED)
        for word in ("AWSAccessKeyId", "Signature", "x-amz-security-token", "ASIAEXAMPLE",
                     "FwoGZXIv"):
            self.assertNotIn(word, shown)
        self.assertTrue(shown.startswith("https://s3.us-east-1.amazonaws.com/"))
        self.assertIn("tcd_admpop_adm1_2023.csv", shown)

    def test_an_ordinary_query_is_kept(self):
        url = "https://data.humdata.org/api/3/action/package_show?id=cod-ps-tcd"
        self.assertEqual(probe.safe(url), url)
        self.assertEqual(probe.safe("https://example.org/a.pdf"), "https://example.org/a.pdf")

    def test_every_mode_fetches_through_the_safe_wrapper(self):
        # surveys_probe's own modes look fetch up at call time.
        self.assertIs(surveys_probe.fetch, probe.fetch)
        with mock.patch.object(probe, "_fetch",
                               return_value=(200, SIGNED, {"Location": SIGNED}, b"x")):
            status, final, headers, _ = probe.fetch("https://data.humdata.org/x")
        self.assertEqual(status, 200)
        self.assertNotIn("Signature", final)
        self.assertNotIn("Signature", headers["Location"])


if __name__ == "__main__":
    unittest.main()
