package service_test

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/joho/godotenv"
	llmpb "github.com/yungtweek/talkie/apps/llm-gateway/gen/llm"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/config"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/logger"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/service"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/vllm"
)

func TestChatCompletion_Integration(t *testing.T) {
	// 짧은 테스트 모드에선 스킵
	if testing.Short() {
		t.Skip("skipping integration test in short mode")
	}

	// 환경 로드 (.env.dev + fallback)
	cfg := config.Load()

	t.Logf("vLLM URL = %s, model = %s, timeoutMs = %d", cfg.VLLMURL, cfg.DefaultModel, cfg.TimeoutMs)

	// vLLM 클라이언트 (이미 TLS InsecureSkipVerify 적용돼 있음)
	client := vllm.NewClient(cfg.VLLMURL, cfg.TimeoutMs)

	// 서비스 생성 (구현에 맞게 수정)
	svc := service.NewLLMService(client, cfg.DefaultModel)

	// 타임아웃 컨텍스트
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	req := &llmpb.ChatCompletionRequest{
		Model:        cfg.DefaultModel,
		SystemPrompt: "You are a helpful assistant.",
		UserPrompt:   "hello! vLLM 인테그레이션 테스트야. 한 줄만 대답해줘.",
		Context:      "",
		Temperature:  0.7,
		MaxTokens:    128,
		TopP:         0.95,
	}

	resp, err := svc.ChatCompletion(ctx, req)
	if err != nil {
		t.Fatalf("ChatCompletion failed: %v", err)
	}

	if resp == nil {
		t.Fatalf("ChatCompletion returned nil response")
	}

	// 응답 로그로 찍어보기 (필드 이름은 proto에 맞게 수정)
	t.Logf("completion response: %#v", resp)
}

func TestMain(m *testing.M) {
	if err := logger.Init(); err != nil {
		panic(err)
	}
	// Best effort: try to load .env.dev from common locations, but don't rely on it.
	_ = godotenv.Load(
		"../../.env.dev",
	)

	code := m.Run()

	// Ensure logs are flushed before exiting
	logger.Sync()

	os.Exit(code)
}
