#!/usr/bin/python3 -I
"""Explicit immutable resource recipes and shared-library integrity checks."""
import argparse
import contextlib
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit

SCHEMA = 'taffish.igv.recipe.v1'
RESERVED = {'manifest.json', 'READY', 'recipe.json', 'RESOURCE_LICENSE.txt', 'genome.json'}
APP_RELEASE = '2.19.9-r1'


class Interrupted(BaseException):
    def __init__(self, signum):
        self.signum = signum


def interrupt(signum, _frame):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise Interrupted(signum)


@contextlib.contextmanager
def blocked_signals():
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def inode(metadata):
    return metadata.st_dev, metadata.st_ino


def durable_mode(descriptor, mode, path_metadata):
    """Require descriptor AND directory-entry permissions before publication.

    Shared filesystems may briefly cache the pre-chmod attributes. Retry only
    observation of this same inode; never chmod a mutable path or accept drift.
    """
    identity = inode(os.fstat(descriptor))
    os.fchmod(descriptor, mode)
    os.fsync(descriptor)
    deadline = time.monotonic() + 2
    while True:
        current = path_metadata()
        require(inode(current) == identity, 'entry replaced during permission synchronization')
        if stat.S_IMODE(current.st_mode) == mode and stat.S_IMODE(os.fstat(descriptor).st_mode) == mode:
            return
        require(time.monotonic() < deadline, 'filesystem did not synchronize requested permissions; retained for diagnosis')
        time.sleep(0.02)


def open_directory(path):
    """Open every physical path component without following replacement links."""
    require(path.is_absolute() and '..' not in path.parts, 'absolute physical path required')
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in path.parts[1:]:
            new = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = new
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


class Directory:
    """Descriptor-anchored I/O; cleanup never resolves a mutable parent path."""
    def __init__(self, path=None, parent=None, name=None):
        self.parent, self.name = parent, name
        if parent is None:
            self.path = Path(path).resolve(strict=True)
            self.fd = open_directory(self.path)
        else:
            parent.guard()
            self.path = parent.path / name
            self.fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent.fd)
        self.identity = inode(os.fstat(self.fd))
        self.owned = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.fd)

    def guard(self):
        if self.parent is not None:
            self.parent.guard()
            current = os.stat(self.name, dir_fd=self.parent.fd, follow_symlinks=False)
            require(stat.S_ISDIR(current.st_mode) and inode(current) == self.identity,
                    'directory identity changed; retained for diagnosis: ' + str(self.path))
        else:
            other = open_directory(self.path)
            try:
                require(inode(os.fstat(other)) == self.identity, 'root identity changed; retained for diagnosis')
            finally:
                os.close(other)

    def names(self):
        self.guard()
        # A new open-file description avoids shared readdir cookies/offsets.
        descriptor = os.open('.', os.O_RDONLY | os.O_DIRECTORY, dir_fd=self.fd)
        try:
            return sorted(os.listdir(descriptor))
        finally:
            os.close(descriptor)

    def exists(self, name):
        try:
            os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def info(self, name):
        return os.stat(name, dir_fd=self.fd, follow_symlinks=False)

    def file(self, name, flags=os.O_RDONLY, mode=0o600):
        self.guard()
        descriptor = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, mode, dir_fd=self.fd)
        try:
            metadata = os.fstat(descriptor)
            require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1,
                    'not a single-link regular file: ' + name)
            require(inode(self.info(name)) == inode(metadata), 'file identity changed: ' + name)
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def read(self, name, limit=1024**2):
        descriptor = self.file(name)
        with os.fdopen(descriptor, 'rb') as stream:
            require(os.fstat(stream.fileno()).st_size <= limit, 'metadata too large: ' + name)
            return stream.read()

    def digest(self, name):
        descriptor = self.file(name)
        with os.fdopen(descriptor, 'rb') as stream:
            fields = ('st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid', 'st_gid', 'st_nlink')
            changes = {}
            for attempt in range(3):
                # Shared mounts can refresh cached attributes on the first read.
                # Discard that entire digest, never the stability checks. Accept
                # only a complete stable read of the same single-link inode.
                stream.seek(0)
                before = os.fstat(stream.fileno())
                h = hashlib.sha256()
                for block in iter(lambda: stream.read(8 * 1024**2), b''):
                    h.update(block)
                after = os.fstat(stream.fileno())
                self.guard()
                require(inode(self.info(name)) == inode(after), 'file replaced during verification: ' + name)
                require(after.st_nlink == 1, 'file link count changed during verification: ' + name)
                changes = {field: (getattr(before, field), getattr(after, field))
                           for field in fields if getattr(before, field) != getattr(after, field)}
                if not changes:
                    return before.st_size, h.hexdigest()
                if attempt < 2:
                    time.sleep(0.02)
            raise ValueError('file changed during verification: ' + name + ' ' + json.dumps(changes))

    def create(self, name):
        # Record ownership before a pending signal can reach cleanup.
        with blocked_signals():
            descriptor = self.file(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            self.owned[name] = inode(os.fstat(descriptor))
        return os.fdopen(descriptor, 'wb')

    def write(self, name, content):
        with self.create(name) as stream:
            stream.write(content)
            stream.flush()
            durable_mode(stream.fileno(), 0o644, lambda: self.info(name))

    def clean_owned(self):
        self.guard()
        require(set(self.names()) == set(self.owned), 'unexpected staging entry; retained for diagnosis')
        for name, identity in self.owned.items():
            metadata = self.info(name)
            require(stat.S_ISREG(metadata.st_mode) and inode(metadata) == identity,
                    'staging file replaced; retained for diagnosis: ' + name)
        for name in self.owned:
            os.unlink(name, dir_fd=self.fd)
        os.rmdir(self.name, dir_fd=self.parent.fd)


def check_directory(root, writable=False, mode=None):
    root.guard()
    metadata = os.fstat(root.fd)
    require(not metadata.st_mode & 0o022, 'root must not be group/world writable')
    if mode is not None:
        require(stat.S_IMODE(metadata.st_mode) == mode, 'directory permission drift: ' + str(root.path))
    if writable:
        require(metadata.st_uid == os.geteuid() and metadata.st_mode & 0o200,
                'installer must own and be able to write root')


def promote(parent, source, destination):
    parent.guard()
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    require(rename is not None, 'atomic no-replace promotion unavailable')
    if rename(parent.fd, os.fsencode(source), parent.fd, os.fsencode(destination), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), destination)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode()


def safe_name(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', value)
            and '..' not in value, 'unsafe resource ID, version or filename')
    return value


def regular(path):
    require(not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode), 'not a regular non-symlink file: ' + str(path))


def recipe_validate(recipe):
    require(isinstance(recipe, dict) and recipe.get('schema') == SCHEMA, 'unsupported recipe schema')
    require(set(recipe) == {'schema', 'id', 'version', 'source', 'license', 'files', 'genome'}, 'unexpected recipe fields')
    safe_name(recipe['id']); safe_name(recipe['version'])
    safe_name(recipe['id'] + '--' + recipe['version'])
    require(recipe['id'].lower() != 'all', 'select a named reference, not all')
    for field in ('source', 'license'):
        require(isinstance(recipe[field], str) and recipe[field].strip() and len(recipe[field]) <= 1024**2,
                'source and resource license/permission notice required')
    require(isinstance(recipe['files'], list) and recipe['files'], 'explicit reference files required')
    outputs = set()
    for item in recipe['files']:
        require(isinstance(item, dict) and set(item) == {'name', 'url', 'sha256', 'size'}, 'invalid file entry')
        name = safe_name(item['name'])
        require(name not in outputs | RESERVED, 'duplicate/reserved filename')
        url = urlsplit(item['url'])
        require(url.scheme == 'https' and url.hostname and not url.username and not url.password and not url.fragment,
                'public HTTPS source without credentials required')
        require(isinstance(item['sha256'], str) and re.fullmatch('[0-9a-f]{64}', item['sha256']), 'SHA256 required')
        require(type(item['size']) is int and item['size'] > 0, 'positive exact byte size required')
        outputs.add(name)
    genome = recipe['genome']
    require(isinstance(genome, dict) and genome.get('id') == recipe['id'], 'genome ID mismatch')
    require(bool(genome.get('twoBitURL')) != bool(genome.get('fastaURL')), 'choose one local FASTA or 2bit sequence')
    if genome.get('fastaURL'):
        require(genome.get('indexURL'), 'prepared FASTA index required')
    allowed = {'id', 'name', 'description', 'twoBitURL', 'fastaURL', 'indexURL', 'twoBitBptURL',
               'chromSizesURL', 'chromAliasURL', 'chromAliasBbURL', 'cytobandURL', 'cytobandBbURL',
               'nameSet', 'wholeGenomeView', 'chromosomeOrder', 'tracks'}
    require(set(genome).issubset(allowed), 'unsupported genome field; review optional remote sources separately')
    referenced = set()
    def check(value, key=''):
        if key.lower().endswith('url'):
            require(isinstance(value, str) and value in outputs, 'genome URL must name a pinned local file')
            referenced.add(value)
        elif isinstance(value, dict):
            for k, v in value.items():
                require(k not in {'hubs', 'urlTemplate'}, 'remote hub/template not part of a fixed offline member')
                check(v, k)
        elif isinstance(value, list):
            for v in value:
                check(v)
        elif isinstance(value, str):
            require(not value.startswith(('http:', 'https:', 'file:', '/')), 'remote/absolute reference not allowed')
    check(genome)
    require(outputs == referenced, 'recipe must contain exactly the local files referenced by genome JSON')
    return recipe


def recipe_load(path):
    regular(path)
    require(path.stat().st_size <= 1024**2, 'recipe exceeds 1 MiB')
    return recipe_validate(json.loads(path.read_text()))


def pin_files(args):
    spec = json.loads(args.spec.read_text())
    regular(args.license_file)
    require(args.license_file.stat().st_size <= 1024**2, 'license notice too large')
    spec['schema'] = SCHEMA
    spec['license'] = args.license_file.read_text()
    # Pinning records reviewed acquisition bytes, not an upstream-signed hash.
    with Directory(args.source_dir) as source:
        for item in spec['files']:
            name = safe_name(item['name'])
            item['size'], item['sha256'] = source.digest(name)
    print(json.dumps(recipe_validate(spec), indent=2))


def verify(member, unit, recipe_hash=None):
    if isinstance(member, Path):
        with Directory(member.parent) as parent, Directory(parent=parent, name=member.name) as opened:
            return verify(opened, unit, recipe_hash)
    check_directory(member, mode=0o755)
    for name in ('manifest.json', 'READY'):
        require(stat.S_IMODE(member.info(name).st_mode) == 0o644, 'manifest/READY permission drift')
    manifest = member.read('manifest.json')
    require(member.read('READY').decode().strip() == hashlib.sha256(manifest).hexdigest(), 'READY/manifest mismatch')
    record = json.loads(manifest)
    require(isinstance(record, dict), 'manifest must be a JSON object')
    require(record.get('schema') == 'taffish.igv.db.v1' and record.get('resource') == unit, 'member schema/ID mismatch')
    require(recipe_hash is None or record.get('recipe_sha256') == recipe_hash, 'existing ID has a different recipe; use a new version')
    expected = {'manifest.json', 'READY'}
    require(isinstance(record.get('files'), list) and record['files'], 'empty inventory')
    for item in record['files']:
        require(isinstance(item, dict), 'inventory entry must be a JSON object')
        name = safe_name(item['name'])
        require(name not in expected, 'duplicate inventory entry')
        require(type(item.get('size')) is int and item['size'] > 0, 'invalid inventory size')
        require(isinstance(item.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', item['sha256']), 'invalid inventory digest')
        require(stat.S_IMODE(member.info(name).st_mode) == 0o644, 'member file permission drift: ' + name)
        require(member.digest(name) == (item['size'], item['sha256']), 'checksum/size mismatch: ' + name)
        require(stat.S_IMODE(member.info(name).st_mode) == 0o644, 'member file permission drift: ' + name)
        expected.add(name)
    require({'recipe.json', 'RESOURCE_LICENSE.txt'}.issubset(expected), 'recipe/license inventory missing')
    require(set(member.names()) == expected, 'unexpected/missing member files')
    recipe = recipe_validate(json.loads(member.read('recipe.json')))
    require(hashlib.sha256(canonical(recipe)).hexdigest() == record['recipe_sha256'], 'recipe identity mismatch')
    require(recipe['id'] + '--' + recipe['version'] == unit, 'recipe/member ID mismatch')
    required = RESERVED | {item['name'] for item in recipe['files']}
    require(expected == required, 'recipe/inventory member mismatch')
    inventory = {item['name']: item for item in record['files']}
    for item in recipe['files']:
        actual = inventory[item['name']]
        require((actual['size'], actual['sha256']) == (item['size'], item['sha256']),
                'pinned recipe/inventory identity mismatch: ' + item['name'])
    require(member.read('RESOURCE_LICENSE.txt').decode() == recipe['source'] + '\n\n' + recipe['license'] + '\n',
            'resource license identity mismatch')
    require(member.read('genome.json') == canonical(recipe['genome']) + b'\n', 'local genome definition mismatch')
    return record


def verify_root(root, allow_empty=False):
    if isinstance(root, Path):
        with Directory(root) as opened:
            return verify_root(opened, allow_empty)
    check_directory(root)
    records = []
    for name in root.names():
        if name.startswith('.'):
            metadata = root.info(name)
            if name == '.install.lock':
                require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1
                        and stat.S_IMODE(metadata.st_mode) == 0o600, 'invalid lock control entry')
            elif name == '.downloads' or re.fullmatch(r'\.[A-Za-z0-9_.-]+\.stage-[A-Za-z0-9_-]+', name):
                require(stat.S_ISDIR(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) == 0o700,
                        'invalid private control directory')
            else:
                raise ValueError('unknown control entry; inspect without deleting: ' + name)
            require(metadata.st_uid == os.fstat(root.fd).st_uid, 'control entry owner mismatch')
            continue
        with Directory(parent=root, name=safe_name(name)) as member:
            records.append(verify(member, name))
    require(allow_empty or records, 'no verified reference member in root')
    return records


def command(stage, argv, cwd=None, pass_fds=()):
    # A disk-backed bounded diagnostic tail avoids storing large progress logs in RAM.
    with tempfile.TemporaryFile() as log:
        child = None
        try:
            with blocked_signals():
                child = subprocess.Popen(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, pass_fds=pass_fds)
            code = child.wait()
        except BaseException:
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            raise
        if code:
            log.seek(max(0, log.tell() - 32768))
            print(f'igv-resources: stage={stage} exit={code}', file=sys.stderr)
            print('\n'.join(log.read().decode(errors='replace').splitlines()[-100:]), file=sys.stderr)
            raise SystemExit(code if code > 0 else 128 - code)


def obtain(item, cache, source_dir):
    blob = item['sha256']
    partial = item['sha256'] + '.part'
    if cache.exists(blob):
        require(cache.digest(blob) == (item['size'], item['sha256']), 'corrupt cache; inspect exact file: ' + blob)
        return blob
    descriptor = cache.file(partial, os.O_RDWR | os.O_CREAT)
    with os.fdopen(descriptor, 'r+b', buffering=0) as out:
        metadata = os.fstat(descriptor)
        require(metadata.st_uid == os.geteuid() and not metadata.st_mode & 0o077, 'partial must be private and owned')
        require(metadata.st_size <= item['size'], 'oversize partial cache')
        if source_dir is not None:
            with Directory(source_dir) as source:
                require(source.digest(item['name']) == (item['size'], item['sha256']), 'source checksum/size mismatch')
                with os.fdopen(source.file(item['name']), 'rb') as inp:
                    remaining = metadata.st_size
                    while remaining:
                        block = inp.read(min(8 * 1024**2, remaining))
                        require(block, 'source truncated during resume; partial retained')
                        require(out.read(len(block)) == block, 'partial prefix differs from source; retained')
                        remaining -= len(block)
                    shutil.copyfileobj(inp, out, 8 * 1024**2)
        elif metadata.st_size < item['size']:
            command('download', ['curl', '--fail', '--location', '--proto', '=https', '--proto-redir', '=https',
                                '--connect-timeout', '30', '--speed-limit', '1024', '--speed-time', '120',
                                '--retry', '3', '--retry-delay', '3', '--continue-at', '-',
                                '--max-filesize', str(item['size']), '--output', '/proc/self/fd/' + str(descriptor), item['url']],
                    pass_fds=(descriptor,))
        os.fsync(descriptor)
        require(inode(cache.info(partial)) == inode(metadata), 'partial replaced; retained for diagnosis')
    require(cache.digest(partial) == (item['size'], item['sha256']),
            'download checksum/size mismatch; private partial retained: ' + partial)
    promote(cache, partial, blob)
    return blob


def install(root, recipe, source_dir, reserve):
    with Directory(root) as opened:
        return install_opened(opened, recipe, source_dir, reserve)


def install_opened(root, recipe, source_dir, reserve):
    check_directory(root, writable=True)
    require(root.path != Path('/'), 'filesystem root cannot be a reference library')
    verify_root(root, allow_empty=True)
    unit = recipe['id'] + '--' + recipe['version']
    identity = hashlib.sha256(canonical(recipe)).hexdigest()
    destination = root.path / unit
    # Persistent flock inode is intentionally never unlinked: unlinking a lock
    # while another waiter holds it can admit two installers. Kernel releases it
    # even after SIGKILL; a legacy lock directory fails closed.
    lock = root.file('.install.lock', os.O_RDWR | os.O_CREAT)
    stage = None
    try:
        require(os.fstat(lock).st_uid == os.geteuid() and not os.fstat(lock).st_mode & 0o077, 'lock must be private and owned')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('install lock is held; do not remove an active lock')
        verify_root(root, allow_empty=True)
        if root.exists(unit):
            with Directory(parent=root, name=unit) as existing:
                verify(existing, unit, identity)
            print('already complete: ' + str(destination))
            return
        if not root.exists('.downloads'):
            os.mkdir('.downloads', 0o700, dir_fd=root.fd)
        with Directory(parent=root, name='.downloads') as cache:
            check_directory(cache, writable=True, mode=0o700)
            required = sum(item['size'] for item in recipe['files'] if not cache.exists(item['sha256'])) + reserve
            require(os.fstatvfs(root.fd).f_bavail * os.fstatvfs(root.fd).f_frsize >= required,
                    f'insufficient space: need {required} free bytes')
            blobs = [(item, obtain(item, cache, source_dir)) for item in recipe['files']]
            with blocked_signals():
                stage_name = '.' + unit + '.stage-' + os.urandom(12).hex()
                os.mkdir(stage_name, 0o700, dir_fd=root.fd)
                stage = Directory(parent=root, name=stage_name)
            for item, blob in blobs:
                space = os.fstatvfs(stage.fd)
                require(space.f_bavail * space.f_frsize >= item['size'] + reserve, 'insufficient installation space')
                with os.fdopen(cache.file(blob), 'rb') as inp, stage.create(item['name']) as out:
                    shutil.copyfileobj(inp, out, 8 * 1024**2)
                    out.flush()
                    durable_mode(out.fileno(), 0o644, lambda: stage.info(item['name']))
        stage.write('genome.json', canonical(recipe['genome']) + b'\n')
        stage.write('recipe.json', canonical(recipe) + b'\n')
        stage.write('RESOURCE_LICENSE.txt', (recipe['source'] + '\n\n' + recipe['license'] + '\n').encode())
        inventory = []
        for name in stage.names():
            size, digest = stage.digest(name)
            inventory.append(dict(name=name, size=size, sha256=digest))
        record = dict(schema='taffish.igv.db.v1', app_release=APP_RELEASE, resource=unit,
                      recipe_sha256=identity, files=inventory)
        manifest = canonical(record) + b'\n'
        stage.write('manifest.json', manifest)
        stage.write('READY', (hashlib.sha256(manifest).hexdigest() + '\n').encode())
        durable_mode(stage.fd, 0o755, lambda: root.info(stage.name))
        verify(stage, unit, identity)
        with blocked_signals():
            promote(root, stage.name, unit)
            os.close(stage.fd)
            stage = None
        os.fsync(root.fd)
        print('installed: ' + str(destination))
    finally:
        try:
            if stage is not None:
                try:
                    original = sys.exc_info()[1]
                    try:
                        stage.clean_owned()
                    except BaseException:
                        if original is not None:
                            print('igv-resources: original failure before cleanup: ' + str(original), file=sys.stderr)
                        print('igv-resources: stage=cleanup failed; retained: ' + str(stage.path), file=sys.stderr)
                        raise
                finally:
                    os.close(stage.fd)
        finally:
            os.close(lock)


def main():
    parser = argparse.ArgumentParser(description='Install explicitly selected fixed IGV reference recipes.',
        epilog='Installer owns the existing root. Installed members use 0755/0644. '
        'No --force or automatic deletion of old members/staging. Repeat install to resume a partial download.')
    parser.add_argument('--version', action='version', version='igv-resources ' + APP_RELEASE)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('catalog', help='show bundled reference recipes; never install a default')
    pin = sub.add_parser('pin', help='pin reviewed local files described by a JSON spec; no network')
    pin.add_argument('--spec', required=True, type=Path)
    pin.add_argument('--source-dir', required=True, type=Path)
    pin.add_argument('--license-file', required=True, type=Path)
    pin.add_argument('--rights-reviewed', required=True, action='store_true')
    prepare = sub.add_parser('install')
    selection = prepare.add_mutually_exclusive_group(required=True)
    selection.add_argument('--recipe', type=Path)
    selection.add_argument('--genome', help='exact ID of a bundled recipe')
    prepare.add_argument('--allow-network', action='store_true', help='explicitly enable HTTPS installation')
    prepare.add_argument('--resource-root', required=True, type=Path)
    prepare.add_argument('--source-dir', type=Path, help='already acquired recipe members, no network')
    prepare.add_argument('--rights-reviewed', action='store_true', required=True,
                         help='confirm acquisition and intended sharing rights for every recipe member')
    prepare.add_argument('--dry-run', action='store_true')
    prepare.add_argument('--reserve-gb', type=float, default=1, help='extra free-space reserve, default 1 GiB')
    check = sub.add_parser('verify')
    check.add_argument('--resource-root', required=True, type=Path)
    check.add_argument('--id', required=True, help='exact prepared member ID: recipe-id--version')
    inventory = sub.add_parser('list', help='verify every visible installed member; never select one automatically')
    inventory.add_argument('--resource-root', required=True, type=Path)
    args = parser.parse_args()
    if os.environ.get('TAFFISH_IGV_RESOURCE_ACTIVE') == '1':
        verify_root(Path('/igv-resources'))
    if args.command == 'catalog':
        print((Path('/opt/igv/recipes') / 'catalog.json').read_text())
        return
    if args.command == 'pin':
        pin_files(args)
        return
    require(args.resource_root.is_absolute(), '--resource-root must be absolute')
    if args.command == 'list':
        print(json.dumps(verify_root(args.resource_root), indent=2))
        return
    if args.command == 'verify':
        with Directory(args.resource_root) as root:
            verify_root(root)
            with Directory(parent=root, name=safe_name(args.id)) as member:
                print(json.dumps(verify(member, args.id), indent=2))
        return
    require(0 <= args.reserve_gb < 1000000, 'invalid reserve')
    if args.genome:
        args.recipe = Path('/opt/igv/recipes') / (safe_name(args.genome) + '.json')
    recipe = recipe_load(args.recipe)
    if args.dry_run:
        print(json.dumps(dict(resource=recipe['id'] + '--' + recipe['version'], recipe=recipe,
            recipe_sha256=hashlib.sha256(canonical(recipe)).hexdigest(),
            download_bytes=sum(f['size'] for f in recipe['files']), reserve_bytes=int(args.reserve_gb * 1024**3),
            destination=str(args.resource_root / (recipe['id'] + '--' + recipe['version'])),
            network=args.source_dir is None), indent=2))
        return
    require(args.source_dir is not None or args.allow_network, 'network is disabled; provide --source-dir or --allow-network')
    install(args.resource_root, recipe, args.source_dir, int(args.reserve_gb * 1024**3))


if __name__ == '__main__':
    try:
        signal.signal(signal.SIGINT, interrupt)
        signal.signal(signal.SIGTERM, interrupt)
        main()
    except Interrupted as error:
        print(f'igv-resources: stage=interrupted exit={128 + error.signum}; verified old members retained', file=sys.stderr)
        sys.exit(128 + error.signum)
    except (ValueError, OSError, KeyError, TypeError, tarfile.TarError) as error:
        print('igv-resources: stage=prepare-or-verify exit=1: ' + str(error), file=sys.stderr)
        sys.exit(1)
