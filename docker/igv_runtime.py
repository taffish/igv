#!/usr/bin/python3 -I
"""Container runtime paths and explicit resource selection; upstream Java is unchanged."""
import json
import os
from pathlib import Path
import re
import runpy
import signal
import subprocess
import sys
import tempfile


def resources():
    return runpy.run_path('/opt/igv/libexec/igv-resources.py')


def shared_check():
    if os.environ.get('TAFFISH_IGV_RESOURCE_ACTIVE') == '1':
        resources()['verify_root'](Path('/igv-resources'))


def resource_genome(member):
    module = resources()
    module['safe_name'](member)
    root = Path('/igv-resources')
    module['verify_root'](root)
    module['verify'](root / member, member)
    return str(root / member / 'genome.json')


def local_genome(value):
    path = Path(value).resolve(strict=True)
    if not path.is_file() or not path.stat().st_size:
        raise ValueError('reference must be a nonempty local file')
    if path.suffix.lower() in ('.fa', '.fasta', '.fna'):
        index = Path(str(path) + '.fai')
        if not index.is_file() or not index.stat().st_size:
            raise ValueError('prepare the local FASTA .fai index first (igvtools index reference.fa)')
    elif path.suffix.lower() == '.json':
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not (data.get('twoBitURL') or data.get('fastaURL')):
            raise ValueError('local genome JSON requires a sequence source')
        def check(node, key=''):
            if key in {'hubs', 'urlTemplate'}:
                raise ValueError('offline genome cannot contain remote hubs/templates')
            if key.lower().endswith('url'):
                if not isinstance(node, str) or '://' in node:
                    raise ValueError('offline genome contains a remote reference')
                target = Path(node) if Path(node).is_absolute() else path.parent / node
                if not target.is_file() or not target.stat().st_size:
                    raise ValueError('missing local genome component: ' + str(target))
            elif isinstance(node, dict):
                for k, v in node.items():
                    check(v, k)
            elif isinstance(node, list):
                for v in node:
                    check(v)
        check(data)
        if data.get('fastaURL') and not data.get('indexURL'):
            raise ValueError('offline FASTA genome JSON requires indexURL')
    elif path.suffix.lower() != '.2bit':
        raise ValueError('offline reference must be indexed FASTA, 2bit or a complete local JSON')
    return str(path)


def java_command(name, args, env):
    shared_check()
    network = env.get('IGV_ALLOW_NETWORK', '0')
    if network not in ('0', '1'):
        raise ValueError('IGV_ALLOW_NETWORK accepts only 0 or 1')
    home = Path(env['HOME'])
    state = Path(env.get('IGV_STATE_DIR', str(home / 'igv')))
    if network == '1' and not env.get('IGV_STATE_DIR'):
        raise ValueError('online use requires an explicit writable IGV_STATE_DIR')
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not os.access(state, os.W_OK):
        raise ValueError('IGV_STATE_DIR must be writable; shared reference libraries stay read-only')
    version_help = args[:1] in (['--version'], ['--help'], ['-h'], ['-v'])
    gui = name != 'igvtools' or args[:1] == ['gui']
    desktop = name == 'igv'
    args = list(args)
    if desktop and args[:1] == ['-v']:
        args = ['--version']
    if desktop and args[:1] == ['-h']:
        args = ['--help']
    if gui and not (desktop and version_help) and not env.get('DISPLAY'):
        raise ValueError('no X DISPLAY is available; use igv-gui for browser access')
    if desktop and not version_help:
        selected = None
        for i, token in enumerate(args):
            if token in ('-g', '--genome'):
                if i + 1 == len(args):
                    raise ValueError('missing genome argument')
                selected = args[i + 1]
                if network == '0':
                    args[i + 1] = local_genome(selected)
        if network == '0' and selected is None:
            raise ValueError('local reference required: --genome reference.fa; no implicit download')
        if network == '0' and any('://' in token for token in args):
            raise ValueError('remote input requires explicit IGV_ALLOW_NETWORK=1 and IGV_STATE_DIR')
        # The upstream preferences override is a per-session file; it never
        # overwrites a user's existing preference file or shared reference.
        prefs = home / 'taffish.preferences'
        entries = ['PORT_ENABLED=false', 'SHOW_GENOME_SERVER_WARNING=false']
        if network == '0':
            catalog = home / 'offline-genomes.tsv'
            catalog.write_text('# Explicit local reference only\n')
            entries += ['IGV.genome.sequence.dir=' + str(catalog),
                        'IGV.backup.genome.sequence.dir=' + str(catalog),
                        'PROVISIONING_URL_DEFAULT=', 'PROVISIONING.URL=',
                        'PROXY.USE=true', 'PROXY.HOST=127.0.0.1', 'PROXY.PORT=9',
                        'PROXY.TYPE=HTTP', 'PROXY.DISABLE_CHECK=true']
        # Do not silently override a second user preferences file.
        if any(token in ('-o', '--preferences', '--igvDirectory', '-p', '--port') for token in args):
            raise ValueError('use IGV_STATE_DIR/igv-gui --state-dir; custom preferences and command ports are not exposed by this launcher')
        prefs.write_text('\n'.join(entries) + '\n')
        args = ['--igvDirectory', str(state), '--preferences', str(prefs)] + args
    if name == 'igvtools' and network == '0':
        if any('://' in token for token in args):
            raise ValueError('remote input requires explicit IGV_ALLOW_NETWORK=1 and IGV_STATE_DIR')
        if args and args[0].lower() in ('count', 'totdf', 'formatexp') and len(args) >= 4:
            if not Path(args[-1]).is_file():
                raise ValueError('IGVTools requires an explicit local genome file; aliases would download')
    heap = env.get('IGV_JAVA_XMX' if desktop else 'IGVTOOLS_JAVA_XMX', '4g' if desktop else '1500m')
    if not re.fullmatch(r'[1-9][0-9]*[mMgG]', heap):
        raise ValueError('heap must be a positive m/g value')
    command = ['/opt/java/bin/java', '--module-path=/opt/igv/lib', '-Xmx' + heap,
               '-Duser.home=' + str(home), '-Djava.io.tmpdir=' + env.get('TMPDIR', '/tmp'),
               '-Dsamjdk.snappy.disable=true', '-Djava.net.preferIPv4Stack=true']
    if network == '0':
        command += ['-Dhttp.proxyHost=127.0.0.1', '-Dhttp.proxyPort=9',
                    '-Dhttps.proxyHost=127.0.0.1', '-Dhttps.proxyPort=9', '-Dhttp.nonProxyHosts=']
    if gui and not (desktop and version_help):
        command += ['@/opt/igv/igv.args']
    else:
        command += ['-Djava.awt.headless=true']
    if name == 'igvtools_gui_hidpi':
        command += ['-Dsun.java2d.uiScale=2']
    if name in ('igvtools_gui', 'igvtools_gui_hidpi'):
        args = ['gui'] + args
    module = 'org.broad.igv.ui.Main' if desktop else 'org.broad.igv.tools.IgvTools'
    return command + ['--module=org.igv/' + module] + args


def main():
    name = Path(sys.argv[0]).name
    number = 0
    child = None
    def stop(sig, _):
        nonlocal number
        number = number or sig
        if child is not None and child.poll() is None:
            child.terminate()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    try:
        with tempfile.TemporaryDirectory(prefix='igv-runtime-') as private:
            env = dict(os.environ, HOME=private)
            command = java_command(name, sys.argv[1:], env)
            if number:
                return 128 + number
            child = subprocess.Popen(command, env=env)
            if number:
                child.terminate()
            while child.poll() is None:
                try:
                    child.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    if number:
                        try:
                            child.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            child.kill(); child.wait(timeout=3)
            return 128 + number if number else (child.returncode if child.returncode >= 0 else 128 - child.returncode)
    except Exception as error:
        print(name + ': ' + str(error), file=sys.stderr)
        return 1
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=3)


if __name__ == '__main__':
    sys.exit(main())
