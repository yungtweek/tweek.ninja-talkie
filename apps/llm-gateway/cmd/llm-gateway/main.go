package main

import (
	"log"

	"github.com/yungtweek/talkie/apps/llm-gateway/internal/config"
	grpcserver "github.com/yungtweek/talkie/apps/llm-gateway/internal/grpc"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/logger"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/service"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/vllm"
	"go.uber.org/zap"
)

func main() {
	// Initialize structured logger
	if err := logger.Init(); err != nil {
		log.Fatalf("failed to init logger: %v", err)
	}
	defer logger.Sync()

	// Load configuration (port, vLLM URL, defaults, timeouts, etc.)
	cfg := config.Load()

	addr := ":" + cfg.Port

	logger.Log.Info("Starting LLM Gateway",
		zap.String("addr", addr),
		zap.String("model", cfg.DefaultModel),
		zap.String("vllm_url", cfg.VLLMURL),
		zap.Int("timeout_ms", cfg.TimeoutMs),
	)

	// Create vLLM HTTP client
	vllmClient := vllm.NewClient(cfg.VLLMURL, cfg.TimeoutMs)

	// Create LLM gRPC service
	llmService := service.NewLLMService(vllmClient, cfg.DefaultModel)

	// Create and run gRPC server (blocking call)
	srv := grpcserver.New(addr, llmService)

	if err := srv.Run(); err != nil {
		logger.Log.Fatal("LLM Gateway gRPC server exited with error", zap.Error(err))
	}
}
