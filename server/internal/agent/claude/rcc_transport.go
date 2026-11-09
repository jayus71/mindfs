package claude

import (
	"context"
	"errors"
	"fmt"
	"io"
	"iter"
	"os"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	claudeagent "github.com/roasbeef/claude-agent-sdk-go"
)

// Keep SDK argument construction, framing and control handling upstream. Only
// the executable boundary and shutdown semantics belong to the RCC adapter.
type rccRunner struct {
	*claudeagent.LocalSubprocessRunner
	args       []string
	waitOnce   sync.Once
	waitErr    error
	waitDone   chan struct{}
	stderrDone chan struct{}
	stderr     *rccStderrTail
}

func (r *rccRunner) Start(ctx context.Context, args, env []string, cwd string) (io.WriteCloser, io.ReadCloser, io.ReadCloser, error) {
	argv := append(append([]string(nil), r.args...), "--", "-p")
	argv = append(argv, args...)
	stdin, stdout, stderr, err := r.LocalSubprocessRunner.Start(ctx, argv, env, cwd)
	if err != nil {
		close(r.stderrDone)
		return nil, nil, nil, err
	}
	go func() {
		_, _ = io.Copy(r.stderr, stderr)
		_ = stderr.Close()
		close(r.stderrDone)
	}()
	return stdin, stdout, io.NopCloser(strings.NewReader("")), nil
}

func (r *rccRunner) Wait() error {
	r.waitOnce.Do(func() {
		<-r.stderrDone
		r.waitErr = r.LocalSubprocessRunner.Wait()
		close(r.waitDone)
	})
	return r.waitErr
}

func (r *rccRunner) Kill() error {
	// The SDK has already waited five seconds. Allow another ten for RCC's
	// own ten-second remote stop request, including network/dispatch delay.
	select {
	case <-r.waitDone:
		return nil
	case <-time.After(10 * time.Second):
		return r.LocalSubprocessRunner.Kill()
	}
}

func (r *rccRunner) terminate() error {
	select {
	case <-r.waitDone:
		return nil
	default:
	}
	if r.ProcessID() == 0 {
		return nil
	}
	process, err := os.FindProcess(r.ProcessID())
	if err != nil {
		return err
	}
	err = process.Signal(syscall.SIGTERM)
	if errors.Is(err, os.ErrProcessDone) {
		return nil
	}
	return err
}

type rccTransport struct {
	*claudeagent.SubprocessTransport
	runner    *rccRunner
	mu        sync.Mutex
	err       error
	closeOnce sync.Once
	closeErr  error
	stderr    rccStderrTail
	closed    atomic.Bool
}

type rccStderrTail struct {
	mu   sync.Mutex
	data []byte
}

func (b *rccStderrTail) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	const limit = 4096
	n := len(p)
	if len(p) >= limit {
		b.data = append(b.data[:0], p[len(p)-limit:]...)
	} else {
		b.data = append(b.data, p...)
		if len(b.data) > limit {
			b.data = append(b.data[:0], b.data[len(b.data)-limit:]...)
		}
	}
	return n, nil
}

func (b *rccStderrTail) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return strings.TrimSpace(string(b.data))
}

func newRCCTransport(command string, args []string, options *claudeagent.Options) (*rccTransport, error) {
	if runtime.GOOS != "linux" {
		return nil, errors.New("RCC agent requires a Linux work node")
	}
	for _, arg := range args {
		if arg == "--" {
			return nil, errors.New("RCC agent args contain only RCC options; the adapter adds -- and Claude arguments")
		}
	}
	if strings.TrimSpace(command) == "" {
		command = "rcc"
	}
	runner := &rccRunner{LocalSubprocessRunner: claudeagent.NewLocalSubprocessRunner(command), args: append([]string(nil), args...), waitDone: make(chan struct{}), stderrDone: make(chan struct{})}
	transport := &rccTransport{SubprocessTransport: claudeagent.NewSubprocessTransportWithRunner(runner, options), runner: runner}
	runner.stderr = &transport.stderr
	return transport, nil
}

func (t *rccTransport) ReadMessages(ctx context.Context) iter.Seq2[claudeagent.Message, error] {
	return func(yield func(claudeagent.Message, error) bool) {
		for msg, err := range t.SubprocessTransport.ReadMessages(ctx) {
			if !yield(msg, err) {
				return
			}
		}
		if ctx.Err() != nil {
			return
		}
		// Wait only after stdout drains: exec.Cmd.Wait closes its pipes. The
		// SDK currently discards iterator errors, so retain the exit error for
		// OpenSession and pending turns as well as yielding it to the SDK.
		if err := t.runner.Wait(); err != nil {
			t.mu.Lock()
			t.err = fmt.Errorf("RCC client exited: %w", err)
			t.mu.Unlock()
			yield(nil, t.Err())
		}
	}
}

func (t *rccTransport) Err() error {
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.err != nil {
		if diagnostic := t.stderr.String(); diagnostic != "" {
			return fmt.Errorf("%w: %s", t.err, diagnostic)
		}
	}
	return t.err
}

func (t *rccTransport) Close() error {
	t.closeOnce.Do(func() {
		t.closed.Store(true)
		// RCC interprets SIGTERM as remote session cancellation. Sending EOF
		// alone can leave the remote session alive. The SDK and runner allow
		// fifteen seconds before the last-resort process-group kill.
		_ = t.runner.terminate()
		t.closeErr = t.SubprocessTransport.Close()
	})
	return t.closeErr
}

func (t *rccTransport) IsReady() bool {
	if t.closed.Load() {
		return false
	}
	select {
	case <-t.runner.waitDone:
		return false
	default:
		return t.SubprocessTransport.IsReady()
	}
}
