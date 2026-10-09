"""Real Chromium/OpenBot checks without a model; never an accuracy evaluation."""
import json
import socket
import time

from computer import Computer, ORIGIN, ROOT, docker


def smoke():
    from lab import parent_integrity
    before = parent_integrity()
    cases = json.loads((ROOT / 'cases.json').read_text())
    directory = ROOT / 'reports' / time.strftime('smoke-%Y%m%d-%H%M%S')
    observations = []
    for case in cases[:3]:
        with Computer(case['documents'], directory / case['id']) as computer:
            isolation = computer.inspect()
            assert isolation['network'] == 'none'
            assert isolation['mounts'] == []
            assert not isolation['ports']
            assert isolation['user'] == 'researcher'
            opened = computer.action('navigate', url=ORIGIN + '/')
            assert 'Synthetic evidence library' in opened['text']
            snapshot = computer.action('snapshot')
            links = [e for e in snapshot['elements'] if e.get('role') == 'link']
            assert len(links) == len(case['documents'])
            doc = case['documents'][0]
            link = next(e for e in links if e.get('name') == doc['title'])
            read = computer.action('click', ref=link['ref'], snapshot_id=snapshot['snapshotId'])
            assert doc['text'] in read['text']
            assert computer.action('calculate', expression='1800 - 1200')['value'] == 600
            computer.action('write_file', path='notes.txt', contents='Synthetic scratch note')
            note = computer.action('read_file', path='notes.txt')
            assert 'Synthetic scratch note' in json.dumps(note)
            for arguments in [('navigate', {'url': 'https://example.com/'}), ('read_file', {'path': '../secret.txt'}),
                              ('calculate', {'expression': '__import__("os").getcwd()'})]:
                try:
                    computer.action(arguments[0], **arguments[1])
                    raise AssertionError('Boundary accepted forbidden input')
                except ValueError:
                    pass
            # OS-level direct egress check, bypassing adapter and HTTP proxy.
            probe = "import socket; s=socket.socket(); s.settimeout(2)\ntry:\n s.connect(('1.1.1.1',443)); print('CONNECTED')\nexcept OSError:\n print('BLOCKED')"
            assert docker('exec', computer.name, 'python3', '-c', probe) == 'BLOCKED'
            screenshot = computer.screenshot()
            assert screenshot.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            name = computer.name
            observations.append({'case_id': case['id'], 'container': isolation, 'checks': {
                'browser_navigation': True, 'accessibility_snapshot': True, 'click_and_read': True,
                'numeric_shell_calculation': True, 'scratch_file_roundtrip': True,
                'external_url_denied': True, 'path_escape_denied': True, 'code_expression_denied': True,
                'direct_external_network_blocked': True, 'screenshot_saved': True}})
        assert name not in docker('ps', '-a', '--format', '{{.Names}}').splitlines()
        observations[-1]['checks']['container_removed'] = True
        print(case['id'] + ': real browser and isolation checks passed', flush=True)
    after = parent_integrity()
    report = {'kind': 'infrastructure_smoke', 'uses_live_model': False, 'clinical_accuracy_evaluated': False,
              'before': before, 'after': after, 'observations': observations}
    (directory / 'summary.json').write_text(json.dumps(report, indent=2))
    integrity_note = ('Parent HEAD, pending merge, staged index and tracked working files remained unchanged.'
                      if after['parent_guard_active'] else
                      'Standalone mode: bundled source hashes verified; no parent repository checked or required.')
    (directory / 'SUMMARY.md').write_text('# Infrastructure smoke results\n\nThree fresh OpenBot containers passed browser, shell arithmetic, workspace, network and teardown checks.\n\nNo live model was called. Clinical output quality has not been evaluated.\n\n' + integrity_note + '\n')
    print('Smoke report: ' + str(directory))


if __name__ == '__main__':
    smoke()
