# Task Builder Prompt

Use this prompt to generate a complete importable task JSON from screenshots.

---

## Prompt

I am building a game automation task. I will give you context about the game and then send screenshots showing each screen in the flow. At the end, output a single complete JSON I can import directly — no explanation, just the JSON.

**Game:** [Game name]
**Package:** [com.example.game]

**UI layout notes:**
- [e.g. "top bar shows stamina, gold, premium currency left to right"]
- [e.g. "red ! badge on any button means unclaimed content"]
- [e.g. "X button top-right closes any panel"]

**Task I want to automate:** [describe the goal in plain English, e.g. "collect daily login reward, then claim auto-gather resources"]

I will now send screenshots of each screen in order. For each one I will tell you what it is and what I want to do on it. After I send all screenshots and say "build it", output this JSON and nothing else:

```json
{
  "name": "task name",
  "game_package": "com.example.game",
  "steps": [
    {
      "name": "short step name",
      "vision_prompt": "Instructions for a vision AI that only sees a screenshot. Describe exact visual identifiers (button text, position, color, badges). Tell it what screen='...' to return and what state.* fields to extract.",
      "conditions": [{"field": "screen", "op": "eq", "value": "screen_name"}],
      "on_match": "next",
      "on_fail": "retry",
      "max_retries": 5,
      "timeout_seconds": 60
    }
  ]
}
```

**Step writing rules:**
- `vision_prompt` is read by a separate vision LLM at runtime with no other context — be explicit about what to look for and what values to return
- `on_match` / `on_fail` options: `"next"`, `"retry"`, `"skip"`, `"complete"`, `"abort"`, or `{"action": "execute", "goal": "tap the X button top-right to close"}` for interactions
- Use `on_fail: "next"` when a feature might not be available that day (skip it, don't fail the whole task)
- Use `on_fail: "retry"` when waiting for a screen to load
- Always end with a step that returns to the main menu using `on_match: "complete"`
- conditions check `screen` for screen type, `state.key` for extracted values; operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `exists`
