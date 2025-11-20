package vllm

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/yungtweek/talkie/apps/llm-gateway/internal/logger"
)

// TestClientChat_Success verifies that the client correctly sends a request
// to the /v1/chat/completions endpoint and parses a successful response.
func TestClientChat_Success(t *testing.T) {
	// Setup a fake vLLM HTTP server.
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("expected POST method, got %s", r.Method)
		}
		if r.URL.Path != "/v1/chat/completions" {
			t.Fatalf("unexpected path: got %s, want %s", r.URL.Path, "/v1/chat/completions")
		}

		var reqBody ChatCompletionRequest
		if err := json.NewDecoder(r.Body).Decode(&reqBody); err != nil {
			t.Fatalf("failed to decode request body: %v", err)
		}
		if reqBody.Model != "test-model" {
			t.Errorf("unexpected model: got %q, want %q", reqBody.Model, "test-model")
		}
		if len(reqBody.Messages) == 0 {
			t.Fatalf("expected at least one message")
		}

		// Build a fake response
		resp := ChatCompletionResponse{
			ID:      "test-id",
			Object:  "chat.completion",
			Created: 1234567890,
			Model:   "test-model",
			Choices: []ChatChoice{
				{
					Index: 0,
					Message: ChatMessage{
						Role:    "assistant",
						Content: "hello from vLLM",
					},
					FinishReason: "stop",
				},
			},
			Usage: Usage{
				PromptTokens:     5,
				CompletionTokens: 7,
				TotalTokens:      12,
			},
		}

		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			t.Fatalf("failed to encode response: %v", err)
		}
	}))
	defer ts.Close()

	client := NewClient(ts.URL, 1000)

	ctx := context.Background()
	req := ChatCompletionRequest{
		Model: "test-model",
		Messages: []ChatMessage{
			{Role: "user", Content: "hi"},
		},
		Temperature: 0.1,
		MaxTokens:   32,
	}

	resp, err := client.Chat(ctx, req)
	if err != nil {
		t.Fatalf("Chat returned error: %v", err)
	}

	if resp.Model != "test-model" {
		t.Errorf("unexpected response model: got %q, want %q", resp.Model, "test-model")
	}
	if len(resp.Choices) != 1 {
		t.Fatalf("expected 1 choice, got %d", len(resp.Choices))
	}
	if resp.Choices[0].Message.Content != "hello from vLLM" {
		t.Errorf("unexpected content: got %q, want %q", resp.Choices[0].Message.Content, "hello from vLLM")
	}
	if resp.Usage.TotalTokens != 12 {
		t.Errorf("unexpected total tokens: got %d, want %d", resp.Usage.TotalTokens, 12)
	}
}

// TestClientChat_Non2xxStatus verifies that non-2xx responses are returned as errors.
func TestClientChat_Non2xxStatus(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "bad request", http.StatusBadRequest)
	}))
	defer ts.Close()

	client := NewClient(ts.URL, 1000)

	_, err := client.Chat(context.Background(), ChatCompletionRequest{Model: "test-model"})
	if err == nil {
		t.Fatal("expected error for non-2xx status, got nil")
	}
}

// TestClientChat_HTTPError verifies that HTTP-level failures (e.g. connection refused)
// are surfaced as errors.
func TestClientChat_HTTPError(t *testing.T) {
	// Create a server and close it immediately to force a connection error.
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	ts.Close()

	client := NewClient(ts.URL, 1000)

	_, err := client.Chat(context.Background(), ChatCompletionRequest{Model: "test-model"})
	if err == nil {
		t.Fatal("expected error due to HTTP failure, got nil")
	}
}

func TestMain(m *testing.M) {
	if err := logger.Init(); err != nil {
		panic(err)
	}
	defer logger.Sync()
	os.Exit(m.Run())
}
