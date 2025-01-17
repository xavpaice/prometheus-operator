# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import unittest
from unittest.mock import patch

from ops.charm import CharmBase
from ops.framework import StoredState

# from ops.model import Network
from ops.testing import Harness
from charms.prometheus_k8s.v0.prometheus import PrometheusConsumer

CONSUMES = {"prometheus": ">=2.0"}
CONSUMER_SERVICE = "prometheus_tester"
CONSUMER_META = """
name: consumer-tester
containers:
  prometheus-tester:
requires:
  monitoring:
    interface: prometheus_scrape
"""
JOBS = [
    {
        "global": {"scrape_interval": "1h"},
        "rule_files": ["/some/file"],
        "file_sd_configs": [{"files": "*some-files*"}],
        "job_name": "my-first-job",
        "metrics_path": "one-path",
        "static_configs": [
            {
                "targets": ["10.1.238.1:6000", "*:7000"],
                "labels": {"some-key": "some-value"},
            }
        ],
    },
    {
        "job_name": "my-second-job",
        "metrics_path": "another-path",
        "static_configs": [
            {"targets": ["*:8000"], "labels": {"some-other-key": "some-other-value"}}
        ],
    },
]
ALLOWED_KEYS = {"job_name", "metrics_path", "static_configs"}


class ConsumerCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.provider = PrometheusConsumer(
            self,
            "monitoring",
            consumes=CONSUMES,
            service_event=self.on.prometheus_tester_pebble_ready,
            jobs=JOBS,
        )


class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(ConsumerCharm, meta=CONSUMER_META)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    @patch("ops.testing._TestingModelBackend.network_get")
    def test_consumer_sets_scrape_metadata(self, _):
        rel_id = self.harness.add_relation("monitoring", "provider")
        self.harness.add_relation_unit(rel_id, "provider/0")
        data = self.harness.get_relation_data(rel_id, self.harness.model.app.name)
        self.assertIn("scrape_metadata", data)
        scrape_metadata = data["scrape_metadata"]
        self.assertIn("model", scrape_metadata)
        self.assertIn("model_uuid", scrape_metadata)
        self.assertIn("application", scrape_metadata)

    @patch("ops.testing._TestingModelBackend.network_get")
    def test_consumer_unit_sets_bind_address_on_pebble_ready(self, mock_net_get):
        bind_address = "192.0.8.2"
        fake_network = {
            "bind-addresses": [
                {
                    "interface-name": "eth0",
                    "addresses": [
                        {"hostname": "prometheus-tester-0", "value": bind_address}
                    ],
                }
            ]
        }
        mock_net_get.return_value = fake_network
        rel_id = self.harness.add_relation("monitoring", "provider")
        self.harness.container_pebble_ready("prometheus-tester")
        data = self.harness.get_relation_data(rel_id, self.harness.charm.unit.name)
        self.assertIn("prometheus_scrape_host", data)
        self.assertEqual(data["prometheus_scrape_host"], bind_address)

    @patch("ops.testing._TestingModelBackend.network_get")
    def test_consumer_unit_sets_bind_address_on_relation_joined(self, mock_net_get):
        bind_address = "192.0.8.2"
        fake_network = {
            "bind-addresses": [
                {
                    "interface-name": "eth0",
                    "addresses": [
                        {"hostname": "prometheus-tester-0", "value": bind_address}
                    ],
                }
            ]
        }
        mock_net_get.return_value = fake_network
        rel_id = self.harness.add_relation("monitoring", "provider")
        self.harness.add_relation_unit(rel_id, "provider/0")
        data = self.harness.get_relation_data(rel_id, self.harness.charm.unit.name)
        self.assertIn("prometheus_scrape_host", data)
        self.assertEqual(data["prometheus_scrape_host"], bind_address)

    @patch("ops.testing._TestingModelBackend.network_get")
    def test_consumer_supports_multiple_jobs(self, _):
        rel_id = self.harness.add_relation("monitoring", "provider")
        self.harness.add_relation_unit(rel_id, "provider/0")
        data = self.harness.get_relation_data(rel_id, self.harness.model.app.name)
        self.assertIn("scrape_jobs", data)
        jobs = json.loads(data["scrape_jobs"])
        self.assertEqual(len(jobs), len(JOBS))
        names = [job["job_name"] for job in jobs]
        job_names = [job["job_name"] for job in JOBS]
        self.assertListEqual(names, job_names)

    @patch("ops.testing._TestingModelBackend.network_get")
    def test_consumer_sanitizes_jobs(self, _):
        rel_id = self.harness.add_relation("monitoring", "provider")
        self.harness.add_relation_unit(rel_id, "provider/0")
        data = self.harness.get_relation_data(rel_id, self.harness.model.app.name)
        self.assertIn("scrape_jobs", data)
        jobs = json.loads(data["scrape_jobs"])
        for job in jobs:
            keys = set(job.keys())
            self.assertTrue(keys.issubset(ALLOWED_KEYS))
