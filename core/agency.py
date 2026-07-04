import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from loguru import logger

class Message:
    """Represents a structured message passed between agents in the swarm."""
    def __init__(self, sender: str, recipient: str, action: str, content: dict = None):
        self.sender = sender
        self.recipient = recipient
        self.action = action
        self.content = content or {}
        self.timestamp = datetime.now().isoformat()

    def __repr__(self) -> str:
        return f"[Msg: {self.sender} -> {self.recipient} | Action: {self.action}]"

class Agent:
    """Base class for all specialized agents in the JARVIS swarm."""
    def __init__(self, name: str, agency=None):
        self.name = name
        self.agency = agency

    def send_message(self, recipient: str, action: str, content: dict = None):
        """Sends an asynchronous message to another agent via the central agency broker."""
        if self.agency:
            self.agency.send_message(self.name, recipient, action, content)
        else:
            logger.error(f"Agent '{self.name}' cannot send message: Not registered to an agency.")

    def receive_message(self, msg: Message):
        """Invoked when a message is delivered to this agent. Must be overridden by subclasses."""
        pass

class Agency:
    """Central message broker managing agent registration and concurrent task execution."""
    def __init__(self, max_workers: int = 16):
        self.agents = {}
        # Thread pool to allow sub-agents to process tasks concurrently (multi-working)
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="JarvisSwarm")

    def register_agent(self, name: str, agent: Agent):
        """Registers a specialized agent to the agency."""
        agent.agency = self
        self.agents[name] = agent
        logger.info(f"Agency: Registered agent '{name}' successfully.")

    def send_message(self, sender: str, recipient: str, action: str, content: dict = None):
        """Creates and dispatches a message to the thread pool for parallel execution."""
        msg = Message(sender, recipient, action, content)
        self.executor.submit(self._dispatch, msg)

    def _dispatch(self, msg: Message):
        """Delivers a message to the target agent within a worker thread."""
        target_agent = self.agents.get(msg.recipient)
        if not target_agent:
            logger.error(f"Agency: Message delivery failed. Recipient agent '{msg.recipient}' not found.")
            return

        try:
            logger.debug(f"Agency: Dispatching {msg} to '{msg.recipient}' thread...")
            target_agent.receive_message(msg)
        except Exception as e:
            logger.error(f"Agency: Error during message delivery to '{msg.recipient}': {e}")
