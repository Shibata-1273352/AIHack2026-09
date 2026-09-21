import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pymupdf
from fastapi.testclient import TestClient
from app import db, runtime, topology_documents as docs, vlm
from app.config import settings
from app.main import app

class TopologyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir = settings.data_dir
        settings.data_dir = Path(self.temp.name)
        if db._conn:
            db._conn.close()
        db._conn = None
        runtime.workers.clear()
        self.client = TestClient(app)
        reg = vlm._registered()
        self.graph = {'nodes': [{'label': n['id'], 'role': n['role'], 'zone': n['zone'], 'annotation': 'page one'} for n in reg['nodes']], 'links': [{'a': l['a'], 'b': l['b'], 'label': 'link', 'dashed': l['kind'] == 'backup'} for l in reg['links']]}

    def tearDown(self):
        if db._conn:
            db._conn.close()
        db._conn = None
        settings.data_dir = self.old_dir
        runtime.workers.clear()
        self.temp.cleanup()

    def pdf(self, pages=1, encrypted=False):
        with pymupdf.open() as p:
            for _ in range(pages):
                p.new_page()
            return p.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='secret') if encrypted else p.tobytes()

    def response(self, graph=None):
        return SimpleNamespace(parsed=copy.deepcopy(graph or self.graph), schema_ok=True, text='{}', resolved_model='test', route='test', outcome='ok', latency_ms=1, input_tokens=1, output_tokens=1, cost_usd=0)

    def test_reject_invalid_pdf_limits_and_encryption(self):
        for content in [b'not pdf', b'%PDF-invalid', self.pdf(4), self.pdf(encrypted=True), b'x' * (docs.MAX_BYTES+1)]:
            with self.assertRaises(ValueError):
                docs.create_document(content, 'bad.pdf')
        self.assertEqual(self.client.post('/api/topology-documents', content=b'bad').status_code, 422)
        self.assertEqual(self.client.get('/api/topology-documents/doc-bad').status_code, 404)

    def test_merge_preserves_annotations_and_unique_links(self):
        d = docs.create_document(self.pdf(2), '../diagram.pdf')
        second = copy.deepcopy(self.graph)
        second['nodes'][0]['annotation'] = 'page two'
        second['links'][0]['label'] = 'additional interface'
        with patch.object(docs.gateway, 'call', side_effect=[self.response(), self.response(second)]):
            docs.analyze_document(d['id'])
        d = docs.get_document(d['id'])
        self.assertEqual(d['filename'], 'diagram.pdf')
        self.assertTrue(d['result']['comparison']['ok'])
        self.assertEqual(len(d['result']['mapped_links']), 5)
        self.assertIn('page two', d['result']['mapped_nodes'][0]['annotation'])
        self.assertIn('additional interface', d['result']['mapped_links'][0]['label'])

    def test_bad_schema_and_partial_failure_never_become_success(self):
        for responses in [[self.response({'nodes': None, 'links': []})], [self.response(), RuntimeError('private provider details')]]:
            d = docs.create_document(self.pdf(len(responses)), 'diagram.pdf')
            with patch.object(docs.gateway, 'call', side_effect=responses):
                docs.analyze_document(d['id'])
            d = docs.get_document(d['id'])
            self.assertEqual(d['status'], 'error')
            self.assertIsNone(d['result'])
            self.assertNotIn('private provider details', d['error'])
            self.assertEqual(d['completed_pages'], len(responses)-1)

    def test_missing_edge_blocks_start(self):
        graph = copy.deepcopy(self.graph)
        graph['links'].pop()
        d = docs.create_document(self.pdf(), 'diagram.pdf')
        with patch.object(docs.gateway, 'call', return_value=self.response(graph)):
            docs.analyze_document(d['id'])
        self.assertFalse(docs.get_document(d['id'])['result']['comparison']['ok'])
        self.assertEqual(self.client.post('/api/incidents', json={'topology_document_id': d['id']}).status_code, 422)
        self.assertIsNone(db.latest_incident())

    def test_upload_reserves_worker_and_attach_reuses_analysis(self):
        with patch('app.main.threading.Thread'):
            response = self.client.post('/api/topology-documents?filename=demo.pdf', content=self.pdf())
        self.assertEqual(response.status_code, 202)
        doc_id = response.json()['id']
        self.assertIn(doc_id, runtime.workers)
        self.assertEqual(self.client.post('/api/demo/reset').status_code, 409)
        with patch.object(docs.gateway, 'call', return_value=self.response()):
            runtime.run_worker(doc_id, docs.analyze_document, doc_id)
        with patch('app.main.agent.start_investigation'):
            response = self.client.post('/api/incidents', json={'topology_document_id': doc_id})
        self.assertEqual(response.status_code, 200)
        with patch.object(docs.gateway, 'call') as call:
            result = vlm.read_topology(response.json()['id'])
            call.assert_not_called()
        self.assertEqual(result['document_id'], doc_id)
        self.assertTrue(result['analysis_reused'])
        self.assertEqual(len(db.list_records(response.json()['id'], 'evidence')), 1)

if __name__ == '__main__':
    unittest.main()
