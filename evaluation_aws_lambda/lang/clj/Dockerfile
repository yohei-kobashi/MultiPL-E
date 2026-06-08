# Clojure language image layered on the common base.
# Installs Java and Clojure from Ubuntu packages for reproducible builds.

ARG BASE_IMAGE=multipl-e-evaluation-base:latest
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# Java runtime/toolchain and Clojure runtime jars.
RUN apt-get update -yqq \
 && apt-get install -yqq --no-install-recommends \
      default-jdk-headless \
      clojure \
      libclojure-java \
      libspec-alpha-clojure \
      libcore-specs-alpha-clojure \
 && rm -rf /var/lib/apt/lists/*

# Make Clojure runtime jars available to the Lambda runtime user.
RUN mkdir -p /opt/clojure \
 && find /usr/share/java -maxdepth 1 \
      \( -name 'clojure*.jar' -o -name 'spec.alpha*.jar' -o -name 'core.specs.alpha*.jar' \) \
      -exec cp -v {} /opt/clojure/ \; \
 && test -n "$(find /opt/clojure -maxdepth 1 -name 'clojure*.jar' -print -quit)" \
 && chmod 0755 /opt/clojure \
 && chmod 0644 /opt/clojure/*.jar

# Base image already sets the Lambda entrypoint and copies /var/task.
