"""The oldest ten turns of a conversation, folded into a sentence or two.

`generate_response` appends a user message and a reply to `chat_history` on every
turn, and at twenty messages it asks this module to compress. The oldest ten are
summarized by the LLM, that summary is merged into whatever summary already
existed, and those ten messages are dropped. The summary is read back into the
system prompt on later turns, so the model keeps a thread it can no longer see.

Unlike the nine delegations before it, this one is not a move the AST
equivalence checker could gate, for two independent reasons:

* The original wrote `self.chat_history` and `self.chat_history_summary`, and
  `tools/ast_equivalence.py` refuses `--param` for an attribute that is
  assigned -- correctly, since a rewritten read cannot stand in for a write. So
  the function returns the new pair and `main.py` assigns it.
* The original reached `ollama` through `main.py`'s module-level import. Here it
  is a function-local import, the same way `llm_client` does it and for the same
  reason: the environment CI runs does not install ollama, and a module-level
  import would make this file unimportable there.

Both are body changes, so equivalence was established the other way -- by
running the version lifted out of the previous commit and this one over the same
grid of inputs and comparing everything observable: the prompts sent to the LLM,
the returned history, and the returned summary. See the note in the commit.

Two behaviours worth knowing before calling this:

`except Exception` catches everything and returns the inputs unchanged, so a
caller cannot tell a successful compression from a failed one, and a persistent
LLM failure means `chat_history` grows without bound -- twenty-one messages next
turn, twenty-two the turn after. That is the behaviour as it shipped.

The summary is replaced, not appended to. An LLM that returns an empty or
whitespace-only combine loses every earlier turn's context: the summary becomes
`""`, and the next compression sees no prior summary and starts over.
"""
from loguru import logger


def compress_chat_history(chat_history, chat_history_summary, *, models):
    """Returns the pair `(remaining_history, new_summary)` to assign back.

    The oldest ten messages are summarized and dropped; everything from the
    eleventh on is kept. Called at twenty messages, that leaves ten -- but the
    ten is a constant here, not a proportion, so a longer history keeps more.

    On any failure the inputs come back untouched, so assigning the result is
    always safe and never a partial write.
    """
    import ollama

    try:
        to_summarize = chat_history[:10]
        history_str = "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in to_summarize)

        prompt = (
            f"Summarize the following recent dialogue history briefly in 2-3 sentences. "
            f"Keep key details, facts, or decisions mentioned:\n\n{history_str}"
        )

        response = ollama.chat(
            model=models["main_brain"],
            messages=[{"role": "user", "content": prompt}]
        )
        summary = response["message"]["content"].strip()

        if chat_history_summary:
            combined_prompt = (
                f"Combine these two summaries of dialogue history into one cohesive, brief summary "
                f"(maximum 4 sentences):\nSummary 1: {chat_history_summary}\nSummary 2: {summary}"
            )
            comb_res = ollama.chat(
                model=models["main_brain"],
                messages=[{"role": "user", "content": combined_prompt}]
            )
            new_summary = comb_res["message"]["content"].strip()
        else:
            new_summary = summary

        remaining = chat_history[10:]
        logger.info(f"Dialogue history compressed. New summary: {new_summary}")
        return remaining, new_summary
    except Exception as e:
        logger.error(f"Error compressing dialogue history: {e}")
        return chat_history, chat_history_summary
