"""
Water-tank temperature control simulator and visualizer.
Environment-specific: tank schematic, flow/temp display, manual sliders.
Use with env from config: python -m environments.native.thermodynamics.water_tank_simulator --config ... --model ...
"""
import argparse
import time
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.widgets import Slider, Button
from stable_baselines3 import PPO

from environments import get_env, EnvSource


def draw_tank_visualization(ax, env, step_count, max_steps):
    """Draw the tank system visualization (temperature, valves, level)."""
    ax.clear()
    ax.set_xlim(-2, 8)
    ax.set_ylim(-1, 6)
    ax.set_aspect('equal')
    ax.axis('off')

    # Tank (V = 1, fills up over 200 steps)
    tank_x, tank_y = 3, 1
    tank_width, tank_height = 2, 3

    actual_volume = getattr(env, "volume", None)
    actual_capacity = getattr(env, "tank_capacity", 1.0)

    if actual_volume is not None and actual_capacity and actual_capacity > 0:
        fill_progress = np.clip(actual_volume / actual_capacity, 0.0, 1.0)
        volume_pct = (actual_volume / actual_capacity * 100)
    else:
        fill_progress = step_count / max_steps if max_steps > 0 else 0.0
        actual_volume = actual_capacity * fill_progress if actual_capacity else 0.0
        volume_pct = fill_progress * 100

    tank_rect = mpatches.Rectangle((tank_x, tank_y), tank_width, tank_height,
                                   linewidth=3, edgecolor='black', facecolor='lightblue', alpha=0.3)
    ax.add_patch(tank_rect)

    fill_height = tank_height * fill_progress
    if fill_height > 0.01:
        fill_rect = mpatches.Rectangle((tank_x, tank_y), tank_width, fill_height,
                                       linewidth=0, facecolor='lightblue', alpha=0.6)
        ax.add_patch(fill_rect)
    else:
        ax.text(tank_x + tank_width/2, tank_y + tank_height/2,
                'EMPTY', ha='center', va='center',
                fontsize=12, fontweight='bold', color='red', style='italic', alpha=0.5)

    temp = env.current_temp
    target_temp = env.target_temp
    temp_error = abs(temp - target_temp)
    temp_normalized = np.clip((temp - 10) / (60 - 10), 0, 1)
    tank_color = plt.cm.RdYlBu_r(temp_normalized)
    tank_fill = mpatches.Rectangle((tank_x, tank_y), tank_width, fill_height,
                                   linewidth=0, facecolor=tank_color, alpha=0.7)
    ax.add_patch(tank_fill)

    ax.text(tank_x + tank_width/2, tank_y + tank_height + 0.3,
            f'Tank (V={actual_capacity:.1f})', ha='center', fontsize=10, fontweight='bold')
    if fill_height > 0.3:
        ax.text(tank_x + tank_width/2, tank_y + fill_height/2,
                f'{temp:.1f}°C', ha='center', va='center',
                fontsize=14, fontweight='bold', color='green' if temp_normalized > 0.5 else 'black')
    else:
        ax.text(tank_x + tank_width/2, tank_y + tank_height/2,
                f'{temp:.1f}°C', ha='center', va='center',
                fontsize=12, fontweight='bold', style='italic', color='gray')

    water_level_y = tank_y + fill_height
    if fill_height > 0.01:
        ax.plot([tank_x - 0.15, tank_x + tank_width + 0.15],
                [water_level_y, water_level_y],
                'b-', linewidth=3, alpha=0.9, label='Water Level')
        ax.text(tank_x - 0.2, water_level_y,
                f'{fill_progress*100:.0f}%',
                ha='right', va='center', fontsize=9,
                fontweight='bold', color='blue',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    else:
        ax.plot([tank_x - 0.15, tank_x + tank_width + 0.15],
                [tank_y, tank_y],
                'r--', linewidth=2, alpha=0.5, label='Empty')

    sensor_y = tank_y + tank_height + 0.8
    ax.plot([tank_x + tank_width/2 - 0.3, tank_x + tank_width/2 + 0.3],
            [sensor_y, sensor_y], 'r-', linewidth=2, label='Target Sensor')
    ax.plot(tank_x + tank_width/2, sensor_y, 'ro', markersize=8)
    ax.text(tank_x + tank_width/2, sensor_y + 0.3,
            f'Target: {target_temp:.1f}°C', ha='center', fontsize=9,
            color='red', fontweight='bold')

    # Hot water line
    hot_line_x = 0.5
    hot_line_y_start = 4
    hot_line_y_end = tank_y + tank_height
    ax.plot([hot_line_x, hot_line_x], [hot_line_y_start, hot_line_y_end],
            'r-', linewidth=8, alpha=0.6, label='Hot Water Line')
    valve_size = env.hot_flow * 0.3
    valve_y = hot_line_y_end - 0.5
    valve_color = 'darkred' if env.hot_flow > 0.5 else 'lightcoral'
    valve_circle = mpatches.Circle((hot_line_x, valve_y), 0.2 + valve_size,
                                   facecolor=valve_color, edgecolor='black', linewidth=2)
    ax.add_patch(valve_circle)
    ax.text(hot_line_x, valve_y, 'V', ha='center', va='center',
            fontsize=12, fontweight='bold', color='white')
    supply_hot = getattr(env, "hot_supply_temp", env.hot_water_temp)
    ax.text(hot_line_x, hot_line_y_start + 0.3,
            f'Hot: {supply_hot:.1f}°C', ha='center', fontsize=9, fontweight='bold', color='red')
    ax.text(hot_line_x, hot_line_y_start + 0.1,
            f'Flow: {env.hot_flow:.2f}', ha='center', fontsize=8, color='darkred')
    if env.hot_flow > 0.01:
        arrow_length = env.hot_flow * 0.5
        ax.arrow(hot_line_x, hot_line_y_end + 0.3, 0, -arrow_length,
                head_width=0.15, head_length=0.1, fc='red', ec='red', linewidth=2)

    # Cold water line
    cold_line_x = tank_x + tank_width + 1.5
    cold_line_y_start = 4
    cold_line_y_end = tank_y + tank_height
    ax.plot([cold_line_x, cold_line_x], [cold_line_y_start, cold_line_y_end],
            'b-', linewidth=8, alpha=0.6, label='Cold Water Line')
    valve_size = env.cold_flow * 0.3
    valve_y = cold_line_y_end - 0.5
    valve_color = 'darkblue' if env.cold_flow > 0.5 else 'lightblue'
    valve_circle = mpatches.Circle((cold_line_x, valve_y), 0.2 + valve_size,
                                   facecolor=valve_color, edgecolor='black', linewidth=2)
    ax.add_patch(valve_circle)
    ax.text(cold_line_x, valve_y, 'V', ha='center', va='center',
            fontsize=12, fontweight='bold', color='white')
    supply_cold = getattr(env, "cold_supply_temp", env.cold_water_temp)
    ax.text(cold_line_x, cold_line_y_start + 0.3,
            f'Cold: {supply_cold:.1f}°C', ha='center', fontsize=9, fontweight='bold', color='blue')
    ax.text(cold_line_x, cold_line_y_start + 0.1,
            f'Flow: {env.cold_flow:.2f}', ha='center', fontsize=8, color='darkblue')
    if env.cold_flow > 0.01:
        arrow_length = env.cold_flow * 0.5
        ax.arrow(cold_line_x, cold_line_y_end + 0.3, 0, -arrow_length,
                head_width=0.15, head_length=0.1, fc='blue', ec='blue', linewidth=2)

    ax.plot([hot_line_x + 0.3, tank_x], [valve_y, tank_y + tank_height],
            'r--', linewidth=2, alpha=0.4)
    ax.plot([cold_line_x - 0.3, tank_x + tank_width], [valve_y, tank_y + tank_height],
            'b--', linewidth=2, alpha=0.4)

    # Dump valve
    dump_flow = getattr(env, "dump_flow", 0.0)
    dump_x = tank_x + tank_width / 2
    dump_y = tank_y - 0.5
    ax.plot([dump_x, dump_x], [tank_y, dump_y + 0.3],
            'gray', linewidth=6, alpha=0.6, label='Drain Pipe')
    valve_size = dump_flow * 0.3
    valve_color = 'darkgray' if dump_flow > 0.1 else 'lightgray'
    valve_circle = mpatches.Circle((dump_x, dump_y), 0.2 + valve_size,
                                   facecolor=valve_color, edgecolor='black', linewidth=2)
    ax.add_patch(valve_circle)
    ax.text(dump_x, dump_y, 'V', ha='center', va='center',
            fontsize=12, fontweight='bold', color='white')
    ax.text(dump_x, dump_y - 0.7,
            f'Dump: {dump_flow:.2f}', ha='center', fontsize=9, fontweight='bold', color='gray')
    if dump_flow > 0.01:
        arrow_length = dump_flow * 0.4
        ax.arrow(dump_x, dump_y - 0.2, 0, -arrow_length,
                 head_width=0.15, head_length=0.1, fc='gray', ec='gray', linewidth=3)

    ax.text(3, 5.5, 'AI Temperature Control Operator', ha='center',
            fontsize=16, fontweight='bold')

    if temp_error < 0.5:
        status_color, status_text = 'green', '✓ On Target'
    elif temp_error < 1.0:
        status_color, status_text = 'orange', '~ Close'
    else:
        status_color, status_text = 'red', '✗ Off Target'
    ax.text(3, tank_y - 1.6, f'Error: {temp_error:.2f}°C - {status_text}',
            ha='center', fontsize=10, color=status_color, fontweight='bold')
    ax.text(3, tank_y - 1.9,
            f'Step: {step_count}/{max_steps} | Volume: {volume_pct:.1f}% ({actual_volume:.2f}/{actual_capacity:.2f})',
            ha='center', fontsize=8, style='italic')


def visualize_episodes(episodes, target_temp, save_path="control_performance.png"):
    """Create plots showing temperature control performance."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle('AI Agent Temperature Control Performance', fontsize=14, fontweight='bold')

    ax1 = axes[0, 0]
    for i, episode in enumerate(episodes):
        steps = range(len(episode["temperatures"]))
        ax1.plot(steps, episode["temperatures"], label=f'Episode {i+1}', alpha=0.7, linewidth=2)
    ax1.axhline(y=target_temp, color='r', linestyle='--', label=f'Target ({target_temp}°C)', linewidth=2)
    ax1.set_xlabel('Time Step')
    ax1.set_ylabel('Temperature (°C)')
    ax1.set_title('Temperature Control')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2 = axes[0, 1]
    for i, episode in enumerate(episodes):
        steps = range(len(episode["hot_flows"]))
        ax2.plot(steps, episode["hot_flows"], label=f'Hot Flow Ep{i+1}', alpha=0.7, linestyle='-')
        ax2.plot(steps, episode["cold_flows"], label=f'Cold Flow Ep{i+1}', alpha=0.7, linestyle='--')
    ax2.set_xlabel('Time Step')
    ax2.set_ylabel('Flow Rate')
    ax2.set_title('Valve Control (Flow Rates)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    ax3 = axes[1, 0]
    for i, episode in enumerate(episodes):
        steps = range(len(episode["temperatures"]))
        errors = [abs(t - target_temp) for t in episode["temperatures"]]
        ax3.plot(steps, errors, label=f'Episode {i+1}', alpha=0.7, linewidth=2)
    ax3.set_xlabel('Time Step')
    ax3.set_ylabel('Temperature Error (°C)')
    ax3.set_title('Control Error')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    ax3.set_yscale('log')

    ax4 = axes[1, 1]
    for i, episode in enumerate(episodes):
        steps = range(len(episode["rewards"]))
        cumulative_reward = np.cumsum(episode["rewards"])
        ax4.plot(steps, cumulative_reward, label=f'Episode {i+1}', alpha=0.7, linewidth=2)
    ax4.set_xlabel('Time Step')
    ax4.set_ylabel('Cumulative Reward')
    ax4.set_title('Learning Progress (Reward)')
    ax4.legend()
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"\nVisualization saved to '{save_path}'")
    plt.show()


def _env_config_from_training(config_path: Path, process_config_path: Path | None):
    """Build env config dict from training config and process config path."""
    from core.normalizer import load_training_config_from_file
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Training config not found: {config_path}")
    training_config = load_training_config_from_file(config_path)
    if process_config_path is None:
        # Repo root: this file is environments/custom/thermodynamics/water_tank_simulator.py
        process_config_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "examples" / "temperature_process.yaml"
    process_config_path = Path(process_config_path)
    if not process_config_path.exists():
        raise FileNotFoundError(f"Process config not found: {process_config_path}")
    return {
        "process_graph_path": str(process_config_path.resolve()),
        "goal": training_config.goal.model_dump(),
    }


def run_with_visualization(
    config_path: Path | str,
    model_path: Path | str,
    process_config_path: Path | str | None = None,
    num_episodes: int = 3,
    show_realtime: bool = True,
    max_steps: int = 600,
    initial_volume: float | None = None,
    target_temp: float = 37.0,
):
    """Run trained model with real-time tank visualization. Env from config."""
    config_path = Path(config_path)
    model_path = Path(model_path)
    env_config = _env_config_from_training(config_path, process_config_path)
    env = get_env(EnvSource.NATIVE, env_config)
    env.max_steps = max_steps

    print(f"Loading model from {model_path}...")
    model = PPO.load(str(model_path))

    all_episodes = []
    for episode in range(num_episodes):
        reset_options = {"target_temp": target_temp}
        if initial_volume is not None:
            reset_options["initial_volume"] = initial_volume
        obs, info = env.reset(options=reset_options)
        done = False
        episode_data = {
            "temperatures": [env.current_temp],
            "hot_flows": [env.hot_flow],
            "cold_flows": [env.cold_flow],
            "rewards": [],
            "steps": 0,
        }
        print(f"\n=== Episode {episode + 1} ===")
        print(f"Starting volume: {env.volume:.2f} / {env.tank_capacity:.2f}")

        if show_realtime:
            fig, ax = plt.subplots(figsize=(10, 8))
            plt.ion()
            plt.show()
            draw_tank_visualization(ax, env, 0, env.max_steps)
            plt.draw()
            plt.pause(0.2)

        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            episode_data["temperatures"].append(env.current_temp)
            episode_data["hot_flows"].append(env.hot_flow)
            episode_data["cold_flows"].append(env.cold_flow)
            episode_data["rewards"].append(reward)
            episode_data["steps"] += 1
            if show_realtime and episode_data["steps"] % 2 == 0:
                draw_tank_visualization(ax, env, episode_data["steps"], env.max_steps)
                plt.draw()
                plt.pause(0.01)

        if show_realtime:
            plt.ioff()
            plt.close(fig)
        all_episodes.append(episode_data)
        volume_ratio = info.get("volume_ratio", env.volume / env.tank_capacity)
        temp_success = abs(info["temperature"] - env.target_temp) < 0.1
        volume_success = 0.80 <= volume_ratio <= 0.85
        print(f"Final: {info['temperature']:.2f}°C (target {env.target_temp}°C)")
        print(f"Volume: {volume_ratio*100:.1f}% | Success: {'✓' if (temp_success and volume_success) else '✗'} | Steps: {episode_data['steps']}")

    visualize_episodes(all_episodes, env.target_temp)
    env.close()


def run_manual_control(
    config_path: Path | str,
    process_config_path: Path | str | None = None,
    model_path: Path | str | None = None,
    max_steps: int = 600,
    init_target: float = 37.0,
    init_hot_temp: float = 60.0,
    init_cold_temp: float = 10.0,
    init_hot_flow: float = 0.0,
    init_cold_flow: float = 0.0,
    init_dump_flow: float = 0.0,
):
    """Manual/AI control with sliders and tank visualization. Env from config."""
    config_path = Path(config_path)
    env_config = _env_config_from_training(config_path, process_config_path)
    env = get_env(EnvSource.NATIVE, env_config)
    env.max_steps = max_steps

    model = None
    if model_path and Path(model_path).exists():
        print(f"Loading model from {model_path}...")
        model = PPO.load(str(model_path))
    use_ai = model is not None

    obs, info = env.reset(options={"target_temp": init_target})
    if use_ai:
        env.disable_drift = False
    else:
        env.disable_drift = True
    env.hot_supply_temp = init_hot_temp
    env.cold_supply_temp = init_cold_temp

    fig = plt.figure(figsize=(14, 10))
    ax_main = plt.subplot2grid((10, 10), (0, 0), colspan=7, rowspan=10)
    ax_main.set_position([0.05, 0.15, 0.55, 0.8])
    control_y_start = 0.02
    control_height = 0.12
    control_spacing = 0.015
    slider_width = 0.3
    slider_height = 0.02
    left_margin = 0.65

    ax_hot_temp = plt.axes([left_margin, control_y_start + 4 * (control_height + control_spacing), slider_width, slider_height])
    hot_temp_slider = Slider(ax_hot_temp, 'Hot Temp', 0.0, 100.0, valinit=init_hot_temp, valfmt='%.1f°C')
    ax_cold_temp = plt.axes([left_margin, control_y_start + 3 * (control_height + control_spacing), slider_width, slider_height])
    cold_temp_slider = Slider(ax_cold_temp, 'Cold Temp', 0.0, 100.0, valinit=init_cold_temp, valfmt='%.1f°C')
    ax_hot_flow = plt.axes([left_margin, control_y_start + 2 * (control_height + control_spacing), slider_width, slider_height])
    hot_flow_slider = Slider(ax_hot_flow, 'Hot Flow', 0.0, env.max_flow_rate, valinit=init_hot_flow, valfmt='%.2f')
    ax_cold_flow = plt.axes([left_margin, control_y_start + 1 * (control_height + control_spacing), slider_width, slider_height])
    cold_flow_slider = Slider(ax_cold_flow, 'Cold Flow', 0.0, env.max_flow_rate, valinit=init_cold_flow, valfmt='%.2f')
    ax_target = plt.axes([left_margin, control_y_start + 0 * (control_height + control_spacing), slider_width, slider_height])
    target_slider = Slider(ax_target, 'Target Temp', 0.0, 100.0, valinit=init_target, valfmt='%.1f°C')
    ax_reset = plt.axes([left_margin + slider_width + 0.05, control_y_start, 0.1, 0.04])
    reset_button = Button(ax_reset, 'Reset')
    ax_mode = plt.axes([left_margin + slider_width + 0.05, control_y_start + 0.05, 0.1, 0.04])
    mode_button = Button(ax_mode, 'AI Mode' if use_ai else 'Manual')
    ai_mode = use_ai
    ax_dump_flow = plt.axes([left_margin, control_y_start - 0.05, slider_width, slider_height])
    dump_flow_slider = Slider(ax_dump_flow, 'Dump Flow', 0.0, env.max_dump_flow_rate, valinit=init_dump_flow, valfmt='%.2f')

    step_count = 0
    prev_hot_temp, prev_cold_temp = init_hot_temp, init_cold_temp

    def update_environment():
        env.hot_supply_temp = hot_temp_slider.val
        env.cold_supply_temp = cold_temp_slider.val
        env.hot_water_temp = hot_temp_slider.val
        env.cold_water_temp = cold_temp_slider.val
        env.target_temp = target_slider.val
        env.hot_flow = hot_flow_slider.val
        env.cold_flow = cold_flow_slider.val
        env.dump_flow = dump_flow_slider.val

    def on_slider_change(val):
        update_environment()
        draw_tank_visualization(ax_main, env, step_count, env.max_steps)
        plt.draw()

    def on_reset(event):
        nonlocal step_count, prev_hot_temp, prev_cold_temp
        obs, info = env.reset()
        step_count = 0
        hot_temp_slider.reset()
        cold_temp_slider.reset()
        hot_flow_slider.reset()
        cold_flow_slider.reset()
        dump_flow_slider.reset()
        target_slider.set_val(init_target)
        prev_hot_temp, prev_cold_temp = init_hot_temp, init_cold_temp
        if ai_mode:
            env.hot_supply_temp = init_hot_temp
            env.cold_supply_temp = init_cold_temp
        update_environment()
        draw_tank_visualization(ax_main, env, step_count, env.max_steps)
        plt.draw()

    def on_mode_toggle(event):
        nonlocal ai_mode
        ai_mode = not ai_mode
        mode_button.label.set_text('AI Mode' if ai_mode else 'Manual')
        env.disable_drift = not ai_mode
        if ai_mode:
            env.hot_supply_temp = hot_temp_slider.val
            env.cold_supply_temp = cold_temp_slider.val
        plt.draw()

    hot_temp_slider.on_changed(on_slider_change)
    cold_temp_slider.on_changed(on_slider_change)
    hot_flow_slider.on_changed(on_slider_change)
    cold_flow_slider.on_changed(on_slider_change)
    target_slider.on_changed(on_slider_change)
    dump_flow_slider.on_changed(on_slider_change)
    reset_button.on_clicked(on_reset)
    mode_button.on_clicked(on_mode_toggle)

    update_environment()
    draw_tank_visualization(ax_main, env, step_count, env.max_steps)
    plt.ion()
    plt.show()

    print("\n=== Manual Control Mode ===")
    print("Use sliders to adjust parameters. AI Mode: agent controls valves.")
    print("Press 'q' to quit.")

    try:
        while True:
            env.target_temp = target_slider.val
            if ai_mode and model:
                env.disable_drift = False
                if abs(hot_temp_slider.val - prev_hot_temp) > 0.1:
                    env.hot_water_temp = env.hot_supply_temp = hot_temp_slider.val
                    prev_hot_temp = hot_temp_slider.val
                if abs(cold_temp_slider.val - prev_cold_temp) > 0.1:
                    env.cold_water_temp = env.cold_supply_temp = cold_temp_slider.val
                    prev_cold_temp = cold_temp_slider.val
                action, _ = model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = env.step(action)
                hot_flow_slider.set_val(env.hot_flow)
                cold_flow_slider.set_val(env.cold_flow)
                dump_flow_slider.set_val(env.dump_flow)
            else:
                obs, reward, terminated, truncated, info = env.manual_step(
                    hot_flow=hot_flow_slider.val,
                    cold_flow=cold_flow_slider.val,
                    dump_flow=dump_flow_slider.val,
                    hot_supply_temp=hot_temp_slider.val,
                    cold_supply_temp=cold_temp_slider.val,
                    disable_drift=True,
                )
            step_count += 1
            if terminated or truncated:
                volume_ratio = info.get("volume_ratio", env.volume / env.tank_capacity)
                temp_success = abs(info["temperature"] - env.target_temp) < 0.1
                volume_success = 0.80 <= volume_ratio <= 0.85
                print(f"Episode finished: {info['temperature']:.2f}°C, vol {volume_ratio*100:.1f}%, success {'✓' if (temp_success and volume_success) else '✗'}")
                obs, info = env.reset()
                step_count = 0
                prev_hot_temp, prev_cold_temp = hot_temp_slider.val, cold_temp_slider.val
                if ai_mode:
                    env.hot_supply_temp = hot_temp_slider.val
                    env.cold_supply_temp = cold_temp_slider.val
            draw_tank_visualization(ax_main, env, step_count, env.max_steps)
            plt.draw()
            plt.pause(0.05)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        plt.ioff()
        env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Water-tank temperature control simulator (visualize or manual).")
    parser.add_argument("--config", type=str, default="config/examples/training_config.yaml", help="Training config (for goal + env).")
    parser.add_argument("--process-config", type=str, default=None, help="Process graph YAML (default: config/examples/temperature_process.yaml).")
    parser.add_argument("--model", type=str, default="./models/temperature-control-agent/best/best_model", help="Path to trained model.")
    parser.add_argument("--manual", action="store_true", help="Manual mode with sliders (AI assists if --model provided).")
    parser.add_argument("--manual-only", action="store_true", help="Pure manual mode (no AI).")
    parser.add_argument("--max-steps", type=int, default=600, help="Max steps per episode.")
    parser.add_argument("--target", type=float, default=37.0, help="Target temperature.")
    parser.add_argument("--hot-temp", type=float, default=60.0, help="Hot supply temperature.")
    parser.add_argument("--cold-temp", type=float, default=10.0, help="Cold supply temperature.")
    parser.add_argument("--episodes", type=int, default=3, help="Episodes in visualize mode.")
    parser.add_argument("--initial-volume", type=float, default=None, help="Initial tank volume ratio (0–1).")
    parser.add_argument("--no-realtime", action="store_true", help="Disable real-time tank viz (only summary plots).")
    args = parser.parse_args()

    if args.manual or args.manual_only:
        run_manual_control(
            config_path=args.config,
            process_config_path=args.process_config,
            model_path=None if args.manual_only else args.model,
            max_steps=args.max_steps,
            init_target=args.target,
            init_hot_temp=args.hot_temp,
            init_cold_temp=args.cold_temp,
        )
    else:
        run_with_visualization(
            config_path=args.config,
            model_path=args.model,
            process_config_path=args.process_config,
            num_episodes=args.episodes,
            show_realtime=not args.no_realtime,
            max_steps=args.max_steps,
            initial_volume=args.initial_volume,
            target_temp=args.target,
        )
