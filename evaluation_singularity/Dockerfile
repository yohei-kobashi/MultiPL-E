Bootstrap: docker
From: ubuntu:22.04

%environment
    export DEBIAN_FRONTEND=noninteractive
    export TZ=Etc/UTC
    export PATH="/julia-1.8.2/bin:/swift-5.7-RELEASE-ubuntu22.04/usr/bin:/erlang/bin:/elixir/bin:/clojure/bin:$PATH"
    export LANG=C.UTF-8

%post
    apt-get update -yqq && apt-get install -yqq \
        curl racket build-essential python3-pip python3-tqdm \
        default-jdk-headless \
        golang-go \
        php-cli \
        ruby \
        lua5.3 \
        r-base \
        rustc \
        scala \
        ocaml-interp \
        ocaml \
        ghc \
        libtest-deep-perl \
        wget \
        lua-unit \
        aspnetcore-runtime-6.0

    apt-get install -yqq libtest-deep-perl
    apt-get install -yqq wget

    # JS/TS
    curl -fsSL https://deb.nodesource.com/setup_current.x | bash -
    apt-get install -y nodejs
    npm install -g typescript

    # Dlang
    wget https://netcologne.dl.sourceforge.net/project/d-apt/files/d-apt.list -O /etc/apt/sources.list.d/d-apt.list
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys EDC4FB09C3AEEDD0
    apt-get update
    apt-get -y --allow-unauthenticated install --reinstall d-apt-keyring
    apt-get update && apt-get install -yqq dmd-compiler dub

    # C#
    apt install -y gnupg ca-certificates
    apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 3FA7E0328081BFF6A14DA29AA6A19B38D3D831EF
    echo "deb https://download.mono-project.com/repo/ubuntu stable-focal main" | tee /etc/apt/sources.list.d/mono-official-stable.list
    apt update --allow-insecure-repositories
    apt install -yqq mono-devel

    # Julia
    curl https://julialang-s3.julialang.org/bin/linux/x64/1.8/julia-1.8.2-linux-x86_64.tar.gz | tar xz

    # Swift
    curl https://download.swift.org/swift-5.7-release/ubuntu2204/swift-5.7-RELEASE/swift-5.7-RELEASE-ubuntu22.04.tar.gz | tar xz

    # Javatuples
    mkdir /usr/multiple && wget https://repo.mavenlibs.com/maven/org/javatuples/javatuples/1.2/javatuples-1.2.jar -O /usr/multiple/javatuples-1.2.jar

    # Luau
    wget https://github.com/Roblox/luau/releases/download/0.594/luau-ubuntu.zip -O /tmp/luau.zip && unzip /tmp/luau.zip -d /bin/

    # Elixir
    mkdir -p /erlang && \
        cd /erlang && \
        wget -nv -O erlang.tar.gz https://builds.hex.pm/builds/otp/ubuntu-22.04/OTP-27.0.tar.gz && \
        tar xzf erlang.tar.gz --strip-components=1 && \
        ./Install -minimal "$(pwd)"

    apt-get update && \
        apt-get -y --no-install-recommends install \
        ca-certificates \
        libodbc1 \
        libssl3 \
        libsctp1

    mkdir -p /elixir && \
        cd /elixir && \
        wget -nv -O elixir.zip https://builds.hex.pm/builds/elixir/v1.17.2-otp-27.zip && \
        unzip -q elixir.zip

    # Clojure
    curl -L -O https://github.com/clojure/brew-install/releases/latest/download/linux-install.sh
    chmod +x linux-install.sh
    ./linux-install.sh --prefix /clojure
    clojure -P

    # Dart
    wget -qO- https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/dart.gpg
    echo 'deb [signed-by=/usr/share/keyrings/dart.gpg arch=amd64] https://storage.googleapis.com/download.dartlang.org/linux/debian stable main' | tee /etc/apt/sources.list.d/dart_stable.list
    apt-get update -yqq && apt-get install -yqq dart

    python3 -m pip install numpy fastapi "uvicorn[standard]"

    mkdir -p /code

%files
    src /code

%workdir /code

%runscript
    exec uvicorn api:app --host 0.0.0.0 --port 9090
