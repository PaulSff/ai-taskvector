"""
Test and visualize a trained model.
"""
import numpy as np
import matplotlib.pyplot as plt
from stable_baselines3 import PPO
from temperature_env import TemperatureControlEnv


def test_and_visualize(model_path, num_episodes=3):
    """Test a trained model and visualize the results."""
    
    # Load model
    print(f"Loading model from {model_path}...")
    model = PPO.load(model_path)
    
    # Create environment
    env = TemperatureControlEnv(
        target_temp=37.0,
        initial_temp=20.0,
        hot_water_temp=60.0,
        cold_water_temp=10.0,
        max_flow_rate=1.0,
        max_steps=200
    )
    
    # Run episodes and collect data
    all_episodes = []
    
    for episode in range(num_episodes):
        obs, info = env.reset()
        done = False
        
        episode_data = {
            "temperatures": [env.current_temp],
            "hot_flows": [env.hot_flow],
            "cold_flows": [env.cold_flow],
            "rewards": [],
            "steps": 0
        }
        
        print(f"\n=== Episode {episode + 1} ===")
        
        while not done:
            action, _states = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            
            episode_data["temperatures"].append(env.current_temp)
            episode_data["hot_flows"].append(env.hot_flow)
            episode_data["cold_flows"].append(env.cold_flow)
            episode_data["rewards"].append(reward)
            episode_data["steps"] += 1
            
            if episode_data["steps"] % 20 == 0:
                env.render()
        
        all_episodes.append(episode_data)
        
        print(f"Final temperature: {info['temperature']:.2f}°C")
        print(f"Target: {env.target_temp}°C")
        print(f"Error: {abs(info['temperature'] - env.target_temp):.2f}°C")
        print(f"Steps: {episode_data['steps']}")
    
    # Visualize
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


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        model_path = sys.argv[1]
    else:
        model_path = "./models/best/best_model"
    
    test_and_visualize(model_path, num_episodes=3)

