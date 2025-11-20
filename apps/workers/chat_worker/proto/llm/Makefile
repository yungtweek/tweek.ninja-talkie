# apps/workers/chat_worker/proto/llm/Makefile

# Use project root so paths don't depend on current working directory
PROJECT_ROOT := $(shell git rev-parse --show-toplevel)

# Directories (absolute, from project root)
PROTO_DIR := $(PROJECT_ROOT)/apps/llm-gateway/proto/llm
OUT_DIR   := $(PROJECT_ROOT)/apps/workers/chat_worker/infrastructure/grpc_stubs/llm

PROTOS := $(wildcard $(PROTO_DIR)/*.proto)

.PHONY: all gen clean

all: gen

gen:
	@echo "PROJECT_ROOT=$(PROJECT_ROOT)"
	@echo "PROTO_DIR=$(PROTO_DIR)"
	@echo "OUT_DIR=$(OUT_DIR)"
	@mkdir -p $(OUT_DIR)
	@touch $(OUT_DIR)/__init__.py
	@. $(PROJECT_ROOT)/.venv/bin/activate && \
	python -m grpc_tools.protoc \
		-I=$(PROTO_DIR) \
		--python_out=$(OUT_DIR) \
		--grpc_python_out=$(OUT_DIR) \
		--pyi_out=$(OUT_DIR) \
		$(PROTOS)
	@sed -i '' 's/^import llm_pb2 as llm__pb2/from . import llm_pb2 as llm__pb2/' $(OUT_DIR)/llm_pb2_grpc.py

clean:
	rm -f $(OUT_DIR)/*_pb2.py
	rm -f $(OUT_DIR)/*_pb2_grpc.py