SINGULARITY_EXEC?=singularity

build: Dockerfile Adb.dockerfile
<<<<<<< HEAD:evaluation_arm64/Makefile
	${DOCKER_EXEC} build --platform linux/arm64 -t multipl-e-evaluation-arm64 .
	${DOCKER_EXEC} build --platform linux/arm64 -t ghcr.io/nuprl/multipl-e-arm64:adb -f Adb.dockerfile
=======
  ${SINGULARITY_EXEC} build --fakeroot multipl-e-evaluation.sif Dockerfile
  ${SINGULARITY_EXEC} build --fakeroot multipl-e-adb.sif Adb.dockerfile
>>>>>>> 06b577f176e8b1c804d9c523f4b69bbd7ba62154:evaluation_singularity/Makefile

test: build
	${SINGULARITY_EXEC} exec \
	--network none \
	--bind $(PWD)/test_inputs:/inputs:ro \
	--bind $(PWD)/test_outputs:/outputs:rw \
	multipl-e-evaluation.sif \
		python3 main.py --dir /inputs --output-dir /outputs --testing

all: build test