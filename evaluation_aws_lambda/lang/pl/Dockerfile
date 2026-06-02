# Perl language image layered on the common base.

ARG BASE_IMAGE=multipl-e-evaluation-base:latest
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# Install Perl and helpful testing module (as used in the previous monolithic image)
RUN set -eux; \
    sed -i -E 's#http://[^ ]*archive.ubuntu.com/ubuntu#mirror://mirrors.ubuntu.com/mirrors.txt#g' /etc/apt/sources.list; \
    sed -i -E 's#http://security.ubuntu.com/ubuntu#mirror://mirrors.ubuntu.com/mirrors.txt#g' /etc/apt/sources.list || true; \
    apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 update -yqq && \
    apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 install -yqq --no-install-recommends \
        ca-certificates gnupg perl libtest-deep-perl && \
    rm -rf /var/lib/apt/lists/*

# Sanity check
RUN perl -e 'print "ok\n"' | grep -q '^ok$'

# Base image already sets the Lambda entrypoint and copies /var/task.

