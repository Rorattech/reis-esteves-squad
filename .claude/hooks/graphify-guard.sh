#!/bin/sh
# Ponte entre os hooks PreToolUse do Claude Code (.claude/settings.json) e a CLI
# do graphify, que é instalada por máquina (pipx) e não vive no repositório.
#
# Este arquivo É versionado; o caminho do binário NÃO pode ser. Cada dev instala
# o graphify onde quiser — aqui a gente descobre onde ele ficou.
#
# Contrato: se o graphify não existir nesta máquina, sai com 0 e sem ruído. Um
# hook de contexto jamais pode quebrar o fluxo de quem ainda não instalou a CLI.
#
# Uso: sh .claude/hooks/graphify-guard.sh <search|read>

mode="$1"

# Escotilha de saída: GRAPHIFY_HOOK_DISABLE=1 desliga o hook sem editar settings.
[ -n "$GRAPHIFY_HOOK_DISABLE" ] && exit 0

find_graphify() {
	# PATH primeiro — respeita pipx, venv ativa, asdf, nix, o que for.
	if command -v graphify >/dev/null 2>&1; then
		command -v graphify
		return 0
	fi

	# Hooks podem rodar com PATH mínimo (/bin:/usr/bin), então procuramos nos
	# lugares onde os instaladores usuais colocam o binário.
	for candidate in \
		"$HOME/.local/bin/graphify" \
		"$HOME/.local/share/pipx/venvs/graphifyy/bin/graphify" \
		"$HOME/bin/graphify" \
		/usr/local/bin/graphify \
		/opt/homebrew/bin/graphify
	do
		if [ -x "$candidate" ]; then
			printf '%s\n' "$candidate"
			return 0
		fi
	done

	return 1
}

bin="$(find_graphify)" || exit 0

# exec preserva o stdin (o JSON do evento) e o código de saída do hook-guard,
# que é o que sinaliza bloqueio no modo --strict.
exec "$bin" hook-guard "$mode"
