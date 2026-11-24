# taf-igv

IGV Desktop 2.19.9-r1: the official Java genome browser and IGVTools, with a supervised
browser-accessible noVNC desktop. The official IGV jar is unchanged.

## Installation

```sh
taf update
taf install igv
# Exact release, after publication:
taf install igv 2.19.9-r1
# Local candidate, from this app directory:
taf install --from .
```

`taf-igv --help` shows use-time help. `taf-igv -- --help` and
`taf-igv -- --version` call IGV; `taf-igv igvtools help count` calls a sibling
upstream executable. No separate installation of Java or a host desktop is required.

## Quick start: local, offline viewing

Work in the directory containing your data. IGV needs a reference; no production
reference is bundled. Supply an indexed FASTA, 2bit, or complete local genome JSON.
Generate a FASTA index once if necessary:

```sh
taf-igv igvtools index reference.fa
taf-igv igvtools sort input.bed sorted.bed
taf-igv igvtools index sorted.bed
```

Start one backend:

```sh
TAFFISH_CONTAINER_BACKEND=docker \
TAFFISH_DOCKER_RUN_ARGS="-p 127.0.0.1:5801:5801 --network bridge" \
taf-igv igv-gui --genome reference.fa -- sorted.bed

TAFFISH_CONTAINER_BACKEND=podman \
TAFFISH_PODMAN_RUN_ARGS="-p 127.0.0.1:5801:5801" \
taf-igv igv-gui --genome reference.fa -- sorted.bed

# Apptainer uses the Linux host network; do not pass Docker -p.
TAFFISH_CONTAINER_BACKEND=apptainer \
taf-igv igv-gui --bind-address 127.0.0.1 --genome reference.fa -- sorted.bed
```

Open http://127.0.0.1:5801/vnc.html?autoconnect=1&resize=scale after the
`ready` message. For a remote server, run this on your workstation first:

```sh
ssh -N -L 5801:127.0.0.1:5801 USER@HOST
```

Ctrl-C stops the session (130); TERM stops it with 143. Closing the main window
normally exits successfully only when the supporting components are still healthy.
Startup prints the URL and diagnostic directory before waiting. Readiness requires
the JVM, Xvfb, Openbox, x11vnc, HTTP bridge, an RFB handshake and the real main window.
A support failure remains an error even when the main window exits at the same time.

Use `--host-port 15801` with a Docker/Podman mapping
`-p 127.0.0.1:15801:5801`. For Apptainer change the listener too:
`--port 15801 --host-port 15801 --bind-address 127.0.0.1`.
Concurrent sessions also need distinct `--display :N` and `--vnc-port N`.

The default virtual desktop is 1440x900. noVNC scaling fits a smaller browser;
the helper positions the main window inside the desktop. Use IGV's File menu
to export snapshots/save sessions into the mounted working directory. Paths
visible in IGV are container paths, not arbitrary host paths.

## CLI, batch mode and other windows

```sh
taf-igv igvtools count sorted.bed coverage.tdf reference.chrom.sizes
taf-igv igv-gui --genome reference.fa -- -b commands.txt
taf-igv igv-gui --tools
taf-igv igv-gui --java-xmx 8g --genome reference.fa
```

The input to `count` includes an explicit local chromosome-sizes/genome file;
symbolic aliases that would download are rejected on the offline path.
Use the `.chrom.sizes` suffix for a tab-separated chromosome name/length file.
In batch mode, upstream IGV ignores the command-line genome during initial
loading: start `commands.txt` with `genome ./reference.fa`, before `load`, `goto`
or `snapshot` commands. Otherwise it can try to load its default online genome.
The upstream batch `genome` command does not strip quotes or support a path
containing spaces. Use a space-free reference basename in the working directory
(a local symlink is sufficient), even if that directory itself contains spaces.
Keep the `./` prefix: a bare filename also triggers an upstream parent-path error.
Other batch commands such as `load` and `snapshotDirectory` accept ordinary
double-quoted paths. This is an upstream syntax limitation, not a change to IGV.
IGV Desktop fills the virtual desktop; the separate IGVTools window keeps its
upstream fixed-size, non-resizable dialog and remains wholly visible.
The direct `igv`, `igvtools_gui` and `igvtools_gui_hidpi` commands require an
existing X display. The headless `igvtools` command does not.

TAFFISH command mode joins shell text rather than preserving argv boundaries.
Pass **literal quotes** through the wrapper for paths containing spaces:

```sh
taf-igv igvtools sort "'input data.bed'" "'sorted data.bed'"
taf-igv igv-gui --genome "'reference data.fa'" -- "'sorted data.bed'"
```

This also applies to `--log-dir`, `--state-dir`, and recipe/source paths.
Do not use arbitrary shell metacharacters in filenames. Batch-file syntax is
upstream IGV syntax, not TAFFISH shell syntax.

## Runtime state and online sources

Private HOME, XDG and temporary directories are created per session. Normal
shutdown removes only that session's runtime data and owned display endpoints.
No write to the image's /opt tree or another user's HOME is required.
Use `--log-dir logs` to retain component logs, process IDs and geometry receipts;
private VNC credentials are removed even when diagnostics are retained.
Cleanup errors are reported and cause failure; suspect paths are retained for
diagnosis rather than followed through replacement symlinks.

Preferences and upstream-managed downloads are ephemeral unless you explicitly
supply an existing writable state directory:

```sh
mkdir -p state
# Add the chosen backend's GUI port options from above.
taf-igv igv-gui --state-dir state --allow-network -- --genome hg38
```

`--allow-network` is an explicit opt-in to IGV's hosted catalogs, tracks and other
online facilities. The state directory must be a persistent writable mount.
Such upstream downloads are not a TAFFISH-verified shared library: they may lack
fixed checksums and can be changed by IGV. Never point this writable state root at
the read-only shared references below. For the direct launcher/IGVTools, the
equivalent variables are `IGV_ALLOW_NETWORK=1` and `IGV_STATE_DIR`, explicitly
passed into the container with the backend's environment options.

Offline launch requires explicit local inputs; launcher configuration disables
implicit genome catalog downloads and the IGV command listener. This is not a
general-purpose network security sandbox: user sessions, plugins and Java options
are not untrusted-code isolation. Use `--network none` for non-browser offline
jobs. Supply state via the documented interface rather than `--igvDirectory`,
custom `--preferences` or an exposed IGV command port.

## Shared reference resources

A hosted genome is independently reusable; its catalog is not itself the sequence.
`igv-resources` accepts exact fixed recipes and never selects a reference for the
user. `catalog` lists the bundled reviewed recipe(s). The initial sacCer3 recipe
contains only GCF_000146045.2 sequence and chromosome sizes (3,558,746 download
bytes), not annotations, optional hubs or the entire IGV catalog.

```sh
taf-igv igv-resources catalog
mkdir -p "$HOME/.local/share/taffish/resources/igv"
```

Choose exactly one writable setup binding and backend (ordinary personal install):

```sh
export TAFFISH_CONTAINER_BACKEND=docker
export TAFFISH_DOCKER_RUN_ARGS="-v $HOME/.local/share/taffish/resources/igv:/resources:rw"

# Or:
export TAFFISH_CONTAINER_BACKEND=podman
export TAFFISH_PODMAN_RUN_ARGS="-v $HOME/.local/share/taffish/resources/igv:/resources:rw"

# Or, on Linux:
export TAFFISH_CONTAINER_BACKEND=apptainer
export TAFFISH_APPTAINER_RUN_ARGS="--bind $HOME/.local/share/taffish/resources/igv:/resources:rw"

TAFFISH_IGV_RESOURCE_AUTO_MOUNT=0 taf-igv igv-resources install --genome sacCer3 --resource-root /resources --rights-reviewed --dry-run
TAFFISH_IGV_RESOURCE_AUTO_MOUNT=0 taf-igv igv-resources install --genome sacCer3 --resource-root /resources --rights-reviewed --allow-network
unset TAFFISH_DOCKER_RUN_ARGS TAFFISH_PODMAN_RUN_ARGS TAFFISH_APPTAINER_RUN_ARGS
```

A dry-run reports exact ID/version, HTTPS sources, sizes, SHA256, license notice and
free-space reserve without changing files or connecting. Installation needs either
`--allow-network` or an offline `--source-dir` containing those exact named files.
Use the same port setup as Quick start, then:

```sh
taf-igv igv-gui --resource sacCer3--GCF_000146045.2-sequence-20261122
```

Discovery order is `TAFFISH_IGV_RESOURCE_PATH`, then
`~/.local/share/taffish/resources/igv`,
`/usr/local/share/taffish/resources/igv`, and
`/opt/taffish/resources/igv`. The selected root is mounted read-only at
`/igv-resources`; every visible installed member is fully verified by the launcher
and helper. A corrupt higher-priority root fails, not silently falls through.
`TAFFISH_IGV_RESOURCE_AUTO_MOUNT=0` disables discovery. Valid root symlinks resolve
to their physical target; dangling links fail. Auto-mount paths reject whitespace,
commas, colons and glob characters. Use an explicit backend bind for those paths
and `--genome /igv-resources/ID--VERSION/genome.json` or `--resource ID--VERSION`.
For manual exposure, use `-v SOURCE:/igv-resources:ro` (Docker/Podman), or
`--bind SOURCE:/igv-resources:ro` (Apptainer), with the run-args value quoted for
the host shell. Explicit `--resource` verifies the complete library even without
auto-discovery. Project-generated references may instead be mounted anywhere and
selected explicitly; they are not falsely labelled as a global database.

For site installation, the administrator creates and owns one 0755 root, for
example `/usr/local/share/taffish/resources/igv`, then runs the same explicit setup
with that host path as the writable binding. For Docker the installer can map its
UID/GID with `--user UID:GID`; rootless Podman can use `--userns keep-id`.
For Apptainer the installer is the invoking Linux user. No helper invokes sudo
or changes directory ownership. Ordinary users only need traverse/read access;
they run the read-only discovery or manual bind without network or administrator
privileges. Published member directories/files are 0755/0644; private download
cache/staging is 0700 and the persistent flock inode is 0600.

Installation has one nonblocking lock per library, resumable bounded-retry HTTPS
downloads, SHA/size checks, per-file free-space checks and same-filesystem
no-replace atomic promotion. Allow roughly twice the download size plus a default
1 GiB reserve (`--reserve-gb`). A complete same-recipe member is an idempotent
skip. Bad cache, conflicting identity, unexpected files, hardlinks or unsafe
permissions fail closed. Zero-byte partials can resume. INT/TERM retain old
members and reusable private partials; only files owned by the interrupted
transaction are eligible for cleanup. SIGKILL may leave a private staging
directory; it is never treated as installed or automatically deleted. The lock
file is deliberately retained so waiters cannot acquire different lock inodes.
There is no destructive `--force`: inspect/quarantine a specific broken member
while no installer runs, then repeat installation. Use a new version for changed
source bytes.

Custom recipes can be pinned with `igv-resources pin --spec spec.json
--source-dir files --license-file rights.txt --rights-reviewed` (redirect JSON
output to a new file). The spec uses the bundled recipe's schema, ID, version,
source, genome definition and named HTTPS files; pin computes size/SHA from
reviewed local acquisition. Local genome URLs must name exactly the recipe files;
FASTA requires a prepared index. First-acquisition SHA is not an upstream-signed
authenticity guarantee. Review source and acquisition/site-sharing rights
separately; program MIT licensing does not license all genome/annotation data.

## Security, scope and provenance

The HTTP UI has **no TLS** and no authentication by default. Always bind the host
port to loopback and use SSH for remote access. `--password-file` provides legacy
VNC authentication (1–8 bytes), not encryption; the old `--password` option exposes
a secret in argv and is discouraged. Never expose VNC or the IGV command socket.
Multiuser public deployments require site-managed authentication/TLS outside this app.

IGV-Web, igv.js, igv-notebook and igv-reports are independently versioned companions,
not dependencies invoked by IGV Desktop. They are not bundled. Normal IGV snapshots
and sessions are native outputs; this app does not invent a new scientific report.

The official v2.19.9 tag is `c102eb6f8404e55fbd4780ffd3c525ffc4cd6c49`.
The official all-platform zip SHA256 is
`733131d4537c7158b23c976cb57f2490afd609fc38153f4861bef88a36edf105`.
Compared with 2.19.8, upstream changes concern autoscaling/categories and complete
reading of remote concatenated gzip members. No upstream Java code is patched.

Debian Bookworm base is manifest-pinned; APT security packages remain a moving
source, with drift/retention comments beside the relevant Dockerfile instructions.
Temurin 21.0.13.1+2 and noVNC 1.7.0 archives are byte-pinned for each architecture.
The Java build is listed in Adoptium's November 2026 Java4Shell fix guidance.
No GUI, timing-sensitive integration test or CPU-specific output assertion runs
during Dockerfile construction. Full runtime checks run separately.

IGV metadata catalog snapshot:
`igvteam/igv-data@28a3b40cdb8313e90e84617e5336f3f947221c0d`.
The reviewed recipe is a deliberate sequence-only local configuration based on
that source; optional annotation/hub URLs remain outside its claimed scope.
The full MIT metadata notice and UCSC resource-use references are stored in the
recipe and installed RESOURCE_LICENSE.txt. The image's IGV/JRE/noVNC distribution
licenses remain with their upstream files. Packaging license: Apache-2.0; IGV: MIT.

## Development checkout

Short commands such as `taf run -- --version` and `taf run igvtools help` work
from this app directory. With TAFFISH 0.12.0, the long-running `taf run igv-gui`
path did not stream the startup information in the checkout audit and reported
exit 1 when interrupted. It is not the supported GUI launch path. Build once,
then invoke the generated wrapper, with the backend-specific options above:

```sh
taf build
TAFFISH_CONTAINER_BACKEND=docker \
TAFFISH_DOCKER_RUN_ARGS="-p 127.0.0.1:5801:5801" \
./target/taf-igv-v2.19.9-r1 igv-gui --genome reference.fa -- sorted.bed
```

The installed `taf-igv` and generated wrapper expose the same app commands.
Do not commit generated `target` artifacts; release-source cleanup keeps only
`target/.gitkeep`. This development limitation does not change IGV or its algorithms.

## Verification and limits

Declared platforms: linux/amd64 and linux/arm64. Native builds and real generated
wrapper tests passed on ARM64 Docker/Podman and xjp amd64 Docker/Podman/Apptainer.
The exact offline matrix also passed read-only, non-root execution. Tests cover
IGVTools sort/index/count, local-reference GUI input and PNG export, actual
INT/TERM shutdown, support failures, closed output, resource installation,
corrupt-library rejection, interrupted recovery, idempotence and read-only sharing.
The browser was exercised through SSH with real menu/popup input, PNG export,
zoom and narrow-window scaling. An independent UID 1002 could read the shared
reference without write permission. The reviewed small reference also passed an
explicit HTTPS install and subsequent network-disabled verification.

Measured final uncompressed image sizes: 775,432,315 bytes (ARM64) and
776,840,949 bytes (amd64). Main image content is the system/X desktop, Java and
the unchanged IGV distribution; no large reference database is baked in.
Validation covers synthetic local data and explicitly identified reference
mechanisms, not production-data scientific acceptance or all hosted genomes.
No publication is implied by these local checks. See release.md and the maintainer's
evidence receipt for the final tested image, wrapper and backend identities.

## References

- Manual: https://igv.org/doc/desktop/
- Source: https://github.com/igvteam/igv/tree/v2.19.9
- Genome metadata: https://github.com/igvteam/igv-data
- Resource terms: https://hgdownload.soe.ucsc.edu/downloads.html
- Java fix: https://adoptium.net/es/news/2026/11/temurin-november-2026-cspu-java4shell
- Citation: Thorvaldsdottir, Robinson and Mesirov (2013), DOI 10.1093/bib/bbs017, PMID 22517427.
