taf-igv 2.19.7-r1

TAFFISH wrapper for IGV Desktop, an interactive genome browser for alignments,
variants, annotations, coverage tracks, and genome browser sessions.

GUI mode:
  TAFFISH_CONTAINER_BACKEND=docker \
  TAFFISH_DOCKER_RUN_ARGS="-p 127.0.0.1:5801:5801" \
  taf-igv igv-gui

Then open:
  http://127.0.0.1:5801/vnc.html?autoconnect=1&resize=scale

Usage:
  taf-igv [TAF-APP-OPTION]
  taf-igv igv-gui [GUI-OPTIONS] [-- IGV-ARGS...]
  taf-igv igv [IGV-ARGS...]
  taf-igv igvtools [COMMAND] [OPTIONS...]
  taf-igv -- [IGV-ARGS...]

TAF app options:
  -h, --help       Show this help text
  -v, --version    Show package and command version
  --compile        Print generated shell code instead of running it
  --               Stop parsing TAFFISH wrapper options

Recommended forms:
  taf-igv igv-gui --help
  taf-igv igv --version
  taf-igv igvtools
  taf-igv -- --help

Docker and Podman port mapping:
  TAFFISH_CONTAINER_BACKEND=docker \
  TAFFISH_DOCKER_RUN_ARGS="-p 127.0.0.1:5801:5801" \
  taf-igv igv-gui

  TAFFISH_CONTAINER_BACKEND=podman \
  TAFFISH_PODMAN_RUN_ARGS="-p 127.0.0.1:5801:5801" \
  taf-igv igv-gui

Alternate host port:
  TAFFISH_DOCKER_RUN_ARGS="-p 127.0.0.1:5802:5801" \
  taf-igv igv-gui --host-port 5802

Remote server over SSH:
  On the server, run IGV with a localhost port mapping.
  From your laptop, tunnel the port:
    ssh -L 5801:127.0.0.1:5801 user@server
  Then open the same 127.0.0.1 URL in your local browser.

Common GUI options:
  --port PORT        noVNC HTTP listen port inside the container
  --host-port PORT   host port shown in the printed URL
  --geometry WxH     virtual screen size, for example 1440x900
  --java-xmx SIZE    Java maximum heap size, for example 8g
  --password PASS    require a VNC password
  --no-password      run without a VNC password, the default

Passing IGV arguments:
  taf-igv igv-gui -- --genome hg38
  taf-igv igv-gui -- session.xml
  taf-igv igv-gui -- batch_script.txt

IGVTools:
  taf-igv igvtools
  taf-igv igvtools sort input.bed sorted.bed
  taf-igv igvtools index sorted.bed
  taf-igv igvtools count alignments.bam coverage.tdf hg38

Direct launcher:
  taf-igv igv --version

The direct launcher requires an X display. For normal TAFFISH use, prefer the
igv-gui helper because it creates Xvfb, x11vnc, and noVNC for you.

Notes:
  - This app packages upstream IGV Desktop v2.19.7.
  - Java 21 is included through a fixed Eclipse Temurin JRE tarball.
  - IGVTools is included because it is part of the official IGV distribution.
  - The igvtools launcher calls the upstream Java module directly to avoid
    noisy GUI module warnings from the stock shell script.
  - The helper prints the exact browser URL at startup.
  - IGV may try to load a default remote genome on startup. Offline sites can
    start with a local genome/session file or load local tracks after opening.
  - The example binds the host port to 127.0.0.1. On shared machines, keep this
    local binding unless you have explicit access control.
  - Apptainer GUI/noVNC use is site-dependent because port, network, and X/VNC
    behavior vary across clusters.

Container:
  image: ghcr.io/taffish/igv:2.19.7-r1
  supported backends: apptainer, podman, docker
  supported native platforms: linux/amd64, linux/arm64

Upstream:
  project: Integrative Genomics Viewer
  homepage: https://igv.org/doc/desktop/
  source:   https://github.com/igvteam/igv
  release:  https://github.com/igvteam/igv/tree/v2.19.7
  download: https://data.broadinstitute.org/igv/projects/downloads/2.19/IGV_2.19.7.zip
  license: MIT
  citation: Thorvaldsdottir, Robinson, and Mesirov. 2013
  doi: 10.1093/bib/bbs017
  pmid: 22517427
