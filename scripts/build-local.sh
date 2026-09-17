#!/usr/bin/env bash
# Build do APK local, no WSL2 + Ubuntu 22.04 — espelha o job "build" da CI
# (.github/workflows/build-apk.yml). Buildozer só roda em Linux; no Windows,
# o WSL2 é o Linux de verdade pra isso.
#
# USO (dentro do Ubuntu do WSL, na raiz do projeto):
#     bash scripts/build-local.sh            # build debug
#     bash scripts/build-local.sh --setup    # (re)instala as dependências do sistema
#     bash scripts/build-local.sh --clean    # limpa a saída do p4a antes (build do zero)
#     bash scripts/build-local.sh --release  # buildozer android release (precisa de keystore)
#
# 1º build: 30-60 min (baixa NDK/SDK/recipes, ~15 GB em ~/.buildozer). Depois
# disso, incremental é minutos — o cache persiste entre execuções.
#
# SEM pipefail de propósito: o build roda como `yes | buildozer`, e o `yes`
# sai com 141 (SIGPIPE) quando o buildozer fecha o stdin. Com pipefail esse
# 141 viraria o status do pipeline e o `if ... then` daria build por falho
# mesmo com o APK gerado. A CI também roda sem pipefail.
set -eu

cd "$(dirname "$0")/.."
PROJ="$(pwd)"

# --- avisos de ambiente -------------------------------------------------------
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERRO: rode isto dentro do WSL/Ubuntu, não no Windows. Buildozer não roda no Windows." >&2
  exit 1
fi
if [[ "$PROJ" == /mnt/* ]]; then
  echo "AVISO: o projeto está em $PROJ (filesystem do Windows via /mnt)." >&2
  echo "       O build fica LENTO e o OneDrive pode brigar com .buildozer/." >&2
  echo "       Recomendado: 'git clone' o repo dentro do WSL (ex.: ~/discipliner) e buildar lá." >&2
  read -rp "       Continuar assim mesmo? [s/N] " r
  [[ "${r:-N}" =~ ^[sS]$ ]] || exit 1
fi

SETUP=0 CLEAN=0 CMD="android debug"
for arg in "$@"; do
  case "$arg" in
    --setup)   SETUP=1 ;;
    --clean)   CLEAN=1 ;;
    --release) CMD="android release" ;;
    *) echo "arg desconhecido: $arg" >&2; exit 2 ;;
  esac
done

# --- dependências do sistema (idempotente; só na 1ª vez ou com --setup) ------
DEPS_MARK="$HOME/.cache/discipliner-build-deps-ok"
if [[ $SETUP -eq 1 || ! -f "$DEPS_MARK" ]]; then
  echo ">> instalando dependências do sistema (pede sudo)..."
  sudo apt-get update
  # mesma lista da CI (Ubuntu 22.04). libtinfo5/libncurses5-dev NÃO existem no
  # Ubuntu 24.04 — por isso a recomendação é instalar o Ubuntu-22.04 no WSL.
  sudo apt-get install -y \
    git zip unzip openjdk-17-jdk \
    python3-pip python3-venv python3-virtualenv \
    autoconf automake autopoint gettext libtool libltdl-dev pkg-config \
    zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 \
    libffi-dev libssl-dev \
    build-essential ccache cmake
  python3 -m pip install --user --upgrade pip
  # buildozer + cython no --user; garante que ~/.local/bin está no PATH abaixo
  python3 -m pip install --user --upgrade buildozer cython
  mkdir -p "$(dirname "$DEPS_MARK")" && touch "$DEPS_MARK"
  echo ">> dependências OK"
fi

export PATH="$HOME/.local/bin:$PATH"
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
echo ">> JAVA_HOME=$JAVA_HOME"
java -version

# Trava a versão do pip usada DENTRO das venvs que o p4a cria (build/venv e as
# de cada recipe): o pip mais novo do PyPI já quebrou a própria instalação 2x
# em builds seguidos ('BuildDependencyInstallError'). Mesmo motivo do
# PIP_CONSTRAINT na CI.
PIP_CONSTRAINT_FILE="$(mktemp)"
echo "pip==24.3.1" > "$PIP_CONSTRAINT_FILE"
export PIP_CONSTRAINT="$PIP_CONSTRAINT_FILE"

if [[ $CLEAN -eq 1 ]]; then
  echo ">> limpando .buildozer/android/platform/build-* (mantém os downloads)..."
  rm -rf .buildozer/android/platform/build-* bin/*.apk 2>/dev/null || true
fi

# --- build com retry (mirrors da CI) ---------------------------------------
# Os mirrors das recipes (freetype no download.savannah.gnu.org, etc.) às vezes
# devolvem 502/504 por alguns minutos; reexecutar o comando resume de onde
# parou (o p4a só marca uma recipe como baixada depois do download completo).
for i in 1 2 3; do
  if yes | buildozer -v $CMD; then
    echo
    echo ">> APK gerado:"
    ls -lh bin/*.apk
    echo
    echo ">> instalar num celular no cabo:  buildozer $CMD deploy run logcat"
    exit 0
  fi
  echo ">> build falhou (tentativa $i/3), tentando de novo em 60s..." >&2
  sleep 60
done
echo ">> build falhou nas 3 tentativas." >&2
exit 1
