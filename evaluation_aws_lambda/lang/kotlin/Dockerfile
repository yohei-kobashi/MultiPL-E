# Kotlin language image layered on the common base.

ARG BASE_IMAGE=multipl-e-evaluation-base:latest
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ENV KOTLIN_VERSION=1.9.25
ENV KOTLIN_HOME=/opt/kotlin-${KOTLIN_VERSION}
ENV PATH="${KOTLIN_HOME}/bin:${PATH}"

# Install JDK required by the Kotlin compiler
RUN apt-get update -yqq \
 && apt-get install -yqq --no-install-recommends default-jdk-headless \
 && rm -rf /var/lib/apt/lists/*

# Install Kotlin command-line compiler
RUN tmpdir="$(mktemp -d)" \
 && wget -nv -O "${tmpdir}/kotlin.zip" "https://github.com/JetBrains/kotlin/releases/download/v${KOTLIN_VERSION}/kotlin-compiler-${KOTLIN_VERSION}.zip" \
 && mkdir -p /opt \
 && unzip -q "${tmpdir}/kotlin.zip" -d /opt \
 && mv /opt/kotlinc "${KOTLIN_HOME}" \
 && rm -rf "${tmpdir}"

# Sanity check: compile and run a tiny Kotlin program
RUN printf 'fun main() = println("ok")' > /tmp/Problem.kt \
 && kotlinc /tmp/Problem.kt -include-runtime -d /tmp/problem.jar \
 && java -jar /tmp/problem.jar | grep -q '^ok$' \
 && rm -f /tmp/Problem.kt /tmp/problem.jar

# Base image already sets the Lambda entrypoint and copies /var/task.
