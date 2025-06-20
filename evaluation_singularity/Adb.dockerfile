Bootstrap: docker
From: ubuntu:22.04

%environment
    export DEBIAN_FRONTEND=noninteractive
    export TZ=Etc/UTC

%post
    apt-get update -yqq && \
        apt-get install -yqq python3-pip python3-tqdm gnat-12
    python3 -m pip install numpy fastapi "uvicorn[standard]"
    mkdir -p /code

%files
    src /code

%workdir /code

%runscript
    exec uvicorn api:app --host 0.0.0.0 --port 9090
