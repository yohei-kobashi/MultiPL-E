SINGULARITY_EXEC?=singularity

build: Dockerfile Adb.dockerfile
	${SINGULARITY_EXEC} build multipl-e-evaluation.sif Dockerfile
	${SINGULARITY_EXEC} build multipl-e-adb.sif Adb.dockerfile

test: build
	${SINGULARITY_EXEC} exec \
	--network none \
	--bind $(PWD)/test_inputs:/inputs:ro \
	--bind $(PWD)/test_outputs:/outputs:rw \
	multipl-e-evaluation.sif \
		python3 main.py --dir /inputs --output-dir /outputs --testing

all: build test