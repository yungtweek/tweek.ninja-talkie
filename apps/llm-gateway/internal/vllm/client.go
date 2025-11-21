package vllm

import (
	"bufio"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/go-resty/resty/v2"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/logger"
	"go.uber.org/zap"
)

// Client is a minimal HTTP client for talking to a vLLM server that exposes
// an OpenAI-compatible /v1/chat/completions endpoint.
type Client struct {
	http *resty.Client
}

// OpenAIChatCompletionChunk represents a single SSE chunk for streamed chat completions.
type OpenAIChatCompletionChunk struct {
	ID      string `json:"id"`
	Object  string `json:"object"`
	Created int64  `json:"created"`
	Model   string `json:"model"`

	Choices []struct {
		Index        int    `json:"index"`
		FinishReason string `json:"finish_reason"`

		Delta struct {
			Role    string `json:"role"`
			Content string `json:"content"`
		} `json:"delta"`
	} `json:"choices"`

	Usage struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
		TotalTokens      int `json:"total_tokens"`
	} `json:"usage"`
}

// NewClient creates a new vLLM client with the given base URL.
// Example: baseURL = "http://localhost:8000"
func NewClient(baseURL string, timeoutMs int) *Client {
	httpClient := &http.Client{
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		},
		Timeout: time.Duration(timeoutMs) * time.Millisecond,
	}

	c := resty.NewWithClient(httpClient).
		SetBaseURL(baseURL).
		SetHeader("Content-Type", "application/json")

	return &Client{
		http: c,
	}
}

// Chat sends a ChatCompletionRequest to the vLLM server and returns the parsed response.
func (c *Client) Chat(ctx context.Context, req ChatCompletionRequest) (*ChatCompletionResponse, error) {
	logger.Log.Debug("vLLM Chat request",
		zap.String("endpoint", "/v1/chat/completions"),
	)

	var resp ChatCompletionResponse

	r, err := c.http.R().
		SetContext(ctx).
		SetBody(req).
		SetResult(&resp).
		Post("/v1/chat/completions")
	if err != nil {
		logger.Log.Error("vLLM HTTP request failed",
			zap.Error(err),
		)
		return nil, fmt.Errorf("vLLM HTTP request failed: %w", err)
	}

	logger.Log.Debug("vLLM HTTP response received",
		zap.Int("status_code", r.StatusCode()),
	)

	if status := r.StatusCode(); status < 200 || status >= 300 {
		logger.Log.Error("vLLM non-2xx status",
			zap.Int("status_code", status),
			zap.ByteString("body", r.Body()),
		)
		return nil, fmt.Errorf("vLLM returned non-2xx status %d: %s", status, string(r.Body()))
	}

	return &resp, nil
}

// ChatStream sends a streaming ChatCompletionRequest to the vLLM server.
// It expects the vLLM server to expose an OpenAI-compatible SSE stream from
// /v1/chat/completions when the request has Stream set to true.
func (c *Client) ChatStream(ctx context.Context, req ChatCompletionRequest, onChunk StreamHandler) error {
	logger.Log.Debug("vLLM ChatStream request",
		zap.String("endpoint", "/v1/chat/completions"),
	)

	// Ensure stream flag is enabled on the outgoing request.
	req.Stream = true

	r, err := c.http.R().
		SetContext(ctx).
		SetBody(req).
		SetDoNotParseResponse(true).
		Post("/v1/chat/completions")
	if err != nil {
		logger.Log.Error("vLLM HTTP stream request failed", zap.Error(err))
		return fmt.Errorf("vLLM HTTP stream request failed: %w", err)
	}
	defer r.RawBody().Close()

	if status := r.StatusCode(); status < 200 || status >= 300 {
		logger.Log.Error("vLLM stream non-2xx status",
			zap.Int("status_code", status),
		)
		return fmt.Errorf("vLLM stream returned non-2xx status %d", status)
	}

	scanner := bufio.NewScanner(r.RawBody())

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		if !strings.HasPrefix(line, "data: ") {
			continue
		}

		payload := strings.TrimPrefix(line, "data: ")
		if payload == "[DONE]" {
			break
		}

		var raw OpenAIChatCompletionChunk
		if err := json.Unmarshal([]byte(payload), &raw); err != nil {
			logger.Log.Error("failed to unmarshal vLLM stream chunk", zap.Error(err))
			return fmt.Errorf("failed to unmarshal vLLM stream chunk: %w", err)
		}

		if len(raw.Choices) == 0 {
			continue
		}

		choice := raw.Choices[0]

		chunk := ChatCompletionStreamChunk{
			DeltaText:        choice.Delta.Content,
			FinishReason:     choice.FinishReason,
			Index:            choice.Index,
			PromptTokens:     raw.Usage.PromptTokens,
			CompletionTokens: raw.Usage.CompletionTokens,
			TotalTokens:      raw.Usage.TotalTokens,
		}

		if logger.Log != nil {
			logger.Log.Debug("vLLM ChatStream chunk",
				zap.String("delta_text", chunk.DeltaText),
				zap.String("finish_reason", chunk.FinishReason),
			)
		}

		if err := onChunk(chunk); err != nil {
			logger.Log.Warn("ChatStream callback returned error", zap.Error(err))
			return err
		}
	}

	if err := scanner.Err(); err != nil {
		logger.Log.Error("vLLM ChatStream scanner error", zap.Error(err))
		return fmt.Errorf("vLLM stream scanner error: %w", err)
	}

	logger.Log.Debug("vLLM ChatStream completed")
	return nil
}
