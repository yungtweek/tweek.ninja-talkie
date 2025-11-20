package config

import (
	"log"
	"os"
	"strconv"

	"github.com/joho/godotenv"
)

// Config holds runtime configuration for the LLM Gateway.
type Config struct {
	Port         string // gRPC listen port (e.g. "50051")
	VLLMURL      string // vLLM base URL (e.g. "http://localhost:8000")
	DefaultModel string // default LLM model name
	TimeoutMs    int    // request timeout in milliseconds
}

// Load loads configuration from environment variables with fallback defaults.
func Load() *Config {
	_ = godotenv.Load(".env.dev")

	cfg := &Config{
		Port:         getEnv("LLM_GATEWAY_PORT", ""),
		VLLMURL:      getEnv("VLLM_URL", ""),
		DefaultModel: getEnv("LLM_DEFAULT_MODEL", ""),
		TimeoutMs:    getEnvInt("LLM_TIMEOUT_MS", 0),
	}

	// 필수 값 검증
	if cfg.VLLMURL == "" || cfg.DefaultModel == "" {
		log.Fatal("missing required env: VLLM_URL, LLM_DEFAULT_MODEL")
	}

	if cfg.TimeoutMs == 0 {
		cfg.TimeoutMs = 10000 // optional만 fallback 허용
	}

	return cfg
}

// getEnv reads an environment variable with a fallback default.
func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if i, err := strconv.Atoi(v); err == nil {
			return i
		}
	}
	return fallback
}
