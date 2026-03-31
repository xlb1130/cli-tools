from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import click
from click.shell_completion import get_completion_class

from cts.cli.lazy import render_payload


def register_completion_commands(manage_group, *, main_group) -> None:
    @manage_group.group()
    def completion() -> None:
        """Shell completion helpers."""

    @completion.command("script")
    @click.option("--shell", "shell_name", type=click.Choice(["bash", "zsh", "fish"]), required=True)
    def completion_script(shell_name: str) -> None:
        completion_class = get_completion_class(shell_name)
        if completion_class is None:
            raise click.ClickException(f"unsupported shell: {shell_name}")
        prog_name = main_group.name or "cts"
        complete_var = f"_{prog_name.replace('-', '_').upper()}_COMPLETE"
        shell_complete = completion_class(main_group, {}, prog_name, complete_var)
        click.echo(shell_complete.source())

    @completion.command("install")
    @click.option("--shell", "shell_name", type=click.Choice(["bash", "zsh", "fish"]), required=False, help="Shell type (auto-detected if not specified).")
    @click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write to a specific file instead of the default shell config.")
    @click.option("--append", is_flag=True, help="Append to config file instead of replacing existing cts completion.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    def completion_install(
        shell_name: Optional[str],
        target_file: Optional[Path],
        append: bool,
        output_format: str,
    ) -> None:
        """Install shell completion for cts."""
        if shell_name is None:
            shell_env = os.environ.get("SHELL", "")
            if "zsh" in shell_env:
                shell_name = "zsh"
            elif "fish" in shell_env:
                shell_name = "fish"
            elif "bash" in shell_env:
                shell_name = "bash"
            else:
                raise click.ClickException("Could not auto-detect shell. Please specify --shell (bash, zsh, or fish).")

        completion_class = get_completion_class(shell_name)
        if completion_class is None:
            raise click.ClickException(f"unsupported shell: {shell_name}")

        prog_name = main_group.name or "cts"
        complete_var = f"_{prog_name.replace('-', '_').upper()}_COMPLETE"
        shell_complete = completion_class(main_group, {}, prog_name, complete_var)
        completion_source = shell_complete.source()

        home = Path.home()
        if target_file is None:
            if shell_name == "bash":
                target_file = home / ".bashrc"
                if not target_file.exists():
                    target_file = home / ".bash_profile"
            elif shell_name == "zsh":
                target_file = home / ".zshrc"
            elif shell_name == "fish":
                target_file = home / ".config" / "fish" / "completions" / f"{prog_name}.fish"
                target_file.parent.mkdir(parents=True, exist_ok=True)

        if shell_name in ("bash", "zsh"):
            completion_dir = home / ".local" / "share" / "cts" / "completions"
            completion_dir.mkdir(parents=True, exist_ok=True)
            completion_script_file = completion_dir / f"{prog_name}.{shell_name}"
            completion_script_file.write_text(completion_source)

            source_line = f"[ -f {completion_script_file} ] && source {completion_script_file}"
            marker_start = "# >>> cts completion >>>"
            marker_end = "# <<< cts completion <<<"
            existing_content = target_file.read_text() if target_file.exists() else ""

            if marker_start in existing_content:
                if append:
                    payload = {
                        "ok": True,
                        "action": "completion_install",
                        "shell": shell_name,
                        "file": str(target_file),
                        "message": "Completion already installed. Use --append to add another or manually edit.",
                        "completion_script": str(completion_script_file),
                    }
                    click.echo(render_payload(payload, output_format))
                    return
                pattern = f"{re.escape(marker_start)}.*?{re.escape(marker_end)}"
                new_content = re.sub(pattern, f"{marker_start}\n{source_line}\n{marker_end}", existing_content, flags=re.DOTALL)
            else:
                completion_block = f"\n{marker_start}\n{source_line}\n{marker_end}\n"
                new_content = existing_content + completion_block

            target_file.write_text(new_content)
            payload = {
                "ok": True,
                "action": "completion_install",
                "shell": shell_name,
                "file": str(target_file),
                "completion_script": str(completion_script_file),
                "message": f"Completion installed. Restart your shell or run: source {target_file}",
                "next_command": f"source {target_file}",
            }
        else:
            target_file.write_text(completion_source)
            payload = {
                "ok": True,
                "action": "completion_install",
                "shell": shell_name,
                "file": str(target_file),
                "message": f"Completion installed. Restart your shell or run: source {target_file}",
                "next_command": f"source {target_file}",
            }

        click.echo(render_payload(payload, output_format))

    @completion.command("bootstrap")
    @click.option("--shell", "shell_name", type=click.Choice(["bash", "zsh", "fish"]), required=False, help="Shell type (auto-detected if not specified).")
    @click.option("--format", "output_format", type=click.Choice(["shell", "text", "json"]), default="shell")
    def completion_bootstrap(shell_name: Optional[str], output_format: str) -> None:
        """Bootstrap shell completion for the current session."""
        if shell_name is None:
            shell_env = os.environ.get("SHELL", "")
            if "zsh" in shell_env:
                shell_name = "zsh"
            elif "fish" in shell_env:
                shell_name = "fish"
            elif "bash" in shell_env:
                shell_name = "bash"
            else:
                raise click.ClickException("Could not auto-detect shell. Please specify --shell (bash, zsh, or fish).")

        completion_class = get_completion_class(shell_name)
        if completion_class is None:
            raise click.ClickException(f"unsupported shell: {shell_name}")

        prog_name = main_group.name or "cts"
        complete_var = f"_{prog_name.replace('-', '_').upper()}_COMPLETE"
        shell_complete = completion_class(main_group, {}, prog_name, complete_var)
        completion_source = shell_complete.source()

        if shell_name == "bash":
            output_lines = [
                f"complete -F _{prog_name}_completion {prog_name}",
                f"_{prog_name}_completion() {{",
                "  local IFS=$'\\n'",
                f"  COMPREPLY=($(env COMP_WORDS=\"${{COMP_WORDS[*]}}\" COMP_CWORD=$COMP_CWORD {complete_var}=complete-{shell_name} {prog_name}))",
                "}",
            ]
        else:
            output_lines = completion_source.splitlines()
        shell_output = "\n".join(output_lines)
        if output_format == "shell":
            click.echo(shell_output)
            return

        payload = {
            "ok": True,
            "action": "completion_bootstrap",
            "shell": shell_name,
            "copy_command": f'eval "$({prog_name} manage completion bootstrap --shell {shell_name})"',
            "command_preview": shell_output,
            "message": f"Use this to enable {shell_name} completion for the current shell session.",
        }
        click.echo(render_payload(payload, "json" if output_format == "json" else "text"))
