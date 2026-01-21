"""
Training script for the temperature control AI agent.
Uses Stable-Baselines3 with PPO algorithm.
"""
import os
import argparse
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from stable_baselines3.common.env_util import make_vec_env
from temperature_env import TemperatureControlEnv


def main(checkpoint_path=None, total_timesteps=100000):
    # Create environment
    print("Creating environment...")
    env = TemperatureControlEnv(
        target_temp=37.0,
        initial_temp=20.0,
        hot_water_temp=60.0,
        cold_water_temp=10.0,
        max_flow_rate=1.0,
        max_dump_flow_rate=1.0,
        mixed_water_cooling_rate=0.01,
        max_steps=600,
        randomize_params=True
    )
    
    # Create vectorized environment for faster training
    # Using 4 parallel environments
    vec_env = make_vec_env(
        TemperatureControlEnv,
        n_envs=4,
        env_kwargs={
            "target_temp": 37.0,
            "initial_temp": 20.0,
            "hot_water_temp": 60.0,
            "cold_water_temp": 10.0,
            "max_flow_rate": 1.0,
            "max_dump_flow_rate": 1.0,
            "mixed_water_cooling_rate": 0.01,
            "max_steps": 600,
            "randomize_params": True
        }
    )
    
    # Create evaluation environment
    eval_env = TemperatureControlEnv(
        target_temp=37.0,
        initial_temp=20.0,
        hot_water_temp=60.0,
        cold_water_temp=10.0,
        max_flow_rate=1.0,
        max_dump_flow_rate=1.0,
        mixed_water_cooling_rate=0.01,
        max_steps=600
    )
    
    # Create model directory
    os.makedirs("models", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    # Initialize or load PPO agent
    if checkpoint_path and os.path.exists(checkpoint_path):
        print(f"Loading model from checkpoint: {checkpoint_path}")
        model = PPO.load(checkpoint_path, env=vec_env)
        # Get current timesteps from the loaded model
        current_timesteps = model.num_timesteps
        print(f"Resuming training from {current_timesteps:,} timesteps")
        print(f"Will train for additional {total_timesteps:,} timesteps (total: {current_timesteps + total_timesteps:,})")
    else:
        if checkpoint_path:
            print(f"Warning: Checkpoint {checkpoint_path} not found. Starting from scratch.")
        print("Initializing new PPO agent...")
        model = PPO(
            "MlpPolicy",
            vec_env,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,  # Encourage exploration
            verbose=1,
            tensorboard_log="./logs/tensorboard/"
        )
        current_timesteps = 0
    
    # Setup callbacks
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path="./models/best/",
        log_path="./logs/eval/",
        eval_freq=5000,
        deterministic=True,
        render=False
    )
    
    checkpoint_callback = CheckpointCallback(
        save_freq=10000,
        save_path="./models/checkpoints/",
        name_prefix="ppo_temp_control"
    )
    
    # Train the agent
    print("Starting training...")
    target_timesteps = current_timesteps + total_timesteps
    if checkpoint_path and os.path.exists(checkpoint_path):
        print(f"Continuing training for {total_timesteps:,} additional timesteps.")
        print(f"Target: {target_timesteps:,} total timesteps (currently at {current_timesteps:,})")
    else:
        print(f"Training will run for {total_timesteps:,} timesteps.")
    print("Check TensorBoard logs at: ./logs/tensorboard/")
    
    model.learn(
        total_timesteps=target_timesteps,
        callback=[eval_callback, checkpoint_callback],
        progress_bar=True,
        reset_num_timesteps=False  # Don't reset timestep counter when resuming
    )
    
    # Save final model
    model.save("./models/ppo_temperature_control_final")
    print("\nTraining complete! Model saved to ./models/ppo_temperature_control_final")
    
    # Test the trained model
    print("\nTesting trained model...")
    test_episode(eval_env, model, num_episodes=5)


def test_episode(env, model, num_episodes=1):
    """Test the trained model on a few episodes."""
    for episode in range(num_episodes):
        obs, info = env.reset()
        done = False
        total_reward = 0
        steps = 0
        
        print(f"\n=== Episode {episode + 1} ===")
        
        while not done:
            action, _states = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            total_reward += reward
            steps += 1
            
            if steps % 10 == 0:
                env.render()
        
        volume_ratio = info.get('volume_ratio', env.volume / env.tank_capacity)
        temp_success = abs(info['temperature'] - env.target_temp) < 0.1
        volume_success = volume_ratio >= 0.95
        print(f"Episode finished after {steps} steps")
        print(f"Final temperature: {info['temperature']:.2f}°C")
        print(f"Target temperature: {env.target_temp}°C")
        print(f"Temperature error: {abs(info['temperature'] - env.target_temp):.2f}°C")
        print(f"Tank volume: {env.volume:.2f} / {env.tank_capacity:.2f} ({volume_ratio*100:.1f}% full)")
        print(f"Success: {'✓' if (temp_success and volume_success) else '✗'} (Temp: {'✓' if temp_success else '✗'}, Volume: {'✓' if volume_success else '✗'})")
        print(f"Total reward: {total_reward:.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train temperature control AI agent with PPO")
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="Path to checkpoint to resume training from (e.g., ./models/checkpoints/ppo_temp_control_80000_steps.zip)"
    )
    parser.add_argument(
        "--timesteps",
        type=int,
        default=100000,
        help="Number of timesteps to train (default: 100000). If resuming, this is additional timesteps."
    )
    args = parser.parse_args()
    
    main(checkpoint_path=args.checkpoint, total_timesteps=args.timesteps)

