# Vision and aim

## The problem

Many heat pumps run on factory or installer defaults that are rarely revisited. Common
results: heating curves set too steep "to be safe", compressors that start dozens of times
a day on mild days, efficiency below what the hardware can do. Owners who run Home Assistant often have the
data to see this – power, temperatures, sometimes a heat meter – but turning sensor history
into a diagnosis requires expertise most people do not have.

AI assistants can now talk to Home Assistant (via its built-in MCP server and LLM API). But
they only get **raw data**: hundreds of state changes per sensor per day. Asking a language
model to count compressor cycles or fit a heating curve from a JSON dump is slow, expensive,
and unreliable – the answer changes every time you ask.

## The aim

> **Make every heat pump owner with Home Assistant able to ask an AI assistant
> "why does my heat pump behave like this, and what should I change?" –
> and get an answer that is grounded in their own data and correct.**

We do this by turning heat pump expertise into **tested, deterministic analysis tools** that
any assistant can call. The assistant does what it is good at – dialogue, explanation, adapting
to the user – and leaves the calculations to code.

## Who it is for

| User | Has | Wants |
|---|---|---|
| **Owner, basic setup** | A power meter on the heat pump (Shelly, smart plug, vendor value) and an outdoor temperature | "Is my heat pump cycling too much? Is it OK?" |
| **Owner, vendor integration** | Viessmann, Vaillant, Daikin, NIBE, Panasonic, … integration with many sensors | "Is my heating curve right? What does the spread tell me?" |
| **Enthusiast / tinkerer** | Heat meter, flow/return, room sensors | Real COP, weather-normalised before/after comparisons of every tweak |
| **Installer / energy advisor** | Customer's Home Assistant (with permission) | Quick, structured health check after commissioning |

The **basic setup is the design target**: if it works with only a power sensor, it works
for almost everyone.

## Product principles

1. **Vendor-independent.** Analyses use *roles* (power, flow temperature, …), never brand
   entities. Brand knowledge lives in small, community-maintained device profiles.
2. **Computed, not guessed.** Every figure the assistant quotes comes from code with tests.
3. **Honest about uncertainty.** Each result carries data coverage, assumptions and missing
   sensors. "Not enough data" is a valid, useful answer.
4. **Read-only first.** The tools never change settings. Recommendations are made by the
   assistant, applied by the human, and verified afterwards with the same tools.
5. **Local and private.** Runs in Home Assistant. The user chooses which sensors are analysed
   and which assistant (cloud or local) sees the results.
6. **Explainable.** Every threshold has a documented reason in the knowledge base and can be
   changed. We say "heuristic" when something is a heuristic.
7. **Global.** °C/°F, both hemispheres, air/ground/water source, heating and cooling,
   hybrid systems. English first, translated UI.

## What we deliberately do **not** build

- **No new AI integration.** Home Assistant already connects to Claude, OpenAI, Ollama and
  MCP clients. We provide tools, not another chat connector.
- **No controller (for now).** No automatic optimisation loop. Writing settings may come later,
  strictly opt-in with an explicit allow-list – after the analyses are proven.
- **No dashboard product.** Other projects visualise; we diagnose. (Figures in tool output
  may come later as optional extras.)
- **No vendor cloud scraping.** We use whatever Home Assistant already has.

## What success looks like

| Horizon | Success |
|---|---|
| **v0.x (now)** | Cycling analysis validated on ≥ 10 real installations of ≥ 5 brands; an assistant answers the core use cases correctly in blind tests |
| **v1.0** | Cycling, heating curve, energy signature, spread, efficiency; available in HACS default; device profiles for the 10 most common integrations |
| **Long term** | The reference "heat pump expert" for Home Assistant; possibly extended to PV, batteries and whole-home energy; candidate for Home Assistant core |

The long-term name is open: "Home Energy Expert" fits once PV and household consumption
join. We start with the heat pump because that is where the expertise gap is largest.
