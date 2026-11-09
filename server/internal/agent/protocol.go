package agent

// Protocol defines the communication protocol for an agent.
type Protocol string

const (
	// ProtocolACP is the Agent Client Protocol (JSON-RPC 2.0 over ndJSON).
	// Claude/Gemini default to ACP wrappers.
	ProtocolACP Protocol = "acp"
	// ProtocolClaudeSDK uses claude-agent-sdk-go stream-json transport.
	ProtocolClaudeSDK Protocol = "claude-sdk"
	// ProtocolRCC uses Claude stream-json over the authenticated RCC client.
	ProtocolRCC Protocol = "rcc"
	// ProtocolCodexSDK uses codex-go-sdk app-server transport.
	ProtocolCodexSDK Protocol = "codex-sdk"
)

// DefaultProtocol returns the default protocol for agents.
func DefaultProtocol(agentName string) Protocol {
	if agentName == "rcc" {
		return ProtocolRCC
	}
	if agentName == "claude" {
		return ProtocolClaudeSDK
	}
	if agentName == "codex" {
		return ProtocolCodexSDK
	}
	return ProtocolACP
}
