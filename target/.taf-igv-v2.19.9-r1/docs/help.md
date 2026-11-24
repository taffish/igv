taf-igv 2.19.9-r1 — IGV Desktop, IGVTools and browser viewing.

Usage:
  taf-igv --help
  taf-igv -- --help
  taf-igv -- --version
  taf-igv igvtools <command> [arguments]
  taf-igv igv-gui --genome reference.fa [options] -- [IGV arguments]

Local data:
  Prepare reference.fa and reference.fa.fai; references are not bundled.
  Missing local resources fail; normal use does not implicitly download.
  Prepare an index: taf-igv igvtools index reference.fa
  Sort/index a track:
    taf-igv igvtools sort input.bed sorted.bed
    taf-igv igvtools index sorted.bed
  Output: sorted.bed and sorted.bed.idx in the current directory.
  Show command help: taf-igv igvtools help count

Browser session (run in the directory containing the reference and tracks):
  Docker:
    TAFFISH_CONTAINER_BACKEND=docker TAFFISH_DOCKER_RUN_ARGS="-p 127.0.0.1:5801:5801" taf-igv igv-gui --genome reference.fa
  Podman:
    TAFFISH_CONTAINER_BACKEND=podman TAFFISH_PODMAN_RUN_ARGS="-p 127.0.0.1:5801:5801" taf-igv igv-gui --genome reference.fa
  Apptainer (Linux; shares host network, no -p):
    TAFFISH_CONTAINER_BACKEND=apptainer taf-igv igv-gui --bind-address 127.0.0.1 --genome reference.fa
  Open http://127.0.0.1:5801/vnc.html?autoconnect=1&resize=scale after "ready".
  Remote server: ssh -N -L 5801:127.0.0.1:5801 USER@HOST
  Ctrl-C or closing the IGV main window stops this session.
  No TLS; no password by default. Keep HTTP on host loopback; use SSH remotely.
  VNC is loopback-only. Do not expose it or IGV command ports.
  --password-file secret.txt enables VNC authentication, not encryption.
  Export snapshots/save sessions into the mounted working directory.
  --log-dir logs retains diagnostics; --state-dir state keeps writable preferences.
  Default geometry: 1440x900; use noVNC scaling in smaller browser windows.
  --host-port changes the printed mapped port; --port changes the listener.
  IGVTools window: replace --genome reference.fa with --tools.
  More options: taf-igv igv-gui --help

Shared references (explicit setup only; choose a reviewed member):
  taf-igv igv-resources catalog
  mkdir -p "$HOME/.local/share/taffish/resources/igv"
  Use the backend run-args variable below for a writable /resources mount:
    Docker: TAFFISH_DOCKER_RUN_ARGS="-v $HOME/.local/share/taffish/resources/igv:/resources:rw"
    Podman: TAFFISH_PODMAN_RUN_ARGS="-v $HOME/.local/share/taffish/resources/igv:/resources:rw"
    Apptainer: TAFFISH_APPTAINER_RUN_ARGS="--bind $HOME/.local/share/taffish/resources/igv:/resources:rw"
  With that variable exported and the matching backend selected:
    TAFFISH_IGV_RESOURCE_AUTO_MOUNT=0 taf-igv igv-resources install --genome sacCer3 --resource-root /resources --rights-reviewed --dry-run
    TAFFISH_IGV_RESOURCE_AUTO_MOUNT=0 taf-igv igv-resources install --genome sacCer3 --resource-root /resources --rights-reviewed --allow-network
  Unset the temporary writable run-args afterward.
  Launch with the backend's GUI port options and:
    taf-igv igv-gui --resource sacCer3--GCF_000146045.2-sequence-20261122
  Auto-discovery: personal resources/igv, /usr/local/share/taffish/resources/igv,
  then /opt/taffish/resources/igv. Mount is read-only; choose a member explicitly.
  Override: TAFFISH_IGV_RESOURCE_PATH=/absolute/prepared/root
  Disable: TAFFISH_IGV_RESOURCE_AUTO_MOUNT=0
  Auto paths cannot contain whitespace, commas, colons or glob characters.
  Manual read-only bind: SOURCE:/igv-resources:ro using -v (Docker/Podman)
  or --bind (Apptainer); see README for paths with spaces and site installation.
  Custom local genomes remain supported through --genome.
  Online upstream sources require --allow-network --state-dir state (create state
  first); these downloads are not a verified shared library.

Paths with spaces:
  TAFFISH joins command text. Preserve literal quotes across the wrapper:
    taf-igv igvtools sort "'input data.bed'" "'sorted data.bed'"
  Apply the same quoting to GUI paths. Avoid shell metacharacters in filenames.

Details: https://github.com/taffish/igv
Upstream: https://igv.org/doc/desktop/
