"""Portability and separate agent-computer state; no live model calls."""
import json
import shutil
import subprocess

import pytest

import lab
from computer import Computer, ORIGIN, ROOT, docker


@pytest.mark.parametrize('copied_guard', [False, True])
def test_standalone_checks_without_parent_or_git(tmp_path, monkeypatch, copied_guard):
    project = tmp_path / 'renamed-agent-project'
    project.mkdir()
    shutil.copytree(ROOT / 'source_snapshot', project / 'source_snapshot')
    if copied_guard:
        # A manually copied guard must not try to access the original checkout.
        (project / '.kareos-parent-guard.json').write_text(json.dumps({'parent_path': str(ROOT.parent)}))
    (project / '.env').write_text('RESEARCH_PROVIDER=openai-compatible\nRESEARCH_MODEL=synthetic-model\nRESEARCH_API_KEY=test-only\n')
    (tmp_path / '.env').write_text('RESEARCH_MODEL=parent-must-not-be-read\n')
    monkeypatch.setattr(lab, 'ROOT', project)
    # Any attempted parent Git read fails immediately, instead of depending on Git.
    monkeypatch.setattr(subprocess, 'check_output', None)
    monkeypatch.delenv('RESEARCH_PROVIDER', raising=False)
    monkeypatch.delenv('RESEARCH_MODEL', raising=False)
    monkeypatch.delenv('RESEARCH_API_KEY', raising=False)
    result = lab.parent_integrity()
    assert result['mode'] == 'standalone'
    assert result['snapshot_hashes_match']
    assert result['parent_index_unchanged'] is None
    assert not (project / '.env.example').exists()
    assert lab.configuration()['RESEARCH_MODEL'] == 'synthetic-model'
    assert lab.configuration()['RESEARCH_API_KEY'] == 'test-only'


def test_snapshot_tampering_is_rejected(tmp_path, monkeypatch):
    shutil.copytree(ROOT / 'source_snapshot', tmp_path / 'source_snapshot')
    manifest = json.loads((tmp_path / 'source_snapshot/manifest.json').read_text(encoding='utf-8-sig'))
    target = tmp_path / 'source_snapshot' / next(iter(manifest))
    target.write_bytes(target.read_bytes() + b'\n# tampered test copy\n')
    monkeypatch.setattr(lab, 'ROOT', tmp_path)
    with pytest.raises(RuntimeError, match='Source snapshot drift'):
        lab.parent_integrity()


def test_agent_computers_do_not_share_state(tmp_path):
    cases = json.loads((ROOT / 'cases.json').read_text())
    with Computer(cases[0]['documents'], tmp_path / 'agent-one') as first, \
            Computer(cases[1]['documents'], tmp_path / 'agent-two') as second:
        assert first.name != second.name
        assert first.token != second.token
        first.action('navigate', url=ORIGIN + '/documents/' + cases[0]['documents'][0]['id'])
        second.action('navigate', url=ORIGIN + '/')
        assert cases[0]['documents'][0]['text'] in first.action('read')['text']
        assert 'Synthetic evidence library' in second.action('read')['text']
        first.action('write_file', path='agent-notes.txt', contents='First agent only')
        second.action('write_file', path='agent-notes.txt', contents='Second agent only')
        assert 'First agent only' in json.dumps(first.action('read_file', path='agent-notes.txt'))
        assert 'Second agent only' in json.dumps(second.action('read_file', path='agent-notes.txt'))
        assert 'First agent only' not in json.dumps(second.action('read_file', path='agent-notes.txt'))
        with pytest.raises(ValueError):
            second.allowed_url(ORIGIN + '/documents/' + cases[0]['documents'][0]['id'])
        names = [first.name, second.name]
    remaining = docker('ps', '-a', '--format', '{{.Names}}').splitlines()
    assert all(name not in remaining for name in names)
