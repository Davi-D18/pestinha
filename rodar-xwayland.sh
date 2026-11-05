#!/bin/sh
# Pestinha em XWayland: força Qt para X11/xcb em vez da plataforma Wayland nativa.
# Usar XWayland faz o backend de janelas (wmctrl/xdotool via X server) responder,
# coisa que o Wayland nativo do Qt não dá ao pet.
set -eu
cd "$(dirname "$0")"
exec env QT_QPA_PLATFORM=xcb .venv/bin/python main.py --direto
