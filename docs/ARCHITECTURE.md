┌─────────────────────────────────────────────────────┐
│                   USER INTERFACE                     │
│  KryosBar (AGS) │ KryosDock (AGS) │ Spotlight (AGS) │
│  KryosAssistant (AGS) │ System Preferences           │
├─────────────────────────────────────────────────────┤
│              WAYLAND COMPOSITOR                      │
│         Hyprland + kryos-hyprland-config             │
│    blur │ rounded corners │ spring animations         │
├─────────────────────────────────────────────────────┤
│              KRYOS AGENT (TypeScript)                │
│  ReAct Loop │ Lumyn Planner │ Tool Registry          │
│  mouse/keyboard/screen tools via ydotool/grim        │
├─────────────────────────────────────────────────────┤
│              VYREX (Go + llama.cpp)               │
│  Model Registry │ OpenAI API Socket │ Hot-swap        │
│  Qwen2.5-7B │ LLaVA │ Whisper │ Cloud fallback        │
├─────────────────────────────────────────────────────┤
│              LINUX KERNEL (Debian bookworm)          │
│  eBPF sandbox │ uinput │ io_uring IPC │ PipeWire      │
└─────────────────────────────────────────────────────┘
