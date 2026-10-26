from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from .decoder import decode
from .ir import TranslationResult
from .player import play_wav
from .prosody import EMOTIONS, VOICES
from .reverse import reverse
from .synth import TARGETS, render_duck, render_result
from .translator import UnknownWordError, translate

app = typer.Typer(add_completion=False, help="中文 ⇄ 嘎语翻译、鸭叫合成与解码")


def _print_result(result: TranslationResult, path: Path, played: bool, show_gloss: bool) -> None:
    typer.echo(f"中文：{result.source}")
    typer.echo(f"鸭语：{result.duck}")
    if show_gloss:
        typer.echo(f"直译：{result.gloss}")
    for warning in result.warnings:
        typer.echo(f"提示：{warning}", err=True)
    typer.echo(f"音频：{path}（{'已播放' if played else '已保存，未播放'}）")


def _run(text: str, *, save: Path | None, no_play: bool, show_gloss: bool, voice: str,
         emotion: str | None, strict: bool, json_out: bool, target: str, tail: bool) -> None:
    try:
        result = translate(text, strict=strict)
    except (UnknownWordError, ValueError) as exc:
        typer.echo(f"错误：{exc}", err=True)
        raise typer.Exit(1) from exc

    path = render_result(result, voice=voice, emotion=emotion, out_path=save, target=target,
                         tail=tail)
    played = False if no_play else play_wav(path)

    if json_out:
        payload = result.to_dict()
        payload["audio"] = str(path)
        payload["played"] = played
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_result(result, path, played, show_gloss)
        if not no_play and not played:
            typer.echo("提示：没有可用的音频设备，WAV 已保存。", err=True)


def _run_reverse(text: str, *, save: Path | None, no_play: bool, show_gloss: bool, voice: str,
                 emotion: str | None, json_out: bool, target: str, tail: bool) -> None:
    try:
        result = reverse(text)
    except ValueError as exc:
        typer.echo(f"错误：{exc}", err=True)
        raise typer.Exit(1) from exc

    path, played = None, False
    try:
        path = render_duck(text, voice=voice, emotion=emotion or "neutral", out_path=save,
                           target=target, tail=tail)
        played = False if no_play else play_wav(path)
    except ValueError:
        pass  # 有非法音节时只翻译不发声

    if json_out:
        payload = result.to_dict()
        payload["audio"] = str(path) if path else None
        payload["played"] = played
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"鸭语：{result.source}")
    typer.echo(f"中文：{result.zh}")
    if show_gloss:
        typer.echo(f"直译：{result.gloss}")
    for warning in result.warnings:
        typer.echo(f"提示：{warning}", err=True)
    if path:
        typer.echo(f"音频：{path}（{'已播放' if played else '已保存，未播放'}）")


def _run_listen(path: Path, *, json_out: bool) -> None:
    try:
        result = decode(path)
    except (OSError, ValueError, EOFError) as exc:
        typer.echo(f"错误：无法读取 {path}：{exc}", err=True)
        raise typer.Exit(1) from exc
    if json_out:
        typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    typer.echo(f"音频：{path}")
    typer.echo(f"鸭语：{result.duck or '（没有检测到鸭叫）'}")
    if result.duck:
        typer.echo(f"中文：{result.zh}")
        typer.echo(f"置信度：{result.confidence:.0%}（{len(result.syllables)} 个音节）")
    for warning in result.warnings:
        typer.echo(f"提示：{warning}", err=True)


def _repl(*, reverse_mode: bool, **kwargs) -> None:
    prompt = "鸭语> " if reverse_mode else "中文> "
    typer.echo(f"嘎语 REPL：输入{'鸭语' if reverse_mode else '中文'}，回车翻译；输入 q 退出。")
    while True:
        try:
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo()
            break
        if line.lower() in {"q", "quit", "exit"}:
            break
        if not line:
            continue
        try:
            if reverse_mode:
                kwargs.pop("strict", None)
                _run_reverse(line, save=None, **kwargs)
            else:
                _run(line, save=None, **kwargs)
        except typer.Exit:
            continue


@app.command()
def main(
    text: str | None = typer.Argument(None, help="要翻译的文本；省略则进入 REPL"),
    reverse_mode: bool = typer.Option(False, "--reverse", "-r", help="鸭语 -> 中文"),
    listen: Path | None = typer.Option(None, "--listen", "-l", help="解码 WAV：声音 -> 鸭语 -> 中文"),
    save: Path | None = typer.Option(None, "--save", "-s", help="WAV 保存路径"),
    no_play: bool = typer.Option(False, "--no-play", help="只生成 WAV，不播放"),
    gloss: bool = typer.Option(True, "--gloss/--no-gloss", help="显示逐词直译"),
    voice: str = typer.Option("adult", "--voice", "-v", help=f"音色：{', '.join(VOICES)}"),
    emotion: str | None = typer.Option(None, "--emotion", "-e",
                                       help=f"覆盖情绪：{', '.join(EMOTIONS)}"),
    target: str = typer.Option("pc", "--target", "-t", help=f"播放设备：{', '.join(TARGETS)}"),
    tail: bool = typer.Option(True, "--tail/--no-tail", help="每句末尾加「嘎嘎嘎」（只在声音里）"),
    strict: bool = typer.Option(False, "--strict", help="遇到未收录词直接报错"),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON"),
    voices: bool = typer.Option(False, "--voices", help="列出可用音色"),
) -> None:
    if voices:
        for name, preset in VOICES.items():
            typer.echo(f"{name:10s} f0={preset.f0:.0f}Hz speed={preset.speed} rough={preset.rough}")
        raise typer.Exit(0)
    if listen is not None:
        _run_listen(listen, json_out=json_out)
        return

    if voice not in VOICES:
        typer.echo(f"错误：未知音色 {voice!r}，可选：{', '.join(VOICES)}", err=True)
        raise typer.Exit(1)
    if emotion is not None and emotion not in EMOTIONS:
        typer.echo(f"错误：未知情绪 {emotion!r}，可选：{', '.join(EMOTIONS)}", err=True)
        raise typer.Exit(1)
    if target not in TARGETS:
        typer.echo(f"错误：未知播放设备 {target!r}，可选：{', '.join(TARGETS)}", err=True)
        raise typer.Exit(1)

    common = {"no_play": no_play, "show_gloss": gloss, "voice": voice, "emotion": emotion,
              "json_out": json_out, "target": target, "tail": tail}
    if text is None:
        if not sys.stdin.isatty():
            lines = [line.strip() for line in sys.stdin.read().splitlines()]
            text = "。".join(line for line in lines if line and line.lower() not in {"q", "quit"})
        else:
            _repl(reverse_mode=reverse_mode, strict=strict, **common)
            return
    if not text:
        typer.echo("错误：请输入要翻译的文本。", err=True)
        raise typer.Exit(1)

    if reverse_mode:
        _run_reverse(text, save=save, **common)
    else:
        _run(text, save=save, strict=strict, **common)
