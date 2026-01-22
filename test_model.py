"""
Test and visualize a trained model.
"""
import argparse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.widgets import Slider, Button
from stable_baselines3 import PPO
from temperature_env import TemperatureControlEnv


def draw_tank_visualization(ax, env, step_count, max_steps):
    """Draw the tank system visualization."""
    ax.clear()
    ax.set_xlim(-2, 8)
    ax.set_ylim(-1, 6)
    ax.set_aspect('equal')
    ax.axis('off')
    
    # Tank (V = 1, fills up over 200 steps)
    tank_x, tank_y = 3, 1
    tank_width, tank_height = 2, 3
    
    # Always get fresh volume from environment (don't cache)
    actual_volume = getattr(env, "volume", None)
    actual_capacity = getattr(env, "tank_capacity", 1.0)
    
    # Always use actual volume if available, otherwise fallback to step progress
    if actual_volume is not None and actual_capacity and actual_capacity > 0:
        fill_progress = np.clip(actual_volume / actual_capacity, 0.0, 1.0)
        volume_pct = (actual_volume / actual_capacity * 100)
    else:
        # Fallback: estimate from step progress (for backward compatibility)
        fill_progress = step_count / max_steps if max_steps > 0 else 0.0
        actual_volume = actual_capacity * fill_progress if actual_capacity else 0.0
        volume_pct = fill_progress * 100
    
    # Tank outline
    tank_rect = mpatches.Rectangle((tank_x, tank_y), tank_width, tank_height,
                                   linewidth=3, edgecolor='black', facecolor='lightblue', alpha=0.3)
    ax.add_patch(tank_rect)
    
    # Tank fill (water level based on progress)
    fill_height = tank_height * fill_progress
    # Draw water fill from bottom
    if fill_height > 0.01:  # Only draw if there's any water
        fill_rect = mpatches.Rectangle((tank_x, tank_y), tank_width, fill_height,
                                       linewidth=0, facecolor='lightblue', alpha=0.6)
        ax.add_patch(fill_rect)
    else:
        # Show empty tank indicator
        ax.text(tank_x + tank_width/2, tank_y + tank_height/2, 
                'EMPTY', ha='center', va='center', 
                fontsize=12, fontweight='bold', color='red', style='italic', alpha=0.5)
    
    # Current temperature in tank (color-coded)
    temp = env.current_temp
    target_temp = env.target_temp
    temp_error = abs(temp - target_temp)
    
    # Color based on temperature (blue=cold, red=hot)
    temp_normalized = np.clip((temp - 10) / (60 - 10), 0, 1)
    tank_color = plt.cm.RdYlBu_r(temp_normalized)
    tank_fill = mpatches.Rectangle((tank_x, tank_y), tank_width, fill_height,
                                   linewidth=0, facecolor=tank_color, alpha=0.7)
    ax.add_patch(tank_fill)
    
    # Tank labels
    ax.text(tank_x + tank_width/2, tank_y + tank_height + 0.3, 
            f'Tank (V={actual_capacity:.1f})', ha='center', fontsize=10, fontweight='bold')
    
    # Temperature label - position based on fill level
    if fill_height > 0.3:  # Only show temp if there's enough water
        ax.text(tank_x + tank_width/2, tank_y + fill_height/2, 
                f'{temp:.1f}°C', ha='center', va='center', 
                fontsize=14, fontweight='bold', color='white' if temp_normalized > 0.5 else 'black')
    else:
        # Show temp above tank if water level is too low
        ax.text(tank_x + tank_width/2, tank_y + tank_height/2, 
                f'{temp:.1f}°C', ha='center', va='center', 
                fontsize=12, fontweight='bold', style='italic', color='gray')
    
    # Water level indicator line (always visible)
    water_level_y = tank_y + fill_height
    if fill_height > 0.01:
        # Draw water level line
        ax.plot([tank_x - 0.15, tank_x + tank_width + 0.15], 
                [water_level_y, water_level_y], 
                'b-', linewidth=3, alpha=0.9, label='Water Level')
        # Add water level label
        ax.text(tank_x - 0.2, water_level_y, 
                f'{fill_progress*100:.0f}%', 
                ha='right', va='center', fontsize=9, 
                fontweight='bold', color='blue',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    else:
        # Show empty indicator
        ax.plot([tank_x - 0.15, tank_x + tank_width + 0.15], 
                [tank_y, tank_y], 
                'r--', linewidth=2, alpha=0.5, label='Empty')
    
    # Target temperature indicator (sensor)
    sensor_y = tank_y + tank_height + 0.8
    ax.plot([tank_x + tank_width/2 - 0.3, tank_x + tank_width/2 + 0.3], 
            [sensor_y, sensor_y], 'r-', linewidth=2, label='Target Sensor')
    ax.plot(tank_x + tank_width/2, sensor_y, 'ro', markersize=8)
    ax.text(tank_x + tank_width/2, sensor_y + 0.3, 
            f'Target: {target_temp:.1f}°C', ha='center', fontsize=9, 
            color='red', fontweight='bold')
    
    # Progress indicator
    progress_text = f'Step: {step_count}/{max_steps} | Volume: {volume_pct:.1f}% ({actual_volume:.2f}/{actual_capacity:.2f})'
    ax.text(tank_x + tank_width/2, tank_y - 0.3, progress_text, 
            ha='center', fontsize=8, style='italic')
    
    # Hot water line (left side)
    hot_line_x = 0.5
    hot_line_y_start = 4
    hot_line_y_end = tank_y + tank_height
    
    # Hot water pipe
    ax.plot([hot_line_x, hot_line_x], [hot_line_y_start, hot_line_y_end], 
            'r-', linewidth=8, alpha=0.6, label='Hot Water Line')
    
    # Hot water valve (position based on flow rate)
    valve_size = env.hot_flow * 0.3  # Valve opening size
    valve_y = hot_line_y_end - 0.5
    valve_color = 'darkred' if env.hot_flow > 0.5 else 'lightcoral'
    valve_circle = mpatches.Circle((hot_line_x, valve_y), 0.2 + valve_size,
                                   facecolor=valve_color, edgecolor='black', linewidth=2)
    ax.add_patch(valve_circle)
    ax.text(hot_line_x, valve_y, 'V', ha='center', va='center', 
            fontsize=12, fontweight='bold', color='white')
    
    # Hot water temperature indicator
    supply_hot = getattr(env, "hot_supply_temp", env.hot_water_temp)
    ax.text(hot_line_x, hot_line_y_start + 0.3, 
            f'Hot: {supply_hot:.1f}°C', ha='center', fontsize=9, 
            fontweight='bold', color='red')
    ax.text(hot_line_x, hot_line_y_start + 0.1, 
            f'Flow: {env.hot_flow:.2f}', ha='center', fontsize=8, color='darkred')
    
    # Hot water arrow (flow direction)
    if env.hot_flow > 0.01:
        arrow_length = env.hot_flow * 0.5
        ax.arrow(hot_line_x, hot_line_y_end + 0.3, 0, -arrow_length,
                head_width=0.15, head_length=0.1, fc='red', ec='red', linewidth=2)
    
    # Cold water line (right side)
    cold_line_x = tank_x + tank_width + 1.5
    cold_line_y_start = 4
    cold_line_y_end = tank_y + tank_height
    
    # Cold water pipe
    ax.plot([cold_line_x, cold_line_x], [cold_line_y_start, cold_line_y_end], 
            'b-', linewidth=8, alpha=0.6, label='Cold Water Line')
    
    # Cold water valve (position based on flow rate)
    valve_size = env.cold_flow * 0.3
    valve_y = cold_line_y_end - 0.5
    valve_color = 'darkblue' if env.cold_flow > 0.5 else 'lightblue'
    valve_circle = mpatches.Circle((cold_line_x, valve_y), 0.2 + valve_size,
                                   facecolor=valve_color, edgecolor='black', linewidth=2)
    ax.add_patch(valve_circle)
    ax.text(cold_line_x, valve_y, 'V', ha='center', va='center', 
            fontsize=12, fontweight='bold', color='white')
    
    # Cold water temperature indicator
    supply_cold = getattr(env, "cold_supply_temp", env.cold_water_temp)
    ax.text(cold_line_x, cold_line_y_start + 0.3, 
            f'Cold: {supply_cold:.1f}°C', ha='center', fontsize=9, 
            fontweight='bold', color='blue')
    ax.text(cold_line_x, cold_line_y_start + 0.1, 
            f'Flow: {env.cold_flow:.2f}', ha='center', fontsize=8, color='darkblue')
    
    # Cold water arrow (flow direction)
    if env.cold_flow > 0.01:
        arrow_length = env.cold_flow * 0.5
        ax.arrow(cold_line_x, cold_line_y_end + 0.3, 0, -arrow_length,
                head_width=0.15, head_length=0.1, fc='blue', ec='blue', linewidth=2)
    
    # Connection lines from valves to tank
    # Hot water connection
    ax.plot([hot_line_x + 0.3, tank_x], [valve_y, tank_y + tank_height], 
            'r--', linewidth=2, alpha=0.4)
    # Cold water connection
    ax.plot([cold_line_x - 0.3, tank_x + tank_width], [valve_y, tank_y + tank_height], 
            'b--', linewidth=2, alpha=0.4)

    # Dump valve (bottom drain)
    dump_flow = getattr(env, "dump_flow", 0.0)
    dump_max = getattr(env, "max_dump_flow_rate", 1.0)
    dump_x = tank_x + tank_width / 2
    dump_y = tank_y - 0.5  # Position below tank
    
    # Drain pipe from bottom of tank to dump valve
    drain_pipe_y_start = tank_y  # Bottom of tank
    drain_pipe_y_end = dump_y + 0.3  # Top of dump valve area
    ax.plot([dump_x, dump_x], [drain_pipe_y_start, drain_pipe_y_end], 
            'gray', linewidth=6, alpha=0.6, label='Drain Pipe')
    
    # Dump valve (circular valve, similar to hot/cold valves)
    valve_size = dump_flow * 0.3  # Valve opening size based on flow
    valve_color = 'darkgray' if dump_flow > 0.1 else 'lightgray'
    valve_circle = mpatches.Circle((dump_x, dump_y), 0.2 + valve_size,
                                   facecolor=valve_color, edgecolor='black', linewidth=2)
    ax.add_patch(valve_circle)
    ax.text(dump_x, dump_y, 'V', ha='center', va='center', 
            fontsize=12, fontweight='bold', color='white')
    
    # Dump flow indicator
    ax.text(dump_x, dump_y - 0.7, 
            f'Dump: {dump_flow:.2f}', ha='center', fontsize=9, 
            fontweight='bold', color='gray')
    
    # Water draining arrow (showing flow direction downward)
    if dump_flow > 0.01:
        arrow_length = dump_flow * 0.4
        ax.arrow(dump_x, dump_y - 0.2, 0, -arrow_length,
                 head_width=0.15, head_length=0.1, fc='gray', ec='gray', linewidth=3)
        
        # Show draining water stream (visual effect)
        for i in range(3):
            stream_y = dump_y - 0.3 - i * 0.15
            stream_width = dump_flow * 0.1
            if stream_y > -0.5:  # Don't draw below view
                ax.plot([dump_x - stream_width, dump_x + stream_width], 
                       [stream_y, stream_y], 
                       'gray', linewidth=2, alpha=0.5 - i * 0.1)
    
    # Title
    ax.text(3, 5.5, 'AI Temperature Control Operator', ha='center', 
            fontsize=16, fontweight='bold')
    
    # Error indicator
    if temp_error < 0.5:
        status_color = 'green'
        status_text = '✓ On Target'
    elif temp_error < 1.0:
        status_color = 'orange'
        status_text = '~ Close'
    else:
        status_color = 'red'
        status_text = '✗ Off Target'
    
    ax.text(3, tank_y - 1.6, f'Error: {temp_error:.2f}°C - {status_text}', 
            ha='center', fontsize=10, color=status_color, fontweight='bold')


def test_and_visualize(model_path, num_episodes=3, show_realtime=True, max_steps=600, initial_volume=None, target_temp=37.0):
    """Test a trained model and visualize the results.
    
    Args:
        model_path: Path to trained model
        num_episodes: Number of test episodes
        show_realtime: Whether to show real-time visualization
        max_steps: Maximum steps per episode
        initial_volume: Initial volume ratio (0.0-1.0). If None, uses random (0.0-0.95)
        target_temp: Target temperature for the episodes
    """
    
    # Load model
    print(f"Loading model from {model_path}...")
    model = PPO.load(model_path)
    
    # Create environment
    env = TemperatureControlEnv(
        target_temp=target_temp,
        initial_temp=20.0,
        hot_water_temp=60.0,
        cold_water_temp=10.0,
        max_flow_rate=1.0,
        max_dump_flow_rate=1.0,
        mixed_water_cooling_rate=0.01,
        max_steps=max_steps
    )
    
    # Run episodes and collect data
    all_episodes = []
    
    for episode in range(num_episodes):
        # Set initial volume if specified, otherwise use random
        reset_options = None
        if initial_volume is not None:
            reset_options = {'initial_volume': initial_volume}
        # If None, reset() will use random volume (0.0-0.95)
        
        obs, info = env.reset(options=reset_options)
        done = False
        starting_volume = env.volume  # Capture starting volume immediately after reset
        
        # Debug: verify volume was set correctly
        if initial_volume is not None:
            expected_volume = env.tank_capacity * initial_volume
            if abs(starting_volume - expected_volume) > 0.01:
                print(f"WARNING: Volume mismatch! Expected {expected_volume:.2f}, got {starting_volume:.2f}")
            else:
                print(f"✓ Volume set correctly: {starting_volume:.2f} (requested: {initial_volume:.2f})")
        
        episode_data = {
            "temperatures": [env.current_temp],
            "hot_flows": [env.hot_flow],
            "cold_flows": [env.cold_flow],
            "rewards": [],
            "steps": 0
        }
        
        print(f"\n=== Episode {episode + 1} ===")
        print(f"Starting volume: {starting_volume:.2f} / {env.tank_capacity:.2f} ({starting_volume/env.tank_capacity*100:.1f}% full)")
        
        # Setup real-time visualization if requested
        if show_realtime:
            fig, ax = plt.subplots(figsize=(10, 8))
            plt.ion()  # Turn on interactive mode
            plt.show()
            # Draw initial state immediately after reset (before any steps)
            # This ensures we see the actual starting volume
            draw_tank_visualization(ax, env, 0, env.max_steps)
            plt.draw()
            plt.pause(0.2)  # Longer pause to ensure initial state is visible
        
        while not done:
            action, _states = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            
            episode_data["temperatures"].append(env.current_temp)
            episode_data["hot_flows"].append(env.hot_flow)
            episode_data["cold_flows"].append(env.cold_flow)
            episode_data["rewards"].append(reward)
            episode_data["steps"] += 1
            
            # Update real-time visualization
            if show_realtime and episode_data["steps"] % 2 == 0:  # Update every 2 steps
                draw_tank_visualization(ax, env, episode_data["steps"], env.max_steps)
                plt.draw()
                plt.pause(0.01)  # Small pause for smooth animation
            
            if episode_data["steps"] % 20 == 0:
                env.render()
        
        if show_realtime:
            plt.ioff()  # Turn off interactive mode
            plt.close(fig)
        
        all_episodes.append(episode_data)
        
        volume_ratio = info.get('volume_ratio', env.volume / env.tank_capacity)
        temp_success = abs(info['temperature'] - env.target_temp) < 0.1
        volume_success = volume_ratio >= 0.80 and volume_ratio <= 0.85  # Must be in ideal range (80-85%)
        print(f"Final temperature: {info['temperature']:.2f}°C")
        print(f"Target: {env.target_temp}°C")
        print(f"Temperature error: {abs(info['temperature'] - env.target_temp):.2f}°C")
        print(f"Tank volume: {env.volume:.2f} / {env.tank_capacity:.2f} ({volume_ratio*100:.1f}% full)")
        print(f"Success: {'✓' if (temp_success and volume_success) else '✗'} (Temp: {'✓' if temp_success else '✗'}, Volume: {'✓' if volume_success else '✗'})")
        print(f"Steps: {episode_data['steps']}")
    
    # Visualize final results
    visualize_episodes(all_episodes, env.target_temp)


def visualize_episodes(episodes, target_temp):
    """Create plots showing temperature control performance."""
    
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle('AI Agent Temperature Control Performance', fontsize=14, fontweight='bold')
    
    # Plot 1: Temperature over time
    ax1 = axes[0, 0]
    for i, episode in enumerate(episodes):
        steps = range(len(episode["temperatures"]))
        ax1.plot(steps, episode["temperatures"], 
                label=f'Episode {i+1}', alpha=0.7, linewidth=2)
    ax1.axhline(y=target_temp, color='r', linestyle='--', 
                label=f'Target ({target_temp}°C)', linewidth=2)
    ax1.set_xlabel('Time Step')
    ax1.set_ylabel('Temperature (°C)')
    ax1.set_title('Temperature Control')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Flow rates over time
    ax2 = axes[0, 1]
    for i, episode in enumerate(episodes):
        steps = range(len(episode["hot_flows"]))
        ax2.plot(steps, episode["hot_flows"], 
                label=f'Hot Flow Ep{i+1}', alpha=0.7, linestyle='-')
        ax2.plot(steps, episode["cold_flows"], 
                label=f'Cold Flow Ep{i+1}', alpha=0.7, linestyle='--')
    ax2.set_xlabel('Time Step')
    ax2.set_ylabel('Flow Rate')
    ax2.set_title('Valve Control (Flow Rates)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Temperature error over time
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
    
    # Plot 4: Cumulative reward
    ax4 = axes[1, 1]
    for i, episode in enumerate(episodes):
        steps = range(len(episode["rewards"]))
        cumulative_reward = np.cumsum(episode["rewards"])
        ax4.plot(steps, cumulative_reward, 
                label=f'Episode {i+1}', alpha=0.7, linewidth=2)
    ax4.set_xlabel('Time Step')
    ax4.set_ylabel('Cumulative Reward')
    ax4.set_title('Learning Progress (Reward)')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('control_performance.png', dpi=150, bbox_inches='tight')
    print("\nVisualization saved to 'control_performance.png'")
    plt.show()


def test_manual_control(
    model_path=None,
    use_ai=True,
    max_steps=600,
    init_target=37.0,
    init_hot_temp=60.0,
    init_cold_temp=10.0,
    init_hot_flow=0.0,
    init_cold_flow=0.0,
    init_dump_flow=0.0,
):
    """Test with manual controls for incoming water temps, flows, target temp, and max steps."""
    
    # Load model if provided and using AI
    model = None
    if use_ai and model_path:
        print(f"Loading model from {model_path}...")
        model = PPO.load(model_path)
    
    # Create environment
    env = TemperatureControlEnv(
        target_temp=init_target,
        initial_temp=20.0,
        hot_water_temp=init_hot_temp,
        cold_water_temp=init_cold_temp,
        max_flow_rate=1.0,
        max_dump_flow_rate=1.0,
        mixed_water_cooling_rate=0.01,
        max_steps=max_steps
    )
    
    # Initialize environment
    obs, info = env.reset()
    # Initialize supply temps from initial slider values (important for AI mode with drift)
    if use_ai:
        env.hot_water_temp = init_hot_temp
        env.cold_water_temp = init_cold_temp
        env.hot_supply_temp = init_hot_temp
        env.cold_supply_temp = init_cold_temp
        env.disable_drift = False  # Enable drift in AI mode (as trained)
    else:
        env.disable_drift = True  # Disable drift in manual mode for precise control
    
    # Create figure with main plot and control panel
    fig = plt.figure(figsize=(14, 10))
    ax_main = plt.subplot2grid((10, 10), (0, 0), colspan=7, rowspan=10)
    ax_main.set_position([0.05, 0.15, 0.55, 0.8])
    
    # Control panel area
    control_y_start = 0.02
    control_height = 0.12
    control_spacing = 0.015
    
    # Slider positions
    slider_width = 0.3
    slider_height = 0.02
    left_margin = 0.65
    
    # Hot water temperature slider
    ax_hot_temp = plt.axes([left_margin, control_y_start + 4 * (control_height + control_spacing), 
                            slider_width, slider_height])
    hot_temp_slider = Slider(ax_hot_temp, 'Hot Temp', 0.0, 100.0, 
                            valinit=init_hot_temp, valfmt='%.1f°C')
    
    # Cold water temperature slider
    ax_cold_temp = plt.axes([left_margin, control_y_start + 3 * (control_height + control_spacing), 
                             slider_width, slider_height])
    cold_temp_slider = Slider(ax_cold_temp, 'Cold Temp', 0.0, 100.0, 
                             valinit=init_cold_temp, valfmt='%.1f°C')
    
    # Hot water flow slider
    ax_hot_flow = plt.axes([left_margin, control_y_start + 2 * (control_height + control_spacing), 
                           slider_width, slider_height])
    hot_flow_slider = Slider(ax_hot_flow, 'Hot Flow', 0.0, env.max_flow_rate, 
                            valinit=init_hot_flow, valfmt='%.2f')
    
    # Cold water flow slider
    ax_cold_flow = plt.axes([left_margin, control_y_start + 1 * (control_height + control_spacing), 
                             slider_width, slider_height])
    cold_flow_slider = Slider(ax_cold_flow, 'Cold Flow', 0.0, env.max_flow_rate, 
                              valinit=init_cold_flow, valfmt='%.2f')
    
    # Target temperature slider
    ax_target = plt.axes([left_margin, control_y_start + 0 * (control_height + control_spacing), 
                          slider_width, slider_height])
    target_slider = Slider(ax_target, 'Target Temp', 0.0, 100.0, 
                          valinit=init_target, valfmt='%.1f°C')
    
    # Reset button
    ax_reset = plt.axes([left_margin + slider_width + 0.05, control_y_start, 0.1, 0.04])
    reset_button = Button(ax_reset, 'Reset')
    
    # AI/Manual toggle button
    ax_mode = plt.axes([left_margin + slider_width + 0.05, control_y_start + 0.05, 0.1, 0.04])
    mode_button = Button(ax_mode, 'AI Mode' if use_ai else 'Manual')
    ai_mode = use_ai
    
    # Manual control sliders (for dump valve when in manual mode)
    ax_dump_flow = plt.axes([left_margin, control_y_start - 0.05, slider_width, slider_height])
    dump_flow_slider = Slider(ax_dump_flow, 'Dump Flow', 0.0, env.max_dump_flow_rate, 
                              valinit=init_dump_flow, valfmt='%.2f')
    
    step_count = 0
    paused = False
    
    def update_environment():
        """Update environment parameters from sliders."""
        # Update supply temperatures
        env.hot_supply_temp = hot_temp_slider.val
        env.cold_supply_temp = cold_temp_slider.val
        env.hot_water_temp = hot_temp_slider.val  # Also update base temp
        env.cold_water_temp = cold_temp_slider.val
        
        # Update target temperature
        env.target_temp = target_slider.val
        
        # Update flows (these will be used in step if in manual mode)
        env.hot_flow = hot_flow_slider.val
        env.cold_flow = cold_flow_slider.val
        env.dump_flow = dump_flow_slider.val
    
    def on_slider_change(val):
        """Called when any slider changes."""
        update_environment()
        draw_tank_visualization(ax_main, env, step_count, env.max_steps)
        plt.draw()
    
    def on_reset(event):
        """Reset the environment."""
        nonlocal step_count, prev_hot_temp, prev_cold_temp
        obs, info = env.reset()
        step_count = 0
        # Reset sliders to initial values
        hot_temp_slider.reset()
        cold_temp_slider.reset()
        hot_flow_slider.reset()
        cold_flow_slider.reset()
        dump_flow_slider.reset()
        target_slider.set_val(init_target)
        # Reset tracking variables
        prev_hot_temp = init_hot_temp
        prev_cold_temp = init_cold_temp
        # Initialize supply temps from sliders (important for AI mode)
        if ai_mode:
            env.hot_water_temp = init_hot_temp
            env.cold_water_temp = init_cold_temp
            env.hot_supply_temp = init_hot_temp
            env.cold_supply_temp = init_cold_temp
        update_environment()
        draw_tank_visualization(ax_main, env, step_count, env.max_steps)
        plt.draw()
    
    def on_mode_toggle(event):
        """Toggle between AI and manual mode."""
        nonlocal ai_mode
        ai_mode = not ai_mode
        mode_button.label.set_text('AI Mode' if ai_mode else 'Manual')
        # Update drift setting based on mode
        if ai_mode:
            env.disable_drift = False  # Enable drift in AI mode (as trained)
            # Reinitialize supply temps from sliders when switching to AI mode
            env.hot_water_temp = hot_temp_slider.val
            env.cold_water_temp = cold_temp_slider.val
            env.hot_supply_temp = hot_temp_slider.val
            env.cold_supply_temp = cold_temp_slider.val
        else:
            env.disable_drift = True  # Disable drift in manual mode
        plt.draw()
    
    # Connect callbacks
    hot_temp_slider.on_changed(on_slider_change)
    cold_temp_slider.on_changed(on_slider_change)
    hot_flow_slider.on_changed(on_slider_change)
    cold_flow_slider.on_changed(on_slider_change)
    target_slider.on_changed(on_slider_change)
    dump_flow_slider.on_changed(on_slider_change)
    reset_button.on_clicked(on_reset)
    mode_button.on_clicked(on_mode_toggle)
    
    # Initial visualization
    update_environment()
    draw_tank_visualization(ax_main, env, step_count, env.max_steps)
    
    plt.ion()
    plt.show()
    
    print("\n=== Manual Control Mode ===")
    print("Use sliders to adjust parameters in real-time")
    print("Press 'q' to quit, 'p' to pause/unpause")
    print("AI Mode: Agent controls valves automatically")
    print("Manual Mode: You control flows via sliders")
    print(f"Max steps this session: {env.max_steps}")
    
    # Main loop
    import time
    from matplotlib import pyplot as plt_backend
    
    # Track previous slider values to detect changes
    prev_hot_temp = init_hot_temp
    prev_cold_temp = init_cold_temp
    
    try:
        while True:
            if not paused:
                # Always update target from slider
                env.target_temp = target_slider.val
                
                if ai_mode and model:
                    # AI mode: Enable drift (as trained), matching normal test mode
                    env.disable_drift = False
                    
                    # Update base supply temperatures from sliders only when they change
                    # This allows drift to work naturally from the base values
                    if abs(hot_temp_slider.val - prev_hot_temp) > 0.1:
                        env.hot_water_temp = hot_temp_slider.val
                        env.hot_supply_temp = hot_temp_slider.val
                        prev_hot_temp = hot_temp_slider.val
                    
                    if abs(cold_temp_slider.val - prev_cold_temp) > 0.1:
                        env.cold_water_temp = cold_temp_slider.val
                        env.cold_supply_temp = cold_temp_slider.val
                        prev_cold_temp = cold_temp_slider.val
                    
                    # AI controls the valves (drift will happen naturally in env.step)
                    action, _states = model.predict(obs, deterministic=True)
                    obs, reward, terminated, truncated, info = env.step(action)
                    
                    # Update flow sliders to show what AI is doing
                    hot_flow_slider.set_val(env.hot_flow)
                    cold_flow_slider.set_val(env.cold_flow)
                    dump_flow_slider.set_val(env.dump_flow)
                else:
                    # Manual mode: use slider values directly via manual_step
                    obs, reward, terminated, truncated, info = env.manual_step(
                        hot_flow=hot_flow_slider.val,
                        cold_flow=cold_flow_slider.val,
                        dump_flow=dump_flow_slider.val,
                        hot_supply_temp=hot_temp_slider.val,
                        cold_supply_temp=cold_temp_slider.val,
                        disable_drift=True  # No drift in manual mode for precise control
                    )
                
                step_count += 1
                
                if terminated or truncated:
                    volume_ratio = info.get('volume_ratio', env.volume / env.tank_capacity)
                    temp_success = abs(info['temperature'] - env.target_temp) < 0.1
                    volume_success = volume_ratio >= 0.80 and volume_ratio <= 0.85  # Must be in ideal range (80-85%)
                    print(f"\nEpisode finished after {step_count} steps")
                    print(f"Final temperature: {info['temperature']:.2f}°C")
                    print(f"Target: {env.target_temp}°C")
                    print(f"Temperature error: {abs(info['temperature'] - env.target_temp):.2f}°C")
                    print(f"Tank volume: {env.volume:.2f} / {env.tank_capacity:.2f} ({volume_ratio*100:.1f}% full)")
                    print(f"Success: {'✓' if (temp_success and volume_success) else '✗'} (Temp: {'✓' if temp_success else '✗'}, Volume: {'✓' if volume_success else '✗'})")
                    obs, info = env.reset()
                    step_count = 0
                    # Reset slider tracking after episode reset
                    prev_hot_temp = hot_temp_slider.val
                    prev_cold_temp = cold_temp_slider.val
                    # Reinitialize supply temps from sliders after reset
                    if ai_mode:
                        env.hot_water_temp = hot_temp_slider.val
                        env.cold_water_temp = cold_temp_slider.val
                        env.hot_supply_temp = hot_temp_slider.val
                        env.cold_supply_temp = cold_temp_slider.val
                
                # Update visualization
                draw_tank_visualization(ax_main, env, step_count, env.max_steps)
                plt.draw()
                plt.pause(0.05)
            
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        plt.ioff()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test/visualize temperature control with optional manual controls.")
    parser.add_argument("model_path", nargs="?", default="./models/best/best_model", help="Path to trained model.")
    parser.add_argument("--manual", action="store_true", help="Manual mode with sliders (AI assists if model_path provided).")
    parser.add_argument("--manual-only", action="store_true", help="Pure manual mode (no AI).")
    parser.add_argument("--max-steps", type=int, default=600, help="Max steps per episode.")
    parser.add_argument("--target", type=float, default=37.0, help="Initial target temperature.")
    parser.add_argument("--hot-temp", type=float, default=60.0, help="Initial hot supply temperature.")
    parser.add_argument("--cold-temp", type=float, default=10.0, help="Initial cold supply temperature.")
    parser.add_argument("--hot-flow", type=float, default=0.0, help="Initial hot flow setting for manual mode.")
    parser.add_argument("--cold-flow", type=float, default=0.0, help="Initial cold flow setting for manual mode.")
    parser.add_argument("--dump-flow", type=float, default=0.0, help="Initial dump flow setting for manual mode.")
    parser.add_argument("--episodes", type=int, default=3, help="Episodes to run in visualize mode.")
    parser.add_argument("--initial-volume", type=float, default=None, help="Initial tank volume ratio (0.0-1.0). If not specified, uses random (0.0-0.95) for each episode.")
    args = parser.parse_args()

    if args.manual or args.manual_only:
        test_manual_control(
            model_path=None if args.manual_only else args.model_path,
            use_ai=not args.manual_only and args.model_path is not None,
            max_steps=args.max_steps,
            init_target=args.target,
            init_hot_temp=args.hot_temp,
            init_cold_temp=args.cold_temp,
            init_hot_flow=args.hot_flow,
            init_cold_flow=args.cold_flow,
            init_dump_flow=args.dump_flow,
        )
    else:
        test_and_visualize(
            args.model_path,
            num_episodes=args.episodes,
            show_realtime=True,
            max_steps=args.max_steps,
            initial_volume=args.initial_volume,
            target_temp=args.target,
        )

