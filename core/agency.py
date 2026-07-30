import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime

from loguru import logger


class AgentNotFound(LookupError):
    """Raised when a message targets an agent name that was never registered."""


class Message:
    """Represents a structured message passed between agents in the swarm."""
    def __init__(self, sender: str, recipient: str, action: str, content: dict = None):
        self.sender = sender
        self.recipient = recipient
        self.action = action
        self.content = content or {}
        self.timestamp = datetime.now().isoformat()

    def get(self, key: str, default=None):
        """Convenience accessor so agents can read payload keys without digging into .content."""
        return self.content.get(key, default)

    @property
    def params(self) -> dict:
        """The intent router's parameter dict, which is what most skill agents act on."""
        return self.content.get("params", {}) or {}

    def __repr__(self) -> str:
        return f"[Msg: {self.sender} -> {self.recipient} | Action: {self.action}]"


class Agent:
    """Base class for all specialized agents in the JARVIS swarm."""
    def __init__(self, name: str, agency=None):
        self.name = name
        self.agency = agency

    def send_message(self, recipient: str, action: str, content: dict = None):
        """Fire-and-forget message to another agent, executed on the agency thread pool."""
        if self.agency:
            self.agency.send_message(self.name, recipient, action, content)
        else:
            logger.error(f"Agent '{self.name}' cannot send message: Not registered to an agency.")

    def request(self, recipient: str, action: str, content: dict = None):
        """Synchronously ask another agent to do work and return its result."""
        if not self.agency:
            logger.error(f"Agent '{self.name}' cannot request: Not registered to an agency.")
            return None
        return self.agency.request(recipient, action, content, sender=self.name)

    def receive_message(self, msg: Message):
        """Invoked when a message is delivered to this agent.

        Subclasses return a string when they produce something JARVIS should say.
        Returning None means the agent handled the message silently.
        """
        raise NotImplementedError(
            f"Agent '{self.name}' received action '{msg.action}' but implements no handler."
        )


class Agency:
    """Central broker managing agent registration, sync requests, and concurrent tasks."""
    def __init__(self, max_workers: int = 16):
        self.agents = {}
        # Thread pool backs the fire-and-forget path only. Synchronous requests run
        # inline (see .request) so Qt widget access stays on the calling thread.
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="JarvisSwarm")

    def register_agent(self, name: str, agent: Agent):
        """Registers a specialized agent to the agency."""
        agent.agency = self
        self.agents[name] = agent
        logger.debug(f"Agency: Registered agent '{name}'.")

    def has_agent(self, name: str) -> bool:
        return name in self.agents

    def send_message(self, sender: str, recipient: str, action: str, content: dict = None) -> Future:
        """Dispatch a message to the thread pool for background execution.

        Use this for work nobody is waiting on. Exceptions are logged, not raised,
        so a failing background agent can never take down its caller.
        """
        msg = Message(sender, recipient, action, content)
        return self.executor.submit(self._dispatch_safe, msg)

    def request(self, recipient: str, action: str, content: dict = None, sender: str = "orchestrator"):
        """Synchronously run an agent's handler and return its result.

        Deliberately executed inline in the calling thread rather than on the pool.
        Skill handlers touch PyQt widgets (orb state, overlays) and Qt requires that
        from the thread that owns them; hopping to a worker would risk hard crashes.
        Running inline also means a handler that itself calls request() cannot
        deadlock by exhausting the pool.

        Exceptions propagate so main.py's existing retry and self-healing loop sees
        the original traceback exactly as it did before agents were introduced.
        """
        msg = Message(sender, recipient, action, content)
        agent = self.agents.get(recipient)
        if not agent:
            raise AgentNotFound(f"No agent registered under '{recipient}'.")

        started = time.perf_counter()
        result = agent.receive_message(msg)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.debug(f"Agency: {msg} completed in {elapsed_ms:.0f}ms")
        return result

    def _dispatch_safe(self, msg: Message):
        """Deliver a background message, absorbing any failure into the log."""
        agent = self.agents.get(msg.recipient)
        if not agent:
            logger.error(f"Agency: Delivery failed. Recipient agent '{msg.recipient}' not found.")
            return None

        try:
            return agent.receive_message(msg)
        except Exception as e:
            logger.error(f"Agency: Error during message delivery to '{msg.recipient}': {e}")
            return None

    def shutdown(self, wait: bool = False):
        """Stop the background pool. Called on application exit."""
        self.executor.shutdown(wait=wait)
