FROM ubuntu:22.04
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update -yqq && \
    apt-get install -yqq python3-pip python3-tqdm gnat-12
RUN python3 -m pip install numpy fastapi "uvicorn[standard]"

COPY src /code
WORKDIR /code
ENTRYPOINT ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "9090"]
