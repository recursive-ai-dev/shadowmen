# Shadow Men

An evolving colony of shadow people with a predator, sexual selection, island speciation, and an arms race. This application runs as a transparent overlay on your Linux desktop, where shadow people interact with each other and your open windows.

## Features

- **Evolutionary Simulation**: Shadow people have heritable traits (speed, scale, climb probability, etc.) that evolve over generations.
- **Predator-Prey Dynamics**: Enable a red predator to start an evolutionary arms race.
- **Window Interaction**: People can walk on, climb, and fall from your open windows (requires `wmctrl`).
- **Island Speciation**: Geographic isolation on different windows/screen edges leads to divergent evolution.
- **Visual Config Panel**: Live-edit simulation parameters without restarting.
- **Desktop Integration**: Runs as a lightweight overlay with autostart support.

## Installation

### System Dependencies

You will need the following system packages (Ubuntu/Debian example):

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 wmctrl
```

### From Source

```bash
git clone https://github.com/user/shadowmen.git
cd shadowmen
pip install -e .
```

## Usage

Start the simulation:

```bash
shadowmen
```

### CLI Arguments

- `--count N`: Initial population size.
- `--predator`: Enable the red predator.
- `--evo-speed N`: Run evolution N× faster.
- `--config-panel`: Open the visual config panel alongside the simulation.
- `--reset`: Wipe the saved population and start fresh.
- `--install-autostart`: Install a desktop autostart entry.

For a full list of arguments, run `shadowmen --help`.

## Keybindings & Controls

- **Ctrl-C**: Quit the simulation.
- **Tray Icon**: Click the preferences icon in your system tray to open the configuration panel.

## How it Works

1. **Genome**: Each shadow person has a genome defining 12 continuous traits.
2. **Fitness**: Accumulated based on survival time and social interactions.
3. **Selection**: Every generation, the fittest individuals are selected to reproduce.
4. **Mutation**: Gaussian mutation allows for new traits to emerge over time.

## License

MIT
