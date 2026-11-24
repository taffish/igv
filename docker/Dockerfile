# Debian base manifest is pinned; APT resolves current Bookworm security packages.
# APT indexes/package bytes can drift or expire; this is not a full package snapshot.
FROM debian:12-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc AS novnc

ENV DEBIAN_FRONTEND=noninteractive

# Official noVNC tag archive is byte-pinned; upstream retention is not guaranteed.
ARG NOVNC_VERSION=1.7.0
ARG NOVNC_SOURCE_SHA256=b1003a11b6e6e8d8f7f5e5586daae7f8ca651d8aee0aa155ff9ac841c48f52c6

RUN apt-get -o Acquire::Retries=5 update \
 && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
      ca-certificates \
      curl \
 && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    curl --http1.1 -fSL --retry 5 --retry-delay 5 --retry-all-errors -o /tmp/novnc.tar.gz "https://github.com/novnc/noVNC/archive/refs/tags/v${NOVNC_VERSION}.tar.gz"; \
    echo "${NOVNC_SOURCE_SHA256}  /tmp/novnc.tar.gz" | sha256sum -c -; \
    mkdir -p /opt; \
    tar -xzf /tmp/novnc.tar.gz -C /opt; \
    mv "/opt/noVNC-${NOVNC_VERSION}" /opt/noVNC

FROM debian:12-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc

ENV DEBIAN_FRONTEND=noninteractive

# Official platform JRE and IGV zip below are fixed by version + SHA256.
# No fallback to a mutable latest URL; missing upstream bytes fail the build.
ARG TEMURIN_TAG=jdk-21.0.13.1%2B2
ARG TEMURIN_VERSION=21.0.13.1_2
ARG TEMURIN_X64_SHA256=18f44fab9065217f3ba61d0eef8a7b5f3c3713aa7293001b0d4ac10ede3850f0
ARG TEMURIN_AARCH64_SHA256=52bc58323d9266538a6361a3cf8365fc1186dd9510d7f33f623681c4aabb7e72
ARG IGV_VERSION=2.19.9
ARG IGV_ZIP_SHA256=733131d4537c7158b23c976cb57f2490afd609fc38153f4861bef88a36edf105

RUN apt-get -o Acquire::Retries=5 update \
 && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
      ca-certificates \
      curl \
 && sed -i 's|http://deb.debian.org/debian|https://deb.debian.org/debian|g; s|http://deb.debian.org/debian-security|https://deb.debian.org/debian-security|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get -o Acquire::Retries=5 update \
 && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
      fonts-dejavu-core \
      fontconfig \
      libasound2 \
      libfreetype6 \
      libx11-6 \
      libxext6 \
      libxi6 \
      libxrandr2 \
      libxrender1 \
      libxtst6 \
      openbox \
      procps \
      python3-websockify \
      unzip \
      websockify \
      x11vnc \
      xauth \
      xdotool \
      x11-utils \
      xvfb \
 && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/opt/java
ENV PATH=/opt/java/bin:${PATH}

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) jre_arch="x64"; jre_sha="${TEMURIN_X64_SHA256}" ;; \
        arm64) jre_arch="aarch64"; jre_sha="${TEMURIN_AARCH64_SHA256}" ;; \
        *) echo "unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl --http1.1 -fSL --retry 5 --retry-delay 5 --retry-all-errors -o /tmp/temurin-jre.tar.gz "https://github.com/adoptium/temurin21-binaries/releases/download/${TEMURIN_TAG}/OpenJDK21U-jre_${jre_arch}_linux_hotspot_${TEMURIN_VERSION}.tar.gz"; \
    echo "${jre_sha}  /tmp/temurin-jre.tar.gz" | sha256sum -c -; \
    mkdir -p "${JAVA_HOME}"; \
    tar -xzf /tmp/temurin-jre.tar.gz -C "${JAVA_HOME}" --strip-components=1; \
    ln -sf "${JAVA_HOME}/bin/java" /usr/local/bin/java; \
    rm -f /tmp/temurin-jre.tar.gz; \
    java -version >/tmp/java-version 2>&1; \
    grep -F "21.0.13.1" /tmp/java-version; \
    rm /tmp/java-version

RUN set -eux; \
    curl --http1.1 -fSL --retry 5 --retry-delay 5 --retry-all-errors -o /tmp/igv.zip "https://data.broadinstitute.org/igv/projects/downloads/2.19/IGV_${IGV_VERSION}.zip"; \
    echo "${IGV_ZIP_SHA256}  /tmp/igv.zip" | sha256sum -c -; \
    mkdir -p /opt; \
    unzip -q /tmp/igv.zip -d /opt; \
    mv "/opt/IGV_${IGV_VERSION}" /opt/igv; \
    rm -f /tmp/igv.zip; \
    chmod +x /opt/igv/igv.sh /opt/igv/igvtools /opt/igv/igvtools_gui /opt/igv/igvtools_gui_hidpi; \
    mkdir -p /docs; \
    ln -s /opt/igv/igvtools_readme.txt /docs/igvtools_readme.txt; \
    printf '%s\n' "${IGV_VERSION}" > /opt/igv/VERSION

COPY --from=novnc /opt/noVNC/ /opt/noVNC/
COPY docker/igv_runtime.py docker/igv-resources.py docker/rfb-probe.py docker/igv-check.py /opt/igv/libexec/
COPY docker/recipes/ /opt/igv/recipes/
COPY docker/igv-gui /usr/local/bin/igv-gui

# Fixed recipes pin resource bytes, not upstream availability. The explicit
# installer alone uses HTTPS; references are not bundled or fetched by smoke.
RUN set -eux; \
    chmod 755 /usr/local/bin/igv-gui /opt/igv/libexec/igv_runtime.py /opt/igv/libexec/igv-resources.py; \
    for name in igv igvtools igvtools_gui igvtools_gui_hidpi; do ln -s /opt/igv/libexec/igv_runtime.py "/usr/local/bin/$name"; done; \
    ln -s /opt/igv/libexec/igv-resources.py /usr/local/bin/igv-resources; \
    mkdir -p /work /igv-resources; \
    chmod -R a+rX /opt/igv /opt/java /opt/noVNC; \
    igv --version >/tmp/igv-version; \
    grep -Fx "${IGV_VERSION}" /tmp/igv-version; \
    igvtools version >/tmp/igvtools-version; \
    grep -F "IGV Version ${IGV_VERSION}" /tmp/igvtools-version; \
    igv-gui --help >/tmp/igv-gui-help; \
    igv-resources --help >/tmp/igv-resources-help; \
    rm /tmp/igv-version /tmp/igvtools-version /tmp/igv-gui-help /tmp/igv-resources-help
# GUI, process lifecycle and scientific fixtures are tested after the build,
# never as architecture/timing-sensitive Dockerfile assertions.

WORKDIR /work
ENV IGV_HOME=/opt/igv \
    IGV_VERSION=2.19.9 \
    IGV_JAVA_XMX=4g \
    PYTHONDONTWRITEBYTECODE=1 \
    TAFFISH_ENV=TAFFISH \
    TAFFISH_NAME=igv
