
# The entire contents of proto/llm/Makefile is replaced with:
PROTO_DIR := .
OUT_DIR := ../../gen/llm

PROTOS := $(wildcard $(PROTO_DIR)/*.proto)

.PHONY: all gen clean

all: gen

# Generate Go code from .proto files
gen:
	@mkdir -p $(OUT_DIR)
	protoc \
		-I=$(PROTO_DIR) \
		--go_out=$(OUT_DIR) \
		--go-grpc_out=$(OUT_DIR) \
		--go_opt=paths=source_relative \
		--go-grpc_opt=paths=source_relative \
		$(PROTOS)

# Clean generated files
clean:
	rm -f $(OUT_DIR)/*.pb.go
