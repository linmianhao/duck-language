from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from .ir import TranslationResult
from .player import play_wav
from .prosody import EMOTIONS, VOICES
from .synth import render_result
from .translator import UnknownWordError, translate

app = typer.Typer(add_completion=False, help="中文 -> 嘎语翻译与程序化鸭叫合成")


def _print_result(result: TranslationResult, path: Path, played: bool, show_gloss: bool) -> None:
    typer.echo(f"中文：{result.source}")
    typer.echo(f"鸭语：{result.duck}")
    if show_gloss:
        typer.echo(f"直译：{result.gloss}")
    for warning in result.warnings:
        typer.echo(f"提示：{warning}", err=True)
    if played:
        typer.echo(f"音频：{path}（已播放）")
    else:
        typer.echo(f"音频：{path}（已保存，未播放）")


def _run(
    text: str,
    *,
    save: Path | None,
    no_play: bool,
    show_gloss: bool,
    voice: str,
    emotion: str | None,
    strict: bool,
    json_out: bool,
) -> None:
    try:
        result = translate(text, strict=strict)
    except (UnknownWordError, ValueError) as exc:
        typer.echo(f"错误：{exc}", err=True)
        raise typer.Exit(1) from exc

    try:
        path = render_result(result, voice=voice, emotion=emotion, out_path=save)
    except Exception as exc:
        typer.echo(f"合成失败：{exc}", err=True)
        raise typer.Exit(1) from exc

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


def _repl(
    *,
    no_play: bool,
    show_gloss: bool,
    voice: str,
    emotion: str | None,
    strict: bool,
    json_out: bool,
) -> None:
    typer.echo("嘎语 REPL：输入中文，回车听鸭叫；输入 q 退出。")
    while True:
        try:
            line = input("中文> ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo()
            break
        if line.lower() in {"q", "quit", "exit"}:
            break
        if not line:
            continue
        try:
            _run(
                line,
                save=None,
                no_play=no_play,
                show_gloss=show_gloss,
                voice=voice,
                emotion=emotion,
                strict=strict,
                json_out=json_out,
            )
        except typer.Exit:
            continue


@app.command()
def main(
    text: str | None = typer.Argument(None, help="要翻译的中文；省略则进入 REPL"),
    save: Path | None = typer.Option(None, "--save", "-s", help="WAV 保存路径"),
    no_play: bool = typer.Option(False, "--no-play", help="只生成 WAV，不播放"),
    gloss: bool = typer.Option(True, "--gloss/--no-gloss", help="显示逐词直译"),
    voice: str = typer.Option(
        "adult",
        "--voice",
        "-v",
        help=f"音色：{', '.join(VOICES)}",
    ),
    emotion: str | None = typer.Option(
        None,
        "--emotion",
        "-e",
        help=f"覆盖情绪：{', '.join(EMOTIONS)}",
    ),
    strict: bool = typer.Option(False, "--strict", help="遇到未收录词直接报错"),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON"),
    voices: bool = typer.Option(False, "--voices", help="列出可用音色"),
) -> None:
    if voices:
        for name, preset in VOICES.items():
            typer.echo(f"{name:10s} f0={preset.f0:.0f}Hz speed={preset.speed} rough={preset.rough}")
        raise typer.Exit(0)

    if voice not in VOICES:
        typer.echo(f"错误：未知音色 {voice!r}，可选：{', '.join(VOICES)}", err=True)
        raise typer.Exit(1)
    if emotion is not None and emotion not in EMOTIONS:
        typer.echo(f"错误：未知情绪 {emotion!r}，可选：{', '.join(EMOTIONS)}", err=True)
        raise typer.Exit(1)

    if text is None:
        if not sys.stdin.isatty():
            lines = [line.strip() for line in sys.stdin.read().splitlines()]
            lines = [line for line in lines if line and line.lower() not in {"q", "quit", "exit"}]
            text = "。".join(lines)
        else:
            _repl(
                no_play=no_play,
                show_gloss=gloss,
                voice=voice,
                emotion=emotion,
                strict=strict,
                json_out=json_out,
            )
            return

    if not text:
        typer.echo("错误：请输入要翻译的中文。", err=True)
        raise typer.Exit(1)

    _run(
        text,
        save=save,
        no_play=no_play,
        show_gloss=gloss,
        voice=voice,
        emotion=emotion,
        strict=strict,
        json_out=json_out,
    )
