"""The probes print no signed credential into the committed log.

HDX answers a download with a redirect to a presigned S3 address. The probes
built on surveys_probe (Central and Southern Africa's among them) print the
address a fetch ended at, so surveys_probe removes the credential first. No
network.
"""

import contextlib
import io
import unittest
import urllib.error
from unittest import mock

from scripts.fetch_census import central_africa_probe
from scripts.fetch_census import southern_africa_probe
from scripts.fetch_census import surveys_probe


SIGNED = ("https://s3.us-east-1.amazonaws.com/hdx-production-filestore/resources/abc/"
          "tcd_admpop_adm1_2023.csv?AWSAccessKeyId=ASIAEXAMPLE&Signature=c2lnbmF0dXJl"
          "&x-amz-security-token=FwoGZXIvYXdzEXAMPLE&Expires=1792267372")
SECRETS = ("AWSAccessKeyId", "Signature", "x-amz-security-token", "ASIAEXAMPLE", "FwoGZXIv")


class Response(io.BytesIO):
    """What urlopen hands back after following HDX's redirect."""
    status = 200

    def __init__(self):
        super().__init__(b"a,b\n1,2\n")
        self.headers = {"Content-Type": "text/csv", "Location": SIGNED}

    def geturl(self):
        return SIGNED


class Credentials(unittest.TestCase):

    def test_a_presigned_address_loses_its_credentials(self):
        shown = surveys_probe.safe(SIGNED)
        for word in SECRETS:
            self.assertNotIn(word, shown)
        self.assertTrue(shown.startswith("https://s3.us-east-1.amazonaws.com/"))
        self.assertIn("tcd_admpop_adm1_2023.csv", shown)

    def test_an_ordinary_query_is_kept(self):
        url = "https://data.humdata.org/api/3/action/package_show?id=cod-ps-tcd"
        self.assertEqual(surveys_probe.safe(url), url)
        self.assertEqual(surveys_probe.safe("https://example.org/a.pdf"),
                         "https://example.org/a.pdf")

    def test_fetch_returns_the_final_address_and_location_without_them(self):
        with mock.patch("urllib.request.urlopen", return_value=Response()):
            status, final, headers, _ = surveys_probe.fetch("https://data.humdata.org/x")
        self.assertEqual(status, 200)
        for word in SECRETS:
            self.assertNotIn(word, final)
            self.assertNotIn(word, headers["Location"])

    def test_an_error_answer_is_cleaned_too(self):
        error = urllib.error.HTTPError(SIGNED, 403, "Forbidden", {"Location": SIGNED},
                                       io.BytesIO(b"denied"))
        with mock.patch("urllib.request.urlopen", side_effect=error):
            status, final, headers, _ = surveys_probe.fetch("https://data.humdata.org/x")
        self.assertEqual(status, 403)
        self.assertNotIn("Signature", final)
        self.assertNotIn("Signature", headers["Location"])

    def test_summary_cleans_what_it_is_handed(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            surveys_probe.summary("https://data.humdata.org/x", 200, SIGNED,
                                  {"Location": SIGNED}, b"x")
        for word in SECRETS:
            self.assertNotIn(word, out.getvalue())
        self.assertIn("tcd_admpop_adm1_2023.csv", out.getvalue())

    def test_the_regional_probes_print_none(self):
        for probe in (central_africa_probe, southern_africa_probe):
            out = io.StringIO()
            with mock.patch("urllib.request.urlopen", return_value=Response()), \
                    contextlib.redirect_stdout(out):
                probe.get("https://data.humdata.org/x")
            for word in SECRETS:
                self.assertNotIn(word, out.getvalue(), probe.__name__)


if __name__ == "__main__":
    unittest.main()
