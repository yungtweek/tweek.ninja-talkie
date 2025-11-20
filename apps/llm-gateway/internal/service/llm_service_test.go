package service

import (
	"context"
	"testing"
	"time"

	pb "github.com/yungtweek/talkie/apps/llm-gateway/gen/llm"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/logger"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/vllm"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// fakeVLLMClient is a simple test double implementing VLLMClient.
type fakeVLLMClient struct {
	lastReq vllm.ChatCompletionRequest
	resp    *vllm.ChatCompletionResponse
	err     error
}

func (f *fakeVLLMClient) Chat(ctx context.Context, req vllm.ChatCompletionRequest) (*vllm.ChatCompletionResponse, error) {
	f.lastReq = req
	return f.resp, f.err
}

func (f *fakeVLLMClient) ChatStream(ctx context.Context, req vllm.ChatCompletionRequest, onChunk vllm.StreamHandler) error {
	// For current tests we only exercise unary Chat. This no-op implementation
	// satisfies the VLLMClient interface for streaming. Tests that need to
	// assert streaming behavior can extend this fake to record and invoke
	// onChunk as needed.
	return nil
}

func TestLLMService_ChatCompletion_Success(t *testing.T) {
	if err := logger.Init(); err != nil {
		t.Fatalf("failed to init logger: %v", err)
	}
	defer logger.Sync()

	fakeResp := &vllm.ChatCompletionResponse{
		ID:      "test-id",
		Object:  "chat.completion",
		Created: time.Now().Unix(),
		Model:   "qwen2.5-7b-instruct",
		Choices: []vllm.ChatChoice{
			{
				Index: 0,
				Message: vllm.ChatMessage{
					Role:    "assistant",
					Content: "안녕, 트윅!",
				},
				FinishReason: "stop",
			},
		},
		Usage: vllm.Usage{
			PromptTokens:     10,
			CompletionTokens: 5,
			TotalTokens:      15,
		},
	}

	fakeClient := &fakeVLLMClient{
		resp: fakeResp,
	}

	svc := NewLLMService(fakeClient, "qwen2.5-7b-instruct")

	req := &pb.ChatCompletionRequest{
		Model:        "qwen2.5-7b-instruct",
		SystemPrompt: "You are a test LLM.",
		UserPrompt:   "인사해줘",
		Context:      "추가 RAG 컨텍스트",
		Temperature:  0.2,
		MaxTokens:    128,
		TopP:         0.9,
	}

	ctx := context.Background()
	resp, err := svc.ChatCompletion(ctx, req)
	if err != nil {
		t.Fatalf("ChatCompletion returned error: %v", err)
	}

	// Assert response mapping
	if resp.OutputText != "안녕, 트윅!" {
		t.Errorf("unexpected OutputText: got %q, want %q", resp.OutputText, "안녕, 트윅!")
	}
	if resp.FinishReason != "stop" {
		t.Errorf("unexpected FinishReason: got %q, want %q", resp.FinishReason, "stop")
	}
	if resp.PromptTokens != 10 || resp.CompletionTokens != 5 || resp.TotalTokens != 15 {
		t.Errorf("unexpected token usage: %+v", resp)
	}

	// Assert that service built userContent with context appended
	if fakeClient.lastReq.Model != "qwen2.5-7b-instruct" {
		t.Errorf("unexpected model in vLLM request: got %q", fakeClient.lastReq.Model)
	}
	if len(fakeClient.lastReq.Messages) != 2 {
		t.Fatalf("expected 2 messages (system + user), got %d", len(fakeClient.lastReq.Messages))
	}
	userMsg := fakeClient.lastReq.Messages[1]
	if userMsg.Role != "user" {
		t.Errorf("unexpected user message role: got %q", userMsg.Role)
	}
	if userMsg.Content == req.UserPrompt {
		t.Errorf("expected context to be appended to user content, but it was unchanged")
	}
}

func TestLLMService_ChatCompletion_NoModel(t *testing.T) {
	if err := logger.Init(); err != nil {
		t.Fatalf("failed to init logger: %v", err)
	}
	defer logger.Sync()

	fakeClient := &fakeVLLMClient{}
	svc := NewLLMService(fakeClient, "qwen2.5-7b-instruct")

	req := &pb.ChatCompletionRequest{
		Model: "",
	}

	_, err := svc.ChatCompletion(context.Background(), req)
	if err == nil {
		t.Fatal("expected error for empty model, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got: %T", err)
	}
	if st.Code() != codes.InvalidArgument {
		t.Fatalf("unexpected status code: got %v, want %v", st.Code(), codes.InvalidArgument)
	}
}

func TestLLMService_ChatCompletion_NilRequest(t *testing.T) {
	if err := logger.Init(); err != nil {
		t.Fatalf("failed to init logger: %v", err)
	}
	defer logger.Sync()

	fakeClient := &fakeVLLMClient{}
	svc := NewLLMService(fakeClient, "qwen2.5-7b-instruct")

	_, err := svc.ChatCompletion(context.Background(), nil)
	if err == nil {
		t.Fatal("expected error for nil request, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got: %T", err)
	}
	if st.Code() != codes.InvalidArgument {
		t.Fatalf("unexpected status code: got %v, want %v", st.Code(), codes.InvalidArgument)
	}
}
