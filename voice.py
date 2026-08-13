#!/usr/bin/env python3
"""Voice loop — speak to JARVIS, it speaks back.

    python voice.py                  # press Enter to talk
    python voice.py --hands-free     # listens continuously
    python voice.py --router tuned   # fine-tuned router (faster)

Speech is a layer over the orchestrator, not a rewrite of it: the same route and
dispatch that serve the text CLI serve this. Whisper runs on the GPU via MLX and
output goes through macOS `say`, so a voice turn is local and free.
"""
import argparse
import logging
import re
import sys
import time

from rich.console import Console
from rich.markup import escape

from core.briefing import BriefingComposer
from core.orchestrator import Response
from integrations import speech
from main import build

console = Console()

#: Above this the reply is trimmed for speech. Spoken, a long answer can't be
#: skimmed — you have to sit through it — so brevity matters more out loud than
#: it does on screen.
SPEAK_LIMIT = 420


def for_speech(text: str) -> str:
    """Flatten an agent reply into something that reads well aloud.

    Section headings and bullets are visual scaffolding; spoken they land as
    "Weather dash" and "asterisk". Long replies are cut at a sentence boundary
    rather than mid-word.
    """
    # Drop standalone headings ("Sport:", "Headlines:") — they're navigation for
    # the eye and land as a stray word followed by a pause when read out.
    spoken = re.sub(r"^\s*\w[\w ]{0,18}:\s*$", "", text, flags=re.M)
    spoken = re.sub(r"^\s*[-•*]\s*", "", spoken, flags=re.M)
    spoken = re.sub(r"^(\w+) — ", r"\1: ", spoken, flags=re.M)
    spoken = re.sub(r"\n{2,}", ". ", spoken)
    spoken = re.sub(r"\n", ", ", spoken)
    spoken = re.sub(r"\s{2,}", " ", spoken).strip()
    # Joining lines that already ended in punctuation doubles it up, and `say`
    # reads ".." and ",," as an audible stumble.
    spoken = re.sub(r"([.,!?])[\s]*[.,]+", r"\1", spoken)
    spoken = re.sub(r"\s+([.,!?])", r"\1", spoken)

    if len(spoken) <= SPEAK_LIMIT:
        return spoken
    cut = spoken[:SPEAK_LIMIT]
    stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[: stop + 1] if stop > SPEAK_LIMIT // 2 else cut) + " There's more on screen."


#: A request routed to every agent at once *is* the morning briefing.
BRIEFING_AGENTS = {"calendar", "weather", "news"}


def turn(orchestrator, heard: speech.Heard, speak: bool, composer=None) -> Response:
    console.print(f"[bold yellow]you[/] {escape(heard.text)}  [dim]({heard.transcribe_ms:.0f}ms)[/]")

    # "What does my day look like" routes to all three agents, and answering it
    # with three LLM calls took ~19s — unbearable spoken. The briefing composes
    # the same content from cache in about 5ms, so the broadest request is also
    # the fastest one. Narrower questions still go to the agents, which is where
    # the model actually earns its latency.
    route = orchestrator.router.route(heard.text)
    if composer and set(route.agents) == BRIEFING_AGENTS:
        briefing = composer.compose()
        response = Response(text=briefing.as_text(), route=route, elapsed=briefing.elapsed)
        spoken_override = briefing.as_speech()
    else:
        response = orchestrator.handle(heard.text, route=route)
        spoken_override = None

    console.print(f"[bold cyan]jarvis[/] {escape(response.text)}")

    spoken = spoken_override or for_speech(response.text)
    console.print(
        f"[dim]route {response.route} · think {response.elapsed:.1f}s · "
        f"{len(spoken)} chars spoken[/]\n"
    )
    if speak:
        speech.speak(spoken)
    return response


def main() -> int:
    ap = argparse.ArgumentParser(description="J.A.R.V.I.S voice")
    ap.add_argument("--hands-free", action="store_true", help="listen continuously")
    ap.add_argument("--router", choices=("llm", "tuned"), help="routing backend")
    ap.add_argument("--no-speak", action="store_true", help="transcribe and answer, but stay quiet")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    ok, why = speech.available()
    if not ok:
        console.print(f"[red]Voice unavailable:[/] {why}")
        return 1

    console.print("[dim]Loading…[/]")
    orchestrator = build(router=args.router)

    # Load both models before the first question rather than during it. MLX
    # (Whisper, tuned router) and Ollama compete for memory, so an unwarmed
    # agent costs ~16s and an unwarmed Whisper ~4s — together that made the
    # first turn 9s against 2.5s for every turn after. Paid here, while the
    # banner is still printing, nobody is waiting on it.
    console.print("[dim]Warming models…[/]")
    llm = getattr(orchestrator.agents.get("weather"), "_llm", None)
    if hasattr(llm, "warm"):
        llm.warm()
    speech.warm()
    # The router's first inference also pays a load. Routing a throwaway phrase
    # is the one warm-up that works for both implementations, since the protocol
    # deliberately exposes nothing else.
    orchestrator.router.route("warm up")

    composer = BriefingComposer(orchestrator.agents)

    console.print("[dim]Measuring room noise…[/]")
    threshold = speech.calibrate()
    console.print(f"[dim]Silence threshold {threshold:.4f}[/]\n")

    mode = "listening continuously" if args.hands_free else "press Enter to talk"
    console.print(f"[bold cyan]J.A.R.V.I.S[/] ready — {mode}. Ctrl-C to exit.\n")

    while True:
        try:
            if not args.hands_free:
                console.input("[dim]Enter to talk…[/]")
            console.print("[dim]listening…[/]")

            started = time.perf_counter()
            heard = speech.listen(threshold)
            if not heard:
                console.print("[dim](nothing heard)[/]\n")
                continue

            turn(orchestrator, heard, speak=not args.no_speak, composer=composer)
            console.print(f"[dim]full turn {time.perf_counter() - started:.1f}s[/]\n")
        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye, sir.[/]")
            return 0
        except Exception as e:
            console.print(f"[red]turn failed:[/] {e}\n")


if __name__ == "__main__":
    sys.exit(main())
