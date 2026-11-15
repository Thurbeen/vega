#!/bin/sh
# Install VEGA into a Fleet v3 store as the Task `vega`, or take it out.
# Safe to run again: it changes only what is missing.
set -eu

usage() {
	cat <<'EOF'
Usage: ./install.sh [--config PATH] [--harness NAME]
       ./install.sh --uninstall [--config PATH]

  --config PATH   Fleet config to install into (else FLEET_CONFIG, then
                  Fleet's per-user config, which `fleet init` writes if absent)
  --harness NAME  The coding agent VEGA runs (default: the first one
                  `fleet doctor` finds on PATH)
  --uninstall     Delete the Task `vega`; this checkout and its files stay
EOF
}

die() {
	printf 'install.sh: %s\n' "$*" >&2
	exit 1
}

here=$(cd "$(dirname "$0")" && pwd -P)
config=
harness=
uninstall=
while [ $# -gt 0 ]; do
	case $1 in
	--config)
		[ $# -ge 2 ] || die "--config needs a path"
		config=$2
		shift 2
		;;
	--config=*)
		config=${1#*=}
		shift
		;;
	--harness)
		[ $# -ge 2 ] || die "--harness needs a name"
		harness=$2
		shift 2
		;;
	--harness=*)
		harness=${1#*=}
		shift
		;;
	--uninstall)
		uninstall=1
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		usage >&2
		exit 2
		;;
	esac
done

command -v fleet >/dev/null 2>&1 ||
	die "fleet is not on PATH: install Fleet v3 first (see README.md)"
command -v jq >/dev/null 2>&1 ||
	die "jq is not on PATH: install jq; VEGA's skills use it too"

version=$(fleet version --json 2>/dev/null) || die "fleet version --json failed: install Fleet v3"
printf '%s' "$version" | jq -e '(.runtimeProtocol // 0) >= 2
	and ((.apiVersions // []) | index("fleet/v1alpha1"))
	and ((.kinds // []) | index("Task"))' >/dev/null 2>&1 ||
	die "$(command -v fleet) is not Fleet v3 ($(printf '%s' "$version" | jq -r '.version // "unknown"' 2>/dev/null)): install Fleet v3 (see README.md)"

# Fleet's own selection: --config, then FLEET_CONFIG, then the per-user file.
named=${config:-${FLEET_CONFIG:-}}
if [ -n "$named" ]; then
	config=$named
elif [ -n "${XDG_CONFIG_HOME:-}" ]; then
	config=$XDG_CONFIG_HOME/fleet/config.toml
else
	config=$HOME/.config/fleet/config.toml
fi
case $config in
/*) ;;
*) config=$PWD/$config ;;
esac

get_vega() {
	vega=$(fleet --config "$config" get task vega 2>&1) && return 0 || rc=$?
	[ "$rc" -eq 3 ] && return 1
	die "$vega"
}

if [ -n "$uninstall" ]; then
	if [ ! -f "$config" ] || ! get_vega; then
		echo "VEGA is not installed in $config."
		exit 0
	fi
	fleet --config "$config" delete task vega >/dev/null
	echo "Deleted the Task vega from $config: fleet up releases its session."
	echo "Its worker Tasks keep running; this checkout stays."
	exit 0
fi

if [ -n "$named" ]; then
	init=$(fleet --config "$config" init 2>&1) || die "$init"
else
	init=$(fleet init 2>&1) || die "$init"
fi

doctor=$(fleet --config "$config" doctor --json 2>/dev/null) || true
if [ -z "$harness" ]; then
	harness=$(printf '%s' "$doctor" | jq -r 'first(.checks[]
		| select(.area == "harness" and .level == "ok") | .name) // empty' 2>/dev/null) || true
	[ -n "$harness" ] ||
		die "no coding agent found on PATH: install and log in to one, or pass --harness"
fi
printf '%s' "$version" | jq -e --arg h "$harness" '.harnesses | index($h)' >/dev/null ||
	die "Fleet has no harness '$harness'; it knows: $(printf '%s' "$version" | jq -r '.harnesses | join(", ")')"
missing=$(printf '%s' "$doctor" | jq -r --arg h "$harness" 'first(.checks[]
	| select(.area == "harness" and .name == $h and .level != "ok")
	| "\(.detail)\(if .hint then ": \(.hint)" else "" end)") // empty' 2>/dev/null) || true
[ -z "$missing" ] || die "harness $harness: $missing"

# Workers declare the changes they open; Fleet follows a change only on a
# forge host the config names. Add the hosts whose CLI is here, once.
added=
if ! grep -Eq '^[[:space:]]*(\[forge\.hosts|hosts[[:space:]]*=|forge\.hosts)' "$config"; then
	hosts=
	for entry in github.com:github:gh gitlab.com:gitlab:glab; do
		cli=${entry##*:}
		host=${entry%%:*}
		kind=${entry#*:}
		kind=${kind%:*}
		if command -v "$cli" >/dev/null 2>&1; then
			hosts="$hosts\"$host\" = { kind = \"$kind\", cli = \"$cli\" }
"
			added="$added $host"
		fi
	done
	if [ -n "$hosts" ]; then
		candidate=$(mktemp "$config.vega.XXXXXX")
		cp "$config" "$candidate"
		printf '\n[forge.hosts]\n%s' "$hosts" >>"$candidate"
		if check=$(fleet --config "$candidate" list task --json 2>&1 >/dev/null); then
			mv "$candidate" "$config"
		else
			rm -f "$candidate"
			die "adding [forge.hosts] to $config failed: $check"
		fi
	fi
fi

workspace=$(jq -rn --arg p "$here/workspace" '"file://" + ($p | split("/") | map(@uri) | join("/"))')
manifest=$(jq -c --arg h "$harness" --arg ws "$workspace" --arg cfg "$config" \
	'.spec.harness = $h | .spec.workspace = [$ws] | .spec.env = {FLEET_CONFIG: $cfg}' \
	"$here/tasks/vega.json")

if get_vega; then
	printf '%s' "$vega" | jq -e '.metadata.deletionTimestamp == null' >/dev/null ||
		die "VEGA is being deleted: run this again once fleet up has released it"
	differs=$(printf '%s' "$vega" | jq -r --argjson want "$manifest" \
		'[("harness", "workspace", "env") as $k | select(.spec[$k] != $want.spec[$k]) | $k] | join(", ")')
	[ -z "$differs" ] ||
		die "VEGA is installed with another $differs: run ./install.sh --uninstall first"
	if ! printf '%s' "$vega" | jq -e '.spec.dispatch' >/dev/null; then
		printf '%s' "$vega" | jq '.spec.dispatch = true | del(.status)' |
			fleet --config "$config" apply -f - >/dev/null
	fi
	echo "VEGA is already installed in $config."
else
	printf '%s' "$manifest" | fleet --config "$config" apply -f - --create-only >/dev/null
	echo "Installed VEGA in $config: the Task vega runs $harness in $here/workspace."
fi
[ -z "$added" ] || echo "Added forge hosts to the config:$added."

echo
echo "Talk to VEGA:"
[ -z "$named" ] || echo "  export FLEET_CONFIG='$config'"
echo "  thurbox                       # VEGA is the session vega"
echo "  fleet send vega \"MESSAGE\"     # or queue a message for it"
if [ "$(fleet --config "$config" version --json | jq -r '.manager.held')" = true ]; then
	[ -z "$added" ] || echo "Restart fleet up to follow changes on the new forge hosts."
else
	echo "Fleet is not running: thurbox starts it, or run fleet up."
fi
