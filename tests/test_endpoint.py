import http.client
import json
import os
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import patch
from endpoint import Handler, request_key


class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def call(self, payload, token=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request('POST', '/api/run', json.dumps(payload),
                     {'Authorization': 'Bearer ' + (token or ''), 'Content-Type': 'application/json'})
        response = conn.getresponse()
        status, data = response.status, json.loads(response.read())
        conn.close()
        return status, data

    @patch.dict(os.environ, {'CASUAR_MCP_TOKEN': 'test-secret'})
    def test_auth_and_real_run(self):
        self.assertEqual(self.call({})[0], 401)
        self.assertEqual(self.call({}, 'test-secret')[0], 401)
        status, result = self.call({'interventions': {'input': {'value': 2, 'start': 1, 'end': 6}}},
                                   request_key('test-secret'))
        self.assertEqual(status, 200)
        self.assertFalse(result['persisted'])
        self.assertGreater(result['final_mean_delta']['state'], 0)
        self.assertEqual(len(result['baseline']), 13)

    @patch.dict(os.environ, {'CASUAR_MCP_TOKEN': 'test-secret'})
    def test_invalid_inputs_and_budget(self):
        for payload in [[], {'steps': 121}, {'steps': 120, 'draws': 5000},
                        {'seed': 'oops'}, {'model': {'variables': {'x': {'initial': 0, 'equation': 'x.real'}}}}]:
            self.assertEqual(self.call(payload, request_key('test-secret'))[0], 400)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_configuration_fails_closed(self):
        self.assertEqual(self.call({})[0], 503)

    @patch.dict(os.environ, {'CASUAR_MCP_TOKEN': 'test-secret'}, clear=True)
    def test_persistence_does_not_silently_fall_back(self):
        self.assertEqual(self.call({'persist': True}, request_key('test-secret'))[0], 503)
