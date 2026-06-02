FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive

ENV TZ=Etc/UTC
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Common tools and apt-provided language runtimes. This remains a single
# non-Lambda amd64 image; Lambda RIC/Mangum and per-language ENTRYPOINTs stay out.
RUN apt-get update -yqq && apt-get install -yqq --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    git \
    gnupg \
    jq \
    locales \
    pkg-config \
    unzip \
    wget \
    xz-utils \
    zlib1g \
    libgmp10 \
    libodbc1 \
    libssl3 \
    libsctp1 \
    racket \
    python2 \
    python3 \
    python3-pip \
    python3-tqdm \
    python3-venv \
    default-jdk-headless \
    golang-go \
    php-cli \
    ruby \
    lua5.3 \
    lua-unit \
    r-base \
    rustc \
    scala \
    ocaml \
    ocaml-interp \
    ghc \
    libtest-deep-perl \
    gnat \
    gprbuild \
    fpc \
    coq \
    z3 \
 && (localedef -i en_US -f UTF-8 en_US.UTF-8 || true) \
 && rm -rf /var/lib/apt/lists/*

# D / DMD. Keep the amd64 image on the official DMD distribution so `rdmd`
# semantics match the AWS Lambda amd64 language image closely.
RUN mkdir -p /opt/dlang \
 && wget -qO /opt/dlang/install.sh https://dlang.org/install.sh \
 && bash /opt/dlang/install.sh install dmd-2.111.0 --path /opt/dlang
ENV PATH="/opt/dlang/dmd-2.111.0/linux/bin64:${PATH}"
ENV LD_LIBRARY_PATH="/opt/dlang/dmd-2.111.0/linux/lib64:${LD_LIBRARY_PATH}"
ENV LIBRARY_PATH="/opt/dlang/dmd-2.111.0/linux/lib64:${LIBRARY_PATH}"
ENV DMD=dmd
ENV DC=dmd

# Node.js / JavaScript / TypeScript
RUN curl -fsSL https://deb.nodesource.com/setup_current.x | bash - \
 && apt-get install -yqq --no-install-recommends nodejs \
 && npm install -g typescript \
 && rm -rf /var/lib/apt/lists/*

# Mono / C#
RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 3FA7E0328081BFF6A14DA29AA6A19B38D3D831EF \
 && echo "deb https://download.mono-project.com/repo/ubuntu stable-focal main" > /etc/apt/sources.list.d/mono-official-stable.list \
 && apt-get update --allow-insecure-repositories -yqq \
 && apt-get install -yqq --no-install-recommends mono-devel \
 && rm -rf /var/lib/apt/lists/*

# .NET / F# / Dafny runtime dependencies
RUN wget -q https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -O /tmp/packages-microsoft-prod.deb \
 && dpkg -i /tmp/packages-microsoft-prod.deb \
 && rm -f /tmp/packages-microsoft-prod.deb \
 && apt-get update -yqq \
 && apt-get install -yqq --no-install-recommends \
      dotnet-sdk-6.0 \
      dotnet-runtime-6.0 \
      dotnet-hostfxr-6.0 \
      dotnet-sdk-8.0 \
      libicu70 \
 && rm -rf /var/lib/apt/lists/*
ENV DOTNET_ROOT=/usr/share/dotnet
ENV PATH="${PATH}:/usr/share/dotnet"
ENV DOTNET_CLI_HOME=/tmp
ENV DOTNET_BUNDLE_EXTRACT_BASE_DIR=/tmp
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV DOTNET_ROLL_FORWARD=Major
RUN command -v dotnet \
 && dotnet --info >/dev/null \
 && if [ ! -e /usr/lib/dotnet ]; then ln -s /usr/share/dotnet /usr/lib/dotnet; fi

# Dafny
RUN mkdir -p /opt/dafny \
 && dotnet tool install --tool-path /opt/dafny dafny --version 4.3.0 \
 && ln -sf /opt/dafny/dafny /usr/local/bin/dafny \
 && dafny --version

# Kotlin
ENV KOTLIN_VERSION=1.9.25
ENV KOTLIN_HOME=/opt/kotlin-${KOTLIN_VERSION}
ENV PATH="${KOTLIN_HOME}/bin:${PATH}"
RUN tmpdir="$(mktemp -d)" \
 && wget -nv -O "${tmpdir}/kotlin.zip" "https://github.com/JetBrains/kotlin/releases/download/v${KOTLIN_VERSION}/kotlin-compiler-${KOTLIN_VERSION}.zip" \
 && unzip -q "${tmpdir}/kotlin.zip" -d /opt \
 && mv /opt/kotlinc "${KOTLIN_HOME}" \
 && rm -rf "${tmpdir}"

# Julia amd64
RUN curl -fsSL https://julialang-s3.julialang.org/bin/linux/x64/1.8/julia-1.8.2-linux-x86_64.tar.gz \
    | tar xz -C / \
 && ln -sf /julia-1.8.2/bin/julia /usr/local/bin/julia

# Swift amd64
RUN curl -fsSL https://download.swift.org/swift-5.7-release/ubuntu2204/swift-5.7-RELEASE/swift-5.7-RELEASE-ubuntu22.04.tar.gz \
    | tar xz -C / \
 && ln -sf /swift-5.7-RELEASE-ubuntu22.04/usr/bin/swift /usr/local/bin/swift \
 && ln -sf /swift-5.7-RELEASE-ubuntu22.04/usr/bin/swiftc /usr/local/bin/swiftc

# Java helper jar
RUN mkdir -p /usr/multiple \
 && wget -q https://repo.mavenlibs.com/maven/org/javatuples/javatuples/1.2/javatuples-1.2.jar -O /usr/multiple/javatuples-1.2.jar

# Luau
RUN wget -q https://github.com/Roblox/luau/releases/download/0.594/luau-ubuntu.zip -O /tmp/luau.zip \
 && unzip -q /tmp/luau.zip -d /bin/ \
 && rm -f /tmp/luau.zip

# Elixir / Erlang
RUN apt-get update -yqq \
 && apt-get install -yqq --no-install-recommends erlang elixir \
 && rm -rf /var/lib/apt/lists/*

# Clojure
RUN curl -L -O https://github.com/clojure/brew-install/releases/latest/download/linux-install.sh \
 && chmod +x linux-install.sh \
 && ./linux-install.sh --prefix /clojure \
 && rm -f linux-install.sh
ENV PATH="/clojure/bin:${PATH}"
RUN clojure -P

# Dart amd64
RUN wget -q https://storage.googleapis.com/dart-archive/channels/stable/release/3.8.1/sdk/dartsdk-linux-x64-release.zip -O /tmp/dartsdk.zip \
 && unzip -q /tmp/dartsdk.zip -d /usr/local/ \
 && rm -f /tmp/dartsdk.zip
ENV PATH="${PATH}:/usr/local/dart-sdk/bin:/root/.pub-cache/bin"

# Lean
ENV ELAN_HOME=/opt/elan
RUN curl -fsSL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -o /tmp/elan-init.sh \
 && env HOME=/opt bash /tmp/elan-init.sh -y --default-toolchain stable \
 && rm -f /tmp/elan-init.sh \
 && chmod -R a+rx ${ELAN_HOME} \
 && ln -sf ${ELAN_HOME}/bin/lean /usr/local/bin/lean \
 && ln -sf ${ELAN_HOME}/bin/lake /usr/local/bin/lake
ENV PATH="${ELAN_HOME}/bin:${PATH}"

# Python packages for humanevalplus and the local FastAPI server.
RUN python3 -m pip install --no-cache-dir numpy fastapi "uvicorn[standard]"

# Lightweight toolchain checks. Keep these cheap so rebuilds fail early when a
# language runtime is missing.
RUN gcc --version \
 && g++ --version \
 && python3 -V \
 && python2 -V \
 && java -version \
 && go version \
 && php -v \
 && ruby -v \
 && lua -v \
 && Rscript -e 'cat("ok\n")' | grep -q '^ok$' \
 && rustc --version \
 && scala -version \
 && ocaml -version \
 && ghc --version \
 && gnatmake --version \
 && gprbuild --version \
 && fpc -iV \
 && coqc --version \
 && z3 --version \
 && printf 'import std.stdio; void main(){ writeln("ok"); }' > /tmp/p.d \
 && rdmd /tmp/p.d | grep -q '^ok$' \
 && rm -f /tmp/p.d \
 && (csc /nologo /help >/dev/null || true) \
 && dotnet --info >/dev/null \
 && dafny --version \
 && kotlinc -version \
 && julia --version \
 && swift --version \
 && node -v \
 && tsc -v \
 && elixir --version \
 && clojure -Sdescribe >/dev/null \
 && dart --version \
 && lean --version

COPY src /code
WORKDIR /code
ENTRYPOINT ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "9090", "--workers", "4", "--limit-concurrency", "100"]
