package service

import (
	"context"
	"time"

	pb "github.com/yungtweek/talkie/apps/llm-gateway/gen/llm"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/logger"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/vllm"
	"go.uber.org/zap"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// VLLMClient defines the minimal interface our service needs from the vLLM client.
type VLLMClient interface {
	Chat(ctx context.Context, req vllm.ChatCompletionRequest) (*vllm.ChatCompletionResponse, error)
	ChatStream(ctx context.Context, req vllm.ChatCompletionRequest, onChunk vllm.StreamHandler) error
}

// LLMService implements the gRPC LlmServiceServer interface.
type LLMService struct {
	pb.UnimplementedLlmServiceServer

	client       VLLMClient
	defaultModel string
}

// NewLLMService creates a new LLMService with the given vLLM client.
func NewLLMService(client VLLMClient, defaultModel string) *LLMService {
	return &LLMService{
		client:       client,
		defaultModel: defaultModel,
	}
}

// ChatCompletion handles a single non-streaming chat completion request.
func (s *LLMService) ChatCompletion(ctx context.Context, req *pb.ChatCompletionRequest) (*pb.ChatCompletionResponse, error) {
	start := time.Now()

	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "request is nil")
	}

	if req.Model == "" {
		req.Model = s.defaultModel
		if req.Model == "" {
			return nil, status.Error(codes.InvalidArgument, "model is required and default model not configured")
		}
		if logger.Log != nil {
			logger.Log.Info("ChatCompletion using configured default model", zap.String("model", req.Model))
		}
	}

	if logger.Log != nil {
		logger.Log.Info("ChatCompletion request",
			zap.String("model", req.Model),
			zap.String("system_prompt", req.SystemPrompt),
			zap.String("user_prompt", req.UserPrompt),
			zap.Bool("has_context", req.Context != ""),
		)
	}

	// Build user message including optional RAG context.
	userContent := req.UserPrompt
	if req.Context != "" {
		userContent = req.UserPrompt + "\n\n" + "Context:\n" + req.Context
	}

	vReq := vllm.ChatCompletionRequest{
		Model: req.Model,
		Messages: []vllm.ChatMessage{
			{Role: "system", Content: req.SystemPrompt},
			{Role: "user", Content: userContent},
		},
		Temperature: req.Temperature,
		MaxTokens:   int(req.MaxTokens),
		TopP:        req.TopP,
		Stream:      false,
	}

	vResp, err := s.client.Chat(ctx, vReq)
	if err != nil {
		if logger.Log != nil {
			logger.Log.Error("ChatCompletion vLLM error",
				zap.String("model", req.Model),
				zap.Error(err),
			)
		}
		return nil, status.Errorf(codes.Internal, "vLLM error: %v", err)
	}

	latencyMs := time.Since(start).Milliseconds()

	if len(vResp.Choices) == 0 {
		return nil, status.Error(codes.Internal, "vLLM returned no choices")
	}

	choice := vResp.Choices[0]

	if logger.Log != nil {
		logger.Log.Info("ChatCompletion success",
			zap.String("model", vResp.Model),
			zap.Int64("latency_ms", latencyMs),
			zap.Int("prompt_tokens", vResp.Usage.PromptTokens),
			zap.Int("completion_tokens", vResp.Usage.CompletionTokens),
			zap.Int("total_tokens", vResp.Usage.TotalTokens),
		)
	}

	resp := &pb.ChatCompletionResponse{
		OutputText:       choice.Message.Content,
		FinishReason:     choice.FinishReason,
		PromptTokens:     int32(vResp.Usage.PromptTokens),
		CompletionTokens: int32(vResp.Usage.CompletionTokens),
		TotalTokens:      int32(vResp.Usage.TotalTokens),
		LatencyMs:        latencyMs,
	}

	return resp, nil
}

func (s *LLMService) ChatCompletionStream(req *pb.ChatCompletionRequest, stream pb.LlmService_ChatCompletionStreamServer) error {
	start := time.Now()

	if req == nil {
		return status.Error(codes.InvalidArgument, "request is nil")
	}

	// Fallback to configured default model when none is provided
	if req.Model == "" {
		req.Model = s.defaultModel
		if req.Model == "" {
			return status.Error(codes.InvalidArgument, "model is required and default model not configured")
		}
		if logger.Log != nil {
			logger.Log.Info("ChatCompletionStream using configured default model", zap.String("model", req.Model))
		}
	}

	if logger.Log != nil {
		logger.Log.Info("ChatCompletionStream request",
			zap.String("model", req.Model),
			zap.String("system_prompt", req.SystemPrompt),
			zap.String("user_prompt", req.UserPrompt),
			zap.Bool("has_context", req.Context != ""),
		)
	}

	// Build user message including optional RAG context.
	userContent := req.UserPrompt
	if req.Context != "" {
		userContent = req.UserPrompt + "\n\n" + "Context:\n" + req.Context
	}

	vReq := vllm.ChatCompletionRequest{
		Model: req.Model,
		Messages: []vllm.ChatMessage{
			{Role: "system", Content: req.SystemPrompt},
			{Role: "user", Content: userContent},
		},
		Temperature: req.Temperature,
		MaxTokens:   int(req.MaxTokens),
		TopP:        req.TopP,
		Stream:      true,
	}

	// Stream chunks from vLLM to the gRPC client.
	err := s.client.ChatStream(stream.Context(), vReq, func(chunk vllm.ChatCompletionStreamChunk) error {
		if logger.Log != nil {
			logger.Log.Debug("ChatCompletionStream chunk",
				zap.String("model", req.Model),
				zap.String("delta_text", chunk.DeltaText),
				zap.String("finish_reason", chunk.FinishReason),
			)
		}

		resp := &pb.ChatCompletionChunkResponse{
			DeltaText:        chunk.DeltaText,
			FinishReason:     chunk.FinishReason,
			PromptTokens:     int32(chunk.PromptTokens),
			CompletionTokens: int32(chunk.CompletionTokens),
			TotalTokens:      int32(chunk.TotalTokens),
		}

		if err := stream.Send(resp); err != nil {
			if logger.Log != nil {
				logger.Log.Warn("ChatCompletionStream send failed", zap.Error(err))
			}
			return err
		}

		return nil
	})

	if err != nil {
		if logger.Log != nil {
			logger.Log.Error("ChatCompletionStream vLLM error",
				zap.String("model", req.Model),
				zap.Error(err),
			)
		}
		return status.Errorf(codes.Internal, "vLLM stream error: %v", err)
	}

	latencyMs := time.Since(start).Milliseconds()
	if logger.Log != nil {
		logger.Log.Info("ChatCompletionStream finished",
			zap.String("model", req.Model),
			zap.Int64("latency_ms", latencyMs),
		)
	}

	return nil
}
