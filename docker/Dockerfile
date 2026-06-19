FROM debian:12-slim AS novnc

ENV DEBIAN_FRONTEND=noninteractive

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

FROM debian:12-slim

ENV DEBIAN_FRONTEND=noninteractive

ARG TEMURIN_TAG=jdk-21.0.9%2B10
ARG TEMURIN_VERSION=21.0.9_10
ARG TEMURIN_X64_SHA256=aeab55d064a1a27a3744b0880b9b414077b4ed2b1790817eea3df60aec946431
ARG TEMURIN_AARCH64_SHA256=1d041073c65e834bdb4da732485a54ff829859dcd1549e7992f15bd73341be29
ARG IGV_VERSION=2.19.8
ARG IGV_ZIP_SHA256=7476fc44f15788f52dfe1d40e99748c7aedcb9dbf6a91f7634a81344e50d07a6

RUN apt-get -o Acquire::Retries=5 update \
 && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
      ca-certificates \
      curl \
 && sed -i 's|http://deb.debian.org/debian|https://deb.debian.org/debian|g; s|http://deb.debian.org/debian-security|https://deb.debian.org/debian-security|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get -o Acquire::Retries=5 update \
 && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
      dbus-x11 \
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
    java -version 2>&1 | grep -F "21.0.9"

RUN set -eux; \
    curl --http1.1 -fSL --retry 5 --retry-delay 5 --retry-all-errors -C - -o /tmp/igv.zip "https://data.broadinstitute.org/igv/projects/downloads/2.19/IGV_${IGV_VERSION}.zip"; \
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
COPY docker/igv /usr/local/bin/igv
COPY docker/igv-gui /usr/local/bin/igv-gui
COPY docker/igvtools /usr/local/bin/igvtools

RUN set -eux; \
    chmod +x /usr/local/bin/igv /usr/local/bin/igv-gui /usr/local/bin/igvtools; \
    ln -s /opt/igv/igvtools_gui /usr/local/bin/igvtools_gui; \
    ln -s /opt/igv/igvtools_gui_hidpi /usr/local/bin/igvtools_gui_hidpi; \
    command -v igv; \
    command -v igv-gui; \
    command -v igvtools; \
    command -v java; \
    command -v Xvfb; \
    command -v x11vnc; \
    command -v websockify; \
    command -v openbox; \
    command -v curl; \
    command -v unzip; \
    java -version 2>&1 | grep -F "21."; \
    igv --version | grep -Fx "IGV ${IGV_VERSION}"; \
    igv --help | grep -F "direct Java launcher" >/dev/null; \
    igv-gui --help | grep -F "browser-accessible noVNC session" >/dev/null; \
    test -s /opt/igv/lib/igv.jar; \
    test -s /opt/igv/igv.args; \
    igvtools version | grep -F "IGV Version ${IGV_VERSION}" >/dev/null; \
    igvtools 2>&1 | grep -F "Usage: igvtools" >/dev/null

WORKDIR /root

ENV IGV_HOME=/opt/igv
ENV IGV_VERSION=2.19.8
ENV IGV_JAVA_XMX=4g
ENV TAFFISH_ENV=TAFFISH
ENV TAFFISH_NAME=igv
