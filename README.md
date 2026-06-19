# taf-igv

TAFFISH wrapper for [Integrative Genomics Viewer](https://igv.org/doc/desktop/),
the desktop genome browser for interactive inspection of alignments, variants,
annotations, coverage tracks, and genome browser sessions.

This app packages upstream IGV Desktop `2.19.8` from the official all-platform
zip distribution. It provides:

- `igv-gui`: a browser-accessible noVNC GUI session for normal TAFFISH use.
- `igv`: a direct IGV Java launcher for environments that already have an X
  display.
- `igvtools`: upstream command-line utilities for sorting, indexing, counting,
  and converting selected text/genomics formats.

IGV is especially useful in TAFFISH because large BAM/CRAM/VCF/BigWig datasets
often live on a server or cluster, while the visual review still needs an
interactive browser-like interface.

Release `2.19.8-r1` updates the packaged IGV Desktop distribution from
`2.19.7` to `2.19.8`. Upstream `2.19.8` adds HGVS search support and includes
search, chromosome aliasing, file-dialog, genome URL, and track configuration
fixes. The TAFFISH GUI/noVNC helper, Java 21 runtime route, and IGVTools
packaging design are unchanged.

## Installation

Install from the public TAFFISH Hub index:

```sh
taf update
taf install igv
```

Install the exact release:

```sh
taf install igv 2.19.8-r1
```

For local testing before the app is published to the public index:

```sh
taf install --from .
```

## Usage

Show TAFFISH app help:

```sh
taf-igv --help
```

Show the TAFFISH package version:

```sh
taf-igv --version
```

Start IGV GUI through Docker and noVNC:

```sh
TAFFISH_CONTAINER_BACKEND=docker \
TAFFISH_DOCKER_RUN_ARGS="-p 127.0.0.1:5801:5801" \
taf-igv igv-gui
```

Then open:

```text
http://127.0.0.1:5801/vnc.html?autoconnect=1&resize=scale
```

The helper prints this URL at startup, plus an SSH tunnel example for remote
servers.

Podman uses the same idea with the Podman run-args variable:

```sh
TAFFISH_CONTAINER_BACKEND=podman \
TAFFISH_PODMAN_RUN_ARGS="-p 127.0.0.1:5801:5801" \
taf-igv igv-gui
```

Use another host port if `5801` is already occupied:

```sh
TAFFISH_DOCKER_RUN_ARGS="-p 127.0.0.1:5802:5801" \
taf-igv igv-gui --host-port 5802
```

For a remote server:

```sh
ssh -L 5801:127.0.0.1:5801 user@server
```

Then open the same localhost URL in your local browser.

## GUI Options

The GUI helper creates an Xvfb display, starts Openbox and x11vnc, exposes it
through noVNC, then launches IGV.

Useful options:

```sh
taf-igv igv-gui --help
taf-igv igv-gui --geometry 1440x900
taf-igv igv-gui --java-xmx 8g
taf-igv igv-gui --password 'choose-a-password'
```

Pass extra IGV arguments after `--`:

```sh
taf-igv igv-gui --java-xmx 8g -- --genome hg38
taf-igv igv-gui -- session.xml
taf-igv igv-gui -- batch_script.txt
```

The direct launcher is also available:

```sh
taf-igv igv --version
taf-igv -- --help
```

The direct launcher requires an existing X display. For normal TAFFISH use,
`taf-igv igv-gui` is the recommended entry point.

## IGVTools

The upstream `igvtools` command-line utilities are included in the same
container. Use command mode to call them explicitly:

```sh
taf-igv igvtools
taf-igv igvtools sort input.bed sorted.bed
taf-igv igvtools index sorted.bed
taf-igv igvtools count alignments.bam coverage.tdf hg38
```

`igvtools` is useful for preprocessing text tracks, computing coverage, and
creating indexes for formats supported by IGVTools. It is not a replacement for
specialized tools such as `samtools` or `bcftools` for BAM/CRAM/VCF workflows.

The packaged `igvtools` launcher calls the upstream IGVTools Java module
directly. This keeps the command-line output cleaner than the stock shell
script, which also loads GUI/JIDE module arguments that are not needed for
headless IGVTools runs.

## Package

```text
name: igv
command: taf-igv
version: 2.19.8-r1
kind: tool
image: ghcr.io/taffish/igv:2.19.8-r1
upstream: IGV Desktop v2.19.8
runtime version: IGV 2.19.8
```

## Container

The container image is built from `docker/Dockerfile`. It starts from
`debian:12-slim`, installs the GUI/noVNC runtime, downloads a fixed
multi-architecture Eclipse Temurin Java 21 JRE tarball for the current build
architecture, then downloads the official IGV `IGV_2.19.8.zip` distribution.
Both downloads are verified with SHA-256 checksums.

The IGV `2.19.8` distribution checksum used by this release is:

```text
7476fc44f15788f52dfe1d40e99748c7aedcb9dbf6a91f7634a81344e50d07a6
```

It provides:

```text
igv
igv-gui
igvtools
igvtools_gui
igvtools_gui_hidpi
java
Xvfb
openbox
x11vnc
websockify/noVNC
```

The image is built and validated for:

```text
linux/amd64
linux/arm64
```

The `<taf-app:...>` entry embeds `--init` for Docker and Podman so long-running
GUI sessions receive signals and clean up child processes more reliably.

## Security And Ports

The documented examples bind the host port to `127.0.0.1`, not all network
interfaces. This is the safest default for local work and SSH tunneling.

By default the VNC session has no password because it is expected to be exposed
only on localhost. On shared machines or exposed network paths, use:

```sh
taf-igv igv-gui --password 'choose-a-password'
```

noVNC is served over plain HTTP inside the container. If a site needs TLS,
authentication, or external network exposure, put those controls outside the
container at the site level.

## Boundaries

This app packages IGV Desktop and the IGVTools utilities distributed with the
same upstream zip. It does not package a JBrowse/HiGlass-style web genome
browser service, cloud data credentials, reference genome downloads, or site
specific track/session catalogs.

IGV can open local files, mounted paths, URLs, and sessions according to
upstream IGV support. Remote cloud/object-store access may require user
credentials or site configuration outside the container.

On startup, upstream IGV may try to load a default remote genome definition and
annotation tracks. In offline clusters, start with a local genome/session file
or load local tracks after the GUI opens.

Apptainer support for GUI/noVNC sessions is site-dependent. The image contains
the needed programs, but port exposure and network policy vary across clusters.

## Smoke

The TAFFISH metadata declares Docker smoke checks that verify:

```text
exist: igv, igv-gui, igvtools, Java 21, Xvfb, x11vnc, websockify, openbox
test:  IGV launcher reports version 2.19.8
test:  Java 21 is available
test:  launcher and GUI helper help are available
test:  direct launcher gives a clear message when no X display exists
test:  igvtools version, main help, and sort help are available
test:  igvtools can sort a tiny BED file
test:  igv-gui starts Xvfb, x11vnc, noVNC, and the IGV process
test:  noVNC vnc.html is reachable inside the container
test:  the user-facing localhost URL is printed
```

These checks validate the packaged IGV distribution, Java runtime, IGVTools,
GUI helper, and browser access path. They do not replace manual visual
inspection with representative BAM/CRAM/VCF/track/session datasets.

## Upstream

```text
project: Integrative Genomics Viewer
homepage: https://igv.org/doc/desktop/
source:   https://github.com/igvteam/igv
release:  https://github.com/igvteam/igv/tree/v2.19.8
download: https://data.broadinstitute.org/igv/projects/downloads/2.19/IGV_2.19.8.zip
license:  MIT
citation: Thorvaldsdottir, Robinson, and Mesirov. 2013. Integrative Genomics Viewer (IGV): high-performance genomics data visualization and exploration
doi:      10.1093/bib/bbs017
pmid:     22517427
```
