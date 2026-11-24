#!/usr/bin/python3
"""Offline packaging checks with synthetic inputs; no production genome download."""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import tempfile
import time


def run(argv, expected=0, cwd=None, env=None):
    result = subprocess.run(argv, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=90)
    assert (result.returncode != 0 if expected == 'failure' else result.returncode == expected), (argv, result.returncode, result.stdout)
    return result.stdout


def fixtures(root):
    (root/'ref.fa').write_text('>chr1\n' + 'ACGT' * 250 + '\n')
    (root/'ref.fa.fai').write_text('chr1\t1000\t6\t1000\t1001\n')
    (root/'input.bed').write_text('chr1\t100\t180\tSynthetic_B\nchr1\t10\t80\tSynthetic_A\n')
    (root/'expected.bed').write_text('chr1\t10\t80\tSynthetic_A\nchr1\t100\t180\tSynthetic_B\n')
    (root/'test.chrom.sizes').write_text('chr1\t1000\n')


def identity(root):
    assert '2.19.9' in run(['igv', '--version']).splitlines()
    assert 'IGV Version 2.19.9' in run(['igvtools', 'version'])
    assert '21.0.13.1' in run(['java', '-version'])
    assert 'IGV' in run(['igv', '--help'])
    assert '--genome' in run(['igv-gui', '--help'])
    assert 'install' in run(['igv-resources', '--help'])
    assert 'sacCer3' in run(['igv-resources', 'catalog'])
    assert 'TAFFISH' == os.environ.get('TAFFISH_ENV')
    assert 'igv' == os.environ.get('TAFFISH_NAME')
    env = dict(os.environ); env.pop('DISPLAY', None)
    assert 'no X DISPLAY' in run(['igv'], 'failure', env=env)
    assert 'Usage: igvtools' in run(['igvtools'])
    assert 'igvtools  sort' in run(['igvtools', 'help', 'sort'])
    run(['igvtools', 'taffish-invalid-command'], 'failure')


def tools(root):
    fixtures(root)
    run(['igvtools', 'sort', 'input.bed', 'sorted.bed'], cwd=root)
    assert (root/'sorted.bed').read_bytes() == (root/'expected.bed').read_bytes()
    run(['igvtools', 'index', 'sorted.bed'], cwd=root)
    assert (root/'sorted.bed.idx').stat().st_size > 0
    run(['igvtools', 'count', '-w', '25', 'sorted.bed', 'coverage.tdf', 'test.chrom.sizes'], cwd=root)
    assert (root/'coverage.tdf').read_bytes()[:3] == b'TDF'
    run(['igvtools', 'count', 'sorted.bed', 'bad.tdf', 'hg38'], 'failure', cwd=root)
    assert not (root/'bad.tdf').exists()


def resource(root):
    fixtures(root)
    library = root/'library'; library.mkdir(mode=0o755)
    recipe = {'schema': 'taffish.igv.recipe.v1', 'id': 'tiny', 'version': 'v1',
              'source': 'synthetic offline packaging test', 'license': 'CC0 synthetic test fixture',
              'genome': {'id': 'tiny', 'name': 'Synthetic reference', 'fastaURL': 'ref.fa', 'indexURL': 'ref.fa.fai'},
              'files': []}
    for name in ('ref.fa', 'ref.fa.fai'):
        content = (root/name).read_bytes()
        recipe['files'].append({'name': name, 'url': 'https://example.invalid/'+name,
                               'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
    spec = root/'recipe.json'; spec.write_text(json.dumps(recipe))
    args = ['igv-resources', 'install', '--recipe', str(spec), '--resource-root', str(library),
            '--rights-reviewed', '--reserve-gb', '0']
    report = json.loads(run(args + ['--dry-run']))
    assert report['recipe']['license'] and report['download_bytes'] == sum(f['size'] for f in recipe['files'])
    run(args, 'failure')
    assert list(library.iterdir()) == []
    run(args + ['--source-dir', str(root)])
    assert 'already complete' in run(args + ['--source-dir', str(root)])
    run(['igv-resources', 'list', '--resource-root', str(library)])
    member = library/'tiny--v1'
    assert (member/'ref.fa').read_bytes() == (root/'ref.fa').read_bytes()
    original = (member/'ref.fa').read_bytes()
    (member/'ref.fa').write_bytes(b'bad')
    run(args + ['--source-dir', str(root)], 'failure')
    assert (member/'ref.fa').read_bytes() == b'bad'
    (member/'ref.fa').write_bytes(original)
    run(['igv-resources', 'list', '--resource-root', str(library)])


def gui(root, extended=False, tools_gui=False):
    fixtures(root)
    # The upstream genome batch command does not strip quotes. A relative,
    # space-free basename works even when the containing working path has spaces.
    (root/'batch.txt').write_text('genome ./ref.fa\nload "'+str(root/'input.bed')+'"\ngoto chr1:1-240\nsnapshotDirectory "'+str(root)+'"\nsnapshot export.png\n')
    baseline = {line.split()[9] for line in Path('/proc/net/tcp').read_text().splitlines()[1:] if line.split()[3] == '0A'}
    cases = [('ready-term', signal.SIGTERM, False, False)]
    if extended:
        cases += [('ready-int', signal.SIGINT, False, False), ('early-int', signal.SIGINT, True, False),
                  ('early-term', signal.SIGTERM, True, False), ('closed-output', signal.SIGTERM, False, True),
                  ('wm-failure', None, False, False)]
    for label, sig, early, broken in cases:
        logs = root/label; logs.mkdir()
        argv = ['igv-gui', '--outdir', str(root), '--log-dir', str(logs), '--bind-address', '127.0.0.1', '--java-xmx', '1024m']
        argv += ['--tools'] if tools_gui else ['--genome', str(root/'ref.fa'), '--', '-b', str(root/'batch.txt')]
        with (logs/'supervisor.log').open('w') as output:
            child = subprocess.Popen(argv, stdout=subprocess.PIPE if broken else output, stderr=output)
            try:
                if broken:
                    child.stdout.close()
                deadline = time.monotonic() + 140
                while True:
                    sessions = list(logs.glob('igv-gui-*'))
                    text = (logs/'supervisor.log').read_text()
                    if sessions and ((early and (sessions[0]/'processes.json').exists()) or (not early and 'igv-gui: ready;' in text)):
                        break
                    assert child.poll() is None, text
                    assert time.monotonic() < deadline, text
                    time.sleep(0.1)
                session = sessions[0]
                # Snapshot writes can briefly be incomplete while children start.
                for _ in range(20):
                    try:
                        processes = json.loads((session/'processes.json').read_text()); break
                    except json.JSONDecodeError:
                        time.sleep(0.02)
                if not early:
                    geometry = json.loads((session/'geometry.json').read_text())
                    minimum = (300, 150) if tools_gui else (1400, 800)
                    assert int(geometry['WIDTH']) >= minimum[0] and int(geometry['HEIGHT']) >= minimum[1]
                    if not tools_gui:
                        while not (root/'export.png').exists():
                            assert time.monotonic() < deadline, (session/'app.log').read_text()[-8000:]
                            time.sleep(0.1)
                        png = (root/'export.png').read_bytes()
                        assert png.startswith(b'\x89PNG\r\n\x1a\n')
                        assert all(x > 100 for x in struct.unpack('!II', png[16:24]))
                if sig is None:
                    os.kill(processes['wm'], signal.SIGTERM)
                else:
                    child.send_signal(sig)
                status = child.wait(timeout=25)
                text = (logs/'supervisor.log').read_text()
                assert (status != 0 and 'wm exited' in text) if sig is None else status == 128 + sig, (status, text)
                assert 'stopped; owned' in text, text
                for pid in processes.values():
                    assert not Path('/proc', str(pid)).exists(), ('process leak', pid)
                for name in ('home', 'config', 'cache', 'runtime', 'tmp', 'web'):
                    assert not os.path.lexists(session/name), ('runtime leak', name)
                assert not os.path.lexists('/tmp/.X1-lock')
                assert not os.path.lexists('/tmp/.X11-unix/X1')
                for port in (5801, 5901):
                    with socket.socket() as sock:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.bind(('127.0.0.1', port))
                after = {line.split()[9] for line in Path('/proc/net/tcp').read_text().splitlines()[1:] if line.split()[3] == '0A'}
                assert baseline == after, ('listener leak', baseline, after)
                (logs/'receipt.json').write_text(json.dumps({'exit': status, 'passed': True, 'processes': processes}))
            finally:
                if child.poll() is None:
                    child.terminate(); child.wait(timeout=25)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['identity', 'tools', 'resource', 'gui', 'gui-extended', 'tools-gui'])
    p.add_argument('--work', type=Path)
    a = p.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix='igv-check-') if a.work is None else None
    root = Path(temporary.name) if temporary else a.work.resolve()
    root.mkdir(parents=True, exist_ok=True)
    try:
        if a.mode.startswith('gui') or a.mode == 'tools-gui':
            gui(root, a.mode == 'gui-extended', a.mode == 'tools-gui')
        else:
            globals()[a.mode](root)
        print('IGV_' + a.mode.upper() + '_PASS', flush=True)
    finally:
        if temporary:
            temporary.cleanup()
